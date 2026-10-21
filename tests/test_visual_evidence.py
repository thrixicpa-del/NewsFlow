"""Disposable window-evidence contracts; no source media or model download."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scriptor.ai_index import ClipIndex


class VisualWindowTests(unittest.TestCase):
    def test_grain_farm_rejects_nongrain_when_generic_farm_wins(self):
        from scriptor.visual_evidence import classify_window
        scores = [
            {"farm": .27, "combat": .235, "warehouse": .20,
             "grain_field": .198, "non_grain_agriculture": .27},
            {"farm": .216, "combat": .206, "warehouse": .20,
             "grain_field": .205, "non_grain_agriculture": .216},
            {"farm": .25, "combat": .205, "warehouse": .19,
             "grain_field": .218, "non_grain_agriculture": .25},
        ]
        result = classify_window("grain harvest agricultural storage wheat field", scores)
        self.assertEqual("contradiction", result["relation"])
        self.assertFalse(result["event_confirmed"])
        self.assertFalse(result["motion_verified"])

    def test_grain_farm_direct_requires_clear_complete_commodity_facets(self):
        from scriptor.visual_evidence import classify_window
        clear = {"farm": .35, "grain_field": .35, "non_grain_agriculture": .20}
        for bad in (
            {**clear, "non_grain_agriculture": .38},
            {**clear, "non_grain_agriculture": .345},
            {**clear, "non_grain_agriculture": .35},
            {**clear, "grain_field": .19},
            {"farm": .35, "grain_field": .35},
            {"farm": .35, "non_grain_agriculture": .20},
        ):
            for query in ("grain harvest agricultural storage wheat field", "wheat harvest",
                          "уборка урожая зерна", "пшеница комбайн"):
                with self.subTest(bad=bad, query=query):
                    for frames in ([bad] * 3, [clear, clear, bad]):
                        self.assertNotIn(classify_window(query, frames)["relation"], {"direct", "context"})
                    if "grain_field" not in bad or "non_grain_agriculture" not in bad:
                        missing = classify_window(query, [bad] * 3)
                        self.assertEqual("unknown", missing["relation"])
                        self.assertEqual("inconsistent-or-weak-window", missing["reason"])
                        self.assertEqual(["unknown"] * 3, missing["frame_relations"])

    def test_grain_farm_guard_preserves_clear_grain_and_real_warehouse_context(self):
        from scriptor.visual_evidence import classify_window
        grain = [{"farm": .35, "grain_field": .35, "non_grain_agriculture": .20}] * 3
        self.assertEqual("direct", classify_window("grain wheat harvest", grain)["relation"])
        for scores in ({"warehouse": .36, "farm": .21},
                       {"warehouse": .40, "farm": .35, "grain_field": .20, "non_grain_agriculture": .35}):
            with self.subTest(scores=scores):
                self.assertEqual("context", classify_window("grain harvest agricultural storage wheat field", [scores] * 3)["relation"])
        tied = [{"warehouse": .35, "farm": .35, "grain_field": .20, "non_grain_agriculture": .35}] * 3
        self.assertNotIn(classify_window("grain wheat harvest", tied)["relation"], {"direct", "context"})

    def test_grain_farm_guard_uses_positive_occurrences_and_preserves_other_crops(self):
        from scriptor.visual_evidence import classify_window
        nongrain = [{"farm": .35, "grain_field": .18, "non_grain_agriculture": .35}] * 3
        for query in ("general agriculture harvest", "tomato harvest agricultural crops",
                      "not grain, but tomato harvest agriculture", "no wheat, but tomato harvest",
                      "не зерно, а помидоры сельхоз урожай", "не пшеница, а помидоры сельхоз урожай"):
            with self.subTest(query=query):
                self.assertEqual("direct", classify_window(query, nongrain)["relation"])
        for query in ("not tomatoes, but grain harvest", "no grain here; wheat harvest",
                      "не помидоры, а уборка урожая зерна"):
            with self.subTest(query=query):
                self.assertNotIn(classify_window(query, nongrain)["relation"], {"direct", "context"})

    def test_grain_rail_can_use_clear_grain_commodity_context_without_claiming_transport(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"rail": .20, "farm": .35, "grain_field": .35,
                   "non_grain_agriculture": .20}] * 3
        for query in ("rail freight train grain transport cargo logistics",
                      "железнодорожные перевозки зерна грузовая логистика"):
            result = classify_window(query, scores)
            self.assertEqual("context", result["relation"])
            self.assertEqual("rail", result["topic"])
            self.assertEqual(["grain_field"], result["supported_kinds"])
            self.assertFalse(result["event_confirmed"])
            self.assertFalse(result["motion_verified"])
            self.assertEqual("grain_field", result["context_facet"]["kind"])

    def test_grain_commodity_context_rejects_crop_alternatives_and_incomplete_evidence(self):
        from scriptor.visual_evidence import classify_window
        query = "rail freight train grain transport cargo logistics"
        clear = {"farm": .35, "grain_field": .35, "non_grain_agriculture": .20}
        for bad in (
            {**clear, "non_grain_agriculture": .36},  # apples, vegetables, nursery or silos
            {**clear, "non_grain_agriculture": .345},  # ambiguous bare-soil tillage
            {**clear, "non_grain_agriculture": .35},
            {"farm": .35, "grain_field": .35},
            {"farm": .35, "non_grain_agriculture": .20},
            {**clear, "grain_field": .19},
            *[{**clear, kind: .36} for kind in ("combat", "equipment_display", "military_naval",
                                               "vessel_incident", "factory", "energy", "interview")],
        ):
            with self.subTest(bad=bad):
                for frames in ([bad] * 3, [clear, clear, bad]):
                    self.assertNotIn(classify_window(query, frames)["relation"], {"direct", "context"})

    def test_grain_commodity_context_requires_positive_general_grain_rail_intent(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"farm": .35, "grain_field": .35, "non_grain_agriculture": .20}] * 3
        for query in (
            "rail freight train transport cargo logistics",
            "rail grain", "grain cargo logistics hiking trail",
            "rail freight train, no grain", "no rail freight train, grain cargo logistics",
            "rail freight train grain logistics without wheat fields",
            "rail freight train grain cargo loading", "grain rail train crossing a bridge",
            "grain rail train derailment", "grain rail freight harvest",
            "grain rail freight train moving", "зерно грузовой поезд движется по мосту",
            "зерно грузовая поездка логистика", "зернистая текстура железнодорожного груза",
            "grain rail freight logistics without visible wheat fields",
            "зерно железнодорожная грузовая логистика без видимых полей",
            "grain rail freight train on fire", "grain rail freight train explodes",
            "зерно грузовой поезд горит", "grain rail freight train crosses a bridge",
            "grain rail freight train arrives", "grain rail freight train under attack",
            "зерно грузовой поезд едет по мосту", "зерно грузовой поезд идет по мосту",
            "grain freight train in motion", "grain freight train running along tracks",
            "grain freight train traveling", "grain freight train passes a bridge",
            "грузовые поезда с зерном сейчас едут", "зерно грузовой движущийся поезд",
            "grain rail freight logistics, frontline artillery battlefield",
            "formal statement about rail freight train grain logistics",
            "map of grain rail freight logistics", "peaceful protest against grain rail freight",
        ):
            with self.subTest(query=query):
                self.assertNotIn(classify_window(query, scores)["relation"], {"direct", "context"})

    def test_grain_facets_leave_existing_visual_roles_and_direct_priority_unchanged(self):
        from scriptor.visual_evidence import classify_window
        for query, kind in (("rail freight train grain cargo logistics", "rail"),
                            ("harvest agriculture farming fields", "farm"),
                            ("seaport cargo cranes ships", "port"),
                            ("formal statement", "official"), ("frontline battlefield", "combat")):
            scores = {kind: .35, "city": .10}
            baseline = classify_window(query, [scores] * 3)
            added = {**scores, "grain_field": .99, "non_grain_agriculture": .98}
            self.assertEqual(baseline, classify_window(query, [added] * 3))

    def test_artillery_in_crop_fields_competes_with_farming_without_rejecting_farms(self):
        from scriptor.visual_evidence import TAXONOMY
        descriptions = (
            "military rocket launchers firing on a green agricultural field",
            "camouflaged army trucks with rocket launchers firing from a green farm field",
        )
        with tempfile.TemporaryDirectory(prefix="newsflow-field-artillery-") as temporary:
            root = Path(temporary)
            index = self.make_index(root)
            ordinary_queries = index._query_vectors

            def queries(texts):
                vectors = ordinary_queries(texts)
                for i, text in enumerate(texts):
                    if text in descriptions:
                        vectors[i] = 0
                        vectors[i, -2] = 1
                return vectors

            index._query_vectors = queries
            for number, (farm, field_artillery, farm_relation, combat_relation) in enumerate((
                    (.30, .34, "contradiction", "direct"),
                    (.30, .305, "unknown", "direct"),
                    (.35, .25, "direct", "contradiction"))):
                with self.subTest(farm=farm, field_artillery=field_artillery):
                    clip = root / f"unlabelled-{number}.mp4"
                    clip.write_bytes(b"disposable field-window")
                    image = np.zeros(512, dtype=np.float32)
                    image[list(TAXONOMY).index("farm")] = farm
                    image[list(TAXONOMY).index("combat")] = .24
                    image[-2] = field_artillery
                    image[-1] = np.sqrt(1 - float(image @ image))
                    index._sample_visual_window = lambda *_, frame=image: ([frame] * 3, [.5, 3., 5.5])
                    actual_farm = index.assess_visual_window("agriculture farming fields", clip, 0, 6)
                    actual_combat = index.assess_visual_window("frontline artillery battlefield military action", clip, 0, 6)
                    self.assertEqual(farm_relation, actual_farm["relation"])
                    self.assertEqual(combat_relation, actual_combat["relation"])
                    self.assertFalse(actual_combat["event_confirmed"])
                    self.assertFalse(actual_combat["motion_verified"])

    def test_vegetable_nursery_trays_cannot_supply_battlefield_evidence(self):
        """A crop close-up must compete with more than grain/harvest prompts."""
        from scriptor.visual_evidence import TAXONOMY
        with tempfile.TemporaryDirectory(prefix="newsflow-seedlings-") as temporary:
            root = Path(temporary)
            clip = root / "unlabelled.mp4"
            clip.write_bytes(b"disposable-window")
            index = self.make_index(root)
            original_queries = index._query_vectors

            def queries(texts):
                vectors = original_queries(texts)
                for i, text in enumerate(texts):
                    if "seedlings" in text and "trays" in text:
                        vectors[i] = 0
                        vectors[i, -2] = 1
                return vectors

            # Measured development case: old farm descriptions lose to combat,
            # while the visible nursery-tray description wins clearly.
            image = np.zeros(512, dtype=np.float32)
            image[list(TAXONOMY).index("combat")] = .240
            image[list(TAXONOMY).index("farm")] = .188
            image[-2] = .280
            image[-1] = np.sqrt(1 - float(image @ image))
            index._query_vectors = queries
            index._sample_visual_window = lambda *_: ([image] * 3, [.5, 3., 5.5])
            battle = index.assess_visual_window("frontline trenches soldiers battlefield military action", clip, 0, 6)
            self.assertEqual("contradiction", battle["relation"])
            self.assertEqual("farm", battle["dominant_kind"])
            farm = index.assess_visual_window("farm agriculture crops", clip, 0, 6)
            self.assertEqual("direct", farm["relation"])
            self.assertFalse(farm["event_confirmed"])
            self.assertFalse(farm["motion_verified"])

    def test_vessel_water_display_is_not_cargo_navigation_evidence(self):
        from scriptor.visual_evidence import TAXONOMY
        with tempfile.TemporaryDirectory(prefix="newsflow-water-display-") as temporary:
            root = Path(temporary)
            clip = root / "vessel.mp4"
            clip.write_bytes(b"disposable-window")
            index = self.make_index(root)
            original_queries = index._query_vectors

            def queries(texts):
                vectors = original_queries(texts)
                for i, text in enumerate(texts):
                    if "fireboat" in text and "water jets" in text:
                        vectors[i] = 0
                        vectors[i, -2] = 1
                return vectors

            image = np.zeros(512, dtype=np.float32)
            image[list(TAXONOMY).index("port")] = .257
            image[-2] = .371
            image[-1] = np.sqrt(1 - float(image @ image))
            index._query_vectors = queries
            index._sample_visual_window = lambda *_: ([image] * 3, [.5, 3., 5.5])
            result = index.assess_visual_window("cargo ship maritime navigation shipping sea freight", clip, 0, 6)
            self.assertEqual("contradiction", result["relation"])
            self.assertEqual("maritime_display", result["dominant_kind"])

    def test_foreground_swimming_is_not_cargo_port_evidence(self):
        """A distant ship must not outweigh the visible beach activity."""
        from scriptor.visual_evidence import TAXONOMY
        with tempfile.TemporaryDirectory(prefix="newsflow-beach-") as temporary:
            root = Path(temporary)
            clip = root / "harbor-background.mp4"
            clip.write_bytes(b"disposable-window")
            index = self.make_index(root)
            original_queries = index._query_vectors

            def queries(texts):
                vectors = original_queries(texts)
                for i, text in enumerate(texts):
                    if "swimming" in text and "beach" in text:
                        vectors[i] = 0
                        vectors[i, -2] = 1
                return vectors

            image = np.zeros(512, dtype=np.float32)
            image[list(TAXONOMY).index("port")] = .232
            image[-2] = .297
            image[-1] = np.sqrt(1 - float(image @ image))
            index._query_vectors = queries
            index._sample_visual_window = lambda *_: ([image] * 3, [.5, 3., 5.5])
            result = index.assess_visual_window("seaport cargo ship logistics", clip, 0, 6)
            self.assertEqual("contradiction", result["relation"])
            self.assertEqual("leisure", result["dominant_kind"])

    def test_industrial_workshop_near_tie_is_not_cargo_warehouse_evidence(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"warehouse": .298, "factory": .295, "port": .217}] * 3
        for query in ("grain cargo warehouse storage", "seaport cargo cranes ships"):
            with self.subTest(query=query):
                self.assertEqual("unknown", classify_window(query, scores)["relation"])
        self.assertEqual("direct", classify_window("industrial factory manufacturing", scores)["relation"])

    def test_clear_warehouse_keeps_direct_and_port_context_without_factory_tie(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"warehouse": .35, "factory": .20, "port": .19}] * 3
        self.assertEqual("direct", classify_window("grain cargo warehouse storage", scores)["relation"])
        self.assertEqual("context", classify_window("seaport cargo cranes ships", scores)["relation"])

    def test_explicit_grain_warehouse_clause_keeps_port_context_for_rail(self):
        from scriptor.visual_evidence import classify_window
        for query in (
            "rail freight train grain transport cargo logistics, grain cargo warehouse storage logistics",
            "железнодорожные перевозки зерна, грузовой склад зерна логистика",
            "rail freight train grain cargo logistics, no warehouse here; grain cargo warehouse storage logistics",
        ):
            with self.subTest(query=query):
                result = classify_window(query, [{"port": .35, "rail": .21}] * 3)
                self.assertEqual("context", result["relation"])
                self.assertEqual("rail", result["topic"])
                self.assertFalse(result["event_confirmed"])
                self.assertFalse(result["motion_verified"])
                self.assertEqual("direct", classify_window(query, [{"rail": .35, "port": .21}] * 3)["relation"])

    def test_grain_rail_context_reuses_persisted_window_with_zero_cold_budget(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-grain-context-") as temporary:
            root = Path(temporary)
            clip = root / "unlabelled.mp4"
            clip.write_bytes(b"disposable-window")
            index = self.make_index(root)
            self.assertEqual("direct", index.assess_visual_window("seaport cargo", clip, 0, 6)["relation"])
            index._visual_memory_clear()
            restored = self.make_index(root)
            restored.visual_window_budget = 0
            with patch.object(restored, "_sample_visual_window", side_effect=AssertionError("no new window")), \
                    patch.object(restored, "_sample_frames", side_effect=AssertionError("no new screen analysis")):
                query = "rail freight train grain cargo logistics, grain cargo warehouse storage logistics"
                result = restored.assess_visual_window(query, clip, 0, 6)
                self.assertEqual("context", result["relation"])
                self.assertEqual("sqlite", result["feature_cache"])
                self.assertEqual("contradiction", restored.assess_visual_window("rail freight train", clip, 0, 6)["relation"])
            self.assertEqual(0, restored._visual_cold_windows)

    def test_grain_rail_context_does_not_expand_without_positive_warehouse_intent(self):
        from scriptor.visual_evidence import classify_window
        for query in (
            "rail freight train grain transport cargo logistics",
            "rail freight train, cargo warehouse storage logistics",
            "rail freight train, no grain cargo warehouse storage logistics",
            "rail freight train grain cargo logistics, no warehouse",
            "no rail freight train, grain cargo warehouse storage logistics",
            "железнодорожные перевозки зерна, без склада",
            "frontline artillery battlefield, rail freight train grain cargo warehouse storage logistics",
            "grain harvest, rail freight train grain cargo warehouse storage logistics",
            "rail freight train grain transport cargo logistics, no grain cargo storage warehouse",
            "rail freight train grain cargo logistics, no grain-cargo storage warehouse",
            "rail freight train grain cargo logistics, without grain: cargo storage warehouse",
            "grain cargo warehouse storage logistics, hiking trail",
            "rail freight train, woodgrain cargo warehouse storage logistics",
        ):
            with self.subTest(query=query):
                self.assertEqual("contradiction", classify_window(query, [{"port": .35, "rail": .21}] * 3)["relation"])

    def test_grain_rail_port_context_preserves_close_negatives_and_explicit_roles(self):
        from scriptor.visual_evidence import classify_window
        query = "rail freight train grain cargo logistics, grain cargo warehouse storage logistics"
        for kind in ("military_naval", "maritime_display", "vessel_incident", "equipment_display", "combat"):
            with self.subTest(kind=kind):
                self.assertEqual("contradiction", classify_window(query, [{"port": .30, kind: .35}] * 3)["relation"])
                self.assertEqual("unknown", classify_window(query, [{"port": .30, kind: .305}] * 3)["relation"])
        for prefix, kind, relation in (
            ("military naval warship", "military_naval", "contradiction"),
            ("sinking cargo ship", "vessel_incident", "context"),
            ("machinery exhibition", "equipment_display", "contradiction"),
            ("formal statement", "official", "contradiction"),
            ("peaceful protest rally", "peaceful_protest", "contradiction"),
            ("map infographic", "map", "contradiction"),
        ):
            with self.subTest(prefix=prefix):
                result = classify_window(prefix + ", " + query, [{"port": .35, kind: .21}] * 3)
                self.assertEqual(relation, result["relation"])
                self.assertEqual(kind if kind != "peaceful_protest" else "protest", result["topic"])

    def make_index(self, root):
        from scriptor.visual_evidence import TAXONOMY
        classes = list(TAXONOMY)
        class Text:
            def query_embed(self, queries):
                for query in ([queries] if isinstance(queries, str) else queries):
                    vector = np.zeros(512, dtype=np.float32)
                    vector[next(i for i, kind in enumerate(classes) if query in TAXONOMY[kind])] = 1
                    yield vector
        class Image:
            def embed(self, images, **kwargs):
                yield from images
        index = ClipIndex(root / "index.sqlite3", embedder_factory=lambda: (Image(), Text()))
        index._visual_models_available = lambda: True
        def frames(path, start, duration):
            vector = np.zeros(512, dtype=np.float32)
            vector[:len(classes)] = .10
            vector[classes.index("port")] = .32
            vector[-1] = np.sqrt(1 - float(vector @ vector))
            return [vector] * 3, [start + .5, start + duration / 2, start + duration - .5]
        index._sample_visual_window = frames
        return index

    def test_exact_window_features_persist_and_changed_bytes_invalidate(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"disposable-media")
            index = self.make_index(root)
            with patch.object(index, "_sample_visual_window", wraps=index._sample_visual_window) as decode:
                first = index.assess_visual_window("cargo seaport", clip, 7, 6)
                again = index.assess_visual_window("cargo ship port", clip, 7, 6)
                self.assertEqual(first["relation"], "direct")
                self.assertEqual(first["sample_times"], [7.5, 10, 12.5])
                self.assertEqual(first["source_start"], 7)
                self.assertEqual(again["relation"], "direct")
                self.assertEqual(decode.call_count, 1)
                index._visual_memory_clear()
                other = self.make_index(root)
                with patch.object(other, "_sample_visual_window", side_effect=AssertionError("warm decode")):
                    self.assertEqual(other.assess_visual_window("cargo seaport", clip, 7, 6)["relation"], "direct")
                clip.write_bytes(b"changed disposable media")
                self.assertEqual(index.assess_visual_window("cargo seaport", clip, 7, 6)["relation"], "direct")
                self.assertEqual(decode.call_count, 2)

    def write_model_refs(self, root, revision):
        from scriptor.ai_index import IMAGE_MODEL, TEXT_MODEL
        for model in (IMAGE_MODEL, TEXT_MODEL):
            reference = root / "models" / ("models--" + model.replace("/", "--")) / "refs" / "main"
            reference.parent.mkdir(parents=True, exist_ok=True)
            reference.write_text(revision, encoding="utf-8")

    def test_changed_local_model_revision_invalidates_persisted_and_memory_features(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            self.write_model_refs(root, "revision-A")
            first = self.make_index(root)
            old = first.assess_visual_window("cargo seaport", clip, 0, 6)
            self.write_model_refs(root, "revision-B")
            second = self.make_index(root)
            with patch.object(second, "_sample_visual_window", wraps=second._sample_visual_window) as decode:
                new = second.assess_visual_window("cargo seaport", clip, 0, 6)
                self.assertEqual(decode.call_count, 1)
            self.assertNotEqual(old["model_revision"], new["model_revision"])
            first._visual_memory_clear()
            third = self.make_index(root)
            with patch.object(third, "_sample_visual_window", side_effect=AssertionError("current revision should be persisted")):
                self.assertEqual(third.assess_visual_window("cargo seaport", clip, 0, 6)["model_revision"], new["model_revision"])
            # An already loaded A model keeps its original identity even if
            # another index starts using B from the same cache directory.
            self.assertEqual(first.assess_visual_window("cargo seaport", clip, 0, 6)["model_revision"], old["model_revision"])

    def test_shared_actual_models_are_keyed_by_local_revision(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            self.write_model_refs(root, "revision-A")
            first = ClipIndex(root / "index.sqlite3")
            with patch("scriptor.onnx_clip.ImageEmbedding", side_effect=[object(), object()]) as image, patch("scriptor.onnx_clip.TextEmbedding", side_effect=[object(), object()]) as text:
                old_models = first._models(local_files_only=True)
                self.write_model_refs(root, "revision-B")
                second = ClipIndex(root / "index.sqlite3")
                new_models = second._models(local_files_only=True)
                self.assertEqual(image.call_count, 2)
                self.assertEqual(text.call_count, 2)
                self.assertIsNot(old_models[0], new_models[0])
                self.assertIs(first._models(local_files_only=True)[0], old_models[0])

    def test_cold_budget_preserves_cached_windows(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            index = self.make_index(root)
            index.visual_window_budget = 1
            self.assertEqual(index.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "direct")
            self.assertEqual(index.assess_visual_window("cargo seaport", clip, 8, 6)["reason"], "cold-window-budget-exhausted")
            self.assertEqual(index.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "direct")

    def test_curated_interval_is_signature_bound_and_precedes_automatic(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "misleading-factory-hint.mp4"
            clip.write_bytes(b"fixture")
            index = ClipIndex(root / "index.sqlite3")
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns) VALUES(?,?,?,?)", (str(clip), clip.name, stat.st_size, stat.st_mtime_ns))
            index.set_visual_evidence(str(clip), [{"kind": "peaceful_protest", "start": 4, "end": 12, "source": "manual"}])
            result = index.assess_visual_window("peaceful protest rally", clip, 4, 6)
            self.assertEqual(result["relation"], "direct")
            self.assertEqual(result["source"], "curated-interval")
            self.assertFalse(result["event_confirmed"])
            self.assertEqual(index.assess_visual_window("peaceful protest rally", clip, 0, 6)["reason"], "curated-window-not-covered")
            clip.write_bytes(b"changed fixture")
            self.assertIsNone(index.assess_visual_window("peaceful protest rally", clip, 4, 6))

    def test_curated_annotation_changes_reach_other_active_index(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            first = ClipIndex(root / "index.sqlite3")
            second = ClipIndex(first.db_path)
            stat = clip.stat()
            with first._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,duration) VALUES(?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns, 30))
            first.set_visual_evidence(str(clip), [{"kind": "port", "start": 0, "end": 6, "source": "manual"}])
            self.assertEqual(second.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "direct")
            with patch.object(second, "_connect", side_effect=AssertionError("unchanged warm annotation queried SQLite")):
                self.assertEqual(second.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "direct")
            first.set_visual_evidence(str(clip), [{"kind": "leisure", "start": 0, "end": 6, "source": "manual"}])
            self.assertEqual(second.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "contradiction")
            first.set_visual_evidence(str(clip), [])
            self.assertIsNone(second.assess_visual_window("cargo seaport", clip, 0, 6))

    def test_annotation_update_invalidates_even_when_file_fingerprint_is_identical(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            first = ClipIndex(root / "index.sqlite3")
            second = ClipIndex(first.db_path)
            stat = clip.stat()
            with first._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,duration) VALUES(?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns, 30))
            with patch.object(second, "_database_fingerprint", return_value=((1, 1, 1),)):
                first.set_visual_evidence(str(clip), [{"kind": "port", "start": 0, "end": 6, "source": "manual"}])
                self.assertEqual(second.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "direct")
                first.set_visual_evidence(str(clip), [{"kind": "leisure", "start": 0, "end": 6, "source": "manual"}])
                self.assertEqual(second.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "contradiction")

    def test_read_session_reuses_rows_and_immediately_observes_other_index_changes(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            first = ClipIndex(root / "index.sqlite3")
            second = ClipIndex(first.db_path)
            stat = clip.stat()
            with first._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,duration,source_url) VALUES(?,?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns, 30, "original"))
            import sqlite3
            with patch("sqlite3.connect", wraps=sqlite3.connect) as opens:
                with second.read_session():
                    for _ in range(100):
                        self.assertEqual(second.catalog_item(clip).source_url, "original")
                        self.assertEqual(second.metadata(clip).duration, 30)
                    self.assertEqual(opens.call_count, 1)
                    with first._connect() as connection:
                        connection.execute("UPDATE clips SET source_url=? WHERE path=?", ("changed", str(clip)))
                    self.assertEqual(second.catalog_item(clip).source_url, "changed")
                    second.candidate_filter = lambda item: item.source_url == "original"
                    self.assertIsNone(second.metadata(clip))
                # The session closes its handle before Windows temp cleanup.
                self.assertIsNone(second._read_session_connection)

    def test_read_session_observes_cross_process_annotation_commit_and_closes_on_error(self):
        import json
        import subprocess
        import sys
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            index = ClipIndex(root / "index.sqlite3")
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns) VALUES(?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns))
            index.set_visual_evidence(str(clip), [{"kind": "port", "start": 0, "end": 6, "source": "manual"}])
            replacement = {"version": 1, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                           "observations": [{"kind": "leisure", "start": 0, "end": 6, "source": "manual"}]}
            with (self.assertRaisesRegex(RuntimeError, "end disposable read session"), index.read_session(),
                  patch.object(index, "_database_fingerprint", return_value=((1, 1, 1),))):
                self.assertEqual(index.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "direct")
                subprocess.run([sys.executable, "-c", "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('UPDATE clips SET visual_evidence=? WHERE path=?',(sys.argv[3],sys.argv[2])); c.commit(); c.close()",
                                str(index.db_path), str(clip), json.dumps(replacement)], check=True, capture_output=True)
                self.assertEqual(index.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "contradiction")
                raise RuntimeError("end disposable read session")
            self.assertIsNone(index._read_session_connection)

    def test_catalog_item_is_unfiltered_and_retains_index_owned_metadata(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            index = ClipIndex(root / "index.sqlite3")
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,source_url,tags) VALUES(?,?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns, "https://example.test/iran", '["port-logistics"]'))
            index.set_visual_evidence(str(clip), [{"kind": "port", "start": 0, "end": 6, "source": "manual"}])
            index.candidate_filter = lambda item: False
            item = index.catalog_item(clip)
            self.assertEqual(item.source_url, "https://example.test/iran")
            self.assertEqual(item.tags, ["port-logistics"])
            self.assertTrue(callable(item._visual_assessor))
            self.assertIsNone(index.metadata(clip))
            self.assertEqual(index.all_items(), [])
            self.assertIsNone(index.catalog_item(root / "missing.mp4"))

    def test_offline_curated_gap_does_not_fall_back_to_path_hints(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "port_cargo_cranes.mp4"
            clip.write_bytes(b"fixture")
            index = ClipIndex(root / "index.sqlite3")
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,duration,tags) VALUES(?,?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns, 30, '["port-logistics"]'))
            index.set_visual_evidence(str(clip), [{"kind": "port", "start": 9, "end": 13, "source": "manual"}])
            result = index.assess_visual_window("cargo seaport", clip, 0, 6, allow_alternatives=True)
            self.assertIsNotNone(result)
            self.assertEqual(result["relation"], "unknown")
            self.assertEqual(result["reason"], "curated-window-not-covered")

    def test_curated_alternative_is_found_without_model_and_exact_calls_stay_exact(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "port_ship.mp4"
            clip.write_bytes(b"fixture")
            index = ClipIndex(root / "index.sqlite3")
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,duration) VALUES(?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns, 30))
            index.set_visual_evidence(str(clip), [{"kind": "port", "start": 4, "end": 10, "source": "manual"}])
            with patch.object(index, "_models", side_effect=AssertionError("model must not load")):
                self.assertEqual(index.assess_visual_window("cargo seaport", clip, 0, 6)["reason"], "curated-window-not-covered")
                alternative = index.assess_visual_window("cargo seaport", clip, 0, 6, allow_alternatives=True)
                self.assertIsNotNone(alternative)
                self.assertEqual(alternative["source_start"], 4)
                self.assertEqual(alternative["duration"], 6)
                self.assertEqual(alternative["relation"], "direct")
                self.assertEqual(alternative["source"], "curated-interval")
                self.assertEqual(index.assess_visual_window("cargo seaport", clip, 5, 6)["reason"], "curated-window-not-covered")
                self.assertEqual(index.assess_visual_window("cargo seaport", clip, 0, 7, allow_alternatives=True)["reason"], "curated-window-not-covered")
    def test_uncached_models_do_not_decode_or_download(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            index = ClipIndex(Path(temporary) / "index.sqlite3")
            with patch.object(index, "_models", side_effect=AssertionError("download")):
                self.assertIsNone(index.assess_visual_window("cargo seaport", Path(temporary) / "missing.mp4", 0, 6))

    def test_offline_real_clip_index_keeps_callback_and_explicit_unknown(self):
        from scriptor.ai_index import IMAGE_MODEL
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "misleading-port-portrait.mp4"
            clip.write_bytes(b"fixture")
            index = ClipIndex(root / "index.sqlite3")
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,embedding,model,tags) VALUES(?,?,?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns,
                                    np.zeros(512, dtype=np.float32).tobytes(), IMAGE_MODEL, '["port-logistics"]'))
            with patch.object(index, "_models", side_effect=AssertionError("offline model must not load")):
                item = index.all_items()[0]
                self.assertTrue(callable(getattr(item, "_visual_assessor", None)))
                result = item._visual_assessor("cargo seaport", 0, 6)
                self.assertEqual(result["relation"], "unknown")
                self.assertEqual(result["reason"], "existing-model-unavailable")
                self.assertEqual(index.assess_visual_window("cargo seaport", clip, 0, 6)["reason"], "existing-model-unavailable")
                retrieved = index.search_many(["cargo seaport"], limit=1)[0][0].item
                self.assertTrue(callable(getattr(retrieved, "_visual_assessor", None)))

    def test_offline_legacy_non_clip_dimensions_do_not_attach_callback(self):
        from scriptor.ai_index import IMAGE_MODEL
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "legacy.mp4"
            clip.write_bytes(b"fixture")
            index = ClipIndex(root / "index.sqlite3")
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,embedding,model) VALUES(?,?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns,
                                    np.zeros(2, dtype=np.float32).tobytes(), IMAGE_MODEL))
            self.assertFalse(hasattr(index.all_items()[0], "_visual_assessor"))
            self.assertIsNone(index.assess_visual_window("cargo seaport", clip, 0, 6))

    def test_topic_positive_and_close_negative_matrix(self):
        from scriptor.visual_evidence import classify_window
        rows = [
            ("cargo seaport", "port", "direct"), ("cargo seaport", "warehouse", "context"),
            ("cargo seaport", "rail", "context"), ("cargo seaport", "road_cargo", "context"),
            ("diplomatic meeting delegations", "meeting", "direct"),
            ("diplomatic meeting delegations", "official", "context"),
            ("diplomatic meeting delegations", "government_building", "context"),
            ("diplomatic meeting delegations", "interview", "contradiction"),
            ("formal government statement", "official", "direct"),
            ("formal government statement", "government_building", "context"),
            ("peaceful civilian protest rally", "peaceful_protest", "direct"),
            ("peaceful civilian protest rally", "police_guard", "context"),
            ("peaceful civilian protest rally", "clashes", "contradiction"),
            ("violent protest clashes dispersal", "clashes", "direct"),
            ("violent protest clashes dispersal", "police_guard", "context"),
            ("peaceful workers labor strike protest", "peaceful_protest", "context"),
            ("peaceful workers labor strike protest", "factory", "context"),
            ("peaceful farmers protest tractors", "farm", "context"),
            ("peaceful farmers protest tractors", "peaceful_protest", "context"),
            ("soldiers in battlefield combat", "combat", "direct"),
            ("farm wheat harvest", "farm", "direct"),
            ("farm wheat harvest", "warehouse", "context"),
            ("freight train railway", "rail", "direct"),
            ("freight train railway", "farm", "contradiction"),
            ("cyber data center servers", "digital", "direct"),
            ("economic sanctions finance", "finance", "direct"),
            ("oil refinery pipelines", "energy", "direct"),
        ]
        for query, kind, expected in rows:
            with self.subTest(query=query, kind=kind):
                scores = {kind: .32}
                if query == "farm wheat harvest" and kind == "farm":
                    scores.update(grain_field=.32, non_grain_agriculture=.18)
                result = classify_window(query, [scores] * 3)
                self.assertEqual(result["relation"], expected)
                self.assertFalse(result["event_confirmed"])
                self.assertFalse(result["motion_verified"])

    def test_weak_or_incomplete_frames_are_unknown(self):
        from scriptor.visual_evidence import classify_window
        for scores in ([{"port": .15}] * 3, [{"port": .32}] * 2,
                       [{"port": float("nan")}] * 3):
            self.assertEqual(classify_window("cargo seaport", scores)["relation"], "unknown")

    def test_specific_protest_distinguishes_direct_action_from_sector_context(self):
        from scriptor.visual_evidence import classify_window
        for query, direct, sector in (("workers labor strike protest", "worker_picket", "factory"),
                                      ("farmers protest tractors", "farmer_protest", "farm")):
            with self.subTest(query=query):
                self.assertEqual(classify_window(query, [{direct: .33}] * 3)["relation"], "direct")
                self.assertEqual(classify_window(query, [{sector: .33}] * 3)["relation"], "context")

    def test_statement_role_precedes_mentioned_port_or_map(self):
        from scriptor.visual_evidence import classify_window
        for subject in ("cargo seaport", "map of battlefield"):
            query = "Nikol Pashinyan press conference statement journalists cameras, " + subject
            self.assertEqual(classify_window(query, [{"official": .33}] * 3)["relation"], "direct")
            self.assertEqual(classify_window(query, [{"port": .33}] * 3)["relation"], "contradiction")

    def test_specific_refinery_precedes_generic_industrial_query_term(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"energy": .34, "factory": .21, "warehouse": .16}] * 3
        result = classify_window("oil refinery industrial oil infrastructure", scores)
        self.assertEqual(result["relation"], "direct")
        self.assertEqual(result["topic"], "energy")

    def test_concurrent_same_window_decodes_once(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            first, second = self.make_index(root), self.make_index(root)
            original = first._sample_visual_window
            calls = []
            def decode(path, start, duration):
                calls.append(start)
                time.sleep(.02)
                return original(path, start, duration)
            first._sample_visual_window = second._sample_visual_window = decode
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(index.assess_visual_window, "cargo seaport", clip, 0, 6) for index in (first, second)]
                self.assertEqual([future.result()["relation"] for future in futures], ["direct", "direct"])
            self.assertEqual(calls, [0])

    def test_file_change_during_decode_never_caches_evidence(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            index = self.make_index(root)
            original = index._sample_visual_window
            def decode(path, start, duration):
                result = original(path, start, duration)
                clip.write_bytes(b"different bytes while decoding")
                return result
            index._sample_visual_window = decode
            result = index.assess_visual_window("cargo seaport", clip, 0, 6)
            self.assertEqual(result["reason"], "source-changed-during-assessment")
            with index._connect() as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM visual_window_features").fetchone()[0], 0)

    def test_alternatives_return_best_exact_window_and_never_exceed_three(self):
        from scriptor.visual_evidence import TAXONOMY
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            index = self.make_index(root)
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,duration) VALUES(?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns, 30))
            original = index._sample_visual_window
            calls = []
            def decode(path, start, duration):
                calls.append(start)
                images, times = original(path, start, duration)
                if start != 12:
                    images[0] = images[0].copy()
                    images[0][list(TAXONOMY).index("port")] = .1
                    images[0][list(TAXONOMY).index("leisure")] = .4
                    images = [images[0]] * 3
                return images, times
            index._sample_visual_window = decode
            result = index.assess_visual_window("cargo seaport", clip, 0, 6, allow_alternatives=True)
            self.assertEqual(result["source_start"], 12)
            self.assertEqual(result["relation"], "direct")
            self.assertEqual(calls, [0, 12])

    def test_callbacks_bind_current_index_without_changing_dataclass_serialization(self):
        from dataclasses import asdict

        from scriptor.ai_index import IMAGE_MODEL
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            first, second = self.make_index(root), self.make_index(root)
            stat = clip.stat()
            with first._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,embedding,model) VALUES(?,?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns,
                                    np.zeros(512, dtype=np.float32).tobytes(), IMAGE_MODEL))
            original = first._search_corpus().items[0]
            self.assertFalse(hasattr(original, "_visual_assessor"))
            one = first._with_visual_assessor(original)
            two = second._with_visual_assessor(original)
            self.assertTrue(hasattr(second.all_items()[0], "_visual_assessor"))
            from scriptor.visual_evidence import TAXONOMY
            retrieved = second.search_many([TAXONOMY["port"][0]], limit=1)[0][0].item
            self.assertTrue(hasattr(retrieved, "_visual_assessor"))
            self.assertEqual(retrieved.metadata_provenance["path_hints"], [clip.name])
            with patch.object(first, "assess_visual_window", return_value={"index": 1}), patch.object(second, "assess_visual_window", return_value={"index": 2}):
                self.assertEqual(one._visual_assessor("cargo seaport", 0, 6), {"index": 1})
                self.assertEqual(two._visual_assessor("cargo seaport", 0, 6), {"index": 2})
            self.assertEqual(asdict(one), asdict(original))

    def test_synthetic_embedders_never_attach_automatic_assessor(self):
        from scriptor.ai_index import IndexedFootageItem
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            index = ClipIndex(Path(temporary) / "index.sqlite3", embedder_factory=lambda: (object(), object()))
            self.assertFalse(hasattr(index._with_visual_assessor(IndexedFootageItem("fixture.mp4", "fixture")), "_visual_assessor"))

    def test_feature_writes_do_not_redecode_shared_search_corpus(self):
        from scriptor.ai_index import IMAGE_MODEL
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            index = self.make_index(root)
            stat = clip.stat()
            with index._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,embedding,model) VALUES(?,?,?,?,?,?)",
                                   (str(clip), clip.name, stat.st_size, stat.st_mtime_ns,
                                    np.zeros(512, dtype=np.float32).tobytes(), IMAGE_MODEL))
            before = index._search_corpus()
            self.assertEqual(index.assess_visual_window("cargo seaport", clip, 0, 6)["relation"], "direct")
            after = index._search_corpus()
            self.assertIs(before.vectors, after.vectors)

    def test_native_decoder_keeps_all_three_frames_inside_exact_window(self):
        import cv2
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            path = Path(temporary) / "fixture.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (32, 32))
            self.assertTrue(writer.isOpened())
            for frame in range(100):
                writer.write(np.full((32, 32, 3), frame * 2, dtype=np.uint8))
            writer.release()
            images, times = ClipIndex._sample_visual_window(path, 4, 3)
            self.assertEqual(len(images), 3)
            self.assertTrue(all(4 <= value < 7 for value in times))
            self.assertTrue(all(float(np.asarray(image).mean()) >= 80 for image in images))
            with self.assertRaises(ValueError):
                ClipIndex._sample_visual_window(path, 8, 3)

    def test_allowed_roots_resolve_once_and_mutation_invalidates(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            index = ClipIndex(root / "index.sqlite3")
            index.allowed_roots = [str(first)]
            original = Path.resolve
            calls = []
            def resolve(path, *args, **kwargs):
                calls.append(str(path))
                return original(path, *args, **kwargs)
            with patch.object(Path, "resolve", resolve):
                self.assertTrue(index.path_allowed(first / "a.mp4"))
                self.assertTrue(index.path_allowed(first / "b.mp4"))
                self.assertEqual(calls.count(str(first)), 1)
                self.assertIn(str(first / "a.mp4"), calls)
                self.assertIn(str(first / "b.mp4"), calls)
                index.allowed_roots[:] = [str(second)]
                self.assertFalse(index.path_allowed(first / "a.mp4"))
                self.assertTrue(index.path_allowed(second / "a.mp4"))
                self.assertEqual(calls.count(str(second)), 1)

    def test_allowed_roots_recheck_candidate_symlink_resolution(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            allowed = root / "allowed"
            allowed.mkdir()
            clip = allowed / "clip.mp4"
            index = ClipIndex(root / "index.sqlite3")
            index.allowed_roots = [str(allowed)]
            self.assertTrue(index.path_allowed(clip))
            original = Path.resolve
            def resolve(path, *args, **kwargs):
                return root / "outside" / "clip.mp4" if path == clip else original(path, *args, **kwargs)
            with patch.object(Path, "resolve", resolve):
                self.assertFalse(index.path_allowed(clip))

    def make_filtered_index(self, root):
        class Text:
            def query_embed(self, queries):
                for _ in ([queries] if isinstance(queries, str) else queries):
                    yield np.asarray([1., 0.], dtype=np.float32)
        return ClipIndex(root / "index.sqlite3", embedder_factory=lambda: (object(), Text()))

    def seed_filtered_candidates(self, index, root):
        rows = [("cargo_iran.mp4", [1., 0.]), ("port_ship.mp4", [.7, .714])]
        with index._connect() as connection:
            for name, vector in rows:
                path = root / name
                path.write_bytes(b"fixture")
                stat = path.stat()
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,embedding,tags) VALUES(?,?,?,?,?,?)",
                                   (str(path), name, stat.st_size, stat.st_mtime_ns,
                                    np.asarray(vector, dtype=np.float32).tobytes(), '["cargo"]'))

    def test_transient_candidate_filter_precedes_topk_and_does_not_poison_shared_corpus(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            first, second = self.make_filtered_index(root), self.make_filtered_index(root)
            self.seed_filtered_candidates(first, root)
            first.candidate_filter = lambda item: "iran" not in item.name
            second.candidate_filter = lambda item: "iran" in item.name
            for index, expected in ((first, "port_ship.mp4"), (second, "cargo_iran.mp4"), (first, "port_ship.mp4")):
                self.assertEqual(index.search("cargo", limit=1)[0].item.name, expected)
                self.assertEqual([item.name for item in index.all_items()], [expected])
                self.assertEqual(index.count(), 1)
                self.assertEqual(len(index._search_corpus().items), 2)
            self.assertIsNone(first.metadata(root / "cargo_iran.mp4"))
            self.assertIsNone(second.metadata(root / "port_ship.mp4"))
            self.assertIsNotNone(first.metadata(root / "port_ship.mp4"))
            first.candidate_filter = None
            self.assertEqual(first.search("cargo", limit=1)[0].item.name, "cargo_iran.mp4")
            self.assertEqual(first.count(), 2)

    def test_transient_candidate_filter_also_precedes_metadata_fallback_topk(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            index = self.make_filtered_index(root)
            self.seed_filtered_candidates(index, root)
            index.candidate_filter = lambda item: "iran" not in item.name
            with patch.object(index, "_text_model_is_cached", return_value=False), patch.object(index, "_models", side_effect=AssertionError("metadata-only query must not load a model")):
                self.assertEqual(index.search("cargo iran", limit=1)[0].item.name, "port_ship.mp4")

    def test_bar_contradicts_official_statement(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"leisure": .30, "official": .21, "interview": .25}] * 3
        self.assertEqual(classify_window("formal government statement", scores)["relation"], "contradiction")

    def test_portrait_and_rally_cannot_supply_port_context(self):
        from scriptor.visual_evidence import classify_window
        for label in ("interview", "peaceful_protest", "official", "farm"):
            scores = [{label: .32, "port": .19, "warehouse": .20}] * 3
            self.assertEqual(classify_window("cargo cranes in a seaport", scores)["relation"], "contradiction")

    def test_map_cannot_confirm_battlefield_action(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"map": .27, "combat": .244}] * 3
        self.assertEqual(classify_window("soldiers advancing on battlefield", scores)["relation"], "contradiction")
        self.assertEqual(classify_window("map of battlefield front lines", scores)["relation"], "direct")

    def test_measured_naval_negative_is_scored_for_general_port_query(self):
        from scriptor.visual_evidence import RULES_VERSION, TAXONOMY, TAXONOMY_VERSION
        naval_prompts = {
            "military naval warship deck with large naval guns turrets missiles sailors at sea",
            "navy destroyer frigate battleship military vessel with naval gun turrets on deck",
        }
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "unlabelled.mp4"
            clip.write_bytes(b"fixture")
            index = self.make_index(root)
            positions = {query: i for i, (_kind, queries) in enumerate(TAXONOMY.items()) for query in queries}
            def text_vectors(queries):
                result = np.zeros((len(queries), 512), dtype=np.float32)
                for i, query in enumerate(queries):
                    result[i, 50 if query in naval_prompts else positions[query]] = 1
                return result
            image = np.zeros(512, dtype=np.float32)
            image[:len(TAXONOMY)] = .1
            image[list(TAXONOMY).index("port")] = .24
            image[50] = .29
            image[-1] = np.sqrt(1 - float(image @ image))
            index._query_vectors = text_vectors
            index._sample_visual_window = lambda _path, start, duration: ([image] * 3, [start + .5, start + 3, start + 5.5])
            result = index.assess_visual_window("cargo seaport cranes ships", clip, 0, 6)
            self.assertEqual(result["relation"], "contradiction")
            self.assertAlmostEqual(result["class_scores"]["military_naval"], .29, places=5)
            self.assertEqual(TAXONOMY_VERSION, 9)
            # The new checkpoint role does not erase measured naval negatives.
            self.assertEqual(RULES_VERSION, 14)
            self.assertFalse(result["event_confirmed"])

    def test_mixed_interval_is_not_direct(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"port": .32, "interview": .18}] * 2 + [{"port": .18, "interview": .34}]
        self.assertNotEqual(classify_window("cargo seaport", scores)["relation"], "direct")

    def test_near_negative_winner_cannot_be_accepted_as_direct_farm(self):
        from scriptor.visual_evidence import classify_window
        scores = [{"farm": .236, "combat": .242, "map": .240},
                  {"farm": .256, "combat": .262},
                  {"farm": .237, "combat": .229}]
        scores = [{**row, "grain_field": row["farm"], "non_grain_agriculture": .15} for row in scores]
        self.assertEqual(classify_window("agriculture farming wheat harvest fields", scores)["relation"], "unknown")
        strong = [{"farm": .28, "combat": .23, "grain_field": .28, "non_grain_agriculture": .15}] * 3
        self.assertEqual(classify_window("agriculture farming wheat harvest fields", strong)["relation"], "direct")

    def test_classifier_upgrade_reuses_features_and_recomputes_relation(self):
        from scriptor.visual_evidence import TAXONOMY
        with tempfile.TemporaryDirectory(prefix="newsflow-visual-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            index = self.make_index(root)
            vector = np.zeros(512, dtype=np.float32)
            vector[:len(TAXONOMY)] = .1
            vector[list(TAXONOMY).index("port")] = .24
            vector[list(TAXONOMY).index("interview")] = .246
            vector[-1] = np.sqrt(1 - float(vector @ vector))
            index._sample_visual_window = lambda _path, start, duration: ([vector] * 3, [start + .5, start + 3, start + 5.5])
            with patch("scriptor.visual_evidence.RULES_VERSION", 3), patch("scriptor.visual_evidence.classify_window", return_value={"relation": "direct", "reason": "legacy-classifier"}):
                old = index.assess_visual_window("cargo seaport", clip, 0, 6)
                self.assertEqual(old["relation"], "direct")
            with patch("scriptor.visual_evidence.RULES_VERSION", 4), patch.object(index, "_sample_visual_window", side_effect=AssertionError("classifier change must not decode")):
                current = index.assess_visual_window("cargo seaport", clip, 0, 6)
                self.assertEqual(current["relation"], "unknown")
                self.assertEqual(current["feature_cache"], "memory")
                self.assertEqual(current["rules_version"], 4)
                self.assertEqual(current["taxonomy_version"], 9)
                index._visual_memory_clear()
                persisted = index.assess_visual_window("cargo seaport", clip, 0, 6)
                self.assertEqual(persisted["relation"], "unknown")
                self.assertEqual(persisted["feature_cache"], "sqlite")
