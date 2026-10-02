import asyncio
import hashlib
import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge


def replay_saved_responses():
    """Revalidate actual saved responses in their ORIGINAL headline context.

    This is not a newly generated pipeline run: subsequent requests would
    change after selection fixes. Preserve evidence; never replay credentials.
    """
    root = Path(__file__).resolve().parents[1] / "docs/evidence/issue-316-live-20261002"
    cases = {item["id"]: item for item in json.loads((root / "dataset.json").read_text(encoding="utf-8"))}
    ledger = json.loads((root / "ledger.json").read_text(encoding="utf-8"))
    results = []
    for call in ledger:
        raw = call["visible_response"]
        assert len(raw) == call["response_chars"]
        assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == call["response_sha256"]
        parsed = json.loads(raw)
        kind = "subheadline" if "subheadline" in parsed else "headline"
        headline = re.search(r"УЖЕ УТВЕРЖДЁННЫЙ HEADLINE: «([^»]+)»", call["request"]["input"])
        item = cases[call["case"]]
        candidates = [(value, bridge._validate_cover_word(kind, value, item, headline=headline[1] if headline else ""))
                      for value in bridge._cover_word_candidates(raw, kind)]
        accepted = [pair for pair in candidates if pair[1]["valid"]]
        selection = bridge._select_cover_word_candidate(accepted, tabloid_mode=call["mode"] == "TABLOID") if accepted else None
        results.append({
            "order": call["order"], "case": call["case"], "mode": call["mode"], "kind": kind,
            "response_sha256": call["response_sha256"], "original_headline_context": headline[1] if headline else "",
            "candidates": [{"value": value, "validation": validation} for value, validation in candidates],
            "selected": selection[0] if selection else None,
            "selection": selection[1] if selection else {"reason": "NO_VALID_CANDIDATE; no repair/provider invoked"},
        })
    return results


