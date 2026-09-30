import tempfile
import unittest
from pathlib import Path

from scripts.capture_scenario_acceptance import (
    _budget_totals,
    _reserve_budget,
    _write_text,
)


class ScenarioAcceptanceCaptureTests(unittest.TestCase):
    def test_visible_evidence_text_keeps_its_original_newline_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario.txt"
            _write_text(path, "Первая строка\nВторая строка\n")
            self.assertEqual(
                path.read_bytes(),
                "Первая строка\nВторая строка\n".encode(),
            )

    def test_shared_diagnostic_budget_counts_one_call_cells_without_consuming_full_run_slots(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "budget.json"
            for number in range(1, 5):
                _reserve_budget(
                    ledger,
                    run_id=f"D{number}",
                    run_kind="D",
                    target=12000,
                    source_head="test",
                    reserved_logical_calls=1,
                    reserved_http_attempts=1,
                    max_full_runs=2,
                    max_logical_calls=18,
                    max_http_attempts=24,
                )

            self.assertEqual(_budget_totals(__import__("json").loads(ledger.read_text())), (0, 4, 4))
            _reserve_budget(
                ledger,
                run_id="R1",
                run_kind="R",
                target=12000,
                source_head="test",
                max_full_runs=2,
                max_logical_calls=18,
                max_http_attempts=24,
            )
            _reserve_budget(
                ledger,
                run_id="R2",
                run_kind="R",
                target=12000,
                source_head="test",
                max_full_runs=2,
                max_logical_calls=18,
                max_http_attempts=24,
            )
            with self.assertRaisesRegex(RuntimeError, "budget is exhausted"):
                _reserve_budget(
                    ledger,
                    run_id="R3",
                    run_kind="R",
                    target=12000,
                    source_head="test",
                    max_full_runs=2,
                    max_logical_calls=18,
                    max_http_attempts=24,
                )


if __name__ == "__main__":
    unittest.main()
