"""Beat-local narration semantics using real imports and disposable storage."""
import unittest

from scriptor import bridge
from scriptor.voice_map import VoiceMapStatus


def status_for(segments, duration):
    return VoiceMapStatus("approximate", "approximate", path="fixture-map.json",
                          reason="Word alignment unavailable", data={
        "audioDuration": duration, "timingMode": "approximate", "schemaVersion": 1,
        "productionItemId": "test-quality-voice", "scriptSha256": "fixture-script",
        "audioSha256": "fixture-audio", "alignmentEngine": "newsflow-fallback",
        "alignmentConfidence": 0.0, "segments": segments,
    })


def segment(text, duration=12, query="", identity=1, start=0):
    return {"id": identity, "start": start, "end": start + duration,
            "duration": duration, "text": text, "visualQuery": query}


class BeatLocalVoiceQualityTests(unittest.TestCase):
    def test_military_council_replaces_stale_frontline_without_rewriting_voice(self):
        texts = ["На фронте продолжаются бои.", "Генералы провели совещание в штабе."]
        raw = "frontline trenches soldiers battlefield military action"
        scenes, provenance = bridge._voice_map_scenes(status_for([
            segment(text, 6, raw, i + 1, i * 6) for i, text in enumerate(texts)], 12))
        self.assertIn("frontline", scenes[0]["visual_query_en"])
        self.assertIn("meeting", scenes[1]["visual_query_en"])
        self.assertNotIn("frontline", scenes[1]["visual_query_en"])
        self.assertEqual(texts, [scene["narration"] for scene in scenes])
        self.assertEqual([[1], [2]], [scene["voice_segment_ids"] for scene in scenes])
        self.assertEqual([6, 6], [scene["duration"] for scene in scenes])
        self.assertEqual("approximate", provenance["alignmentMode"])

    def test_unfinished_rally_clause_crosses_segment_without_prior_combat_or_future_meeting(self):
        texts = ["На фронте продолжаются бои.", "Горожане собрались на мирный",
                 "митинг. Власти начали переговоры."]
        segments = [segment(text, 6, "", i + 1, i * 6) for i, text in enumerate(texts)]
        segments[1]["visualQuery"] = "frontline trenches soldiers battlefield military action"
        scenes, provenance = bridge._voice_map_scenes(status_for(segments, 18))
        self.assertIn("peaceful", scenes[1]["visual_query_en"])
        self.assertIn("protest", scenes[1]["visual_query_en"])
        self.assertNotIn("frontline", scenes[1]["visual_query_en"])
        self.assertNotIn("diplomatic", scenes[1]["visual_query_en"])
        self.assertIn("diplomatic", scenes[2]["visual_query_en"])
        self.assertEqual(texts, [scene["narration"] for scene in scenes])
        self.assertEqual([[1], [2], [3]], [scene["voice_segment_ids"] for scene in scenes])
        self.assertEqual("approximate", provenance["alignmentMode"])

    def test_negation_and_named_speaker_cross_contiguous_segment_boundary(self):
        for texts, raw, wanted, forbidden in (
            (["Военные не", "начали обстрел города."], "", None, "shelling"),
            (["Путин утром", "прокомментировал решение перед журналистами."],
             "official statement government briefing", "Putin", None),
        ):
            with self.subTest(texts=texts):
                segments = [segment(text, 6, raw, i + 1, i * 6) for i, text in enumerate(texts)]
                scenes, _ = bridge._voice_map_scenes(status_for(segments, 12))
                for scene in scenes:
                    if wanted:
                        self.assertIn(wanted, scene["visual_query_en"])
                        self.assertIn("press conference", scene["visual_query_en"])
                    if forbidden:
                        self.assertNotIn(forbidden, scene["visual_query_en"])
                self.assertEqual(texts, [scene["narration"] for scene in scenes])
                self.assertEqual([(0, 6, 6), (6, 12, 6)], [
                    (scene["narration_start"], scene["narration_end"], scene["duration"]) for scene in scenes])

    def test_stale_authored_shelling_cannot_override_cross_segment_negation(self):
        raw = "artillery shelling city"
        scenes, _ = bridge._voice_map_scenes(status_for([
            segment("Военные не", 6, raw), segment("начали обстрел города.", 6, raw, 2, 6)], 12))
        for scene in scenes:
            self.assertNotIn("shelling", scene["visual_query_en"])
            self.assertNotIn("artillery", scene["visual_query_en"])

    def test_reported_statement_author_is_not_the_speaker_after_segment_cut(self):
        scenes, _ = bridge._voice_map_scenes(status_for([
            segment("Заявление Путина", 6), segment("прокомментировал Зеленский.", 6, "", 2, 6)], 12))
        for scene in scenes:
            self.assertIn("Zelensky", scene["visual_query_en"])
            self.assertNotIn("Putin", scene["visual_query_en"])

    def test_affirmed_shelling_remains_when_another_attack_is_negated(self):
        raw = "artillery shelling city"
        for texts in (["Военные начали", "обстрел города."],
                      ["Атака не началась, обстрел", "продолжился ночью."]):
            with self.subTest(texts=texts):
                scenes, _ = bridge._voice_map_scenes(status_for([
                    segment(text, 6, raw, i + 1, i * 6) for i, text in enumerate(texts)], 12))
                self.assertEqual([raw, raw], [scene["visual_query_en"] for scene in scenes])

    def test_cross_segment_stitch_stops_at_sentence_or_explicit_action_boundary(self):
        for first, second in (("Делегации провели встречу.", "Порт возобновил погрузку."),
                              ("Делегации провели встречу", "Затем порт возобновил погрузку."),
                              ("Делегации провели встречу,", "а порт возобновил погрузку.")):
            with self.subTest(first=first):
                scenes, _ = bridge._voice_map_scenes(status_for([
                    segment(first, 6), segment(second, 6, "", 2, 6)], 12))
                self.assertIn("diplomatic", scenes[0]["visual_query_en"])
                self.assertNotIn("port", scenes[0]["visual_query_en"])
                self.assertIn("port", scenes[1]["visual_query_en"])
                self.assertNotIn("diplomatic", scenes[1]["visual_query_en"])

    def test_action_marker_split_across_segments_starts_the_later_clause(self):
        for first, second in (("Делегации провели встречу, после", "этого порт возобновил погрузку."),
                              ("Делегации провели встречу, После", "этого, порт возобновил погрузку."),
                              ("Делегации провели встречу", "Затем, порт возобновил погрузку.")):
            with self.subTest(first=first, second=second):
                scenes, _ = bridge._voice_map_scenes(status_for([
                    segment(first, 6), segment(second, 6, "", 2, 6)], 12))
                self.assertIn("diplomatic", scenes[0]["visual_query_en"])
                self.assertNotIn("port", scenes[0]["visual_query_en"])
                self.assertIn("port", scenes[1]["visual_query_en"])
                self.assertNotIn("diplomatic", scenes[1]["visual_query_en"])

    def test_unfinished_clause_does_not_cross_a_temporal_gap(self):
        scenes, _ = bridge._voice_map_scenes(status_for([
            segment("Горожане собрались на мирный", 6),
            segment("митинг.", 6, "", 2, 6.5)], 12.5))
        self.assertNotIn("митинг", scenes[0]["scene_intent"]["text"])
        self.assertNotIn("protest", scenes[0]["visual_query_en"])
        self.assertIn("protest", scenes[1]["visual_query_en"])

    def test_unfinished_clause_stitch_has_finite_segment_and_word_budgets(self):
        for texts in (["Мирный"] * 6 + ["митинг."],
                      [" ".join(["Этот"] * 33), " ".join(["этот"] * 33) + " митинг."]):
            with self.subTest(parts=len(texts)):
                segments = [segment(text, 6, "", i + 1, i * 6) for i, text in enumerate(texts)]
                scenes, _ = bridge._voice_map_scenes(status_for(segments, len(texts) * 6))
                self.assertNotIn("митинг", scenes[0]["scene_intent"]["text"])
                self.assertNotIn("protest", scenes[0]["visual_query_en"])
                self.assertIn("protest", scenes[-1]["visual_query_en"])

    def test_continuing_grain_condition_and_sale_reject_stale_authored_harvest(self):
        texts = ["Но эти меры ограниченно помогают,", "если пшеницу невозможно выгодно вывезти за границу,",
                 "либо продают её с логистическим дисконтом,", "либо ищут субсидию на её хранение."]
        raw = "grain harvest agricultural storage wheat field"
        segments = [segment(text, 6, raw, i + 1, i * 6) for i, text in enumerate(texts)]
        scenes, _ = bridge._voice_map_scenes(status_for(segments, 24))
        for scene in scenes:
            self.assertIn("warehouse", scene["visual_query_en"])
            self.assertNotIn("harvest", scene["visual_query_en"])
        self.assertEqual(texts, [scene["narration"] for scene in scenes])
        self.assertEqual([6] * 4, [scene["duration"] for scene in scenes])

    def test_explicit_crops_and_harvesting_keep_compatible_authored_query(self):
        raw = "grain harvest agricultural storage wheat field"
        for text in ("Комбайны начали уборку урожая.", "Пшеница созревает в поле.",
                     "Жатва началась.", "На полях идёт жатва."):
            scenes, _ = bridge._voice_map_scenes(status_for([segment(text, 6, raw)], 6))
            self.assertEqual(raw, scenes[0]["visual_query_en"])

    def test_later_explicit_action_does_not_replace_earlier_beat(self):
        text = "Делегации провели встречу в столице сегодня. Затем порт возобновил погрузку судов ночью."
        scenes, provenance = bridge._voice_map_scenes(status_for([segment(text)], 12))
        self.assertIn("diplomatic", scenes[0]["visual_query_en"])
        self.assertNotIn("port", scenes[0]["visual_query_en"])
        self.assertIn("port", scenes[1]["visual_query_en"])
        self.assertNotIn("diplomatic", scenes[1]["visual_query_en"])
        self.assertEqual(text.split(), " ".join(row["narration"] for row in scenes).split())
        self.assertEqual([(0, 6, 6), (6, 12, 6)], [
            (row["narration_start"], row["narration_end"], row["duration"]) for row in scenes])
        self.assertEqual("approximate", provenance["alignmentMode"])
        self.assertEqual("newsflow-fallback", provenance["alignmentEngine"])
        self.assertEqual(0.0, provenance["alignmentConfidence"])
        self.assertEqual("Word alignment unavailable", provenance["alignmentUnavailableReason"])

    def test_authored_union_does_not_leak_later_topic_into_early_beat(self):
        text = "Делегации провели встречу в столице сегодня. Порт возобновил погрузку судов поздно ночью."
        raw = "diplomatic negotiations meeting, seaport cargo ships"
        scenes, _ = bridge._voice_map_scenes(status_for([segment(text, query=raw)], 12))
        self.assertIn("diplomatic", scenes[0]["visual_query_en"])
        self.assertNotIn("seaport", scenes[0]["visual_query_en"])
        self.assertIn("port", scenes[1]["visual_query_en"])
        self.assertNotIn("diplomatic", scenes[1]["visual_query_en"])

    def test_pronoun_context_survives_cut_then_resets_at_concrete_object(self):
        text = "Путин выступил перед журналистами в столице. Он прокомментировал решение правительства утром сегодня."
        objects = segment("Порт возобновил погрузку судов.", duration=6, identity=2, start=12)
        scenes, _ = bridge._voice_map_scenes(status_for([segment(text), objects], 18))
        self.assertEqual(["putin"], scenes[0]["scene_intent"]["target_people"])
        self.assertEqual(["putin"], scenes[1]["scene_intent"]["target_people"])
        self.assertIn("Putin", scenes[1]["visual_query_en"])
        self.assertEqual([], scenes[2]["scene_intent"]["target_people"])
        self.assertNotIn("Putin", scenes[2]["visual_query_en"])

    def test_compatible_authored_query_keeps_editorial_location(self):
        text = "Делегации провели встречу в столице сегодня. Делегации продолжили переговоры в здании вечером."
        query = "Geneva diplomatic negotiations delegation meeting"
        scenes, _ = bridge._voice_map_scenes(status_for([segment(text, query=query)], 12))
        self.assertEqual([query, query], [row["visual_query_en"] for row in scenes])

    def test_repeated_generic_fragments_use_their_own_nearest_context(self):
        segments = [
            segment("Вашингтон меняет правила.", duration=6,
                    query="Washington White House US government"),
            segment("И вот вопрос. И вот вопрос. И вот вопрос.", duration=18,
                    query=bridge.GENERIC_VISUAL_QUERY, identity=2, start=6),
            segment("Киев меняет правила.", duration=6,
                    query="Kyiv Ukraine government", identity=3, start=24),
        ]
        scenes, _ = bridge._voice_map_scenes(status_for(segments, 30))
        self.assertIn("Washington", scenes[1]["visual_query_en"])
        self.assertIn("Kyiv", scenes[3]["visual_query_en"])

    def test_official_and_port_union_is_local_even_without_official_topic_tag(self):
        text = "Власти прокомментировали новое решение правительства сегодня. Порт возобновил погрузку судов поздно ночью."
        raw = "official statement government briefing, seaport cargo ships"
        scenes, _ = bridge._voice_map_scenes(status_for([segment(text, query=raw)], 12))
        self.assertIn("statement", scenes[0]["visual_query_en"])
        self.assertNotIn("seaport", scenes[0]["visual_query_en"])
        self.assertIn("port", scenes[1]["visual_query_en"])
        self.assertNotIn("briefing", scenes[1]["visual_query_en"])

    def test_negative_clause_crossing_cut_does_not_create_shelling(self):
        text = "Власти подтвердили сегодня что военные не начали обстрел города прошлой ночью вновь."
        scenes, _ = bridge._voice_map_scenes(status_for([segment(text)], 12))
        self.assertEqual("не", scenes[0]["narration"].split()[-1])
        self.assertEqual("начали", scenes[1]["narration"].split()[0])
        for scene in scenes:
            self.assertNotIn("shelling", scene["visual_query_en"])
            self.assertNotIn("artillery", scene["visual_query_en"])

    def test_pronoun_before_cut_keeps_person_for_predicate_after_cut(self):
        text = "Путин прибыл утром. Позже он прокомментировал решение правительства перед журналистами."
        scenes, _ = bridge._voice_map_scenes(status_for([segment(text)], 12))
        self.assertEqual("он", scenes[0]["narration"].split()[-1])
        self.assertEqual("прокомментировал", scenes[1]["narration"].split()[0])
        self.assertEqual(["putin"], scenes[1]["scene_intent"]["target_people"])
        self.assertIn("Putin", scenes[1]["visual_query_en"])

    def test_contrasting_action_clauses_do_not_share_visuals_across_cuts(self):
        cases = [
            ("Делегации провели встречу в столице сегодня, а порт возобновил погрузку судов ночью.",
             "diplomatic", "port"),
            ("Власти отменили митинг в столице сегодня, но рабочие устроили забастовку у завода.",
             "statement", "labor strike"),
        ]
        for text, earlier, later in cases:
            with self.subTest(text=text):
                scenes, _ = bridge._voice_map_scenes(status_for([segment(text)], 12))
                self.assertIn(earlier, scenes[0]["visual_query_en"])
                self.assertNotIn(later, scenes[0]["visual_query_en"])
                self.assertIn(later, scenes[1]["visual_query_en"])
                self.assertNotIn(earlier, scenes[1]["visual_query_en"])
                self.assertEqual(text.split(), " ".join(row["narration"] for row in scenes).split())

    def test_compatible_authored_diplomatic_details_do_not_erase_location(self):
        text = "Делегации провели встречу в столице сегодня. Делегации продолжили переговоры в здании вечером."
        for details in ("journalists", "cameras", "journalists cameras"):
            query = f"Geneva diplomatic negotiations delegation meeting {details}"
            with self.subTest(details=details):
                scenes, _ = bridge._voice_map_scenes(status_for([segment(text, query=query)], 12))
                self.assertEqual([query, query], [row["visual_query_en"] for row in scenes])

    def test_linked_transport_clauses_do_not_borrow_finance_or_future_protest(self):
        clauses = [
            ("Глубоководные порты работали стабильнее.", 6, "seaport cargo cranes ships"),
            ("Для зерна,", 2, "grain harvest agricultural storage wheat field"),
            ("где прибыль на тонне может быть небольшой,", 6, ""),
            ("а вопрос того, имеет ли экспортная сделка экономический смысл.", 6, "economy finance business markets"),
            ("На одном из направлений доставка раньше занимала две недели,", 6, ""),
            ("а теперь растянулась более чем на месяц.", 4, ""),
            ("Рабочие устроили забастовку у завода.", 6, "peaceful workers labor strike picket line"),
        ]
        segments, cursor = [], 0
        for identity, (text, duration, query) in enumerate(clauses, 1):
            segments.append(segment(text, duration, query, identity, cursor))
            cursor += duration
        scenes, _ = bridge._voice_map_scenes(status_for(segments, cursor))
        for row in scenes[:-1]:
            self.assertIn("port", row["visual_query_en"])
            self.assertNotIn("finance", row["visual_query_en"])
            self.assertNotIn("labor strike", row["visual_query_en"])
        self.assertIn("labor strike", scenes[-1]["visual_query_en"])
        self.assertNotIn("seaport", scenes[-1]["visual_query_en"])

    def test_stored_grain_harvest_cannot_replace_explicit_loading_or_freight(self):
        for text in ("Терминалы загружают большие суда и отправляют партии зерна покупателям.",
                     "Маршрут должен принимать большие объёмы нового урожая.",
                     "Зерно конкурирует за проход с топливом и другими грузами."):
            raw = "grain harvest farming combine wheat field"
            scenes, _ = bridge._voice_map_scenes(status_for([segment(text, 6, raw)], 6))
            with self.subTest(text=text):
                self.assertIn("cargo", scenes[0]["visual_query_en"])
                self.assertNotIn("harvest", scenes[0]["visual_query_en"])


if __name__ == "__main__":
    unittest.main()
