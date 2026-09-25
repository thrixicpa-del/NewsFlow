import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_cards_enter_the_new_editor_before_looking_for_the_section(self):
        """The welcome handoff blocks Cards just like it blocks end screens."""
        from scriptor.youtube_studio import _open_editor_section

        class TransitionButton:
            def __init__(self, page):
                self.page = page

            def is_visible(self, timeout):
                return True

            def click(self, timeout, force=False):
                self.page.in_new_editor = True

        class Body:
            def __init__(self, page):
                self.page = page

            def inner_text(self, timeout):
                return "Конечные заставки Подсказки" if self.page.in_new_editor else "Перейти к редактору"

            def evaluate(self, _script, _label):
                return self.page.in_new_editor

        class Page:
            def __init__(self):
                self.in_new_editor = False
                self.button = TransitionButton(self)

            def locator(self, _selector):
                return Body(self)

            def get_by_label(self, _label, exact):
                if not exact:
                    raise AssertionError("The Studio handoff must use its exact accessible label")
                return self.button

            def wait_for_timeout(self, _milliseconds):
                return None

        page = Page()
        try:
            _open_editor_section(page, "cards")
        except StudioAutomationError as exc:
            self.fail(f"Cards must pass the Studio welcome handoff before opening their section: {exc}")
        self.assertTrue(page.in_new_editor)

    def test_cards_accept_the_new_editor_when_the_welcome_text_is_retained(self):
        """Studio retains the welcome DOM after it has revealed editor sections."""
        from scriptor.youtube_studio import _open_editor_section

        class Body:
            def inner_text(self, timeout):
                return "Перейти к редактору Конечные заставки Подсказки"

            def evaluate(self, _script, _label):
                return True

        class Page:
            def locator(self, _selector):
                return Body()

            def wait_for_timeout(self, _milliseconds):
                raise AssertionError("The retained welcome text must not trigger a wait loop")

        try:
            _open_editor_section(Page(), "cards")
        except Exception as exc:
            self.fail(f"The visible new-editor sections must win over retained welcome text: {exc}")

    def test_cards_wait_for_the_late_studio_welcome_handoff(self):
        """The Editor URL can render before either the welcome or its sections."""
        from scriptor.youtube_studio import _open_editor_section

        class TransitionButton:
            def __init__(self, page):
                self.page = page

            def is_visible(self, timeout):
                return True

            def click(self, timeout, force=False):
                self.page.step = 2

        class Body:
            def __init__(self, page):
                self.page = page

            def inner_text(self, timeout):
                return [
                    "Видеоредактор",
                    "Перейти к редактору",
                    "Конечные заставки Подсказки",
                ][self.page.step]

            def evaluate(self, _script, _label):
                return self.page.step == 2

        class Page:
            def __init__(self):
                self.step = 0
                self.button = TransitionButton(self)

            def locator(self, _selector):
                return Body(self)

            def get_by_label(self, _label, exact):
                if not exact:
                    raise AssertionError("The handoff requires the exact Studio label")
                return self.button

            def wait_for_timeout(self, _milliseconds):
                if self.step == 0:
                    self.step = 1

        page = Page()
        try:
            _open_editor_section(page, "cards")
        except Exception as exc:
            self.fail(f"Cards must wait for the delayed Studio handoff: {exc}")
        self.assertEqual(page.step, 2)

    def test_editor_section_stops_for_identity_verification(self):
        """Automation must not click controls behind Studio's identity gate."""
        from scriptor.youtube_studio import _open_editor_section

        class Body:
            def inner_text(self, timeout):
                return "Подтверждение личности Чтобы продолжить, подтвердите личность"

            def evaluate(self, _script, _label):
                raise AssertionError("The section control must not be evaluated behind verification")

        class Page:
            def locator(self, _selector):
                return Body()

        try:
            _open_editor_section(Page(), "cards")
        except StudioAutomationError as exc:
            self.assertIn("подтвердите личность", str(exc).casefold())
        except Exception as exc:
            self.fail(f"Identity verification must be reported before touching editor controls: {exc}")
        else:
            self.fail("Identity verification must stop the Studio action")

    def test_identity_verification_opens_the_same_profile_at_the_editor(self):
        """A human verification must remain visible in the channel's Studio profile."""
        from scriptor.youtube_studio import open_studio_identity_verification

        profile = Path(r"D:\\disposable\\youtube-profile")
        with patch("scriptor.youtube_studio.subprocess.Popen") as popen:
            open_studio_identity_verification(profile, "4aNnkPSxX_o")

        command = popen.call_args.args[0]
        self.assertIn(f"--user-data-dir={profile}", command)
        self.assertIn("--new-window", command)
        self.assertEqual(command[-1], "https://studio.youtube.com/video/4aNnkPSxX_o/editor")

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
