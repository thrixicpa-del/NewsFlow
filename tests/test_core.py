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

    def test_title_placeholder_and_fallback_append(self):
        first = build_requests(["Имя"], "Напиши: {title}", [])[0]
        second = build_requests(["Имя"], "Напиши сценарий", [])[0]
        self.assertEqual(first.prompt, "Напиши: Имя")
        self.assertTrue(second.prompt.endswith("Название сценария: Имя"))

    def test_single_character_target_in_prompt_becomes_approximate_runtime_contract(self):
        request = build_requests(
            ["Имя"],
            "Напиши сценарий на тему {title}. Нужно около 10 000 символов, считать Python.",
            [],
        )[0]

        self.assertEqual((request.target_chars, request.allowed_min, request.allowed_max), (10000, 9000, 11000))
        self.assertIn("9000–11000", request.prompt)

    def test_structured_length_contract_is_prioritized_without_truncating_the_user_template(self):
        template = (
            "FULL_USER_PROMPT_BEGIN\\n"
            "Сохрани все мои правила. Старое текстовое число: 5 000 символов.\\n"
            "Уникальный хвост шаблона: FULL_USER_PROMPT_END {title}"
        )
        request = build_requests(
            ["Проверочная тема"],
            template,
            [],
            default_target_chars=10000,
            default_allowed_min=9000,
            default_allowed_max=11000,
        )[0]

        self.assertEqual((request.target_chars, request.allowed_min, request.allowed_max), (10000, 9000, 11000))
        self.assertIn("ПРИОРИТЕТНЫЙ КОНТРАКТ ОБЪЕМА NEWSFLOW", request.prompt)
        self.assertIn("ОБЯЗАТЕЛЬНО сам контролируй количество символов", request.prompt)
        self.assertIn("ПЕРЕД ОТПРАВКОЙ ФИНАЛЬНОГО ОТВЕТА сам проверь длину", request.prompt)
        self.assertIn("len(text.strip())", request.prompt)
        self.assertIn("а не слова, токены или приблизительный объем", request.prompt)
        self.assertIn("приоритет над любыми конфликтующими числами", request.prompt)
        self.assertIn("FULL_USER_PROMPT_BEGIN", request.prompt)
        self.assertIn("FULL_USER_PROMPT_END Проверочная тема", request.prompt)
        self.assertIn("Старое текстовое число: 5 000 символов.", request.prompt)
        self.assertLess(
            request.prompt.index("ПРИОРИТЕТНЫЙ КОНТРАКТ ОБЪЕМА NEWSFLOW"),
            request.prompt.index("FULL_USER_PROMPT_BEGIN"),
        )

    def test_global_structured_length_contract_applies_to_every_scenario(self):
        requests = build_requests(
            ["Первый", "Второй"],
            "Напиши: {title}",
            [],
            default_target_chars=10000,
        )

        self.assertTrue(all(
            (item.target_chars, item.allowed_min, item.allowed_max) == (10000, 9000, 11000)
            for item in requests
        ))

    def test_range_length_contract_overrides_the_global_preset_contract(self):
        requests = build_requests(
            ["Первый", "Второй"],
            "Напиши: {title}",
            [PromptRange(2, 2, "", target_chars=6000)],
            default_target_chars=10000,
        )

        self.assertEqual((requests[0].target_chars, requests[0].allowed_min, requests[0].allowed_max), (10000, 9000, 11000))
        self.assertEqual((requests[1].target_chars, requests[1].allowed_min, requests[1].allowed_max), (6000, 5400, 6600))


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
