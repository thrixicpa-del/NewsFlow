import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge, config
from scriptor.command_contract import COMMAND_CONTRACT
from scriptor.config import Settings
from scriptor.publication_v2 import (
    apply_bulk_schedule_range,
    begin_upload_attempt,
    build_channel_schedule,
    build_distribution_preview,
    cancel_publication_execution,
    claim_execution,
    classify_publication_error,
    complete_publication_stage,
    complete_upload_attempt,
    confirm_publication_snapshots,
    fail_publication_stage,
    migrate_legacy_publication_data,
    next_upload_candidates,
    normalize_channel_publication_rule,
    persist_publication_receipt,
    publication_receipt,
    reconcile_publication_executions,
    reconcile_publication_items,
    reconcile_youtube_video_state,
    release_execution,
    retry_publication_stage,
    validate_publication_schedule,
    validate_publication_snapshot,
)


class PublicationV2MigrationTests(unittest.TestCase):
    def test_migration_uses_canonical_production_item_id_field(self):
        """Modern ProductionItems use ``id``; title lookup must not be required."""
        settings = Settings(
            idea_production_items=[{"id": "canonical-pi", "title": "Одинаковый заголовок"}],
            youtube_publication_jobs=[{
                "id": "job-canonical", "productionItemId": "canonical-pi",
                "title": "Одинаковый заголовок", "videoPath": "D:/missing/video.mp4",
                "packageFolder": "D:/missing",
            }],
        )

        migrate_legacy_publication_data(settings)

        self.assertIn("canonical-pi", settings.youtube_publication_items)
        self.assertEqual(settings.youtube_publication_items["canonical-pi"]["legacyLinks"]["legacyJobId"], "job-canonical")

    def test_migration_links_legacy_job_to_stable_production_item_without_mutating_legacy_record(self):
        """Removing ProductionItem linkage or editing legacy data must fail this migration contract."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "episode.mp4"
            video.write_bytes(b"not-a-real-mp4")
            legacy_job = {
                "id": "legacy-job-1", "title": "Выпуск A", "videoPath": str(video),
                "packageFolder": str(root), "channelId": "channel-a", "status": "uploaded",
                "videoId": "youtube-known-id", "videoUrl": "https://youtu.be/youtube-known-id",
            }
            settings = Settings(
                idea_production_items=[{"production_item_id": "pi-a", "title": "Выпуск A"}],
                youtube_publication_jobs=[dict(legacy_job)],
            )

            report = migrate_legacy_publication_data(settings)

        self.assertEqual(report.migrated_items, 1)
        self.assertEqual(settings.youtube_publication_jobs, [legacy_job])
        item = settings.youtube_publication_items["pi-a"]
        self.assertEqual(item["legacyLinks"]["legacyJobId"], "legacy-job-1")
        self.assertEqual(item["legacyLinks"]["videoPath"], str(video))
        self.assertEqual(len(settings.youtube_publication_snapshots), 1)
        execution = next(iter(settings.youtube_publication_executions.values()))
        self.assertEqual(execution["youtubeVideoId"], "youtube-known-id")
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")

    def test_migration_keeps_missing_artifact_as_recoverable_state_instead_of_deleting_it(self):
        """A missing MP4 must remain visible in the registry and legacy queue."""
        missing_video = "D:/missing/episode.mp4"
        legacy_job = {"id": "legacy-missing", "title": "Выпуск B", "videoPath": missing_video, "packageFolder": "D:/missing"}
        settings = Settings(
            idea_production_items=[{"production_item_id": "pi-b", "title": "Выпуск B"}],
            youtube_publication_jobs=[dict(legacy_job)],
        )

        report = migrate_legacy_publication_data(settings)

        self.assertEqual(report.missing_artifacts, 1)
        self.assertEqual(settings.youtube_publication_jobs, [legacy_job])
        self.assertFalse(settings.youtube_publication_items["pi-b"]["artifacts"]["video"]["exists"])
        self.assertIn("VIDEO_MISSING", settings.youtube_publication_items["pi-b"]["readiness"]["reasons"])

    def test_migration_projects_legacy_montage_rows_when_ideas_and_legacy_jobs_are_absent(self):
        """A restored montage queue must populate V2 even when older versions had no ProductionItems."""
        settings = Settings(
            montage_task_statuses={
                "13": {"title": "Тема 13", "status": "Ошибка", "outputPath": "D:/missing/13.mp4", "voicePath": "D:/voice/13.mp3"},
                "14": {"title": "Тема 14", "status": "Готово", "outputPath": "D:/missing/14.mp4", "voicePath": "D:/voice/14.mp3"},
            },
            pipeline_montage_outputs=["D:/missing/13.mp4", "D:/missing/14.mp4"],
            voice_scenario_outputs={"13": "D:/voice/13.mp3", "14": "D:/voice/14.mp3"},
        )

        report = migrate_legacy_publication_data(settings)

        self.assertEqual(report.migrated_items, 2)
        self.assertEqual(set(settings.youtube_publication_items), {"legacy-montage:13", "legacy-montage:14"})
        item = settings.youtube_publication_items["legacy-montage:13"]
        self.assertEqual(item["metadata"]["title"], "Тема 13")
        self.assertEqual(item["artifacts"]["video"]["path"], "D:/missing/13.mp4")
        self.assertEqual(item["artifacts"]["audio"]["path"], "D:/voice/13.mp3")
        self.assertEqual(item["readiness"]["state"], "VIDEO_MISSING")

    def test_v2_registry_snapshot_and_execution_survive_settings_restart(self):
        """Dropping V2 state during Settings save/load would make resume unsafe."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(
                youtube_publication_items={"pi-1": {"productionItemId": "pi-1"}},
                youtube_publication_snapshots={"snapshot-1": {"id": "snapshot-1", "idempotencyKey": "key-1"}},
                youtube_publication_executions={"snapshot-1": {"youtubeVideoId": "already-uploaded"}},
                youtube_publication_receipts={"snapshot-1": {"finalStatus": "SCHEDULED"}},
                youtube_publication_migration_version=2,
            )
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

        self.assertEqual(restored.youtube_publication_items, settings.youtube_publication_items)
        self.assertEqual(restored.youtube_publication_snapshots, settings.youtube_publication_snapshots)
        self.assertEqual(restored.youtube_publication_executions, settings.youtube_publication_executions)
        self.assertEqual(restored.youtube_publication_receipts, settings.youtube_publication_receipts)
        self.assertEqual(restored.youtube_publication_migration_version, 2)


