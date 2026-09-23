import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch


class CommandContractTests(unittest.TestCase):
    def test_critical_paths_have_one_registered_canonical_handler(self):
        from scriptor.command_contract import COMMAND_CONTRACT

        expected = {
            "save-settings", "add-topic", "generate-ideas", "generate-scenarios",
            "import-manual-scenario", "remove-scenarios",
            "generate-voice-queue",
            "generate-voice-range", "generate-covers", "run-montage-queue",
            "package-outputs", "export-results-batch", "generate-seo", "generate-tags",
            "upload-publication-jobs", "confirm-publication-v2-distribution",
            "migrate-publication-v2",
        }
        self.assertTrue(expected.issubset(COMMAND_CONTRACT))
        for command in expected:
            entry = COMMAND_CONTRACT[command]
            self.assertTrue(entry.handler)
            self.assertTrue(entry.service)
            self.assertTrue(entry.forbidden_legacy_modules)

    def test_contract_rejects_non_object_critical_payload_and_unknown_command(self):
        from scriptor.command_contract import (
            CommandContractError,
            validate_command_request,
        )

        with self.assertRaises(CommandContractError):
            validate_command_request("generate-covers", [1, 2])
        with self.assertRaises(CommandContractError):
            validate_command_request("not-a-newsflow-command", {})

    def test_contract_accepts_object_payload_and_snapshot_response(self):
        from scriptor.command_contract import (
            validate_command_request,
            validate_command_result,
        )

        validate_command_request("generate-ideas", {"requirements": "проверка"})
        validate_command_result("generate-ideas", {"ideaResults": [], "operationResult": {"kind": "ideas"}})

    def test_registered_handler_names_exist_on_the_active_bridge(self):
        from scriptor import bridge
        from scriptor.command_contract import COMMAND_CONTRACT

        for entry in COMMAND_CONTRACT.values():
            self.assertTrue(callable(getattr(bridge, entry.handler, None)), entry.handler)

    def test_active_bridge_does_not_import_a_forbidden_legacy_module(self):
        from scriptor.command_contract import COMMAND_CONTRACT

        bridge_source = Path(__file__).with_name("bridge.py").read_text(encoding="utf-8")
        for entry in COMMAND_CONTRACT.values():
            for module in entry.forbidden_legacy_modules:
                module_tail = module.rsplit(".", 1)[-1]
                self.assertNotIn(f"from .{module_tail} import", bridge_source, module)

    def test_bridge_rejects_bad_critical_payload_before_any_handler_runs(self):
        from scriptor import bridge

        output = StringIO()
        with patch.object(bridge.sys, "argv", ["bridge", "generate-covers", "[]"]), \
             patch("sys.stdout", output), \
             self.assertRaises(SystemExit):
            bridge.main()

        self.assertIn("Payload команды generate-covers должен быть объектом", output.getvalue())
