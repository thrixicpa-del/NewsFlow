import tempfile
import unittest
from pathlib import Path

from scriptor.core import (
    PromptRange,
    build_requests,
    parse_titles,
    read_text_file,
    safe_filename,
    write_exports,
)


class ParseTitlesTests(unittest.TestCase):
    def test_reads_utf8_and_cp1251_txt_files(self):
        with tempfile.TemporaryDirectory() as folder:
            utf8 = Path(folder, "utf8.txt")
            cp1251 = Path(folder, "cp1251.txt")
            utf8.write_bytes("Привет UTF-8".encode("utf-8-sig"))
            cp1251.write_bytes("Привет Windows".encode("cp1251"))
            self.assertEqual(read_text_file(utf8), "Привет UTF-8")
            self.assertEqual(read_text_file(cp1251), "Привет Windows")

    def test_rejects_non_txt_drop(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "prompt.docx")
            path.write_bytes(b"data")
            with self.assertRaisesRegex(ValueError, "TXT"):
                read_text_file(path)

    def test_each_non_empty_line_is_one_title(self):
        text = "Первый сценарий\nВторой сценарий\n\n\nТретий"
        self.assertEqual(
            parse_titles(text),
            ["Первый сценарий", "Второй сценарий", "Третий"],
        )

    def test_windows_line_endings_are_separate_titles(self):
        self.assertEqual(parse_titles("Тема 1\r\nТема 2\r\n\r\nТема 3"), ["Тема 1", "Тема 2", "Тема 3"])

    def test_supports_more_than_one_hundred_scenarios(self):
        text = "\n".join(f"Сценарий {i}" for i in range(250))
        self.assertEqual(len(parse_titles(text)), 250)


class PromptTests(unittest.TestCase):
    def test_ranges_are_one_based_and_inclusive(self):
        ranges = [PromptRange(1, 5, "коротко"), PromptRange(6, 10, "подробно")]
        requests = build_requests([f"S{i}" for i in range(1, 11)], "Шаблон: {title}", ranges)
        self.assertIn("коротко", requests[4].prompt)
        self.assertNotIn("подробно", requests[4].prompt)
        self.assertIn("подробно", requests[5].prompt)

    def test_single_explicit_character_target_gets_python_runtime_bounds(self):
        request = build_requests(
            ["Тема"],
            "Напиши сценарий на тему {title}. Нужно примерно 10 000 символов. Считай через Python.",
            [],
        )[0]

        self.assertEqual(request.target_chars, 10000)
        self.assertEqual(request.allowed_min, 9000)
        self.assertEqual(request.allowed_max, 11000)
        self.assertIn("около 10 000 символов", request.prompt)
        self.assertIn("от 9 000 до 11 000 символов", request.prompt)
        self.assertIn("пересчитает фактическое количество символов Python", request.prompt)

    def test_legacy_unit_before_character_range_is_still_recognized(self):
        request = build_requests(
            ["Тема"],
            "КОЛИЧЕСТВО СИМВОЛОВ: 10 000 - 15 000. Считать при помощи Python. Тема: {title}",
            [],
        )[0]

        self.assertEqual(
            (request.target_chars, request.allowed_min, request.allowed_max),
            (12500, 10000, 15000),
        )
        self.assertIn("от 10 000 до 15 000 символов", request.prompt)

    def test_structured_range_length_overrides_template_free_text_target(self):
        request = build_requests(
            ["Тема"],
            "Напиши сценарий на тему {title}. Нужно примерно 10 000 символов.",
            [PromptRange(1, 1, "", target_chars=5000)],
        )[0]

        self.assertEqual(request.target_chars, 5000)
        self.assertEqual(request.allowed_min, 4500)
        self.assertEqual(request.allowed_max, 5500)
        self.assertIn("около 5 000 символов", request.prompt)
        self.assertIn("от 4 500 до 5 500 символов", request.prompt)

    def test_title_placeholder_and_fallback_append(self):
        first = build_requests(["Имя"], "Напиши: {title}", [])[0]
        second = build_requests(["Имя"], "Напиши сценарий", [])[0]
        self.assertEqual(first.prompt, "Напиши: Имя")
        self.assertTrue(second.prompt.endswith("Название сценария: Имя"))


class ExportTests(unittest.TestCase):
    def test_safe_filename_removes_windows_forbidden_characters(self):
        self.assertEqual(safe_filename('  a<b>:c"/d\\e|f?g*  '), "a b c d e f g")

    def test_exports_individual_and_combined_files(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = write_exports(Path(folder), [("Один", "Текст 1"), ("Два", "Текст 2")])
            self.assertEqual(len(paths), 3)
            combined = Path(folder, "Все сценарии.txt").read_text(encoding="utf-8")
            self.assertIn("Один", combined)
            self.assertIn("Текст 2", combined)


if __name__ == "__main__":
    unittest.main()