class PublicationV2RegistryTests(unittest.TestCase):
    def test_registry_counts_video_ready_and_missing_items_without_conflating_them_with_queue(self):
        """A queue row must not hide a ready video or turn quota into a missing-file count."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ready = root / "ready.mp4"
            ready.write_bytes(b"mp4")
            settings = Settings(
                idea_production_items=[
                    {"production_item_id": "pi-ready", "title": "Готовый выпуск"},
                    {"production_item_id": "pi-missing", "title": "Нет файла"},
                ],
                youtube_publication_jobs=[
                    {"id": "legacy-ready", "title": "Готовый выпуск", "videoPath": str(ready), "packageFolder": str(root)},
                    {"id": "legacy-missing", "title": "Нет файла", "videoPath": str(root / "gone.mp4"), "packageFolder": str(root)},
                ],
            )

            registry = reconcile_publication_items(settings)

        self.assertEqual(
            {key: registry["counters"][key] for key in ("total", "videoReady", "videoMissing")},
            {"total": 2, "videoReady": 1, "videoMissing": 1},
        )
        self.assertEqual(registry["items"]["pi-ready"]["readiness"]["state"], "VIDEO_READY")
        self.assertEqual(registry["items"]["pi-missing"]["readiness"]["state"], "VIDEO_MISSING")


class PublicationV2DistributionTests(unittest.TestCase):
    def test_preview_command_is_registered_to_the_current_publication_service(self):
        registration = COMMAND_CONTRACT["preview-publication-v2-distribution"]

        self.assertEqual(registration.handler, "preview_publication_v2_distribution")
        self.assertEqual(registration.service, "scriptor.publication_v2")

    def test_bridge_bulk_range_preview_filters_channels_and_does_not_persist_assignments(self):
        """Range controls are a dry run until the operator explicitly confirms it."""
        settings = Settings(
            analytics_channels=[
                {"profile_id": "channel-a", "name": "A"},
                {"profile_id": "channel-b", "name": "B"},
            ],
            youtube_oauth_tokens={
                "channel-a": "{\"token\": \"a\"}",
                "channel-b": "{\"token\": \"b\"}",
            },
            youtube_publication_items={
                f"pi-{index}": {"productionItemId": f"pi-{index}", "readiness": {"state": "VIDEO_READY"}}
                for index in range(3)
            },
            youtube_channel_publication_rules={
                "channel-a": {"channelId": "channel-a", "enabled": True, "quota": 3},
                "channel-b": {"channelId": "channel-b", "enabled": True, "quota": 3},
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "reconcile_publication_items"), \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.preview_publication_v2_distribution({"bulkSchedule": {
                "date": "2026-11-15", "startTime": "04:00", "endTime": "10:00",
                "timezone": "Europe/Minsk", "channelIds": ["channel-b"], "maxPerChannel": 2,
            }})

        rows = result["publicationPreview"]["assignments"]
        self.assertEqual([row["channelId"] for row in rows], ["channel-b", "channel-b", ""])
        self.assertEqual([row.get("publishAt", "") for row in rows[:2]], [
            "2026-11-15T04:00:00+03:00", "2026-11-15T04:15:00+03:00",
        ])
        self.assertEqual(settings.youtube_publication_assignments, {})


    def test_bridge_auto_preview_excludes_orphan_channel_rule_when_real_channels_are_known(self):
        """A stale rule for a removed/unconnected channel must never receive new auto assignments."""
        settings = Settings(
            analytics_channels=[{"profile_id": "channel-good", "name": "Good"}],
            youtube_oauth_tokens={"channel-good": "{\"token\": \"ok\"}"},
            youtube_publication_items={
                "pi-1": {
                    "productionItemId": "pi-1",
                    "metadata": {"index": 1},
                    "readiness": {"state": "CONTENT_READY", "contentReady": True},
                },
            },
            youtube_channel_publication_rules={
                "channel-orphan": {"channelId": "channel-orphan", "enabled": True, "quota": 1, "distributionStrategy": "balanced"},
                "channel-good": {"channelId": "channel-good", "enabled": True, "quota": 1, "distributionStrategy": "balanced"},
            },
        )

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "reconcile_publication_items"), \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.preview_publication_v2_distribution({})

        rows = result["publicationPreview"]["assignments"]
        self.assertEqual(rows[0]["channelId"], "channel-good")

    def test_preview_preserves_locked_assignment_and_allocates_only_remaining_ready_item(self):
        """Auto-distribution must not move a locked slot while filling visible channel quota."""
        items = {
            "pi-1": {"productionItemId": "pi-1", "metadata": {"title": "Первый"}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 300},
            "pi-2": {"productionItemId": "pi-2", "metadata": {"title": "Второй"}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 500},
        }
        rules = [
            {"channelId": "channel-a", "enabled": True, "quota": 1, "distributionStrategy": "ordered"},
            {"channelId": "channel-b", "enabled": True, "quota": 1, "distributionStrategy": "ordered"},
        ]
        assignments = {"pi-1": {"productionItemId": "pi-1", "channelId": "channel-b", "source": "manual", "locked": True}}

        preview = build_distribution_preview(items, rules, assignments)

        rows = {row["productionItemId"]: row for row in preview["assignments"]}
        self.assertEqual(rows["pi-1"]["channelId"], "channel-b")
        self.assertTrue(rows["pi-1"]["locked"])
        self.assertEqual(rows["pi-2"]["channelId"], "channel-a")
        self.assertEqual(assignments["pi-1"]["channelId"], "channel-b")

    def test_topic_routing_and_priority_are_deterministic(self):
        items = {
            "pi-economy": {
                "productionItemId": "pi-economy",
                "metadata": {"index": 1, "topic": "Европа экономика", "direction": "Европа", "priority": 8},
                "readiness": {"state": "CONTENT_READY", "contentReady": True},
            },
            "pi-sport": {
                "productionItemId": "pi-sport",
                "metadata": {"index": 2, "topic": "Европа спорт", "direction": "Европа", "priority": 1},
                "readiness": {"state": "CONTENT_READY", "contentReady": True},
            },
        }
        rules = [
            {
                "channelId": "economy", "enabled": True, "oauthConnected": True, "quota": 2,
                "distributionStrategy": "balanced", "channelPriority": 10,
                "includeKeywords": ["экономика"], "excludeKeywords": ["спорт"],
            },
            {
                "channelId": "general", "enabled": True, "oauthConnected": True, "quota": 2,
                "distributionStrategy": "balanced", "channelPriority": 0,
            },
        ]

        preview = build_distribution_preview(items, rules, {})
        rows = {row["productionItemId"]: row for row in preview["assignments"]}

        self.assertEqual(rows["pi-economy"]["channelId"], "economy")
        self.assertEqual(rows["pi-sport"]["channelId"], "general")

    def test_channel_priority_breaks_equal_balance_ties(self):
        preview = build_distribution_preview(
            {
                "pi": {
                    "productionItemId": "pi",
                    "metadata": {"index": 1},
                    "readiness": {"state": "CONTENT_READY", "contentReady": True},
                },
            },
            [
                {"channelId": "low", "enabled": True, "oauthConnected": True, "quota": 3, "distributionStrategy": "balanced", "channelPriority": 0},
                {"channelId": "high", "enabled": True, "oauthConnected": True, "quota": 3, "distributionStrategy": "balanced", "channelPriority": 20},
            ],
            {},
        )

        self.assertEqual(preview["assignments"][0]["channelId"], "high")

    def test_large_84_item_preview_is_deterministic_complete_and_quota_safe(self):
        """Commercial bulk planning must not lose, duplicate or over-allocate items at realistic batch size."""
        items = {
            f"pi-{index:03}": {
                "productionItemId": f"pi-{index:03}",
                "metadata": {
                    "index": index,
                    "priority": 2 if index <= 8 else 0,
                    "topicFamily": "economy" if index % 3 == 0 else "world",
                },
                "durationSeconds": 540 + (index % 7) * 30,
                "readiness": {"state": "CONTENT_READY", "contentReady": True},
            }
            for index in range(1, 85)
        }
        rules = []
        for index in range(8):
            channel_id = f"channel-{index + 1}"
            rules.append({
                "channelId": channel_id,
                "enabled": True,
                "oauthConnected": True,
                "quota": 11 if index < 4 else 10,
                "monetized": index < 4,
                "distributionStrategy": "longest_monetized" if index < 4 else "balanced",
                "publishMode": "schedule",
                "timezone": "Europe/Moscow" if index % 2 == 0 else "Europe/Warsaw",
                "firstPublishAt": "2026-11-16T04:00:00",
                "intervalMinutes": 15 if index % 2 == 0 else 30,
                "allowedWeekdays": list(range(7)),
                "publishWindowStart": "04:00",
                "publishWindowEnd": "23:45",
                "dailyCap": 24,
            })

        first = build_distribution_preview(items, rules, {})
        second = build_distribution_preview(items, rules, {})

        self.assertEqual(first, second)
        rows = first["assignments"]
        self.assertEqual(len(rows), 84)
        self.assertEqual(len({row["productionItemId"] for row in rows}), 84)
        self.assertTrue(all(row["channelId"] for row in rows))

        quota_by_channel = {rule["channelId"]: rule["quota"] for rule in rules}
        usage = {
            channel_id: sum(1 for row in rows if row["channelId"] == channel_id)
            for channel_id in quota_by_channel
        }
        self.assertEqual(sum(usage.values()), 84)
        self.assertTrue(all(usage[channel_id] <= quota for channel_id, quota in quota_by_channel.items()))
        self.assertTrue(all(datetime.fromisoformat(row["publishAt"]).minute in {0, 15, 30, 45} for row in rows))
        self.assertEqual(first["scheduleWarnings"], [])


    def test_preview_resolves_per_channel_schedule_before_snapshot_confirmation(self):
        """A scheduled assignment must display its exact channel-local time in the dry run."""
        preview = build_distribution_preview(
            {"pi-1": {"productionItemId": "pi-1", "readiness": {"state": "VIDEO_READY"}}},
            [{"channelId": "channel-a", "enabled": True, "quota": 1, "publishMode": "schedule",
              "timezone": "Europe/Minsk", "firstPublishAt": "2026-09-10T18:00:00+03:00", "intervalMinutes": 180}],
            {},
        )

        self.assertEqual(preview["assignments"][0]["publishAt"], "2026-09-10T18:00:00+03:00")


    def test_longest_monetized_uses_monetized_eligible_channel_and_duration_bounds(self):
        """Longest-first must actually prefer monetized eligible channels, not merely sort the videos."""
        items = {
            "pi-long": {"productionItemId": "pi-long", "metadata": {"index": 1}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 900},
            "pi-mid": {"productionItemId": "pi-mid", "metadata": {"index": 2}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 600},
            "pi-short": {"productionItemId": "pi-short", "metadata": {"index": 3}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 300},
        }
        rules = [
            {"channelId": "regular", "enabled": True, "oauthConnected": True, "quota": 2, "monetized": False,
             "distributionStrategy": "longest_monetized"},
            {"channelId": "money", "enabled": True, "oauthConnected": True, "quota": 1, "monetized": True,
             "distributionStrategy": "longest_monetized", "minDurationSeconds": 500, "maxDurationSeconds": 1200},
        ]

        preview = build_distribution_preview(items, rules, {})

        rows = {row["productionItemId"]: row for row in preview["assignments"]}
        self.assertEqual(rows["pi-long"]["channelId"], "money")
        self.assertEqual(rows["pi-mid"]["channelId"], "regular")
        self.assertEqual(rows["pi-short"]["channelId"], "regular")
        self.assertEqual(rows["pi-long"]["reason"], "longest_monetized")

    def test_longest_monetized_returns_remaining_items_to_their_normal_order(self):
        """After monetized quota is filled, regular channels keep their own ordered strategy."""
        items = {
            "pi-1": {"productionItemId": "pi-1", "metadata": {"index": 1}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 1000},
            "pi-2": {"productionItemId": "pi-2", "metadata": {"index": 2}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 100},
            "pi-3": {"productionItemId": "pi-3", "metadata": {"index": 3}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 900},
            "pi-4": {"productionItemId": "pi-4", "metadata": {"index": 4}, "readiness": {"state": "VIDEO_READY"}, "durationSeconds": 800},
        }
        rules = [
            {"channelId": "money", "enabled": True, "oauthConnected": True, "quota": 1, "monetized": True,
             "distributionStrategy": "longest_monetized", "publishMode": "publish_now"},
            {"channelId": "regular", "enabled": True, "oauthConnected": True, "quota": 3, "monetized": False,
             "distributionStrategy": "ordered", "publishMode": "schedule", "timezone": "UTC",
             "firstPublishAt": "2026-09-10T10:00:00+00:00", "intervalMinutes": 15},
        ]

        preview = build_distribution_preview(items, rules, {})
        rows = {row["productionItemId"]: row for row in preview["assignments"]}

        self.assertEqual(rows["pi-1"]["channelId"], "money")
        self.assertEqual(rows["pi-2"]["publishAt"], "2026-09-10T10:00:00+00:00")
        self.assertEqual(rows["pi-3"]["publishAt"], "2026-09-10T10:15:00+00:00")
        self.assertEqual(rows["pi-4"]["publishAt"], "2026-09-10T10:30:00+00:00")

    def test_balanced_distribution_uses_fill_ratio_and_skips_auth_invalid_channels(self):
        """Balanced allocation must fill the least-used eligible channel and ignore auth-invalid channels."""
        items = {
            "locked-1": {"productionItemId": "locked-1", "readiness": {"state": "VIDEO_READY"}},
            "locked-2": {"productionItemId": "locked-2", "readiness": {"state": "VIDEO_READY"}},
            "new": {"productionItemId": "new", "readiness": {"state": "VIDEO_READY"}},
        }
        rules = [
            {"channelId": "auth-bad", "enabled": True, "oauthConnected": False, "quota": 4, "distributionStrategy": "balanced"},
            {"channelId": "busy", "enabled": True, "oauthConnected": True, "quota": 4, "distributionStrategy": "balanced"},
            {"channelId": "free", "enabled": True, "oauthConnected": True, "quota": 4, "distributionStrategy": "balanced"},
        ]
        assignments = {
            "locked-1": {"productionItemId": "locked-1", "channelId": "busy", "source": "manual", "locked": True},
            "locked-2": {"productionItemId": "locked-2", "channelId": "busy", "source": "manual", "locked": True},
        }

        preview = build_distribution_preview(items, rules, assignments)

        row = next(item for item in preview["assignments"] if item["productionItemId"] == "new")
        self.assertEqual(row["channelId"], "free")
        self.assertEqual(row["reason"], "balanced")

    def test_preview_explains_blackout_conflict_before_confirmation(self):
        items = {
            "pi-1": {
                "productionItemId": "pi-1",
                "readiness": {"state": "CONTENT_READY", "contentReady": True},
            },
        }
        rules = [{
            "channelId": "channel-a",
            "enabled": True,
            "oauthConnected": True,
            "quota": 1,
            "distributionStrategy": "balanced",
            "publishMode": "schedule",
            "timezone": "Europe/Moscow",
            "firstPublishAt": "2026-09-25T18:00:00+03:00",
            "intervalMinutes": 15,
            "blackoutPeriods": [{
                "start": "2026-09-25T18:00:00+03:00",
                "end": "2026-09-25T19:00:00+03:00",
            }],
        }]

        preview = build_distribution_preview(items, rules, {
            "pi-1": {
                "productionItemId": "pi-1",
                "channelId": "channel-a",
                "publishAt": "2026-09-25T18:15:00+03:00",
                "source": "manual",
                "locked": True,
            },
        })

        row = preview["assignments"][0]
        self.assertIn("blackout", row["scheduleWarning"].casefold())
        self.assertIn("перенесите", row["scheduleSuggestion"].casefold())

    def test_bridge_preview_keeps_uploaded_automation_cancelled_snapshot_frozen(self):
        """Stopping downstream automation must not release an already uploaded video for redistribution."""
        settings = Settings(
            analytics_channels=[
                {"profile_id": "channel-a", "name": "A"},
                {"profile_id": "channel-b", "name": "B"},
            ],
            youtube_oauth_tokens={
                "channel-a": "{\"token\": \"a\"}",
                "channel-b": "{\"token\": \"b\"}",
            },
            youtube_publication_items={
                "pi-uploaded": {"productionItemId": "pi-uploaded", "readiness": {"state": "VIDEO_READY"}},
            },
            youtube_channel_publication_rules={
                "channel-a": {"channelId": "channel-a", "enabled": True, "quota": 1},
                "channel-b": {"channelId": "channel-b", "enabled": True, "quota": 1},
            },
            youtube_publication_snapshots={
                "snap-uploaded": {
                    "id": "snap-uploaded",
                    "productionItemId": "pi-uploaded",
                    "channelId": "channel-b",
                    "requestedPublishAt": "2026-11-15T04:00:00+03:00",
                },
            },
            youtube_publication_executions={
                "snap-uploaded": {
                    "snapshotId": "snap-uploaded",
                    "productionItemId": "pi-uploaded",
                    "overallStatus": "AUTOMATION_CANCELLED",
                    "youtubeVideoId": "yt-existing",
                    "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}},
                },
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "reconcile_publication_items"), \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.preview_publication_v2_distribution({})

        row = result["publicationPreview"]["assignments"][0]
        self.assertEqual(row["channelId"], "channel-b")
        self.assertTrue(row["locked"])
        self.assertEqual(row["reason"], "confirmed_snapshot")

    def test_bridge_preview_preserves_confirmed_snapshot_as_locked_and_does_not_redistribute_it(self):
        """Confirmed/scheduled work must never be moved by an ordinary auto-preview."""
        settings = Settings(
            analytics_channels=[
                {"profile_id": "channel-a", "name": "A"},
                {"profile_id": "channel-b", "name": "B"},
            ],
            youtube_oauth_tokens={
                "channel-a": "{\"token\": \"a\"}",
                "channel-b": "{\"token\": \"b\"}",
            },
            youtube_publication_items={
                "pi-confirmed": {"productionItemId": "pi-confirmed", "readiness": {"state": "VIDEO_READY"}},
                "pi-new": {"productionItemId": "pi-new", "readiness": {"state": "VIDEO_READY"}},
            },
            youtube_channel_publication_rules={
                "channel-a": {"channelId": "channel-a", "enabled": True, "quota": 2},
                "channel-b": {"channelId": "channel-b", "enabled": True, "quota": 2},
            },
            youtube_publication_snapshots={
                "snap-1": {"id": "snap-1", "productionItemId": "pi-confirmed", "channelId": "channel-b",
                           "requestedPublishAt": "2026-11-15T04:00:00+03:00"},
            },
            youtube_publication_executions={
                "snap-1": {"snapshotId": "snap-1", "productionItemId": "pi-confirmed", "overallStatus": "SCHEDULED",
                           "youtubeVideoId": None, "steps": {}},
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "reconcile_publication_items"), \
             patch.object(bridge, "snapshot", return_value={}):
            result = bridge.preview_publication_v2_distribution({})

        rows = {row["productionItemId"]: row for row in result["publicationPreview"]["assignments"]}
        self.assertEqual(rows["pi-confirmed"]["channelId"], "channel-b")
        self.assertTrue(rows["pi-confirmed"]["locked"])
        self.assertEqual(rows["pi-confirmed"]["reason"], "confirmed_snapshot")
        self.assertNotEqual(rows["pi-new"]["productionItemId"], "pi-confirmed")


class PublicationV2RuleTests(unittest.TestCase):
    def test_channel_rule_normalizes_blackout_periods(self):
        rule = normalize_channel_publication_rule({
            "channelId": "channel-a",
            "quota": 1,
            "intervalMinutes": 15,
            "timezone": "Europe/Moscow",
            "blackoutPeriods": [{
                "start": "2026-09-25T18:00",
                "end": "2026-09-25T19:00",
                "label": "Техническое окно",
            }],
        })

        self.assertEqual(rule["blackoutPeriods"], [{
            "start": "2026-09-25T18:00:00+03:00",
            "end": "2026-09-25T19:00:00+03:00",
            "label": "Техническое окно",
        }])

        with self.assertRaisesRegex(ValueError, "blackout"):
            normalize_channel_publication_rule({
                "channelId": "channel-a",
                "quota": 1,
                "intervalMinutes": 15,
                "timezone": "Europe/Moscow",
                "blackoutPeriods": [{"start": "2026-09-25T19:00", "end": "2026-09-25T18:00"}],
            })


    def test_channel_rule_rejects_non_quarter_hour_interval_and_reversed_ranges(self):
        with self.assertRaisesRegex(ValueError, "15"):
            normalize_channel_publication_rule({
                "channelId": "channel-a", "enabled": True, "quota": 3,
                "publishMode": "schedule", "timezone": "Europe/Minsk",
                "intervalMinutes": 17,
            })
        with self.assertRaisesRegex(ValueError, "диапазон"):
            normalize_channel_publication_rule({
                "channelId": "channel-a", "enabled": True, "quota": 3,
                "intervalMinutes": 15, "orderStart": 20, "orderEnd": 10,
            })

    def test_channel_rule_freezes_explicit_ads_and_range_policy(self):
        rule = normalize_channel_publication_rule({
            "channelId": "channel-a", "enabled": True, "quota": 8, "monetized": True,
            "distributionStrategy": "longest_monetized",
            "intervalMinutes": 45, "timezone": "Europe/Minsk",
            "orderStart": 1, "orderEnd": 20,
            "minDurationSeconds": 300, "maxDurationSeconds": 1200,
            "automation": {"upload": False, "metadata": False, "ads": False, "post": False},
        })

        self.assertEqual(rule["intervalMinutes"], 45)
        self.assertEqual((rule["orderStart"], rule["orderEnd"]), (1, 20))
        self.assertTrue(rule["monetized"])
        self.assertTrue(rule["automation"]["upload"])
        self.assertTrue(rule["automation"]["metadata"])
        self.assertTrue(rule["automation"]["ads"])
        self.assertFalse(rule["automation"]["post"])


class PublicationV2PresetTests(unittest.TestCase):
    def test_rule_preset_save_apply_delete_round_trip(self):
        settings = Settings()
        rules = {
            "channel-a": {
                "channelId": "channel-a", "enabled": True, "quota": 4, "intervalMinutes": 30,
                "timezone": "Europe/Minsk", "orderStart": 1, "orderEnd": 20,
                "automation": {"post": False},
            },
        }
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {"v2": {}}}):
            bridge.save_publication_v2_rule_preset({"name": "Будни", "rules": rules})
            settings.youtube_channel_publication_rules = {}
            bridge.apply_publication_v2_rule_preset({"name": "Будни"})
            applied = settings.youtube_channel_publication_rules["channel-a"]
            self.assertEqual(applied["quota"], 4)
            self.assertEqual(applied["intervalMinutes"], 30)
            self.assertEqual((applied["orderStart"], applied["orderEnd"]), (1, 20))
            self.assertFalse(applied["automation"]["post"])
            bridge.delete_publication_v2_rule_preset({"name": "Будни"})

        self.assertEqual(settings.youtube_publication_v2_rule_presets, [])

    def test_rule_presets_survive_settings_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(youtube_publication_v2_rule_presets=[{
                "name": "Срочные",
                "rules": {"channel-a": {"channelId": "channel-a", "quota": 2, "intervalMinutes": 15}},
            }])
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

        self.assertEqual(restored.youtube_publication_v2_rule_presets, settings.youtube_publication_v2_rule_presets)


    def test_plan_versions_survive_settings_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(
                youtube_publication_plan_versions=[{
                    "id": "plan:test",
                    "name": "Вечерний план",
                    "createdAt": "2026-09-22T18:00:00+03:00",
                    "assignments": [{
                        "productionItemId": "pi-1",
                        "channelId": "channel-a",
                        "publishAt": "2026-09-22T18:15:00+03:00",
                        "source": "auto",
                        "locked": False,
                    }],
                }],
            )
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

        self.assertEqual(restored.youtube_publication_plan_versions, settings.youtube_publication_plan_versions)

class PublicationV2SchedulerTests(unittest.TestCase):
    def test_bulk_range_schedules_each_channel_independently_on_quarter_hour_grid(self):
        """A bulk window is a per-channel boundary, never one global timeline shared by every channel."""
        assignments = [
            {"productionItemId": "a-1", "channelId": "channel-a", "source": "auto", "locked": False, "reason": "auto"},
            {"productionItemId": "b-1", "channelId": "channel-b", "source": "auto", "locked": False, "reason": "auto"},
            {"productionItemId": "a-2", "channelId": "channel-a", "source": "auto", "locked": False, "reason": "auto"},
            {"productionItemId": "b-2", "channelId": "channel-b", "source": "auto", "locked": False, "reason": "auto"},
        ]
        rules = {
            "channel-a": {"channelId": "channel-a", "timezone": "Europe/Minsk", "intervalMinutes": 15},
            "channel-b": {"channelId": "channel-b", "timezone": "Europe/Minsk", "intervalMinutes": 30},
        }

        scheduled = apply_bulk_schedule_range(assignments, {
            "date": "2026-11-15", "startTime": "04:00", "endTime": "05:00",
            "timezone": "Europe/Minsk",
        }, rules)

        by_id = {row["productionItemId"]: row["publishAt"] for row in scheduled}
        self.assertEqual(by_id, {
            "a-1": "2026-11-15T04:00:00+03:00",
            "a-2": "2026-11-15T04:15:00+03:00",
            "b-1": "2026-11-15T04:00:00+03:00",
            "b-2": "2026-11-15T04:30:00+03:00",
        })
        self.assertTrue(all(datetime.fromisoformat(value).minute in {0, 15, 30, 45} for value in by_id.values()))

    def test_scheduler_rejects_non_quarter_hour_start_or_interval(self):
        """All automatic slots must stay on :00/:15/:30/:45 so UI and backend cannot disagree."""
        with self.assertRaisesRegex(ValueError, "15"):
            build_channel_schedule(
                ["pi-1"],
                {"channelId": "channel-a", "firstPublishAt": "2026-09-10T04:07:00+03:00",
                 "intervalMinutes": 15, "timezone": "Europe/Minsk"},
            )
        with self.assertRaisesRegex(ValueError, "15"):
            build_channel_schedule(
                ["pi-1"],
                {"channelId": "channel-a", "firstPublishAt": "2026-09-10T04:00:00+03:00",
                 "intervalMinutes": 20, "timezone": "Europe/Minsk"},
            )

    def test_scheduler_moves_next_slot_to_next_day_when_interval_leaves_publication_window(self):
        """A naive interval-only scheduler would incorrectly publish this third item at midnight."""
        slots = build_channel_schedule(
            ["pi-1", "pi-2", "pi-3"],
            {"channelId": "channel-a", "firstPublishAt": "2026-09-10T18:00:00+02:00", "intervalMinutes": 180,
             "timezone": "Europe/Warsaw", "publishWindowStart": "09:00", "publishWindowEnd": "21:00"},
        )

        self.assertEqual([slot["publishAt"] for slot in slots], [
            "2026-09-10T18:00:00+02:00", "2026-09-10T21:00:00+02:00", "2026-09-11T09:00:00+02:00",
        ])

    def test_scheduler_respects_max_per_hour_and_explicit_topic_cooldown(self):
        hourly = build_channel_schedule(
            ["pi-1", "pi-2", "pi-3"],
            {
                "channelId": "channel-a",
                "firstPublishAt": "2026-09-10T04:00:00+03:00",
                "intervalMinutes": 15,
                "timezone": "Europe/Minsk",
                "maxVideosPerHour": 2,
            },
        )
        self.assertEqual([slot["publishAt"] for slot in hourly], [
            "2026-09-10T04:00:00+03:00",
            "2026-09-10T04:15:00+03:00",
            "2026-09-10T05:00:00+03:00",
        ])

        cooldown = build_channel_schedule(
            ["pi-a", "pi-b", "pi-c"],
            {
                "channelId": "channel-a",
                "firstPublishAt": "2026-09-10T04:00:00+03:00",
                "intervalMinutes": 15,
                "timezone": "Europe/Minsk",
                "topicCooldownMinutes": 45,
            },
            item_topics={"pi-a": "iran", "pi-b": "iran", "pi-c": "europe"},
        )
        self.assertEqual([slot["publishAt"] for slot in cooldown], [
            "2026-09-10T04:00:00+03:00",
            "2026-09-10T04:45:00+03:00",
            "2026-09-10T05:00:00+03:00",
        ])

    def test_scheduler_skips_explicit_blackout_period(self):
        slots = build_channel_schedule(
            ["pi-1", "pi-2", "pi-3"],
            {
                "channelId": "channel-a",
                "firstPublishAt": "2026-09-25T17:45:00+03:00",
                "intervalMinutes": 15,
                "timezone": "Europe/Moscow",
                "blackoutPeriods": [{
                    "start": "2026-09-25T18:00:00+03:00",
                    "end": "2026-09-25T19:00:00+03:00",
                    "label": "Техническое окно",
                }],
            },
        )

        self.assertEqual([slot["publishAt"] for slot in slots], [
            "2026-09-25T17:45:00+03:00",
            "2026-09-25T19:00:00+03:00",
            "2026-09-25T19:15:00+03:00",
        ])

    def test_manual_slot_inside_blackout_is_a_confirmation_conflict(self):
        conflicts = validate_publication_schedule(
            [{
                "productionItemId": "pi-1",
                "channelId": "channel-a",
                "publishAt": "2026-09-25T18:15:00+03:00",
                "locked": True,
            }],
            {
                "channel-a": {
                    "timezone": "Europe/Moscow",
                    "blackoutPeriods": [{
                        "start": "2026-09-25T18:00:00+03:00",
                        "end": "2026-09-25T19:00:00+03:00",
                    }],
                },
            },
        )

        self.assertIn("blackout_period", {conflict["kind"] for conflict in conflicts})


    def test_manual_schedule_rejects_hourly_cap_and_topic_cooldown_conflicts(self):
        assignments = [
            {"productionItemId": "pi-a1", "channelId": "channel-a", "publishAt": "2026-09-25T04:00:00+03:00", "locked": True},
            {"productionItemId": "pi-a2", "channelId": "channel-a", "publishAt": "2026-09-25T04:15:00+03:00", "locked": True},
            {"productionItemId": "pi-b", "channelId": "channel-a", "publishAt": "2026-09-25T04:30:00+03:00", "locked": True},
        ]
        conflicts = validate_publication_schedule(
            assignments,
            {
                "channel-a": {
                    "timezone": "Europe/Moscow",
                    "maxVideosPerHour": 2,
                    "topicCooldownMinutes": 45,
                },
            },
            item_topics={"pi-a1": "iran", "pi-a2": "iran", "pi-b": "europe"},
        )

        kinds_by_item = {
            production_id: {item["kind"] for item in conflicts if item["productionItemId"] == production_id}
            for production_id in ("pi-a1", "pi-a2", "pi-b")
        }
        self.assertIn("topic_cooldown", kinds_by_item["pi-a2"])
        self.assertIn("max_videos_per_hour", kinds_by_item["pi-b"])

    def test_bulk_range_preserves_topic_cooldown_per_channel(self):
        assignments = [
            {"productionItemId": "pi-a1", "channelId": "channel-a", "source": "auto", "locked": False},
            {"productionItemId": "pi-a2", "channelId": "channel-a", "source": "auto", "locked": False},
        ]
        scheduled = apply_bulk_schedule_range(
            assignments,
            {
                "date": "2026-09-25",
                "startTime": "04:00",
                "endTime": "05:00",
                "timezone": "Europe/Moscow",
            },
            {
                "channel-a": {
                    "channelId": "channel-a",
                    "timezone": "Europe/Moscow",
                    "intervalMinutes": 15,
                    "topicCooldownMinutes": 45,
                },
            },
            item_topics={"pi-a1": "iran", "pi-a2": "iran"},
        )

        self.assertEqual(
            [row["publishAt"] for row in scheduled],
            ["2026-09-25T04:00:00+03:00", "2026-09-25T04:45:00+03:00"],
        )


    def test_scheduler_respects_daily_cap_before_allocating_next_day_slot(self):
        """Daily quota is a hard calendar constraint, not a display-only counter."""
        slots = build_channel_schedule(
            ["pi-1", "pi-2", "pi-3"],
            {"channelId": "channel-a", "firstPublishAt": "2026-09-10T09:00:00+03:00", "intervalMinutes": 60,
             "timezone": "Europe/Minsk", "publishWindowStart": "09:00", "publishWindowEnd": "21:00", "dailyCap": 2},
        )

        self.assertEqual([slot["publishAt"] for slot in slots], [
            "2026-09-10T09:00:00+03:00", "2026-09-10T10:00:00+03:00", "2026-09-11T09:00:00+03:00",
        ])

    def test_schedule_validation_reports_manual_slot_conflicts_without_moving_them(self):
        """A locked manual time outside the channel window must be shown before snapshot confirmation."""
        conflicts = validate_publication_schedule([
            {"productionItemId": "pi-1", "channelId": "channel-a", "publishAt": "2026-09-10T08:00:00+03:00", "locked": True},
            {"productionItemId": "pi-2", "channelId": "channel-a", "publishAt": "2026-09-10T08:00:00+03:00", "locked": True},
        ], {"channel-a": {"timezone": "Europe/Minsk", "publishWindowStart": "09:00", "publishWindowEnd": "21:00", "dailyCap": 3}})

        self.assertEqual({conflict["kind"] for conflict in conflicts}, {"outside_window", "duplicate_slot"})


class PublicationV2StateIntegrityTests(unittest.TestCase):
    def test_later_success_cannot_hide_an_existing_downstream_failure(self):
        settings = Settings(
            youtube_publication_snapshots={
                "snap": {"id": "snap", "productionItemId": "pi", "publishMode": "publish_now"},
            },
            youtube_publication_executions={
                "snap": {
                    "snapshotId": "snap", "productionItemId": "pi", "youtubeVideoId": "yt-1",
                    "activeLease": {"workerId": "worker"},
                    "steps": {
                        "VIDEO_UPLOAD": {"status": "SUCCESS"},
                        "THUMBNAIL": {"status": "FAILED"},
                        "ADS": {"status": "RUNNING"},
                    },
                },
            },
        )

        complete_publication_stage(settings, "snap", "worker", "ADS", {"mode": "AUTO_ONLY"})

        self.assertEqual(settings.youtube_publication_executions["snap"]["overallStatus"], "PARTIAL")
        self.assertEqual(settings.youtube_publication_executions["snap"]["steps"]["THUMBNAIL"]["status"], "FAILED")
        self.assertEqual(settings.youtube_publication_executions["snap"]["steps"]["ADS"]["status"], "SUCCESS")

    def test_scheduled_terminal_execution_remains_scheduled_instead_of_becoming_done(self):
        steps = {
            name: {"status": "SUCCESS"}
            for name in ("AUTH_CHECK", "VIDEO_UPLOAD", "YOUTUBE_PROCESSING", "TITLE", "DESCRIPTION", "TAGS", "THUMBNAIL", "ADS", "POST", "CARDS", "END_SCREEN")
        }
        steps["SCHEDULE"] = {"status": "RUNNING"}
        settings = Settings(
            youtube_publication_snapshots={
                "snap": {"id": "snap", "productionItemId": "pi", "publishMode": "schedule",
                         "requestedPublishAt": "2026-11-15T04:00:00+03:00"},
            },
            youtube_publication_executions={
                "snap": {
                    "snapshotId": "snap", "productionItemId": "pi", "youtubeVideoId": "yt-1",
                    "activeLease": {"workerId": "worker"}, "steps": steps,
                },
            },
        )

        complete_publication_stage(settings, "snap", "worker", "SCHEDULE", {"verified": True})

        self.assertEqual(settings.youtube_publication_executions["snap"]["overallStatus"], "SCHEDULED")


class PublicationV2SnapshotTests(unittest.TestCase):
    def test_confirmed_assignment_creates_one_immutable_snapshot_with_explicit_publish_mode_and_privacy(self):
        """Implicit scheduling or duplicate snapshots would make retry and audit unsafe."""
        settings = Settings(youtube_publication_items={
            "pi-1": {"productionItemId": "pi-1", "metadata": {"title": "Выпуск", "description": "Описание", "tags": ["тег"]},
                     "artifacts": {"video": {"path": "D:/out.mp4", "exists": True}}, "readiness": {"state": "VIDEO_READY"}},
        })
        assignments = [{"productionItemId": "pi-1", "channelId": "channel-a", "publishAt": "2026-09-10T18:00:00+02:00"}]
        rules = {"channel-a": {"privacy": "private", "publishMode": "schedule"}}

        created = confirm_publication_snapshots(settings, assignments, rules)
        repeated = confirm_publication_snapshots(settings, assignments, rules)

        self.assertEqual(len(created), 1)
        self.assertEqual(created, repeated)
        snapshot = settings.youtube_publication_snapshots[created[0]]
        self.assertEqual(snapshot["productionItemId"], "pi-1")
        self.assertEqual(snapshot["privacy"], "private")
        self.assertEqual(snapshot["publishMode"], "schedule")
        self.assertEqual(snapshot["requestedPublishAt"], "2026-09-10T18:00:00+02:00")
        self.assertTrue(snapshot["idempotencyKey"])

    def test_cancelled_preupload_snapshot_can_be_reconfirmed_without_mutating_old_snapshot(self):
        """Cancel before transport releases planning while preserving the immutable old confirmation."""
        settings = Settings(youtube_publication_items={
            "pi-1": {
                "productionItemId": "pi-1",
                "metadata": {"title": "Выпуск", "description": "Описание", "tags": ["тег"]},
                "artifacts": {"video": {"path": "D:/out.mp4", "exists": True}},
                "readiness": {"state": "VIDEO_READY", "contentReady": True},
            },
        })
        rules = {"channel-a": {"privacy": "private", "publishMode": "schedule", "timezone": "UTC", "intervalMinutes": 15}}

        first = confirm_publication_snapshots(
            settings,
            [{"productionItemId": "pi-1", "channelId": "channel-a", "publishAt": "2026-09-10T10:00:00+00:00"}],
            rules,
        )[0]
        cancel_publication_execution(settings, first)
        second = confirm_publication_snapshots(
            settings,
            [{"productionItemId": "pi-1", "channelId": "channel-a", "publishAt": "2026-09-10T11:00:00+00:00"}],
            rules,
        )[0]

        self.assertNotEqual(first, second)
        self.assertEqual(settings.youtube_publication_snapshots[first]["requestedPublishAt"], "2026-09-10T10:00:00+00:00")
        self.assertEqual(settings.youtube_publication_executions[first]["overallStatus"], "CANCELLED")
        self.assertEqual(settings.youtube_publication_snapshots[second]["requestedPublishAt"], "2026-09-10T11:00:00+00:00")
        self.assertEqual(settings.youtube_publication_executions[second]["overallStatus"], "SCHEDULED")

    def test_manual_datetime_local_is_frozen_with_channel_timezone_offset(self):
        settings = Settings(youtube_publication_items={
            "pi-1": {"productionItemId": "pi-1", "metadata": {"title": "Выпуск"},
                     "artifacts": {"video": {"path": "D:/out.mp4", "exists": True}},
                     "readiness": {"state": "VIDEO_READY"}},
        })
        created = confirm_publication_snapshots(
            settings,
            [{"productionItemId": "pi-1", "channelId": "channel-a", "publishAt": "2026-11-15T04:15:00"}],
            {"channel-a": {"privacy": "private", "publishMode": "schedule", "timezone": "Europe/Minsk",
                           "intervalMinutes": 15}},
        )

        self.assertEqual(
            settings.youtube_publication_snapshots[created[0]]["requestedPublishAt"],
            "2026-11-15T04:15:00+03:00",
        )

    def test_snapshot_freezes_current_cta_for_later_studio_post(self):
        settings = Settings(
            seo_call_to_action="CTA at confirmation",
            youtube_publication_items={
                "pi-1": {
                    "productionItemId": "pi-1",
                    "metadata": {"title": "Выпуск"},
                    "artifacts": {"video": {"path": "D:/out.mp4", "exists": True}},
                    "readiness": {"state": "VIDEO_READY"},
                },
            },
        )
        created = confirm_publication_snapshots(
            settings,
            [{"productionItemId": "pi-1", "channelId": "channel-a"}],
            {"channel-a": {"privacy": "private", "publishMode": "publish_now", "intervalMinutes": 15}},
        )
        settings.seo_call_to_action = "CTA changed later"

        snapshot = settings.youtube_publication_snapshots[created[0]]
        self.assertEqual(snapshot["communityPost"]["callToAction"], "CTA at confirmation")

    def test_scheduled_snapshot_rejects_non_private_initial_privacy_before_transport(self):
        """YouTube schedule semantics require a private draft, so reject invalid input before any upload."""
        settings = Settings(youtube_publication_items={
            "pi-1": {"productionItemId": "pi-1", "metadata": {"title": "Выпуск"},
                     "artifacts": {"video": {"path": "D:/out.mp4", "exists": True}}, "readiness": {"state": "VIDEO_READY"}},
        })

        with self.assertRaisesRegex(ValueError, "private"):
            confirm_publication_snapshots(settings, [{"productionItemId": "pi-1", "channelId": "channel-a", "publishAt": "2026-09-10T18:00:00+03:00"}],
                                          {"channel-a": {"privacy": "public", "publishMode": "schedule"}})

    def test_preflight_blocks_only_missing_or_invalid_snapshot_and_never_reopens_known_upload(self):
        """Preflight reports exact readiness reasons and treats an existing YouTube ID as immutable."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"mp4")
            settings = Settings(youtube_oauth_tokens={"channel-a": "protected-token"}, youtube_publication_snapshots={
                "snapshot-1": {"id": "snapshot-1", "channelId": "channel-a", "videoPath": str(video),
                               "metadata": {"title": "Ролик"}, "privacy": "private", "publishMode": "publish_now"},
            }, youtube_publication_executions={"snapshot-1": {"youtubeVideoId": "yt-existing"}})

            preflight = validate_publication_snapshot(settings, "snapshot-1")

        self.assertTrue(preflight["ok"])
        self.assertTrue(preflight["uploadAlreadyExists"])
        self.assertEqual(preflight["reasons"], [])


