import unittest

from scriptor.youtube_studio import (_click_exact_visible_button, planned_studio_actions, studio_details_url, studio_editor_url,
                                     studio_shell_loaded, studio_control_labels, end_screen_requires_editor_entry,
                                     studio_transition_label)


class YouTubeStudioActionsTests(unittest.TestCase):
    def test_pending_task_has_ads_linked_post_cards_and_end_screen_actions(self):
        actions = planned_studio_actions({
            "ads": {"status": "pending"},
            "post": {"status": "pending"},
            "cards": {"status": "pending"},
            "endScreen": {"status": "pending"},
            "postDraft": {"text": "Описание", "videoUrl": "https://www.youtube.com/watch?v=current"},
            "plan": {
                "ads": {"mode": "AUTO+MANUAL_39S", "monetizationEnabled": True, "midRollEligible": True,
                        "automaticSlotsEnabled": True, "manualSlotsSeconds": [39, 78]},
                "cards": [{"videoId": "previous", "atSeconds": 210}],
                "endScreen": {"startSeconds": 580, "items": [{"kind": "subscribe"}]},
            },
        })

        self.assertEqual([item["kind"] for item in actions], ["ads", "post", "cards", "end-screen"])
        self.assertEqual(actions[0]["mode"], "AUTO+MANUAL_39S")
        self.assertEqual(actions[0]["manualSlotsSeconds"], [39, 78])
        self.assertEqual(actions[0]["videoUrl"], "https://www.youtube.com/watch?v=current")
        self.assertEqual(actions[1]["cards"][0]["atSeconds"], 210)
        self.assertEqual(actions[2]["startSeconds"], 580)

    def test_terminal_or_skipped_steps_are_not_repeated(self):
        self.assertEqual(planned_studio_actions({
            "post": {"status": "scheduled"},
            "cards": {"status": "done"},
            "endScreen": {"status": "skipped"},
            "postDraft": {}, "plan": {},
        }), [])

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
