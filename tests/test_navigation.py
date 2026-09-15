import unittest

from scriptor.navigation import ANTHROPIC_CONSOLE_URL, open_anthropic_console


class NavigationTests(unittest.TestCase):
    def test_opens_official_anthropic_console(self):
        opened = []
        self.assertTrue(open_anthropic_console(opened.append))
        self.assertEqual(opened, [ANTHROPIC_CONSOLE_URL])
        self.assertTrue(ANTHROPIC_CONSOLE_URL.startswith("https://console.anthropic.com"))


if __name__ == "__main__":
    unittest.main()
