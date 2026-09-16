"""Regression coverage for the provider-neutral action trace."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class ObservabilityTests(unittest.TestCase):
    def test_action_trace_keeps_correlation_and_job_ids_but_redacts_secrets(self):
        from scriptor.observability import action_trace_path, start_action_trace

        trace = start_action_trace(
            "generate-covers",
            {
                "productionItemIds": ["production-42"],
                "apiKey": "sk-secret-value",
                "oauthToken": "Bearer private-token",
            },
        )
        trace.succeeded({"operationResult": {"jobIds": ["cover-job-9"]}})

        records = [
            json.loads(line) for line in action_trace_path().read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("actionId") == trace.action_id
        ]
        self.assertEqual(["started", "succeeded"], [record["event"] for record in records])
        self.assertEqual(records[0]["actionId"], records[1]["actionId"])
        self.assertEqual("fastgen", records[0]["provider"])
        self.assertEqual(["production-42"], records[0]["productionItemIds"])
        self.assertEqual(["cover-job-9"], records[1]["jobIds"])
        serialized = json.dumps(records, ensure_ascii=False)
        self.assertNotIn("sk-secret-value", serialized)
        self.assertNotIn("private-token", serialized)

    def test_action_trace_uses_only_the_isolated_runtime_root(self):
        from scriptor.observability import action_trace_path, start_action_trace

        start_action_trace("test-redaction", {}).failed(ValueError("OAuth token private-value"))
        trace_path = action_trace_path()
        test_root = Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()
        self.assertTrue(trace_path.is_relative_to(test_root))
        self.assertNotIn("private-value", trace_path.read_text(encoding="utf-8"))

    def test_current_bridge_command_records_a_correlated_successful_lifecycle(self):
        from scriptor.observability import action_trace_path

        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "scriptor.bridge", "add-topic", json.dumps({
                "topic": "Trace fixture", "_actionTrace": {"id": "renderer-action-17"},
            })],
            cwd=root,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        response = json.loads(result.stdout)
        self.assertIsInstance(response, dict)
        records = [
            json.loads(line) for line in action_trace_path().read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("actionId") == "renderer-action-17"
        ]
        self.assertEqual(["started", "succeeded"], [record["event"] for record in records])
        self.assertEqual("renderer-action-17", records[0]["actionId"])
        self.assertEqual(records[0]["actionId"], records[1]["actionId"])
        self.assertEqual(records[0]["actionId"], response["actionTrace"]["id"])

    def test_failed_bridge_command_keeps_the_same_redacted_action_context(self):
        from scriptor.observability import action_trace_path

        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "scriptor.bridge", "add-topic", json.dumps({"topic": ""})],
            cwd=root,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(1, result.returncode)
        response = json.loads(result.stdout)
        records = [
            json.loads(line) for line in action_trace_path().read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("actionId") == response["actionTrace"]["id"]
        ]
        self.assertEqual(["started", "failed"], [record["event"] for record in records])
        self.assertNotIn("token", json.dumps(records, ensure_ascii=False).casefold())


if __name__ == "__main__":
    unittest.main()
