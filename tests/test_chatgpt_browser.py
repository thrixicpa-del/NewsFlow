import unittest


class ChatGPTBrowserUrlTests(unittest.TestCase):
    def test_accepts_an_https_chatgpt_project_url(self):
        from scriptor.chatgpt_browser import validate_chatgpt_project_url

        self.assertEqual(
            validate_chatgpt_project_url(
                "https://chatgpt.com/g/example-project"
            ),
            "https://chatgpt.com/g/example-project",
        )

    def test_rejects_a_non_chatgpt_url_before_browser_navigation(self):
        from scriptor.chatgpt_browser import (
            ChatGPTBrowserError,
            validate_chatgpt_project_url,
        )

        with self.assertRaises(ChatGPTBrowserError):
            validate_chatgpt_project_url("https://example.invalid/not-chatgpt")


if __name__ == "__main__":
    unittest.main()
