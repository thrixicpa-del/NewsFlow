import tempfile
import unittest
from pathlib import Path

from scripts.capture_scenario_acceptance import (
    _budget_totals,
    _estimate_max_call_usd,
    _mark_logical_call_error,
    _planner_test_route_kwargs,
    _post_adapter_payload_comparison,
    _reserve_budget,
    _write_text,
)


class ScenarioAcceptanceCaptureTests(unittest.TestCase):
    def test_started_planner_cell_remains_a_logical_attempt_after_transport_error(self):
        entry = {"logical_call": 1, "result": "PENDING"}
        _mark_logical_call_error(entry, TimeoutError())

        self.assertEqual(entry["result"], "ERROR")
        self.assertEqual(entry["error_type"], "TimeoutError")

    def test_cost_reservation_counts_reasoning_inside_output_once(self):
        estimate = _estimate_max_call_usd(
            "gpt-5.4", input_chars=1000, max_output_tokens=32768,
        )

        self.assertEqual(estimate["input_token_upper_bound"], 1000)
        self.assertEqual(estimate["output_token_upper_bound"], 32768)
        self.assertAlmostEqual(estimate["estimated_max_usd"], 0.49402, places=5)

    def test_test_planner_route_changes_only_structured_planner_calls(self):
        planner = _planner_test_route_kwargs(
            {"text_format": {"type": "json_schema"}, "max_output_tokens": 6144},
            model="gpt-5.4",
            reasoning_effort="medium",
            planner_output_tokens=32768,
        )
        writer = _planner_test_route_kwargs(
            {"max_output_tokens": 5120},
            model="gpt-5.4",
            reasoning_effort="medium",
            planner_output_tokens=32768,
        )

        self.assertEqual(planner["model"], "gpt-5.4")
        self.assertEqual(planner["reasoning_effort"], "medium")
        self.assertEqual(planner["max_output_tokens"], 32768)
        self.assertEqual(writer, {"max_output_tokens": 5120})

    def test_planner_matrix_comparison_removes_only_model_and_reasoning(self):
        first = {
            "model": "gpt-5.4-mini", "reasoning": {"effort": "none"},
            "instructions": "same", "input": "same", "text": {"format": {"strict": True}},
            "max_output_tokens": 32768,
        }
        second = {
            **first, "model": "gpt-5.4", "reasoning": {"effort": "medium"},
        }

        self.assertEqual(_post_adapter_payload_comparison(first), _post_adapter_payload_comparison(second))
        self.assertNotIn("model", _post_adapter_payload_comparison(first))
        self.assertNotIn("reasoning", _post_adapter_payload_comparison(first))

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
