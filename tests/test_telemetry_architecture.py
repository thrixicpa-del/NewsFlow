"""Provider-neutral telemetry architecture remains local unless explicitly enabled."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


class TelemetryArchitectureTests(unittest.TestCase):
    def test_default_plan_is_local_only_and_documents_optional_adapters(self):
        from scriptor.telemetry import telemetry_plan

        plan = telemetry_plan({})
        self.assertEqual("local", plan.default_exporter)
        self.assertFalse(plan.external_export_enabled)
        self.assertEqual({"opentelemetry", "sentry"}, {adapter.name for adapter in plan.optional_adapters})

    def test_local_event_redacts_attributes_and_stays_inside_test_root(self):
        from scriptor.telemetry import LocalTelemetryExporter, TelemetryEvent

        exporter = LocalTelemetryExporter()
        exporter.emit(TelemetryEvent(
            name="provider.request.failed",
            action_id="telemetry-action-18",
            duration_ms=17.5,
            attributes={"provider": "fastgen", "apiKey": "sk-" + "private-value", "oauthToken": "Bearer secret"},
        ))

        trace_path = exporter.path()
        self.assertTrue(trace_path.is_relative_to(Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()))
        record = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual("telemetry-action-18", record["actionId"])
        self.assertEqual("[REDACTED]", record["attributes"]["apiKey"])
        self.assertEqual("[REDACTED]", record["attributes"]["oauthToken"])
        self.assertNotIn("private-value", json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
