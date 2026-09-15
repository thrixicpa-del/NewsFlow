import unittest

from scriptor.app import ScriptorApp


class SeoParsingTests(unittest.TestCase):
    def test_parses_json_inside_code_fence(self):
        result = ScriptorApp._parse_seo_json(
            '```json\n{"title":"Заголовок","description":"Описание","tags":["один","два"]}\n```'
        )
        self.assertEqual(result["title"], "Заголовок")
        self.assertEqual(result["tags"], ["один", "два"])


if __name__ == "__main__":
    unittest.main()
