import unittest
from unittest.mock import patch

from scriptor.youtube_studio import (
    StudioAutomationError,
    StudioIdentityVerificationRequired,
    _click_exact_visible_button,
    _open_video_editor,
    _save_editor_changes,
    _verify_cards_saved,
    end_screen_requires_editor_entry,
    identity_verification_required,
    planned_studio_actions,
    studio_control_labels,
    studio_details_url,
    studio_editor_url,
    studio_monetization_url,
    studio_shell_loaded,
    studio_transition_label,
)


class YouTubeStudioActionsTests(unittest.TestCase):
    def test_pending_task_has_ads_linked_post_cards_and_end_screen_actions(self):
        actions = planned_studio_actions({
            "ads": {"status": "pending"},
            "post": {"status": "pending"},
            "cards": {"status": "pending"},
            "endScreen": {"status": "pending"},
            "postDraft": {"text": "Описание", "videoUrl": "https://www.youtube.com/watch?v=current"},
            "plan": {
                "ads": {"mode": "AUTO+MANUAL", "monetizationEnabled": True, "midRollEligible": True,
                        "automaticSlotsEnabled": True, "manualSlotsSeconds": [39, 78]},
                "cards": [{"videoId": "previous", "atSeconds": 210}],
                "endScreen": {"startSeconds": 580, "items": [{"kind": "subscribe"}]},
            },
        })

        self.assertEqual([item["kind"] for item in actions], ["ads", "post", "cards", "end-screen"])
        self.assertEqual(actions[0]["mode"], "AUTO+MANUAL")
        self.assertEqual(actions[0]["manualSlotsSeconds"], [39, 78])
        self.assertEqual(actions[1]["videoUrl"], "https://www.youtube.com/watch?v=current")
        self.assertEqual(actions[2]["cards"][0]["atSeconds"], 210)
        self.assertEqual(actions[3]["startSeconds"], 580)

    def test_pending_monetization_action_is_planned_with_manual_slots(self):
        actions = planned_studio_actions({
            "post": {"status": "skipped"},
            "ads": {"status": "pending"},
            "cards": {"status": "skipped"},
            "endScreen": {"status": "skipped"},
            "postDraft": {},
            "plan": {"ads": {
                "enabled": True, "monetizationEnabled": True,
                "automaticSlotsEnabled": True, "midRollEligible": True,
                "mode": "AUTO+MANUAL", "manualSlotsSeconds": [39, 78],
            }},
        })

        self.assertEqual([item["kind"] for item in actions], ["ads"])
        self.assertEqual(actions[0]["manualSlotsSeconds"], [39, 78])

    def test_terminal_or_skipped_steps_are_not_repeated(self):
        self.assertEqual(planned_studio_actions({
            "post": {"status": "scheduled"},
            "cards": {"status": "done"},
            "endScreen": {"status": "skipped"},
            "postDraft": {}, "plan": {},
        }), [])

    def test_monetization_uses_the_exact_uploaded_video_route(self):
        self.assertEqual(
            studio_monetization_url("video-a"),
            "https://studio.youtube.com/video/video-a/monetization",
        )

    def test_cards_and_end_screen_use_the_exact_video_editor_url(self):
        self.assertEqual(
            studio_editor_url("video-a"),
            "https://studio.youtube.com/video/video-a/editor",
        )
        self.assertEqual(
            studio_details_url("video-a"),
            "https://studio.youtube.com/video/video-a/edit",
        )

    def test_studio_shell_requires_real_visible_text_not_an_empty_document(self):
        self.assertFalse(studio_shell_loaded(""))
        self.assertFalse(studio_shell_loaded("   "))
        self.assertTrue(studio_shell_loaded("Контент канала Редактор Карточки"))

    def test_russian_studio_controls_use_current_editor_names(self):
        self.assertIn("подсказ", studio_control_labels("cards").casefold())
        self.assertIn("конечн", studio_control_labels("end-screen").casefold())

    def test_legacy_end_screen_panel_requires_transition_to_editor(self):
        self.assertTrue(end_screen_requires_editor_entry("Все функции теперь собраны в одном разделе. Перейти к редактору"))
        self.assertFalse(end_screen_requires_editor_entry("Добавить элемент Подписаться"))
        self.assertEqual(studio_transition_label(), "Перейти к редактору")

    def test_new_editor_sections_are_opened_with_their_plus_control(self):
        self.assertEqual(studio_control_labels("cards"), "Подсказки")
        self.assertEqual(studio_control_labels("end-screen"), "Конечные заставки")

    def test_legacy_transition_uses_accessible_button_label(self):
        class Button:
            def __init__(self):
                self.clicked = False

            def is_visible(self, timeout):
                return True

            def click(self, timeout):
                self.clicked = True

        class Page:
            def __init__(self):
                self.label = ""
                self.button = Button()

            def get_by_label(self, label, exact):
                self.label = label
                return self.button

        page = Page()
        self.assertTrue(_click_exact_visible_button(page, "Перейти к редактору"))
        self.assertEqual(page.label, "Перейти к редактору")
        self.assertTrue(page.button.clicked)

    def test_editor_navigation_clicks_exact_current_video_editor_route(self):
        class Body:
            def __init__(self, page):
                self.page = page
                self.evaluate_args = []

            def inner_text(self, timeout):
                return "Сведения о видео Редактор Подсказки Конечные заставки"

            def evaluate(self, _script, video_id):
                self.evaluate_args.append(video_id)
                self.page.url = f"https://studio.youtube.com/video/{video_id}/editor"
                return True

        class Page:
            def __init__(self):
                self.url = ""
                self.body = Body(self)

            def goto(self, url, **_kwargs):
                self.url = url

            def locator(self, _selector):
                return self.body

            def wait_for_timeout(self, _milliseconds):
                return None

        page = Page()
        _open_video_editor(page, "video-a")

        self.assertEqual(page.body.evaluate_args, ["video-a"])
        self.assertEqual(page.url, "https://studio.youtube.com/video/video-a/editor")

    def test_editor_navigation_reports_access_denied_before_any_click(self):
        class Body:
            def __init__(self):
                self.evaluated = False

            def inner_text(self, timeout):
                return "Редактор У вас нет доступа к этому разделу"

            def evaluate(self, *_args):
                self.evaluated = True
                return True

        class Page:
            def __init__(self):
                self.url = ""
                self.body = Body()

            def goto(self, url, **_kwargs):
                self.url = url

            def locator(self, _selector):
                return self.body

        page = Page()
        with self.assertRaises(StudioAutomationError) as raised:
            _open_video_editor(page, "video-a")

        self.assertIn("нет доступа", str(raised.exception).casefold())
        self.assertFalse(page.body.evaluated)

    def test_editor_navigation_surfaces_identity_verification_as_distinct_error(self):
        class Body:
            def inner_text(self, timeout):
                return "Редактор Подтвердите личность"

        class Page:
            def __init__(self):
                self.url = ""

            def goto(self, url, **_kwargs):
                self.url = url

            def locator(self, _selector):
                return Body()

        self.assertTrue(identity_verification_required("Подтвердите личность"))
        with self.assertRaises(StudioIdentityVerificationRequired):
            _open_video_editor(Page(), "video-a")

    def test_save_waits_until_studio_consumes_enabled_button(self):
        class Button:
            def __init__(self):
                self.clicked = False

            @property
            def first(self):
                return self

            def is_visible(self, timeout):
                return True

            def is_enabled(self, timeout):
                return not self.clicked

            def click(self, timeout):
                self.clicked = True

        class Body:
            def inner_text(self, timeout):
                return "Редактор Подсказки Конечные заставки"

        class Page:
            def __init__(self):
                self.button = Button()
                self.role_request = None

            def locator(self, _selector):
                return Body()

            def get_by_role(self, role, name):
                self.role_request = (role, name)
                return self.button

            def get_by_label(self, label, exact):
                raise LookupError((label, exact))

            def wait_for_timeout(self, _milliseconds):
                return None

        page = Page()
        _save_editor_changes(page)

        self.assertTrue(page.button.clicked)
        self.assertEqual(page.role_request[0], "button")

    def test_card_save_verification_reopens_cards_and_requires_every_visible_title(self):
        class Body:
            def inner_text(self, timeout):
                return "Ролик один Ролик два"

        class Page:
            def locator(self, _selector):
                return Body()

            def wait_for_timeout(self, _milliseconds):
                return None

        cards = [
            {"videoTitle": "Ролик один"},
            {"videoTitle": "Ролик два"},
        ]
        with patch("scriptor.youtube_studio._open_editor_section") as open_section:
            _verify_cards_saved(Page(), cards)

        self.assertEqual(open_section.call_count, 1)
        self.assertEqual(open_section.call_args.args[1], "cards")