class CoverQualitySelectionTests(unittest.TestCase):
    def test_all_17_original_responses_replay_without_network_or_mutating_evidence(self):
        root = Path(__file__).resolve().parents[1] / "docs/evidence/issue-316-live-20261002"
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file()}
        with patch("socket.socket", side_effect=AssertionError("Offline replay must not open sockets")):
            results = replay_saved_responses()
        self.assertEqual(len(results), 17)
        self.assertEqual([row["order"] for row in results], list(range(1, 18)))
        rejects = {candidate["value"]: candidate["validation"] for row in results for candidate in row["candidates"]}
        self.assertEqual(rejects["Дороже станет весь импорт"]["reason_code"], "CLAIM_STRENGTH_ERROR")
        self.assertFalse(rejects["Москва: протест под арестом"]["valid"])
        self.assertEqual(results[3]["selected"], "Импортёры платят больше")
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file()}
        self.assertEqual(before, after)

    def test_still_is_not_a_universal_scope_claim(self):
        item = {"title": "Помидоры остаются дорогими"}
        self.assertTrue(bridge._validate_cover_word("headline", "Помидоры всё ещё дорогие", item)["valid"])

    def test_negated_universal_scope_does_not_license_positive_expansion(self):
        item = {"title": "Не весь импорт подорожал после новых сборов"}
        self.assertFalse(bridge._validate_cover_word("subheadline", "Весь импорт подорожал", item)["valid"])

    def test_action_is_not_transferred_to_its_object(self):
        cases = (
            ({"title": "Цены на помидоры не падают"}, "Помидоры не падают", "Цены не падают"),
            ({"title": "Работники закрыли завод"}, "Завод закрыли работников", "Работники закрыли завод"),
        )
        for item, bad, good in cases:
            with self.subTest(bad=bad):
                self.assertFalse(bridge._validate_cover_word("headline", bad, item)["valid"])
                self.assertTrue(bridge._validate_cover_word("headline", good, item)["valid"])

    def test_new_clause_retains_its_own_subject(self):
        item = {"title": "Документы пока недоступны, инженеры продолжают восстановление"}
        self.assertTrue(bridge._validate_cover_word("subheadline", "Инженеры продолжают восстановление", item)["valid"])

    def test_hook_cannot_outvote_any_safe_quality_dimension(self):
        safe = bridge._validate_cover_word("headline", "Альфа вернула файл", {"title": "Альфа вернула файл"})
        for key in ("factual_pass", "grounding_pass", "naturalness_pass", "semantic_coherence_pass",
                    "literal_clarity_pass", "specificity_score", "literalness_score"):
            with self.subTest(key=key):
                weak = {**safe, "editorial_evaluation": {**safe["editorial_evaluation"],
                        key: 0, "hook_score": 5, "emotion_score": 5, "directness_score": 5}}
                value, validation = bridge._select_cover_word_candidate(
                    [("Альфа вернула файл", safe), ("Более эмоциональная строка", weak)], tabloid_mode=True,
                )
                self.assertEqual(value, "Альфа вернула файл")
                self.assertEqual(validation["selection_evidence"]["tabloid_differentiation"], "UNAVAILABLE")

    def test_subheadline_cannot_expand_a_specific_scope_to_everything(self):
        item = {"title": "Сборы на китайские товары", "script": "Импортёры платят больше за китайские товары."}
        for kind in ("headline", "subheadline"):
            with self.subTest(kind=kind):
                result = bridge._validate_cover_word(kind, "Дороже станет весь импорт", item)
                self.assertFalse(result["valid"], result)
                self.assertEqual(result["reason_code"], "CLAIM_STRENGTH_ERROR")
        self.assertTrue(bridge._validate_cover_word("subheadline", "Импортёры платят больше", item)["valid"])

    def test_subheadline_cannot_escalate_an_action(self):
        result = bridge._validate_cover_word("subheadline", "Трамп предъявил ультиматум", {"title": "Трамп обсуждает условия с Китаем"})
        self.assertFalse(result["valid"], result)
        self.assertEqual(result["reason_code"], "CLAIM_STRENGTH_ERROR")

    def test_universal_quantifier_requires_the_same_source_object(self):
        item = {"title": "Все магазины открыты", "script": "Сборы выросли на китайский импорт."}
        self.assertFalse(bridge._validate_cover_word("subheadline", "Подорожал весь импорт", item)["valid"])
        supported = {"title": "Весь импорт подорожал после новых сборов"}
        self.assertTrue(bridge._validate_cover_word("subheadline", "Весь импорт подорожал", supported)["valid"])

    def test_state_is_not_transferred_from_participant_to_event_or_institution(self):
        cases = (
            ({"title": "Москва: протест завершился арестом", "script": "Мужчина вышел с плакатом. Его задержали. Суд отправил участника протеста под арест."}, "Москва: протест под арестом", "Мужчина под арестом"),
            ({"title": "Москва: протест завершился арестом", "script": "Мужчина вышел с плакатом. Суд отправил его под арест."}, "Москва: протест под арестом", "Мужчина под арестом"),
            ({"title": "Завод остановил работу", "script": "Сотрудники остались без зарплаты."}, "Завод без зарплаты", "Сотрудники без зарплаты"),
            ({"title": "Приложение обновлено", "script": "Пользователи остались без доступа."}, "Приложение без доступа", "Пользователи без доступа"),
        )
        for item, bad, good in cases:
            with self.subTest(bad=bad):
                result = bridge._validate_cover_word("headline", bad, item)
                self.assertFalse(result["valid"], result)
                self.assertFalse(result["editorial_evaluation"]["subject_state_pass"])
                self.assertTrue(bridge._validate_cover_word("headline", good, item)["valid"])

    def test_tabloid_without_stronger_grounded_hook_is_honestly_degraded(self):
        async def generate(*_args, **_kwargs):
            return json.dumps({"candidates": ["Альфа вернула документы", "Альфа восстановила документы"]}, ensure_ascii=False)

        item = {"title": "Альфа вернула документы и восстановила документы"}
        value, validation, _ = asyncio.run(bridge._generate_cover_word_v2(
            SimpleNamespace(generate=generate), "headline", item, "", bridge._cover_word_structure_pair(item), tabloid_mode=True,
        ))
        self.assertIn(value, ("Альфа вернула документы", "Альфа восстановила документы"))
        self.assertEqual(validation["selection_evidence"]["tabloid_differentiation"], "UNAVAILABLE")
        self.assertTrue(validation["selection_evidence"]["degraded_result"])
        self.assertIn("unavailable", validation["selection_reason"])


if __name__ == "__main__":
    unittest.main()
