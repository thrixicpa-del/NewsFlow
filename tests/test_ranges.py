import unittest

from scriptor.app import ScriptorApp


class NumberRangeTests(unittest.TestCase):
    def test_parses_single_numbers_and_ranges(self):
        self.assertEqual(ScriptorApp._parse_number_ranges("2, 5-8", 10), {2, 5, 6, 7, 8})

    def test_clamps_range_to_existing_items(self):
        self.assertEqual(ScriptorApp._parse_number_ranges("8-60", 12), {8, 9, 10, 11, 12})

    def test_rejects_invalid_range(self):
        with self.assertRaises(ValueError):
            ScriptorApp._parse_number_ranges("8-2", 20)

    def test_calculates_remaining_fastgen_usage(self):
        usage = {
            "account_limits": {"img_gen_per_hour_limit": 20},
            "current_usage": {"hourly_usage": {"image_generation": {"current_usage": 7}}},
        }
        self.assertEqual(
            ScriptorApp._usage_remaining(usage, "image_generation", "img_gen_per_hour_limit"),
            (7, 20, 13),
        )


if __name__ == "__main__":
    unittest.main()
