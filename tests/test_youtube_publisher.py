import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge
from scriptor import config
from scriptor.config import FastGenKey, OpenAIKey, Settings, WProjectKey
from scriptor.youtube_oauth import youtube_oauth_scopes
from scriptor.youtube_api import parse_analytics_rows, parse_current_channel, parse_google_account_email
from scriptor.youtube_api import build_private_video_insert_body, normalize_youtube_tags
from scriptor.runner import RunState
from scriptor.youtube_allocation import allocate_ready_jobs, build_allocation_summary, recommend_quota
from scriptor.youtube_publisher import (
    AnalyticsMetricPoint,
    PublicationJob,
    aggregate_analytics_metrics,
    apply_rewritten_title,
    build_linked_community_post,
    build_staggered_publication_grid,
    can_upload,
    create_publication_job,
    manual_ad_break_checklist,
    plan_jobs_on_publication_grid,
    publication_job_record,
    schedule_publication,
    suggest_youtube_title,
)


class PublicationJobTests(unittest.TestCase):
    def test_adding_channel_enables_default_oauth_handoff_for_future_channels(self):
        """Every new row must be ready for the Google → tinkbro token handoff."""
        settings = Settings()
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.add_channel({"name": "Новый канал"})

        self.assertEqual(settings.youtube_oauth_service_url, "https://a.tinkbro.online")

    def test_operator_can_move_any_ready_job_between_channels(self):
        """A manual move must override the allocation suggestion and persist the target channel."""
        job = publication_job_record(create_publication_job(
            video_path="D:/ready/video.mp4", package_folder="D:/ready", title="Выпуск",
        ))
        settings = Settings(
            youtube_publication_jobs=[job],
            analytics_channels=[{"profile_id": "source", "name": "Первый"}, {"profile_id": "target", "name": "Второй"}],
        )

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {"jobs": []}}):
            result = bridge.move_publication_job_channel({"jobId": job["id"], "channelId": "target"})

        self.assertEqual(settings.youtube_publication_jobs[0]["channelId"], "target")
        self.assertEqual(result["operationResult"]["kind"], "publication-channel-moved")

    def test_description_prefix_uses_the_first_enabled_matching_topic_range(self):
        """A generic opening belongs only to the selected one-based topic range."""
        from scriptor.seo_prefixes import prepend_description_prefix

        result = prepend_description_prefix(
            "Основное описание выпуска.",
            topic_index=4,
            ranges=[
                {"start": 1, "end": 5, "text": "Подписывайтесь на канал.", "enabled": True},
                {"start": 4, "end": 6, "text": "Другой текст.", "enabled": True},
            ],
        )

        self.assertEqual(result, "Подписывайтесь на канал.\n\nОсновное описание выпуска.")

    def test_fixed_description_prefix_is_always_before_topic_prefix_and_seo_text(self):
        """Contacts entered once must begin every generated description."""
        from scriptor.seo_prefixes import prepend_description_prefix

        result = prepend_description_prefix(
            "Основное описание выпуска.",
            topic_index=4,
            fixed_prefix="Контакты: example@channel.test",
            ranges=[{"start": 1, "end": 5, "text": "Подписывайтесь на канал."}],
        )

        self.assertEqual(
            result,
            "Контакты: example@channel.test\n\nПодписывайтесь на канал.\n\nОсновное описание выпуска.",
        )

    def test_operator_can_save_description_prefix_ranges_without_replacing_the_seo_prompt(self):
        """Saving the range editor alone must not require retyping the SEO template."""
        settings = Settings(seo_prompt_template="Существующий SEO-промпт")

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_seo_settings({"descriptionPrefixRanges": [{"start": 2, "end": 4, "text": "Вступление"}]})

        self.assertEqual(settings.seo_description_prefix_ranges, [{"start": 2, "end": 4, "text": "Вступление", "enabled": True}])

    def test_operator_can_save_fixed_description_prefix_without_retyping_seo_prompt(self):
        """The permanent contact block is stored independently from prompt text."""
        settings = Settings(seo_prompt_template="Существующий SEO-промпт")

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_seo_settings({"fixedDescriptionPrefix": "Контакты: @newsflow"})

        self.assertEqual(settings.seo_description_prefix, "Контакты: @newsflow")
        self.assertEqual(settings.seo_prompt_template, "Существующий SEO-промпт")

    def test_operator_can_clear_saved_seo_call_to_action(self):
        settings = Settings(seo_call_to_action="Старое пожелание")

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_seo_settings({"callToAction": ""})

        self.assertEqual(settings.seo_call_to_action, "")

    def test_tag_limit_is_capped_to_youtube_five_hundred_characters(self):
        settings = Settings(tag_char_limit=500)

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_tag_limits({"hashtagBatchSize": 5, "tagCharLimit": 5000})

        self.assertEqual(settings.tag_char_limit, 500)

    def test_persisted_legacy_tag_limit_is_migrated_to_youtube_limit(self):
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            settings_path.write_text('{"tag_char_limit":5000}', encoding="utf-8")
            with patch.object(config, "config_path", return_value=settings_path):
                restored = config.load_settings()

        self.assertEqual(restored.tag_char_limit, 500)

    def test_seo_and_tags_become_stale_when_scenario_content_or_title_changes(self):
        settings = Settings(seo_queue=[{
            "production_item_id": "production-1",
            "source_title": "Старое название",
            "script": "Старый сценарий",
            "requirements": "",
            "status": "Готово",
            "title": "Готовый SEO заголовок",
            "description": "Готовое описание",
            "hashtags": ["#старое"],
            "tags": ["старый тег"],
            "tags_status": "Готово",
            "tags_error": "",
            "error": "",
        }])
        job = SimpleNamespace(
            request=SimpleNamespace(
                production_item_id="production-1",
                prompt="",
            ),
            result="Новый сценарий",
        )

        changed = bridge._sync_scenario_to_seo(
            settings,
            "Новое название",
            job,
            create_if_missing=False,
            legacy_titles=("Старое название",),
        )

        self.assertTrue(changed)
        row = settings.seo_queue[0]
        self.assertEqual(row["production_item_id"], "production-1")
        self.assertEqual(row["source_title"], "Новое название")
        self.assertEqual(row["script"], "Новый сценарий")
        self.assertEqual(row["status"], "Ожидает")
        self.assertEqual(row["tags_status"], "Ожидают")
        self.assertEqual(row["title"], "")
        self.assertEqual(row["description"], "")
        self.assertEqual(row["hashtags"], [])
        self.assertEqual(row["tags"], [])

    def test_seo_format_instruction_uses_exact_configured_hashtag_count(self):
        instruction = bridge._seo_format_instruction(9)

        self.assertIn("ровно 9", instruction)
        self.assertNotIn("3–5", instruction)

    def test_auto_pipeline_generates_tags_after_seo_stage(self):
        job = SimpleNamespace(
            request=SimpleNamespace(index=0),
            state=RunState.DONE,
            result="Готовый сценарий",
        )
        settings = Settings(
            seo_queue=[{
                "source_title": "Тема",
                "status": "Готово",
                "description": "Готовое SEO описание",
                "tags": [],
                "tags_status": "Ожидают",
            }],
            auto_pipeline_stages={
                "scenarios": False,
                "covers": False,
                "seo": True,
                "voice": False,
                "montage": False,
                "package": False,
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "load_session", return_value=(["Тема"], [job])), \
             patch.object(bridge, "transfer_scenarios"), \
             patch.object(bridge, "generate_seo") as generate_seo_mock, \
             patch.object(bridge, "generate_tags", return_value={}) as generate_tags_mock, \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.run_auto_pipeline({"enabled": True, "stages": settings.auto_pipeline_stages})

        generate_seo_mock.assert_not_called()
        generate_tags_mock.assert_called_once_with({"indices": [0], "chatUrl": ""})

    def test_allocation_channel_exposes_assigned_video_names_and_durations(self):
        """The allocation screen needs readable assignments, not opaque IDs."""
        settings = Settings(youtube_publication_jobs=[
            {"id": "job-1", "title": "Длинный выпуск", "channelId": "channel-a", "durationSeconds": 725},
            {"id": "job-2", "title": "Резерв", "durationSeconds": 90},
        ])

        assigned = bridge._publication_allocation_assigned_jobs(settings, "channel-a")

        self.assertEqual(assigned, [{"id": "job-1", "title": "Длинный выпуск", "durationSeconds": 725}])

    def test_channel_notes_are_saved_separately_from_the_operator_tag(self):
        settings = Settings(analytics_channels=[{"profile_id": "one", "operator_tag": "основной", "operator_notes": ""}])

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.update_analytics_channel_metadata({"index": 0, "tag": "монета", "notes": "Загружать длинные ролики"})

        self.assertEqual(settings.analytics_channels[0]["operator_tag"], "монета")
        self.assertEqual(settings.analytics_channels[0]["operator_notes"], "Загружать длинные ролики")

    def test_upload_tags_keep_whole_unique_values_within_youtube_five_hundred_character_limit(self):
        tags = ["  Ормуз  ", "Ормуз", "", "танкеры", "x" * 484, "последний"]

        normalized = normalize_youtube_tags(tags)

        self.assertEqual(normalized, ["Ормуз", "танкеры", "x" * 484])
        self.assertLessEqual(len(",".join(normalized)), 500)

    def test_upload_body_normalizes_tags_before_youtube_receives_them(self):
        body = build_private_video_insert_body(
            title="Ормуз: риски для торговли",
            description="Описание",
            tags=["первый", "первый", "x" * 498, "лишний"],
        )

        self.assertEqual(body["snippet"]["tags"], ["первый"])
        self.assertLessEqual(len(",".join(body["snippet"]["tags"])), 500)

    def test_upload_body_keeps_explicit_supported_privacy_for_confirmed_snapshot(self):
        """Publication V2 resolves privacy into its immutable snapshot before upload."""
        body = build_private_video_insert_body(
            title="Закрытый выпуск", description="Описание", tags=[], privacy="unlisted",
        )

        self.assertEqual(body["status"]["privacyStatus"], "unlisted")

    def test_rewriting_blocked_title_makes_only_that_publication_job_ready(self):
        blocked = publication_job_record(create_publication_job(
            video_path="D:/ready/video.mp4", package_folder="D:/ready",
            title="Срочный новостной заголовок " * 5,
        ))
        untouched = publication_job_record(create_publication_job(
            video_path="D:/ready/other.mp4", package_folder="D:/other", title="Другой выпуск",
        ))
        settings = Settings(youtube_publication_jobs=[blocked, untouched])

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {"jobs": []}}):
            result = bridge.rewrite_publication_title({"jobId": blocked["id"], "title": "Короткий заголовок выпуска"})

        self.assertEqual(settings.youtube_publication_jobs[0]["title"], "Короткий заголовок выпуска")
        self.assertEqual(settings.youtube_publication_jobs[0]["status"], "ready")
        self.assertEqual(settings.youtube_publication_jobs[1]["title"], "Другой выпуск")
        self.assertEqual(result["operationResult"]["kind"], "publication-title-rewritten")

    def test_automatic_title_fallback_prefers_a_short_seo_heading(self):
        job = create_publication_job(
            video_path="C:/ready.mp4", package_folder="C:/package",
            title="Очень длинный исходный заголовок " * 5,
            seo_title="Ормуз: риск для мировой торговли",
        )

        self.assertEqual(suggest_youtube_title(job), "Ормуз: риск для мировой торговли")

    def test_marking_prepared_post_done_does_not_change_uploaded_video_state(self):
        job = publication_job_record(create_publication_job(
            video_path="D:/ready/video.mp4", package_folder="D:/ready", title="Выпуск",
        ))
        job.update({"status": "uploaded", "videoStatus": "uploaded", "post": {"status": "prepared", "text": "Текст"}})
        settings = Settings(youtube_publication_jobs=[job])

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {"jobs": []}}):
            result = bridge.mark_publication_post_done({"jobId": job["id"]})

        self.assertEqual(settings.youtube_publication_jobs[0]["status"], "uploaded")
        self.assertEqual(settings.youtube_publication_jobs[0]["post"]["status"], "published-manually")
        self.assertEqual(result["operationResult"]["kind"], "publication-post-marked")

    def test_allocation_recommendation_prioritises_monetisation_growth_and_default(self):
        self.assertEqual(recommend_quota({"monetized": True, "growthSignal": True}), 3)
        self.assertEqual(recommend_quota({"monetized": False, "growthSignal": True}), 2)
        self.assertEqual(recommend_quota({"monetized": False, "growthSignal": False}), 1)

    def test_allocation_preserves_locked_quota_and_reports_unknown_duration(self):
        summary = build_allocation_summary(
            [{"channelId": "a", "monetized": True, "quota": 4, "quotaLocked": True,
              "minDurationSeconds": 600, "maxDurationSeconds": 1800}],
            [{"id": "known", "durationSeconds": 720, "status": "ready"},
             {"id": "unknown", "durationSeconds": None, "status": "ready"}],
        )

        self.assertEqual(summary["channels"][0]["recommendedQuota"], 4)
        self.assertEqual(summary["missingDurationJobIds"], ["unknown"])
        self.assertEqual(summary["counters"], {"required": 4, "ready": 2, "assigned": 0, "missing": 4, "reserve": 2})

    def test_allocation_assigns_compatible_jobs_and_keeps_duration_mismatches_in_reserve(self):
        result = allocate_ready_jobs(
            [{"channelId": "monetized", "monetized": True, "minDurationSeconds": 600, "maxDurationSeconds": 2000},
             {"channelId": "growth", "growthSignal": True, "minDurationSeconds": 60, "maxDurationSeconds": 599}],
            [{"id": "long-1", "status": "ready", "durationSeconds": 700},
             {"id": "long-2", "status": "ready", "durationSeconds": 800},
             {"id": "long-3", "status": "ready", "durationSeconds": 900},
             {"id": "short-1", "status": "ready", "durationSeconds": 120},
             {"id": "short-2", "status": "ready", "durationSeconds": 180},
             {"id": "no-duration", "status": "ready", "durationSeconds": None}],
        )

        self.assertEqual(result["assignments"], {
            "monetized": ["long-1", "long-2", "long-3"],
            "growth": ["short-1", "short-2"],
        })
        self.assertEqual(result["skipped"], {"no-duration": "Нужно определить длительность ролика"})

    def test_publication_job_serializes_measured_duration_for_allocation(self):
        job = create_publication_job(
            video_path="D:/ready/video.mp4", package_folder="D:/ready", title="Реальный выпуск",
            duration_seconds=742.5,
        )

        self.assertEqual(publication_job_record(job)["durationSeconds"], 742.5)
    def test_linked_post_uses_seo_and_call_to_action_without_hashtags_at_video_time(self):
        job = schedule_publication(
            create_publication_job(
                video_path="D:/ready/video.mp4",
                package_folder="D:/ready",
                title="Ормуз: риски для торговли",
                seo_description="Разбираем риски для танкеров. #Ормуз #новости",
            ),
            datetime(2026, 8, 30, 18, 45, tzinfo=timezone.utc),
        )

        post = build_linked_community_post(job, video_url="https://youtu.be/example", call_to_action="Смотрите новый выпуск и напишите своё мнение. #видео")

        self.assertEqual(post["publishAt"], "2026-08-30T18:45:00+00:00")
        self.assertEqual(post["status"], "prepared")
        self.assertIn("Разбираем риски для танкеров.", post["text"])
        self.assertIn("Смотрите новый выпуск", post["text"])
        self.assertIn("https://youtu.be/example", post["text"])
        self.assertNotIn("#", post["text"])
        self.assertTrue(post["requiresManualConfirmation"])

    def test_manual_ad_break_checklist_is_every_39_seconds_without_crossing_video_end(self):
        self.assertEqual(manual_ad_break_checklist(118), ["00:39", "01:18"])
        self.assertEqual(manual_ad_break_checklist(39), [])

    def test_youtube_upload_body_is_private_and_carries_ready_package_metadata(self):
        body = build_private_video_insert_body(
            title="Ормуз: риски для торговли",
            description="Описание из SEO-пакета",
            tags=["Ормуз", "танкеры"],
            publish_at="2026-08-30T04:00:00+00:00",
        )

        self.assertEqual(body["snippet"], {"title": "Ормуз: риски для торговли", "description": "Описание из SEO-пакета", "tags": ["Ормуз", "танкеры"]})
        self.assertEqual(body["status"], {"privacyStatus": "private", "publishAt": "2026-08-30T04:00:00+00:00", "selfDeclaredMadeForKids": False})

    def test_current_channel_parser_uses_youtube_response_not_user_entered_label(self):
        profile = parse_current_channel({"items": [{"id": "UC123", "snippet": {"title": "Новости 24", "thumbnails": {"high": {"url": "https://i.ytimg.com/channel.jpg"}}}, "statistics": {"subscriberCount": "1510", "viewCount": "48000"}}]})

        self.assertEqual(profile, {"channelId": "UC123", "name": "Новости 24", "thumbnailUrl": "https://i.ytimg.com/channel.jpg", "subscribers": 1510, "viewsTotal": 48000})

    def test_current_channel_parser_explains_when_google_account_has_no_channel(self):
        with self.assertRaisesRegex(ValueError, "сделайте нужный канал каналом по умолчанию"):
            parse_current_channel({"items": []})

    def test_google_account_email_parser_returns_the_authorised_identity(self):
        self.assertEqual(parse_google_account_email({"email": "owner@example.com", "verified_email": True}), "owner@example.com")

    def test_youtube_oauth_requests_only_the_scopes_chosen_by_operator(self):
        standard = youtube_oauth_scopes(include_monetary=False)
        with_income = youtube_oauth_scopes(include_monetary=True)

        self.assertIn("https://www.googleapis.com/auth/youtube.upload", standard)
        self.assertIn("https://www.googleapis.com/auth/yt-analytics.readonly", standard)
        self.assertNotIn("https://www.googleapis.com/auth/yt-analytics-monetary.readonly", standard)
        self.assertIn("https://www.googleapis.com/auth/yt-analytics-monetary.readonly", with_income)

    def test_analytics_summary_filters_channels_and_marks_partial_revenue_coverage(self):
        points = [
            AnalyticsMetricPoint("channel-a", datetime(2026, 8, 30, 4, tzinfo=timezone.utc), 120, 5, 1, 3.5),
            AnalyticsMetricPoint("channel-b", datetime(2026, 8, 30, 4, tzinfo=timezone.utc), 80, 2, 1, None),
            AnalyticsMetricPoint("channel-a", datetime(2026, 8, 30, 5, tzinfo=timezone.utc), 240, 8, 0, 4.0),
        ]

        all_channels = aggregate_analytics_metrics(
            points,
            channel_ids=["channel-a", "channel-b"],
            start_at=datetime(2026, 8, 30, 4, tzinfo=timezone.utc),
            end_at=datetime(2026, 8, 30, 6, tzinfo=timezone.utc),
        )
        only_a = aggregate_analytics_metrics(
            points,
            channel_ids=["channel-a"],
            start_at=datetime(2026, 8, 30, 4, tzinfo=timezone.utc),
            end_at=datetime(2026, 8, 30, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(all_channels["totals"], {"views": 440, "subscribers": 15, "publications": 2, "revenue": 7.5})
        self.assertEqual(all_channels["revenueCoverage"], {"availableChannels": ["channel-a"], "missingChannels": ["channel-b"]})
        self.assertEqual([point["views"] for point in all_channels["series"]], [200, 240])
        self.assertEqual(only_a["totals"], {"views": 360, "subscribers": 13, "publications": 1, "revenue": 7.5})
        self.assertEqual(only_a["revenueCoverage"], {"availableChannels": ["channel-a"], "missingChannels": []})

    def test_new_ready_video_becomes_private_draft_without_a_date(self):
        job = create_publication_job(
            video_path="D:/NewsFlow Studio/Новости/Тема 1/ролик.mp4",
            package_folder="D:/NewsFlow Studio/Новости/Тема 1",
            title="Тема 1",
            script_name="01 — Ормуз.txt",
            seo_title="Ормуз: что происходит",
            seo_description="Проверяемое описание выпуска.",
            seo_phrases=["Ормуз", "нефть", "танкеры"],
            tags=["Ормуз", "новости"],
            hashtags=["#Ормуз", "#новости"],
            thumbnail_path="D:/NewsFlow Studio/Новости/Тема 1/обложка.png",
        )

        self.assertIsInstance(job, PublicationJob)
        self.assertEqual(job.status, "ready")
        self.assertEqual(job.privacy, "private")
        self.assertIsNone(job.publish_at)
        self.assertEqual(job.script_name, "01 — Ормуз.txt")
        self.assertEqual(job.seo_title, "Ормуз: что происходит")
        self.assertEqual(job.seo_phrases, ["Ормуз", "нефть", "танкеры"])
        self.assertEqual(job.tags, ["Ормуз", "новости"])
        self.assertEqual(job.thumbnail_path, "D:/NewsFlow Studio/Новости/Тема 1/обложка.png")

    def test_scheduled_private_draft_waits_for_selected_time(self):
        job = create_publication_job(
            video_path="D:/NewsFlow Studio/Новости/Тема 2/ролик.mp4",
            package_folder="D:/NewsFlow Studio/Новости/Тема 2",
            title="Тема 2",
        )
        publish_at = datetime(2026, 8, 30, 18, 45, tzinfo=timezone.utc)

        scheduled = schedule_publication(job, publish_at)

        self.assertEqual(scheduled.status, "scheduled")
        self.assertEqual(scheduled.privacy, "private")
        self.assertEqual(scheduled.publish_at, publish_at)

    def test_title_over_one_hundred_characters_waits_for_rephrasing_before_upload(self):
        title = (
            "Россия усиливает давление на Ормузский пролив: мировая торговля рискует "
            "оказаться в заложниках нового кризиса"
        )

        job = create_publication_job(
            video_path="D:/NewsFlow Studio/Новости/Тема 3/ролик.mp4",
            package_folder="D:/NewsFlow Studio/Новости/Тема 3",
            title=title,
        )

        self.assertGreater(len(title), 100)
        self.assertEqual(job.status, "needs-title-rewrite")
        self.assertEqual(job.title, title)
        self.assertIn("100", job.title_rewrite_instruction)
        self.assertFalse(can_upload(job))

    def test_valid_rephrased_title_restores_job_to_ready_queue(self):
        job = create_publication_job(
            video_path="D:/NewsFlow Studio/Новости/Тема 4/ролик.mp4",
            package_folder="D:/NewsFlow Studio/Новости/Тема 4",
            title="Россия усиливает давление на Ормузский пролив: мировая торговля рискует оказаться в заложниках нового кризиса",
        )

        rewritten = apply_rewritten_title(job, "Ормуз под давлением: риски для мировой торговли")

        self.assertEqual(rewritten.status, "ready")
        self.assertEqual(rewritten.title, "Ормуз под давлением: риски для мировой торговли")
        self.assertEqual(rewritten.title_rewrite_instruction, "")
        self.assertTrue(can_upload(rewritten))

    def test_spread_mode_keeps_stable_distinct_times_when_the_operator_chooses_distribution(self):
        channels = [f"channel-{index:03}" for index in range(100)]
        first_cycle = datetime(2026, 8, 30, 4, 0, tzinfo=timezone.utc)

        grid = build_staggered_publication_grid(
            channel_ids=channels,
            first_cycle_at=first_cycle,
            cycles=6,
            interval_hours=3,
            distribution="spread",
        )

        self.assertEqual(set(grid), set(channels))
        self.assertEqual(grid, build_staggered_publication_grid(channels, first_cycle, 6, 3))
        for times in grid.values():
            self.assertEqual(len(times), 6)
            self.assertTrue(all((later - earlier).total_seconds() == 10_800 for earlier, later in zip(times, times[1:])))
        for cycle_index in range(6):
            times = [grid[channel][cycle_index] for channel in channels]
            self.assertEqual(len(set(times)), 100)
            cycle_start = first_cycle + timedelta(hours=cycle_index * 3)
            cycle_end = cycle_start + timedelta(hours=3)
            self.assertTrue(all(cycle_start <= value < cycle_end for value in times))

    def test_schedule_allows_shared_times_with_an_hourly_rule(self):
        first_cycle = datetime(2026, 8, 30, 4, 0, tzinfo=timezone.utc)

        grid = build_staggered_publication_grid(
            channel_ids=["channel-a", "channel-b"],
            first_cycle_at=first_cycle,
            cycles=3,
            interval_minutes=60,
            distribution="aligned",
        )

        self.assertEqual(
            grid["channel-a"],
            [first_cycle, first_cycle + timedelta(hours=1), first_cycle + timedelta(hours=2)],
        )
        self.assertEqual(grid["channel-b"], grid["channel-a"])

    def test_bulk_grid_assigns_jobs_to_channels_and_keeps_each_channel_interval(self):
        jobs = [create_publication_job(
            video_path=f"D:/NewsFlow Studio/Новости/{index}/ролик.mp4",
            package_folder=f"D:/NewsFlow Studio/Новости/{index}",
            title=f"Тема {index}",
        ) for index in range(6)]
        first_cycle = datetime(2026, 8, 30, 4, 0, tzinfo=timezone.utc)

        planned = plan_jobs_on_publication_grid(
            jobs,
            channel_ids=["channel-a", "channel-b"],
            first_cycle_at=first_cycle,
            interval_minutes=60,
            distribution="aligned",
        )

        self.assertEqual([job.status for job in planned], ["scheduled"] * 6)
        times_by_channel = {
            channel: [job.publish_at for job in planned if job.channel_id == channel]
            for channel in ("channel-a", "channel-b")
        }
        self.assertEqual(times_by_channel["channel-a"], [first_cycle, first_cycle + timedelta(hours=1), first_cycle + timedelta(hours=2)])
        self.assertEqual(times_by_channel["channel-b"], times_by_channel["channel-a"])

    def test_result_package_resolves_sanitized_filename_through_durable_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original_title = 'Ормуз: что происходит? Риски / торговля'
            production_id = "production-seo-1"
            rendered_stem = bridge.safe_filename(original_title)
            video = root / f"{rendered_stem}.mp4"
            video.write_bytes(b"mp4")
            cover = root / "cover.png"
            cover.write_bytes(b"png")
            settings = Settings(
                montage_output_folder=str(root),
                montage_project_folder=str(root),
                pipeline_montage_outputs=[str(video)],
                montage_task_statuses={
                    "0": {
                        "scenarioIndex": 0,
                        "title": original_title,
                        "status": "Готово",
                        "outputPath": str(video),
                    },
                },
            )
            settings.cover_queue = [{
                "production_item_id": production_id,
                "title": original_title,
                "path": str(cover),
            }]
            settings.seo_queue = [{
                "production_item_id": production_id,
                "source_title": original_title,
                "status": "Готово",
                "title": "SEO вариант",
                "description": "Описание из SEO",
                "hashtags": ["#Ормуз"],
                "tags": ["Ормуз", "торговля"],
            }]
            job = SimpleNamespace(
                request=SimpleNamespace(
                    index=0,
                    title=original_title,
                    production_item_id=production_id,
                ),
                state=RunState.DONE,
                result="Текст сценария",
            )

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=([original_title], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}):
                bridge.package_outputs({})

            package = Path(settings.video_result_packages[str(video)])
            self.assertEqual(
                (package / "Название сценария.txt").read_text(encoding="utf-8-sig").strip(),
                original_title,
            )
            self.assertEqual(
                (package / "Описание.txt").read_text(encoding="utf-8-sig").strip(),
                "Описание из SEO",
            )
            self.assertEqual(
                (package / "Теги.txt").read_text(encoding="utf-8-sig").strip(),
                "Ормуз, торговля",
            )
            self.assertTrue((package / "Обложка.png").is_file())

    def test_result_package_keeps_scenario_title_separate_from_seo_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "Ормуз — сценарный заголовок.mp4"
            video.write_bytes(b"mp4")
            cover = root / "cover.png"
            cover.write_bytes(b"png")
            title = video.stem
            settings = Settings(montage_output_folder=str(root), pipeline_montage_outputs=[str(video)])
            settings.cover_queue = [{"title": title, "path": str(cover)}]
            settings.seo_queue = [{
                "source_title": title,
                "status": "Готово",
                "title": "SEO вариант заголовка",
                "description": "SEO описание выпуска",
                "tags": ["Ормуз", "танкеры"],
            }]
            job = SimpleNamespace(
                request=SimpleNamespace(title=title),
                state=RunState.DONE,
                result="Текст сценария",
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=([title], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}):
                bridge.package_outputs({})

            package = Path(settings.video_result_packages[str(video)])
            self.assertEqual((package / "Заголовок.txt").read_text(encoding="utf-8-sig").strip(), title)
            self.assertEqual((package / "SEO-заголовок.txt").read_text(encoding="utf-8-sig").strip(), "SEO вариант заголовка")
            self.assertEqual((package / "Название сценария.txt").read_text(encoding="utf-8-sig").strip(), title)
            self.assertIn("SEO вариант заголовка", (package / "SEO-фразы.txt").read_text(encoding="utf-8-sig"))
            self.assertIn("танкеры", (package / "Теги.txt").read_text(encoding="utf-8-sig"))

    def test_publication_queue_presets_and_log_survive_settings_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(
                youtube_publication_jobs=[{"id": "job-1", "title": "Ормуз", "status": "ready"}],
                youtube_publication_presets=[{"name": "Каждые 3 часа", "intervalMinutes": 180}],
                youtube_publication_activity=[{"kind": "created", "jobId": "job-1"}],
            )
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

            self.assertEqual(restored.youtube_publication_jobs, [{"id": "job-1", "title": "Ормуз", "status": "ready"}])
            self.assertEqual(restored.youtube_publication_presets, [{"name": "Каждые 3 часа", "intervalMinutes": 180}])
            self.assertEqual(restored.youtube_publication_activity, [{"kind": "created", "jobId": "job-1"}])

    def test_allocation_profiles_and_presets_survive_settings_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(
                youtube_publication_allocation_profiles=[{"channelId": "a", "quota": 3, "quotaLocked": True}],
                youtube_publication_allocation_presets=[{"name": "Основной", "channelIds": ["a"]}],
            )
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

        self.assertEqual(restored.youtube_publication_allocation_profiles[0]["quota"], 3)
        self.assertEqual(restored.youtube_publication_allocation_presets[0]["name"], "Основной")

    def test_clear_production_queue_preserves_directions_channels_oauth_analytics_and_allocation_presets(self):
        settings = Settings(
            analytics_channels=[{"profile_id": "one", "name": "Канал"}],
            youtube_oauth_tokens={"one": "protected"},
            youtube_analytics_metric_points=[{"channelId": "one", "views": 20}],
            youtube_publication_allocation_presets=[{"name": "Основной"}],
            youtube_engagement_policies=[{"channelId": "one", "enabled": True}],
            youtube_engagement_tasks=[{"jobId": "job", "channelId": "one"}],
            youtube_publication_jobs=[{"id": "job", "title": "Ролик"}],
            idea_topics=["Прошлая тема"],
            idea_directions=[{"id": "direction-1", "title": "Сохранить редакционное направление"}],
            footage_folders=["D:/NewsFlow/Footage"],
            cover_face_library_folder="D:/NewsFlow/Faces",
            cover_api_keys=[FastGenKey("FastGen", "fastgen-test-secret", True)],
            openai_api_keys=[OpenAIKey("OpenAI", "openai-test-secret", True)],
            wproject_api_keys=[WProjectKey("WProject", "wproject-test-secret", True)],
            pipeline_montage_outputs=["D:/keep/video.mp4"],
            video_result_packages={"D:/keep/video.mp4": "D:/keep"},
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "save_session"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.clear_production_queue({
                "confirmed": True,
                "confirmationPhrase": "УДАЛИТЬ ПРОИЗВОДСТВО",
            })

        self.assertEqual(settings.analytics_channels, [{"profile_id": "one", "name": "Канал"}])
        self.assertEqual(settings.youtube_oauth_tokens, {"one": "protected"})
        self.assertEqual(settings.youtube_analytics_metric_points, [{"channelId": "one", "views": 20}])
        self.assertEqual(settings.youtube_publication_allocation_presets, [{"name": "Основной"}])
        self.assertEqual(settings.youtube_engagement_policies, [{"channelId": "one", "enabled": True}])
        self.assertEqual(settings.youtube_engagement_tasks, [])
        self.assertEqual(settings.idea_topics, ["Прошлая тема"])
        self.assertEqual(settings.idea_directions, [
            {"id": "direction-1", "title": "Сохранить редакционное направление"},
        ])
        self.assertEqual(settings.footage_folders, ["D:/NewsFlow/Footage"])
        self.assertEqual(settings.cover_face_library_folder, "D:/NewsFlow/Faces")
        self.assertEqual(settings.cover_api_keys[0].secret, "fastgen-test-secret")
        self.assertEqual(settings.openai_api_keys[0].secret, "openai-test-secret")
        self.assertEqual(settings.wproject_api_keys[0].secret, "wproject-test-secret")
        self.assertEqual(settings.youtube_publication_jobs, [])
        self.assertEqual(settings.pipeline_montage_outputs, [])
        self.assertEqual(settings.video_result_packages, {})

    def test_clear_production_queue_persists_an_empty_release_after_restart(self):
        """The confirmed command must clear durable queue state, not just its UI snapshot."""
        from scriptor.session import load_session, save_session

        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NEWSFLOW_TEST_MODE": "1",
            "NEWSFLOW_TEST_ROOT": directory,
            "LOCALAPPDATA": directory,
            "NEWSFLOW_PRODUCTION_LOCALAPPDATA": "C:/Users/borov/AppData/Local",
        }, clear=False):
            output = Path(directory) / "release-output"
            output.mkdir()
            artefact = output / "old.mp4"
            artefact.write_bytes(b"obsolete-production-output")
            settings = Settings(
                output_folder=str(output), voicer_output_folder=str(output),
                cover_output_folder=str(output), seo_output_folder=str(output),
                media_output_folder=str(output), cutter_output_folder=str(output),
                footage_download_folder=str(output), mixer_output_folder=str(output),
                montage_output_folder=str(output), montage_project_folder=str(output),
                idea_results=["Старая тема"],
                idea_production_items=[{"id": "production-1", "title": "Старая тема"}],
                cover_queue=[{"title": "Старая тема"}],
                seo_queue=[{"title": "Старая тема"}],
                voice_tts_jobs={"production-1": {"id": "voice-1", "title": "Старая тема"}},
                voice_tts_batches=[{"id": "batch-1", "title": "Старая тема"}],
                voice_active_tts_batch_id="batch-1",
                voice_scenario_outputs={"1": str(output / "old.mp3")},
                voice_task_statuses={"1": "Готово"},
                montage_task_statuses={"1": "Готово"},
                youtube_publication_jobs=[{"id": "publication-1", "title": "Старая тема"}],
                youtube_publication_items={"production-1": {"id": "publication-item-1", "title": "Старая тема"}},
                youtube_publication_snapshots={"production-1": {"id": "snapshot-1"}},
                youtube_publication_executions={"production-1": {"id": "execution-1"}},
                youtube_publication_receipts={"production-1": {"id": "receipt-1"}},
                youtube_publication_assignments={"production-1": {"jobId": "publication-1"}},
                analytics_channels=[{"profile_id": "keep", "name": "Канал"}],
                youtube_oauth_tokens={"keep": "protected-oauth-fixture"},
                footage_folders=["D:/NewsFlow/Footage"],
                cover_face_library_folder="D:/NewsFlow/Faces",
                cover_api_keys=[FastGenKey("FastGen", "fastgen-test-secret", True)],
                openai_api_keys=[OpenAIKey("OpenAI", "openai-test-secret", True)],
                wproject_api_keys=[WProjectKey("WProject", "wproject-test-secret", True)],
            )
            config.save_settings(settings)
            save_session(["Старая тема"], [
                bridge.Job(bridge.ScenarioRequest(0, "Старая тема", ""), RunState.DONE, "Текст", ""),
            ])

            bridge.clear_production_queue({
                "confirmed": True,
                "confirmationPhrase": "УДАЛИТЬ ПРОИЗВОДСТВО",
            })

            restored = config.load_settings()
            titles, jobs = load_session()

        self.assertFalse(artefact.exists())
        self.assertEqual((titles, jobs), ([], []))
        self.assertEqual(restored.idea_results, [])
        self.assertEqual(restored.idea_production_items, [])
        self.assertEqual(restored.cover_queue, [])
        self.assertEqual(restored.seo_queue, [])
        self.assertEqual(restored.voice_tts_jobs, {})
        self.assertEqual(restored.voice_tts_batches, [])
        self.assertEqual(restored.voice_active_tts_batch_id, "")
        self.assertEqual(restored.voice_scenario_outputs, {})
        self.assertEqual(restored.voice_task_statuses, {})
        self.assertEqual(restored.montage_task_statuses, {})
        self.assertEqual(restored.youtube_publication_jobs, [])
        self.assertEqual(restored.youtube_publication_items, {})
        self.assertEqual(restored.youtube_publication_snapshots, {})
        self.assertEqual(restored.youtube_publication_executions, {})
        self.assertEqual(restored.youtube_publication_receipts, {})
        self.assertEqual(restored.youtube_publication_assignments, {})
        self.assertEqual(restored.analytics_channels, [{"profile_id": "keep", "name": "Канал"}])
        self.assertEqual(restored.youtube_oauth_tokens, {"keep": "protected-oauth-fixture"})
        self.assertEqual(restored.footage_folders, ["D:/NewsFlow/Footage"])
        self.assertEqual(restored.cover_face_library_folder, "D:/NewsFlow/Faces")
        self.assertEqual(restored.cover_api_keys[0].secret, "fastgen-test-secret")
        self.assertEqual(restored.openai_api_keys[0].secret, "openai-test-secret")
        self.assertEqual(restored.wproject_api_keys[0].secret, "wproject-test-secret")

    def test_constructor_assigns_only_selected_duration_compatible_jobs(self):
        settings = Settings(
            analytics_channels=[{"profile_id": "monetized", "name": "Старый", "monetary_access": True},
                                {"profile_id": "fresh", "name": "Новый"}],
            youtube_publication_allocation_profiles=[
                {"channelId": "monetized", "minDurationSeconds": 600, "maxDurationSeconds": 1800},
                {"channelId": "fresh", "minDurationSeconds": 60, "maxDurationSeconds": 599},
            ],
            youtube_publication_jobs=[
                {"id": "long", "title": "Длинный", "status": "ready", "durationSeconds": 800},
                {"id": "short", "title": "Короткий", "status": "ready", "durationSeconds": 180},
                {"id": "other", "title": "Не выбран", "status": "ready", "durationSeconds": 180},
            ],
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.assign_publication_jobs({"jobIds": ["long", "short"], "channelIds": ["monetized", "fresh"]})

        jobs = {item["id"]: item for item in settings.youtube_publication_jobs}
        self.assertEqual(result["operationResult"]["count"], 2)
        self.assertEqual(jobs["long"]["channelId"], "monetized")
        self.assertEqual(jobs["short"]["channelId"], "fresh")
        self.assertNotIn("channelId", jobs["other"])

    def test_analytics_metric_history_survives_settings_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(
                youtube_analytics_metric_points=[{"channelId": "channel-a", "at": "2026-08-30T04:00:00+00:00", "views": 120}],
                youtube_analytics_updated_at="2026-08-30T04:05:00+00:00",
            )
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

            self.assertEqual(restored.youtube_analytics_metric_points, settings.youtube_analytics_metric_points)
            self.assertEqual(restored.youtube_analytics_updated_at, settings.youtube_analytics_updated_at)

    def test_oauth_tokens_are_persisted_separately_from_publication_metadata(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(youtube_oauth_tokens={"channel-profile-a": '{"refresh_token":"secret"}'})
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

            self.assertEqual(restored.youtube_oauth_tokens, settings.youtube_oauth_tokens)

    def test_adding_channel_creates_visible_profile_row_and_operation_result(self):
        settings = Settings()
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"channels": []}):
            result = bridge.add_channel({"name": "Взгляд сверху", "channel": ""})

        self.assertEqual(settings.analytics_channels[0]["name"], "Взгляд сверху")
        self.assertTrue(settings.analytics_channels[0]["profile_id"])
        self.assertEqual(settings.analytics_channels[0]["status"], "Ожидает входа Google")
        self.assertEqual(result["operationResult"]["kind"], "analytics-channel-added")

    def test_opening_connected_channel_uses_its_creator_studio_url_and_profile(self):
        settings = Settings(analytics_channels=[{
            "profile_id": "profile-a", "channel_id": "UC-real", "name": "Взгляд сверху",
        }])
        with TemporaryDirectory() as directory:
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "app_data_root", return_value=Path(directory)), \
                 patch.object(bridge, "chrome_path", return_value=Path("C:/Chrome/chrome.exe")), \
                 patch.object(bridge.subprocess, "Popen") as popen:
                bridge.open_analytics_channel({"index": 0})

        self.assertIn("--user-data-dir=", popen.call_args.args[0][1])
        self.assertEqual(popen.call_args.args[0][-1], "https://studio.youtube.com/channel/UC-real")

    def test_channel_metadata_saves_operator_tag(self):
        settings = Settings(analytics_channels=[{"profile_id": "profile-a", "name": "Взгляд сверху"}])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.update_analytics_channel_metadata({"index": 0, "tag": "основной канал"})

        self.assertEqual(settings.analytics_channels[0]["operator_tag"], "основной канал")
        self.assertEqual(result["operationResult"]["kind"], "analytics-channel-metadata")

    def test_connecting_channel_stores_only_serialized_oauth_token_for_its_profile(self):
        with TemporaryDirectory() as directory:
            client_file = Path(directory) / "client.json"
            client_file.write_text("{}", encoding="utf-8")
            settings = Settings(
                google_oauth_client_file=str(client_file),
                analytics_channels=[{"profile_id": "profile-a", "name": "Тест", "status": "Ожидает входа Google"}],
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "authorize_desktop_channel", return_value={"refresh_token": "secret", "token": "short"}), \
                 patch.object(bridge, "fetch_current_channel", return_value=({"channelId": "UC-real", "name": "Реальный канал", "thumbnailUrl": "https://i.ytimg.com/real.jpg", "subscribers": 15, "viewsTotal": 120}, {"refresh_token": "secret", "token": "refreshed"})):
                bridge.connect_youtube_channel({"index": 0, "includeMonetary": True})

            self.assertEqual(settings.youtube_oauth_tokens["profile-a"], '{"refresh_token": "secret", "token": "refreshed"}')
            self.assertIn("подключён", settings.analytics_channels[0]["status"].casefold())
            self.assertTrue(settings.analytics_channels[0]["monetary_access"])
            self.assertEqual(settings.analytics_channels[0]["channel_id"], "UC-real")
            self.assertEqual(settings.analytics_channels[0]["thumbnail_url"], "https://i.ytimg.com/real.jpg")
            self.assertEqual(settings.analytics_channels[0]["name"], "Реальный канал")

    def test_local_channel_oauth_preserves_remote_handoff_endpoint(self):
        """Desktop fallback must not disable the configured token handoff for other channels."""
        with TemporaryDirectory() as directory:
            client_file = Path(directory) / "client.json"
            client_file.write_text("{}", encoding="utf-8")
            settings = Settings(
                google_oauth_client_file=str(client_file),
                youtube_oauth_service_url="https://a.tinkbro.online",
                analytics_channels=[{"profile_id": "profile-a", "name": "Тест"}],
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "authorize_desktop_channel", return_value={"token": "short"}), \
                 patch.object(bridge, "fetch_current_channel", return_value=({"channelId": "UC-real", "name": "Реальный канал", "subscribers": 15, "viewsTotal": 120}, {"token": "fresh"})):
                bridge.connect_youtube_channel({"index": 0})

        self.assertEqual(settings.youtube_oauth_service_url, "https://a.tinkbro.online")

    def test_connecting_channel_opens_oauth_in_its_own_saved_chrome_profile(self):
        """Changing the regular Chrome login must not change OAuth's channel identity."""
        with TemporaryDirectory() as directory:
            client_file = Path(directory) / "client.json"
            client_file.write_text("{}", encoding="utf-8")
            settings = Settings(
                google_oauth_client_file=str(client_file),
                analytics_channels=[{"profile_id": "profile-a", "name": "Тест"}],
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "app_data_root", return_value=Path(directory)), \
                 patch.object(bridge, "chrome_path", return_value=Path("C:/Chrome/chrome.exe")), \
                 patch.object(bridge, "authorize_desktop_channel", return_value={"token": "short"}) as authorize, \
                 patch.object(bridge, "fetch_current_channel", return_value=({"channelId": "UC-real", "name": "Реальный канал", "subscribers": 15, "viewsTotal": 120}, {"token": "fresh"})):
                bridge.connect_youtube_channel({"index": 0})

        browser_command = authorize.call_args.kwargs["browser_command"]
        self.assertIn("--user-data-dir=", browser_command)
        self.assertIn("YouTubeChannelProfiles", browser_command)
        self.assertIn("profile-a", browser_command)
        self.assertIn("chrome.exe", browser_command.casefold())
        self.assertIn("--new-window", browser_command)

    def test_switching_google_account_archives_only_the_selected_channel_profile(self):
        """Account switching revokes NewsFlow's selected token without touching another channel's profile."""
        settings = Settings(
            youtube_oauth_tokens={"profile-a": '{"token":"old"}', "profile-b": '{"token":"keep"}'},
            analytics_channels=[
                {"profile_id": "profile-a", "channel_id": "UC-a", "name": "Первый", "status": "OAuth подключён"},
                {"profile_id": "profile-b", "channel_id": "UC-b", "name": "Второй", "status": "OAuth подключён"},
            ],
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "YouTubeChannelProfiles" / "profile-a"
            untouched = root / "YouTubeChannelProfiles" / "profile-b"
            selected.mkdir(parents=True); untouched.mkdir(parents=True)
            (selected / "session.txt").write_text("old", encoding="utf-8")
            (untouched / "session.txt").write_text("keep", encoding="utf-8")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={} ), \
                 patch.object(bridge, "app_data_root", return_value=root):
                result = bridge.reset_youtube_channel_account({"index": 0})

            self.assertFalse(selected.exists())
            self.assertTrue(untouched.exists())
            self.assertNotIn("profile-a", settings.youtube_oauth_tokens)
            self.assertIn("profile-b", settings.youtube_oauth_tokens)
            self.assertEqual(settings.analytics_channels[0]["status"], "Ожидает нового входа Google")
            self.assertEqual(result["operationResult"]["kind"], "youtube-account-reset")

    def test_analytics_refresh_records_actual_channel_counter_changes(self):
        with TemporaryDirectory() as directory:
            client_file = Path(directory) / "client.json"
            client_file.write_text("{}", encoding="utf-8")
            settings = Settings(
                google_oauth_client_file=str(client_file),
                youtube_oauth_tokens={"profile-a": '{"token":"old"}'},
                analytics_channels=[{"profile_id": "profile-a", "name": "Канал", "subscribers": "10", "views_total": 100, "status": "OAuth подключён"}],
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "fetch_current_channel", return_value=({"channelId": "UC-a", "name": "Канал", "subscribers": 13, "viewsTotal": 175}, {"token": "fresh"})):
                bridge.refresh_analytics({})

            self.assertEqual(settings.youtube_analytics_metric_points[0]["views"], 75)
            self.assertEqual(settings.youtube_analytics_metric_points[0]["subscribers"], 3)
            self.assertEqual(settings.analytics_channels[0]["views_hour"], "75")
            self.assertEqual(settings.youtube_oauth_tokens["profile-a"], '{"token": "fresh"}')

    def test_analytics_rows_use_response_headers_not_a_fixed_column_order(self):
        """YouTube may reorder columns, so the parser must retain the named metrics."""
        rows = parse_analytics_rows({
            "columnHeaders": [
                {"name": "averageViewPercentage"},
                {"name": "video"},
                {"name": "views"},
            ],
            "rows": [[62.5, "abc123", 210]],
        })

        self.assertEqual(rows, [{"averageViewPercentage": 62.5, "video": "abc123", "views": 210}])

    def test_analytics_refresh_binds_video_metrics_to_a_connected_channel(self):
        settings = Settings(
            youtube_oauth_tokens={"profile-a": '{"token":"old"}'},
            analytics_channels=[{"profile_id": "profile-a", "name": "Канал", "subscribers": "10", "views_total": 100}],
        )
        analytics = {
            "daily": [{"day": "2026-08-29", "views": 25, "subscribersGained": 2}],
            "videos": [{"video": "video-1", "views": 25, "averageViewDuration": 122.0, "averageViewPercentage": 54.2}],
            "financialAvailable": False,
            "errors": [],
        }
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "fetch_current_channel", return_value=({"channelId": "UC-a", "name": "Канал", "subscribers": 12, "viewsTotal": 125}, {"token": "fresh"})), \
             patch.object(bridge, "fetch_youtube_analytics", return_value=analytics):
            bridge.refresh_analytics({})

        self.assertEqual(settings.youtube_analytics_video_metrics[0]["videoId"], "video-1")
        self.assertEqual(settings.youtube_analytics_video_metrics[0]["channelId"], "profile-a")
        self.assertFalse(settings.youtube_analytics_video_metrics[0]["financialAvailable"])

    def test_operator_can_save_any_positive_parallel_upload_count(self):
        settings = Settings()
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_publication_settings({"uploadConcurrency": 17})

        self.assertEqual(settings.youtube_publication_upload_concurrency, 17)

    def test_uploading_a_scheduled_job_records_video_url_and_linked_post_draft(self):
        settings = Settings(
            youtube_publication_upload_concurrency=3,
            youtube_oauth_tokens={"profile-a": '{"token":"authorised"}'},
            youtube_publication_jobs=[{
                "id": "job-a", "videoPath": "D:/ready.mp4", "packageFolder": "D:/package",
                "title": "Ормуз: риски для торговли", "status": "scheduled", "privacy": "private",
                "channelId": "profile-a", "publishAt": "2026-08-30T04:00:00+00:00",
                "seoDescription": "Описание выпуска #новости", "tags": ["Ормуз"],
            }],
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "upload_private_video", return_value=({"videoId": "abc123", "videoUrl": "https://www.youtube.com/watch?v=abc123", "privacyStatus": "private"}, {"token": "refreshed"})):
            bridge.upload_publication_jobs({"jobIds": ["job-a"], "callToAction": "Смотрите выпуск. #видео"})

        job = settings.youtube_publication_jobs[0]
        self.assertEqual(job["status"], "uploaded")
        self.assertEqual(job["videoUrl"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(job["post"]["publishAt"], "2026-08-30T04:00:00+00:00")
        self.assertNotIn("#", job["post"]["text"])
        self.assertEqual(settings.youtube_oauth_tokens["profile-a"], '{"token": "refreshed"}')
        self.assertEqual(len(settings.youtube_engagement_tasks), 1)
        self.assertEqual(settings.youtube_engagement_tasks[0]["jobId"], "job-a")
        self.assertEqual(settings.youtube_engagement_tasks[0]["post"]["status"], "pending")

    def test_operator_can_assign_selected_jobs_to_an_hourly_shared_grid(self):
        settings = Settings(youtube_publication_jobs=[
            {"id": "job-a", "videoPath": "D:/a.mp4", "packageFolder": "D:/a", "title": "Тема A", "status": "ready", "privacy": "private"},
            {"id": "job-b", "videoPath": "D:/b.mp4", "packageFolder": "D:/b", "title": "Тема B", "status": "ready", "privacy": "private"},
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.schedule_publication_jobs({
                "jobIds": ["job-a", "job-b"],
                "channelIds": ["channel-a", "channel-b"],
                "firstCycleAt": "2026-08-30T04:00:00+00:00",
                "intervalMinutes": 60,
                "distribution": "aligned",
            })

        self.assertEqual([item["status"] for item in settings.youtube_publication_jobs], ["scheduled", "scheduled"])
        self.assertEqual([item["channelId"] for item in settings.youtube_publication_jobs], ["channel-a", "channel-b"])
        self.assertEqual([item["publishAt"] for item in settings.youtube_publication_jobs], [
            "2026-08-30T04:00:00+00:00", "2026-08-30T04:00:00+00:00",
        ])

    def test_scheduling_keeps_measured_video_duration_for_later_smart_allocation(self):
        settings = Settings(youtube_publication_jobs=[
            {"id": "job-a", "videoPath": "D:/a.mp4", "packageFolder": "D:/a", "title": "Тема A", "status": "ready", "privacy": "private", "durationSeconds": 720},
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.schedule_publication_jobs({
                "jobIds": ["job-a"], "channelIds": ["channel-a"],
                "firstCycleAt": "2026-08-30T04:00:00+00:00", "intervalMinutes": 60,
            })

        self.assertEqual(settings.youtube_publication_jobs[0]["durationSeconds"], 720)

    def test_first_then_batches_uses_fifteen_minute_slots_before_repeating_them(self):
        """A 3-hour cadence should first cover 09:00, 09:15, 09:30 across channels."""
        start = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)

        grid = build_staggered_publication_grid(
            ["view", "truth", "news"], start, 2,
            interval_minutes=180,
            distribution="first-then-batches",
            slot_minutes=15,
            batch_capacity=1,
        )

        self.assertEqual(grid["view"], [start, start + timedelta(minutes=180)])
        self.assertEqual(grid["truth"], [start + timedelta(minutes=15), start + timedelta(minutes=195)])
        self.assertEqual(grid["news"], [start + timedelta(minutes=30), start + timedelta(minutes=210)])

    def test_always_batches_respects_selected_channels_per_fifteen_minute_slot(self):
        start = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)

        grid = build_staggered_publication_grid(
            ["one", "two", "three"], start, 1,
            interval_minutes=180,
            distribution="always-batches",
            slot_minutes=15,
            batch_capacity=2,
        )

        self.assertEqual(grid["one"], [start])
        self.assertEqual(grid["two"], [start])
        self.assertEqual(grid["three"], [start + timedelta(minutes=15)])

    def test_stretch_cycle_avoids_repeating_minutes_when_the_cadence_is_too_short(self):
        start = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)

        grid = build_staggered_publication_grid(
            ["one", "two", "three"], start, 2,
            interval_minutes=30,
            distribution="stretch-cycle",
            slot_minutes=15,
            batch_capacity=1,
        )

        self.assertEqual(grid["one"], [start, start + timedelta(minutes=45)])
        self.assertEqual(grid["two"], [start + timedelta(minutes=15), start + timedelta(minutes=60)])
        self.assertEqual(grid["three"], [start + timedelta(minutes=30), start + timedelta(minutes=75)])

    def test_operator_can_save_schedule_preset_and_move_one_job_without_changing_others(self):
        settings = Settings(youtube_publication_jobs=[
            {"id": "job-a", "videoPath": "D:/a.mp4", "packageFolder": "D:/a", "title": "Тема A", "status": "scheduled", "privacy": "private", "channelId": "channel-a", "publishAt": "2026-08-30T04:00:00+00:00"},
            {"id": "job-b", "videoPath": "D:/b.mp4", "packageFolder": "D:/b", "title": "Тема B", "status": "scheduled", "privacy": "private", "channelId": "channel-b", "publishAt": "2026-08-30T04:00:00+00:00"},
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_publication_preset({"name": "Каждый час", "intervalMinutes": 60, "distribution": "aligned", "channelIds": ["channel-a", "channel-b"]})
            bridge.move_publication_job({"jobId": "job-a", "publishAt": "2026-08-30T04:25:00+00:00"})

        self.assertEqual(settings.youtube_publication_presets, [{"name": "Каждый час", "intervalMinutes": 60, "distribution": "aligned", "channelIds": ["channel-a", "channel-b"]}])
        self.assertEqual(settings.youtube_publication_jobs[0]["publishAt"], "2026-08-30T04:25:00+00:00")
        self.assertEqual(settings.youtube_publication_jobs[1]["publishAt"], "2026-08-30T04:00:00+00:00")

    def test_publication_queue_reads_all_metadata_from_ready_result_package(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            source.write_bytes(b"source")
            package = root / "package"
            package.mkdir()
            ready_mp4 = package / "Ормуз.mp4"
            ready_mp4.write_bytes(b"mp4")
            (package / "Название сценария.txt").write_text("Ормуз: сценарный заголовок\n", encoding="utf-8-sig")
            (package / "Заголовок.txt").write_text("Ормуз: сценарный заголовок\n", encoding="utf-8-sig")
            (package / "SEO-заголовок.txt").write_text("SEO вариант\n", encoding="utf-8-sig")
            (package / "Описание.txt").write_text("Описание ролика\n", encoding="utf-8-sig")
            (package / "SEO-фразы.txt").write_text("Ормуз\nтанкеры\n", encoding="utf-8-sig")
            (package / "Теги.txt").write_text("Ормуз, танкеры\n", encoding="utf-8-sig")
            (package / "Хештеги.txt").write_text("#Ормуз #танкеры\n", encoding="utf-8-sig")
            (package / "Обложка.png").write_bytes(b"png")
            settings = Settings(video_result_packages={str(source): str(package)})
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}):
                result = bridge.queue_ready_publication_outputs({})

            self.assertEqual(result["operationResult"]["count"], 1)
            self.assertEqual(len(settings.youtube_publication_jobs), 1)
            queued = settings.youtube_publication_jobs[0]
            self.assertEqual(queued["title"], "Ормуз: сценарный заголовок")
            self.assertEqual(queued["seoTitle"], "SEO вариант")
            self.assertEqual(queued["seoPhrases"], ["Ормуз", "танкеры"])
            self.assertEqual(queued["tags"], ["Ормуз", "танкеры"])
            self.assertEqual(queued["hashtags"], ["#Ормуз", "#танкеры"])
            self.assertEqual(queued["privacy"], "private")


if __name__ == "__main__":
    unittest.main()
