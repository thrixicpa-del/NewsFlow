import unittest

from scriptor.youtube_studio import (StudioAutomationError, _click_exact_visible_button, _open_video_editor, planned_studio_actions, studio_details_url, studio_editor_url,
                                     studio_shell_loaded, studio_control_labels, end_screen_requires_editor_entry,
                                     studio_transition_label)


class YouTubeStudioActionsTests(unittest.TestCase):
    def test_pending_task_has_linked_post_cards_and_end_screen_actions(self):
        actions = planned_studio_actions({
            "post": {"status": "pending"},
            "cards": {"status": "pending"},
            "endScreen": {"status": "pending"},
            "postDraft": {"text": "Описание", "videoUrl": "https://www.youtube.com/watch?v=current"},
            "plan": {
                "cards": [{"videoId": "previous", "atSeconds": 210}],
                "endScreen": {"startSeconds": 580, "items": [{"kind": "subscribe"}]},
            },
        })

        self.assertEqual([item["kind"] for item in actions], ["post", "cards", "end-screen"])
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

    def test_editor_navigation_uses_actionable_menuitem_not_first_text_container(self):
        class TextNode:
            def is_visible(self, timeout):
                return True

            def click(self, timeout):
                return None

        class MenuItem:
            def __init__(self, page):
                self.page = page

            def is_visible(self, timeout):
                return True

            def click(self, timeout):
                self.page.url = "https://studio.youtube.com/video/video-a/editor"

        class Body:
            def inner_text(self, timeout):
                return "Сведения о видео Редактор"

        class Locator:
            def __init__(self, body):
                self.body = body

            @property
            def first(self):
                return self.body

            def is_visible(self, timeout):
                return self.body.is_visible(timeout)

            def click(self, timeout):
                return self.body.click(timeout)

            def inner_text(self, timeout):
                return self.body.inner_text(timeout)

        class Page:
            def __init__(self):
                self.url = ""
                self.text_node = TextNode()
                self.menuitem = MenuItem(self)
                self.menuitem_request = None

            def goto(self, url, **_kwargs):
                self.url = url

            def locator(self, _selector):
                return Locator(Body())

            def get_by_text(self, _label):
                return Locator(self.text_node)

            def get_by_role(self, role, name, exact):
                self.menuitem_request = (role, name, exact)
                return Locator(self.menuitem)

            def wait_for_timeout(self, _milliseconds):
                return None

        page = Page()
        _open_video_editor(page, "video-a")
        self.assertTrue(page.url.endswith("/editor"))
        self.assertEqual(page.menuitem_request, ("menuitem", "Редактор", True))

    def test_editor_navigation_reports_studio_access_denied_before_clicking(self):
        class DisabledMenuItem:
            def is_visible(self, timeout):
                return True

            def click(self, timeout):
                return None

        class Body:
            def inner_text(self, timeout):
                return "Сведения о видео Редактор У вас нет доступа к этому разделу"

        class Locator:
            def __init__(self, body):
                self.body = body

            @property
            def first(self):
                return self.body

            def is_visible(self, timeout):
                return self.body.is_visible(timeout)

            def click(self, timeout):
                return self.body.click(timeout)

            def inner_text(self, timeout):
                return self.body.inner_text(timeout)

        class Page:
            def __init__(self):
                self.url = ""

            def goto(self, url, **_kwargs):
                self.url = url

            def locator(self, _selector):
                return Locator(Body())

            def get_by_role(self, *_args, **_kwargs):
                return Locator(DisabledMenuItem())

            def wait_for_timeout(self, _milliseconds):
                return None

        with self.assertRaises(StudioAutomationError) as raised:
            _open_video_editor(Page(), "video-a")
        self.assertIn("нет доступа", str(raised.exception).casefold())

    def test_editor_navigation_reports_access_denied_after_studio_redirect(self):
        class MenuItem:
            def __init__(self, page):
                self.page = page

            def is_visible(self, timeout):
                return True

            def click(self, timeout):
                self.page.url = "https://studio.youtube.com/channel/channel-a/videos"
                self.page.text = "У вас нет доступа к этому разделу"

        class Body:
            def __init__(self, page):
                self.page = page

            def inner_text(self, timeout):
                return self.page.text

        class Page:
            def __init__(self):
                self.url = ""
                self.text = "Сведения о видео Редактор"

            def goto(self, url, **_kwargs):
                self.url = url

            def locator(self, _selector):
                return Body(self)

            def get_by_role(self, *_args, **_kwargs):
                return MenuItem(self)

            def wait_for_timeout(self, _milliseconds):
                return None

        with self.assertRaises(StudioAutomationError) as raised:
            _open_video_editor(Page(), "video-a")
        self.assertIn("нет доступа", str(raised.exception).casefold())
