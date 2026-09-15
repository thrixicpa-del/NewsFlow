import unittest

from scriptor.ui_helpers import clipboard_action


class ClipboardShortcutTests(unittest.TestCase):
    def test_physical_keycodes_work_independently_of_layout(self):
        self.assertEqual(clipboard_action("Cyrillic_es", 67), "copy")
        self.assertEqual(clipboard_action("Cyrillic_em", 86), "paste")
        self.assertEqual(clipboard_action("Cyrillic_che", 88), "cut")
        self.assertEqual(clipboard_action("Cyrillic_ef", 65), "select_all")

    def test_latin_keysyms_work(self):
        self.assertEqual(clipboard_action("c", 0), "copy")
        self.assertEqual(clipboard_action("V", 0), "paste")
        self.assertIsNone(clipboard_action("q", 81))


if __name__ == "__main__":
    unittest.main()