class PublicationV2ExecutionTests(unittest.TestCase):
    def test_execution_lease_and_granular_retry_never_reset_confirmed_video_upload(self):
        """A second worker or Cards retry must not create/re-upload the same YouTube video."""
        settings = Settings(youtube_publication_executions={
            "snapshot-1": {
                "snapshotId": "snapshot-1", "youtubeVideoId": "yt-1", "activeLease": None,
                "steps": {
                    "VIDEO_UPLOAD": {"status": "SUCCESS", "attempts": 1},
                    "CARDS": {"status": "FAILED", "attempts": 2, "error": {"category": "RETRYABLE"}},
                },
            },
        })

        self.assertTrue(claim_execution(settings, "snapshot-1", "worker-a"))
        self.assertFalse(claim_execution(settings, "snapshot-1", "worker-b"))
        retry_publication_stage(settings, "snapshot-1", "CARDS")

        execution = settings.youtube_publication_executions["snapshot-1"]
        self.assertEqual(execution["youtubeVideoId"], "yt-1")
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(execution["steps"]["CARDS"]["status"], "RETRYING")

    def test_paused_queue_starts_no_new_upload_and_processing_does_not_consume_upload_slot(self):
        """A paused queue must be inert, while a finished transport frees its upload worker."""
        settings = Settings(youtube_publication_upload_concurrency=1, youtube_publication_executions={
            "snapshot-processing": {"snapshotId": "snapshot-processing", "overallStatus": "PROCESSING",
                                    "youtubeVideoId": "yt-known", "activeLease": {"workerId": "old"},
                                    "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}, "YOUTUBE_PROCESSING": {"status": "RUNNING"}}},
            "snapshot-ready": {"snapshotId": "snapshot-ready", "overallStatus": "READY", "youtubeVideoId": None,
                               "activeLease": None, "steps": {"VIDEO_UPLOAD": {"status": "PENDING"}}},
        })

        self.assertEqual(next_upload_candidates(settings), ["snapshot-ready"])
        settings.youtube_publication_queue_paused = True
        self.assertEqual(next_upload_candidates(settings), [])

    def test_verified_youtube_description_includes_frozen_hashtags(self):
        """Readback compares the exact final description sent to YouTube, including hashtags."""
        settings = Settings(
            youtube_publication_snapshots={
                "snapshot-1": {
                    "id": "snapshot-1",
                    "metadata": {
                        "title": "Выпуск",
                        "description": "Описание",
                        "tags": ["тег"],
                        "hashtags": ["#NewsFlow", "#Новости"],
                    },
                    "publishMode": "publish_now",
                },
            },
            youtube_publication_executions={
                "snapshot-1": {
                    "snapshotId": "snapshot-1",
                    "youtubeVideoId": "yt-1",
                    "overallStatus": "PROCESSING",
                    "steps": {
                        "VIDEO_UPLOAD": {"status": "SUCCESS"},
                        "YOUTUBE_PROCESSING": {"status": "RUNNING"},
                        "DESCRIPTION": {"status": "PENDING"},
                    },
                },
            },
        )

        reconcile_youtube_video_state(settings, "snapshot-1", {
            "snippet": {
                "title": "Выпуск",
                "description": "Описание\n\n#NewsFlow #Новости",
                "tags": ["тег"],
            },
            "status": {"privacyStatus": "private"},
            "processingDetails": {"processingStatus": "succeeded"},
        })

        self.assertEqual(
            settings.youtube_publication_executions["snapshot-1"]["steps"]["DESCRIPTION"]["status"],
            "SUCCESS",
        )

    def test_verified_youtube_state_completes_only_confirmed_metadata_and_keeps_unverified_stage_honest(self):
        """Verification confirms only API evidence; absent thumbnail proof is not reported as success."""
        settings = Settings(youtube_publication_snapshots={
            "snapshot-1": {"id": "snapshot-1", "metadata": {"title": "Выпуск", "description": "Описание", "tags": ["тег"]},
                           "publishMode": "publish_now"},
        }, youtube_publication_executions={
            "snapshot-1": {"snapshotId": "snapshot-1", "youtubeVideoId": "yt-1", "overallStatus": "PROCESSING",
                           "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}, "YOUTUBE_PROCESSING": {"status": "RUNNING"},
                                     "TITLE": {"status": "PENDING"}, "DESCRIPTION": {"status": "PENDING"}, "TAGS": {"status": "PENDING"}, "THUMBNAIL": {"status": "PENDING"}}},
        })

        reconcile_youtube_video_state(settings, "snapshot-1", {"snippet": {"title": "Выпуск", "description": "Описание", "tags": ["тег"]},
                                                                  "processingDetails": {"processingStatus": "succeeded"}, "status": {"privacyStatus": "private"}})

        steps = settings.youtube_publication_executions["snapshot-1"]["steps"]
        self.assertEqual(steps["YOUTUBE_PROCESSING"]["status"], "SUCCESS")
        self.assertEqual(steps["TITLE"]["status"], "SUCCESS")
        self.assertEqual(steps["DESCRIPTION"]["status"], "SUCCESS")
        self.assertEqual(steps["TAGS"]["status"], "SUCCESS")
        self.assertEqual(steps["THUMBNAIL"]["status"], "PENDING")

    def test_youtube_readback_verifies_frozen_seo_title_instead_of_source_title(self):
        settings = Settings(
            youtube_publication_snapshots={
                "snapshot-1": {
                    "id": "snapshot-1",
                    "metadata": {
                        "title": "Исходное название сценария",
                        "seoTitle": "SEO-заголовок для YouTube",
                        "description": "Описание",
                        "tags": ["тег"],
                    },
                    "publishMode": "publish_now",
                },
            },
            youtube_publication_executions={
                "snapshot-1": {
                    "snapshotId": "snapshot-1",
                    "youtubeVideoId": "yt-1",
                    "overallStatus": "PROCESSING",
                    "steps": {
                        "VIDEO_UPLOAD": {"status": "SUCCESS"},
                        "YOUTUBE_PROCESSING": {"status": "RUNNING"},
                        "TITLE": {"status": "PENDING"},
                        "DESCRIPTION": {"status": "PENDING"},
                        "TAGS": {"status": "PENDING"},
                    },
                },
            },
        )

        reconcile_youtube_video_state(
            settings,
            "snapshot-1",
            {
                "snippet": {
                    "title": "SEO-заголовок для YouTube",
                    "description": "Описание",
                    "tags": ["тег"],
                },
                "processingDetails": {"processingStatus": "succeeded"},
                "status": {"privacyStatus": "private"},
            },
        )

        self.assertEqual(
            settings.youtube_publication_executions["snapshot-1"]["steps"]["TITLE"]["status"],
            "SUCCESS",
        )


    def test_cancel_after_youtube_id_stops_automation_without_deleting_or_reuploading_video(self):
        """Cancellation after transport is a downstream stop, never a YouTube deletion."""
        settings = Settings(youtube_publication_executions={
            "snapshot-1": {"snapshotId": "snapshot-1", "youtubeVideoId": "yt-1", "overallStatus": "UPLOADED",
                           "activeLease": None, "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}, "TITLE": {"status": "PENDING"}}},
        })

        cancel_publication_execution(settings, "snapshot-1")

        execution = settings.youtube_publication_executions["snapshot-1"]
        self.assertEqual(execution["youtubeVideoId"], "yt-1")
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(execution["overallStatus"], "AUTOMATION_CANCELLED")

    def test_release_lease_and_receipt_preserve_known_video_identity_across_restart_projection(self):
        """A receipt must use the existing YouTube identity and expose unverified stages honestly."""
        settings = Settings(youtube_publication_snapshots={
            "snapshot-1": {"id": "snapshot-1", "productionItemId": "pi-1", "channelId": "channel-a",
                           "metadata": {"title": "Ролик"}, "privacy": "private", "publishMode": "schedule",
                           "requestedPublishAt": "2026-09-10T18:00:00+03:00"},
        }, youtube_publication_executions={
            "snapshot-1": {"snapshotId": "snapshot-1", "youtubeVideoId": "yt-1", "youtubeVideoUrl": "https://youtu.be/yt-1",
                           "overallStatus": "SCHEDULED", "activeLease": {"workerId": "worker-a"},
                           "confirmedPublishAt": None,
                           "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}, "TITLE": {"status": "UNVERIFIED"},
                                     "SCHEDULE": {"status": "SUCCESS"}}},
        })

        release_execution(settings, "snapshot-1", "worker-a")
        receipt = publication_receipt(settings, "snapshot-1")

        self.assertIsNone(settings.youtube_publication_executions["snapshot-1"]["activeLease"])
        self.assertEqual(receipt["youtubeVideoId"], "yt-1")
        self.assertEqual(receipt["stages"]["TITLE"], "UNVERIFIED")
        self.assertEqual(receipt["finalStatus"], "PARTIAL")

    def test_receipt_is_persisted_separately_from_immutable_snapshot(self):
        """History must survive restart without mutating the confirmed snapshot input."""
        snapshot = {"id": "snapshot-1", "productionItemId": "pi-1", "channelId": "channel-a", "metadata": {"title": "Ролик"}}
        settings = Settings(youtube_publication_snapshots={"snapshot-1": dict(snapshot)}, youtube_publication_executions={
            "snapshot-1": {"snapshotId": "snapshot-1", "overallStatus": "DONE", "youtubeVideoId": "yt-1",
                           "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}}},
        })

        receipt = persist_publication_receipt(settings, "snapshot-1")

        self.assertEqual(settings.youtube_publication_snapshots["snapshot-1"], snapshot)
        self.assertEqual(settings.youtube_publication_receipts["snapshot-1"]["youtubeVideoId"], "yt-1")
        self.assertEqual(receipt["finalStatus"], "DONE")

    def test_restart_reconciliation_never_reuploads_unknown_interrupted_transport(self):
        """An interrupted upload without a returned ID requires reconciliation, not a blind second insert."""
        settings = Settings(youtube_publication_executions={
            "snapshot-interrupted": {"snapshotId": "snapshot-interrupted", "overallStatus": "UPLOADING", "youtubeVideoId": None,
                                     "activeLease": {"workerId": "crashed-worker"}, "steps": {"VIDEO_UPLOAD": {"status": "RUNNING", "attempts": 1}}},
            "snapshot-uploaded": {"snapshotId": "snapshot-uploaded", "overallStatus": "UPLOADING", "youtubeVideoId": "yt-2",
                                  "activeLease": {"workerId": "crashed-worker"}, "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS", "attempts": 1}, "TITLE": {"status": "FAILED"}}},
        })

        result = reconcile_publication_executions(settings)

        interrupted = settings.youtube_publication_executions["snapshot-interrupted"]
        uploaded = settings.youtube_publication_executions["snapshot-uploaded"]
        self.assertEqual(result["interrupted"], 1)
        self.assertEqual(interrupted["overallStatus"], "USER_ACTION_REQUIRED")
        self.assertEqual(interrupted["steps"]["VIDEO_UPLOAD"]["status"], "USER_ACTION_REQUIRED")
        self.assertEqual(uploaded["youtubeVideoId"], "yt-2")
        self.assertEqual(uploaded["overallStatus"], "PARTIAL")
        self.assertIsNone(uploaded["activeLease"])

    def test_upload_attempt_persists_lease_before_transport_and_known_id_exits_upload_queue(self):
        """The transport handoff must be crash-safe before network I/O and immutable after YouTube answers."""
        settings = Settings(youtube_publication_executions={
            "snapshot-1": {"snapshotId": "snapshot-1", "overallStatus": "READY", "youtubeVideoId": None,
                           "activeLease": None, "steps": {"VIDEO_UPLOAD": {"status": "PENDING", "attempts": 0}}},
        })

        begin_upload_attempt(settings, "snapshot-1", "worker-a")
        complete_upload_attempt(settings, "snapshot-1", "worker-a", {"videoId": "yt-new", "videoUrl": "https://youtu.be/yt-new"})

        execution = settings.youtube_publication_executions["snapshot-1"]
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(execution["youtubeVideoId"], "yt-new")
        self.assertEqual(execution["overallStatus"], "PROCESSING")
        self.assertIsNone(execution["activeLease"])
        self.assertEqual(next_upload_candidates(settings), [])

    def test_downstream_retryable_failure_is_classified_without_resetting_video_upload(self):
        """A temporary thumbnail error remains a granular retry and cannot reopen an uploaded MP4."""
        settings = Settings(youtube_publication_executions={
            "snapshot-1": {"snapshotId": "snapshot-1", "youtubeVideoId": "yt-known", "overallStatus": "FORMATTING",
                           "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}, "THUMBNAIL": {"status": "RUNNING", "attempts": 1}}},
        })

        category = classify_publication_error(RuntimeError("HTTP 503 temporarily unavailable"))
        fail_publication_stage(settings, "snapshot-1", "THUMBNAIL", category, "Поставщик временно недоступен")

        execution = settings.youtube_publication_executions["snapshot-1"]
        self.assertEqual(category, "RETRYABLE")
        self.assertEqual(execution["youtubeVideoId"], "yt-known")
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(execution["steps"]["THUMBNAIL"]["status"], "FAILED")
        self.assertEqual(execution["overallStatus"], "PARTIAL")

    def test_completed_thumbnail_stage_preserves_uploaded_video_and_is_not_retryable_normally(self):
        """A confirmed thumbnail action is downstream-only and leaves the MP4 transport immutable."""
        settings = Settings(youtube_publication_executions={
            "snapshot-1": {"snapshotId": "snapshot-1", "youtubeVideoId": "yt-known", "overallStatus": "FORMATTING",
                           "activeLease": {"workerId": "thumbnail-worker"},
                           "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}, "THUMBNAIL": {"status": "RUNNING", "attempts": 1}}},
        })

        complete_publication_stage(settings, "snapshot-1", "thumbnail-worker", "THUMBNAIL", {"path": "D:/cover.png"})

        execution = settings.youtube_publication_executions["snapshot-1"]
        self.assertEqual(execution["youtubeVideoId"], "yt-known")
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(execution["steps"]["THUMBNAIL"]["status"], "SUCCESS")
        with self.assertRaisesRegex(ValueError, "Готовый этап"):
            retry_publication_stage(settings, "snapshot-1", "THUMBNAIL")


class PublicationV2BridgeTests(unittest.TestCase):
    def test_v2_upload_persists_running_state_then_keeps_returned_youtube_id_before_downstream_work(self):
        """Bridge upload uses a frozen snapshot and cannot lose the YouTube ID to a later thumbnail failure."""
        with TemporaryDirectory() as directory:
            video = Path(directory) / "episode.mp4"
            video.write_bytes(b"mp4")
            settings = Settings(youtube_oauth_tokens={"channel-a": '{"token":"safe"}'}, youtube_publication_snapshots={
                "snapshot-1": {"id": "snapshot-1", "channelId": "channel-a", "videoPath": str(video),
                               "metadata": {"title": "Выпуск", "description": "Описание", "tags": ["тег"]},
                               "privacy": "private", "publishMode": "publish_now"},
            }, youtube_publication_executions={
                "snapshot-1": {"snapshotId": "snapshot-1", "overallStatus": "READY", "youtubeVideoId": None,
                               "activeLease": None, "steps": {"VIDEO_UPLOAD": {"status": "PENDING", "attempts": 0}}},
            })
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings") as save, \
                 patch.object(bridge, "snapshot", return_value={"publication": {}}), \
                 patch.object(bridge, "upload_private_video", return_value=({"videoId": "yt-new", "videoUrl": "https://youtu.be/yt-new", "privacyStatus": "private"}, {"token": "refreshed"})) as upload:
                result = bridge.upload_publication_v2_snapshots({"snapshotIds": ["snapshot-1"]})

        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertGreaterEqual(save.call_count, 2)
        self.assertEqual(settings.youtube_publication_executions["snapshot-1"]["youtubeVideoId"], "yt-new")
        self.assertEqual(settings.youtube_publication_executions["snapshot-1"]["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(upload.call_args.kwargs["thumbnail_path"], "")

    def test_v2_upload_uses_frozen_seo_title_and_keeps_source_title_as_identity_metadata(self):
        with TemporaryDirectory() as directory:
            video = Path(directory) / "episode.mp4"
            video.write_bytes(b"mp4")
            settings = Settings(
                youtube_oauth_tokens={"channel-a": '{"token":"safe"}'},
                youtube_publication_snapshots={
                    "snapshot-1": {
                        "id": "snapshot-1",
                        "channelId": "channel-a",
                        "videoPath": str(video),
                        "metadata": {
                            "title": "Исходное название сценария",
                            "seoTitle": "SEO-заголовок для YouTube",
                            "description": "SEO-описание",
                            "tags": ["тег"],
                            "hashtags": ["#новости"],
                        },
                        "privacy": "private",
                        "publishMode": "publish_now",
                    },
                },
                youtube_publication_executions={
                    "snapshot-1": {
                        "snapshotId": "snapshot-1",
                        "overallStatus": "READY",
                        "youtubeVideoId": None,
                        "activeLease": None,
                        "steps": {"VIDEO_UPLOAD": {"status": "PENDING", "attempts": 0}},
                    },
                },
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={"publication": {}}), \
                 patch.object(
                     bridge,
                     "upload_private_video",
                     return_value=(
                         {"videoId": "yt-new", "videoUrl": "https://youtu.be/yt-new", "privacyStatus": "private"},
                         {"token": "refreshed"},
                     ),
                 ) as upload:
                bridge.upload_publication_v2_snapshots({"snapshotIds": ["snapshot-1"]})

        body = upload.call_args.kwargs["body"]
        self.assertEqual(body["snippet"]["title"], "SEO-заголовок для YouTube")
        self.assertEqual(
            settings.youtube_publication_snapshots["snapshot-1"]["metadata"]["title"],
            "Исходное название сценария",
        )


    def test_v2_upload_queue_drains_requested_batch_without_exceeding_configured_transport_workers(self):
        """Finished transports free their slot so the next requested snapshot starts in the same queue run."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            one, two = root / "one.mp4", root / "two.mp4"
            one.write_bytes(b"mp4")
            two.write_bytes(b"mp4")
            snapshots = {
                f"snapshot-{index}": {"id": f"snapshot-{index}", "channelId": "channel-a", "videoPath": str(path),
                                      "metadata": {"title": f"Выпуск {index}", "description": "Описание", "tags": []}, "privacy": "private", "publishMode": "publish_now"}
                for index, path in ((1, one), (2, two))
            }
            executions = {
                snapshot_id: {"snapshotId": snapshot_id, "overallStatus": "READY", "youtubeVideoId": None,
                              "activeLease": None, "steps": {"VIDEO_UPLOAD": {"status": "PENDING", "attempts": 0}}}
                for snapshot_id in snapshots
            }
            settings = Settings(youtube_publication_upload_concurrency=1, youtube_oauth_tokens={"channel-a": '{"token":"safe"}'},
                                youtube_publication_snapshots=snapshots, youtube_publication_executions=executions)
            responses = iter([({"videoId": "yt-1", "videoUrl": "https://youtu.be/yt-1", "privacyStatus": "private"}, {"token": "one"}),
                              ({"videoId": "yt-2", "videoUrl": "https://youtu.be/yt-2", "privacyStatus": "private"}, {"token": "two"})])
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={"publication": {}}), \
                 patch.object(bridge, "upload_private_video", side_effect=lambda *args, **kwargs: next(responses)) as upload:
                result = bridge.upload_publication_v2_snapshots({"snapshotIds": ["snapshot-1", "snapshot-2"]})

        self.assertEqual(result["operationResult"]["count"], 2)
        self.assertEqual(upload.call_count, 2)
        self.assertEqual({settings.youtube_publication_executions["snapshot-1"]["youtubeVideoId"], settings.youtube_publication_executions["snapshot-2"]["youtubeVideoId"]}, {"yt-1", "yt-2"})

    def test_v2_reconciliation_uses_youtube_readback_without_reopening_upload(self):
        """API verification advances existing video stages and does not call the upload transport."""
        settings = Settings(youtube_oauth_tokens={"channel-a": '{"token":"safe"}'}, youtube_publication_snapshots={
            "snapshot-1": {"id": "snapshot-1", "channelId": "channel-a", "metadata": {"title": "Выпуск", "description": "Описание", "tags": []}, "publishMode": "publish_now"},
        }, youtube_publication_executions={
            "snapshot-1": {"snapshotId": "snapshot-1", "youtubeVideoId": "yt-1", "overallStatus": "PROCESSING", "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}}},
        })
        response = {"snippet": {"title": "Выпуск", "description": "Описание", "tags": []}, "processingDetails": {"processingStatus": "succeeded"}, "status": {"privacyStatus": "private"}}
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {}}), \
             patch.object(bridge, "fetch_youtube_video_state", return_value=(response, {"token": "refreshed"})) as fetch:
            result = bridge.reconcile_publication_v2_youtube({"snapshotIds": ["snapshot-1"]})

        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(settings.youtube_publication_executions["snapshot-1"]["youtubeVideoId"], "yt-1")
        self.assertEqual(settings.youtube_publication_executions["snapshot-1"]["steps"]["TITLE"]["status"], "SUCCESS")

    def test_v2_studio_waits_for_processing_before_ads_editor_steps(self):
        settings = Settings(
            analytics_channels=[{"profile_id": "channel-a", "channel_id": "UC-a", "name": "Канал A"}],
            youtube_publication_snapshots={
                "snapshot-1": {
                    "id": "snapshot-1", "productionItemId": "pi-1", "channelId": "channel-a",
                    "durationSeconds": 600, "monetized": True,
                    "adPolicy": {"enabled": True, "manualIntervalSeconds": 39, "automaticSlotsEnabled": True},
                    "metadata": {"title": "Выпуск", "description": "Описание", "tags": []},
                    "publishMode": "publish_now",
                },
            },
            youtube_publication_executions={
                "snapshot-1": {
                    "snapshotId": "snapshot-1", "productionItemId": "pi-1", "youtubeVideoId": "yt-new",
                    "youtubeVideoUrl": "https://youtu.be/yt-new", "overallStatus": "PROCESSING",
                    "activeLease": None,
                    "steps": {
                        "VIDEO_UPLOAD": {"status": "SUCCESS"},
                        "YOUTUBE_PROCESSING": {"status": "RUNNING"},
                        "ADS": {"status": "PENDING"},
                    },
                },
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {}}), \
             patch.object(bridge, "_youtube_channel_profile_dir", return_value=Path("C:/profiles/channel-a")), \
             patch.object(bridge, "execute_studio_task") as execute:
            result = bridge.run_publication_v2_studio({"snapshotIds": ["snapshot-1"], "steps": ["ads"]})

        self.assertEqual(result["operationResult"]["count"], 0)
        self.assertEqual(result["operationResult"]["skipped"], 1)
        self.assertEqual(settings.youtube_publication_executions["snapshot-1"]["steps"]["ADS"]["status"], "PENDING")
        execute.assert_not_called()

    def test_v2_studio_waits_for_processing_before_community_post(self):
        settings = Settings(
            analytics_channels=[{"profile_id": "channel-a", "channel_id": "UC-a", "name": "Канал A"}],
            youtube_publication_snapshots={
                "snapshot-1": {
                    "id": "snapshot-1",
                    "productionItemId": "pi-1",
                    "channelId": "channel-a",
                    "durationSeconds": 300,
                    "monetized": False,
                    "automation": {"post": True},
                    "metadata": {"title": "Выпуск", "description": "Описание", "tags": []},
                    "publishMode": "publish_now",
                },
            },
            youtube_publication_executions={
                "snapshot-1": {
                    "snapshotId": "snapshot-1",
                    "productionItemId": "pi-1",
                    "youtubeVideoId": "yt-new",
                    "youtubeVideoUrl": "https://youtu.be/yt-new",
                    "overallStatus": "PROCESSING",
                    "activeLease": None,
                    "steps": {
                        "VIDEO_UPLOAD": {"status": "SUCCESS"},
                        "YOUTUBE_PROCESSING": {"status": "RUNNING"},
                        "POST": {"status": "PENDING"},
                    },
                },
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {}}), \
             patch.object(bridge, "_youtube_channel_profile_dir", return_value=Path("C:/profiles/channel-a")), \
             patch.object(bridge, "execute_studio_task") as execute:
            result = bridge.run_publication_v2_studio({
                "snapshotIds": ["snapshot-1"],
                "steps": ["post"],
            })

        self.assertEqual(result["operationResult"]["count"], 0)
        self.assertEqual(result["operationResult"]["skipped"], 1)
        self.assertEqual(
            settings.youtube_publication_executions["snapshot-1"]["steps"]["POST"]["status"],
            "PENDING",
        )
        execute.assert_not_called()


    def test_v2_studio_honors_frozen_non_ads_automation_policy(self):
        """Confirmed channel policy disables cards/end-screen without changing completed upload."""
        settings = Settings(
            analytics_channels=[{"profile_id": "channel-a", "channel_id": "UC-a", "name": "Канал A"}],
            youtube_publication_snapshots={
                "snapshot-1": {
                    "id": "snapshot-1", "productionItemId": "pi-1", "channelId": "channel-a",
                    "durationSeconds": 600, "monetized": True,
                    "automation": {"post": True, "cards": False, "endScreen": False, "ads": True},
                    "adPolicy": {"enabled": True, "manualIntervalSeconds": 39, "automaticSlotsEnabled": True},
                    "metadata": {"title": "Выпуск", "description": "Описание", "tags": ["тег"]},
                    "publishMode": "publish_now",
                },
            },
            youtube_publication_executions={
                "snapshot-1": {
                    "snapshotId": "snapshot-1", "productionItemId": "pi-1",
                    "youtubeVideoId": "yt-existing", "overallStatus": "FORMATTING", "activeLease": None,
                    "steps": {
                        "VIDEO_UPLOAD": {"status": "SUCCESS"},
                        "YOUTUBE_PROCESSING": {"status": "SUCCESS"},
                        "CARDS": {"status": "PENDING"},
                        "END_SCREEN": {"status": "PENDING"},
                    },
                },
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {}}), \
             patch.object(bridge, "execute_studio_task") as execute:
            result = bridge.run_publication_v2_studio({
                "snapshotIds": ["snapshot-1"],
                "steps": ["cards", "end-screen"],
            })

        execution = settings.youtube_publication_executions["snapshot-1"]
        self.assertEqual(result["operationResult"]["failed"], 0)
        self.assertEqual(result["operationResult"]["skipped"], 2)
        self.assertEqual(execution["steps"]["CARDS"]["status"], "NOT_REQUIRED")
        self.assertEqual(execution["steps"]["END_SCREEN"]["status"], "NOT_REQUIRED")
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        execute.assert_not_called()

    def test_v2_studio_partial_ads_preserves_auto_mode_and_never_reuploads_mp4(self):
        """AUTO success plus incomplete manual slots stays retryable without reopening VIDEO_UPLOAD."""
        settings = Settings(
            analytics_channels=[{"profile_id": "channel-a", "channel_id": "UC-a", "name": "Канал A"}],
            youtube_publication_items={
                "pi-1": {"productionItemId": "pi-1", "durationSeconds": 600},
            },
            youtube_publication_snapshots={
                "snapshot-1": {
                    "id": "snapshot-1", "productionItemId": "pi-1", "channelId": "channel-a",
                    "durationSeconds": 600, "monetized": True,
                    "adPolicy": {"enabled": True, "manualIntervalSeconds": 39, "automaticSlotsEnabled": True},
                    "automation": {"ads": True},
                    "metadata": {"title": "Выпуск", "description": "Описание", "tags": ["тег"]},
                    "publishMode": "publish_now",
                },
            },
            youtube_publication_executions={
                "snapshot-1": {
                    "snapshotId": "snapshot-1", "productionItemId": "pi-1",
                    "youtubeVideoId": "yt-existing", "youtubeVideoUrl": "https://youtu.be/yt-existing",
                    "overallStatus": "FORMATTING", "activeLease": None,
                    "steps": {
                        "VIDEO_UPLOAD": {"status": "SUCCESS"},
                        "YOUTUBE_PROCESSING": {"status": "SUCCESS"},
                        "ADS": {"status": "PENDING"},
                    },
                },
            },
        )

        def partial_ads(task, **_kwargs):
            task["_studioResults"] = {
                "ads": {
                    "mode": "AUTO_ONLY",
                    "automatic": True,
                    "manual": False,
                    "manualMidrollApplicable": True,
                    "manualSlots": [39, 78, 117],
                    "confirmedManualSlots": [39],
                },
            }
            return ["ads"]

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {}}), \
             patch.object(bridge, "_youtube_channel_profile_dir", return_value=Path("C:/profiles/channel-a")), \
             patch.object(bridge, "execute_studio_task", side_effect=partial_ads):
            result = bridge.run_publication_v2_studio({"snapshotIds": ["snapshot-1"], "steps": ["ads"]})

        execution = settings.youtube_publication_executions["snapshot-1"]
        self.assertEqual(result["operationResult"]["failed"], 1)
        self.assertEqual(execution["youtubeVideoId"], "yt-existing")
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(execution["steps"]["ADS"]["status"], "FAILED")
        self.assertEqual(execution["steps"]["ADS"]["providerResult"]["mode"], "AUTO_ONLY")
        self.assertEqual(execution["steps"]["ADS"]["providerResult"]["confirmedManualSlotsSeconds"], [39])

    def test_v2_studio_uses_prior_public_v2_video_for_cards_without_reupload(self):
        settings = Settings(
            analytics_channels=[{"profile_id": "channel-a", "channel_id": "UC-a", "name": "Канал A"}],
            youtube_publication_snapshots={
                "snapshot-old": {
                    "id": "snapshot-old", "productionItemId": "pi-old", "channelId": "channel-a",
                    "durationSeconds": 500, "metadata": {"title": "Старый"}, "publishMode": "publish_now",
                },
                "snapshot-new": {
                    "id": "snapshot-new", "productionItemId": "pi-new", "channelId": "channel-a",
                    "durationSeconds": 600, "metadata": {"title": "Новый", "description": "Описание"},
                    "publishMode": "publish_now",
                },
            },
            youtube_publication_executions={
                "snapshot-old": {
                    "snapshotId": "snapshot-old", "productionItemId": "pi-old", "youtubeVideoId": "yt-old",
                    "youtubePrivacyStatus": "public", "actualPublishedAt": "2026-09-21T10:00:00+00:00",
                    "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}},
                },
                "snapshot-new": {
                    "snapshotId": "snapshot-new", "productionItemId": "pi-new", "youtubeVideoId": "yt-new",
                    "youtubeVideoUrl": "https://youtu.be/yt-new", "overallStatus": "FORMATTING",
                    "activeLease": None,
                    "steps": {
                        "VIDEO_UPLOAD": {"status": "SUCCESS"},
                        "YOUTUBE_PROCESSING": {"status": "SUCCESS"},
                        "CARDS": {"status": "PENDING"},
                    },
                },
            },
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"publication": {}}), \
             patch.object(bridge, "_youtube_channel_profile_dir", return_value=Path("C:/profiles/channel-a")), \
             patch.object(bridge, "execute_studio_task", return_value=["cards"]) as execute:
            result = bridge.run_publication_v2_studio({"snapshotIds": ["snapshot-new"], "steps": ["cards"]})

        self.assertEqual(result["operationResult"]["count"], 1)
        task = execute.call_args.args[0]
        self.assertEqual(task["plan"]["cards"][0]["videoId"], "yt-old")
        execution = settings.youtube_publication_executions["snapshot-new"]
        self.assertEqual(execution["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(execution["steps"]["CARDS"]["status"], "SUCCESS")

    def test_v2_thumbnail_command_runs_only_for_known_video_without_reopening_upload(self):
        """A thumbnail retry calls the independent thumbnail API and leaves VIDEO_UPLOAD successful."""
        with TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.png"
            cover.write_bytes(b"png")
            settings = Settings(youtube_oauth_tokens={"channel-a": '{"token":"safe"}'}, youtube_publication_snapshots={
                "snapshot-1": {"id": "snapshot-1", "channelId": "channel-a", "thumbnailPath": str(cover)},
            }, youtube_publication_executions={
                "snapshot-1": {"snapshotId": "snapshot-1", "youtubeVideoId": "yt-1", "overallStatus": "FORMATTING", "activeLease": None,
                               "steps": {"VIDEO_UPLOAD": {"status": "SUCCESS"}, "THUMBNAIL": {"status": "PENDING"}}},
            })
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={"publication": {}}), \
                 patch.object(bridge, "set_youtube_thumbnail", return_value={"credentials": {"token": "refreshed"}, "response": {}}) as set_thumbnail:
                result = bridge.run_publication_v2_thumbnails({"snapshotIds": ["snapshot-1"]})

        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(set_thumbnail.call_args.args[1], "yt-1")
        self.assertEqual(settings.youtube_publication_executions["snapshot-1"]["steps"]["VIDEO_UPLOAD"]["status"], "SUCCESS")
        self.assertEqual(settings.youtube_publication_executions["snapshot-1"]["steps"]["THUMBNAIL"]["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
