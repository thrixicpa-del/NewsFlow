import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.capture_scenario_writer_diagnostics import (
    build_diagnostic_cases,
    load_control_fixture,
)


class ScenarioWriterDiagnosticFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_root = (
            Path(__file__).resolve().parent / "fixtures" / "pr293_writer_diagnostics"
        )
        cls.fixture = load_control_fixture(cls.fixture_root / "CONTROL_FIXTURE.json")
        cls.full_template = (
            Path(__file__).resolve().parents[1]
            / "docs" / "verification" / "evidence"
            / "scenario-live-293-final-stage-20260930"
            / "scenario-live-293-a3-20260930-140000"
            / "01-user-template.txt"
        ).read_text(encoding="utf-8")
        cls.short_template = (cls.fixture_root / "DIAGNOSTIC_SHORT_TEMPLATE.txt").read_text(
            encoding="utf-8"
        )

    def test_control_fixture_matches_its_declared_hashes_and_preserves_all_owned_steps(self):
        manifest = json.loads((self.fixture_root / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            self.assertEqual(
                hashlib.sha256((self.fixture_root / name).read_bytes()).hexdigest(),
                expected,
            )

        cases = build_diagnostic_cases(
            self.fixture, self.full_template, self.short_template
        )
        self.assertEqual([case.id for case in cases], ["D1", "D2", "D3", "D4"])
        self.assertEqual([case.part_id for case in cases], ["P1", "P1", "P3", "P3"])
        self.assertEqual(
            [atom.id for atom in cases[0].plan.content_atoms],
            [f"E{index:02d}" for index in range(1, 13)],
        )
        self.assertEqual(
            [part.content_ids for part in cases[0].plan.parts],
            [tuple(f"E{index:02d}" for index in range(1, 5)),
             tuple(f"E{index:02d}" for index in range(5, 9)),
             tuple(f"E{index:02d}" for index in range(9, 13))],
        )
        self.assertIn(
            "Машины покидают площадки; оба квартала работают от восстановленной сети",
            cases[2].input,
        )

    def test_each_template_pair_changes_only_the_manual_contract_in_the_post_adapter_payload(self):
        cases = build_diagnostic_cases(
            self.fixture, self.full_template, self.short_template
        )
        for left, right in ((cases[0], cases[1]), (cases[2], cases[3])):
            with self.subTest(pair=f"{left.id}/{right.id}"):
                self.assertEqual(left.instructions, right.instructions)
                self.assertNotIn(self.full_template, left.instructions)
                self.assertNotIn(self.short_template, right.instructions)
                self.assertEqual(
                    left.input.replace(self.full_template, "<MANUAL_TEMPLATE>"),
                    right.input.replace(self.short_template, "<MANUAL_TEMPLATE>"),
                )
                self.assertEqual(left.payload["model"], right.payload["model"])
                self.assertEqual(left.payload["max_output_tokens"], 5120)
                self.assertEqual(left.payload["input"], left.input)
                self.assertEqual(left.payload["instructions"], left.instructions)
                self.assertNotIn("text", left.payload)
                self.assertNotIn("tools", left.payload)
                self.assertNotIn("previous_response_id", left.payload)

    def test_harness_runs_as_a_script_without_changing_the_import_path(self):
        result = subprocess.run(
            [sys.executable, "scripts/capture_scenario_writer_diagnostics.py", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--preflight-only", result.stdout)


if __name__ == "__main__":
    unittest.main()
