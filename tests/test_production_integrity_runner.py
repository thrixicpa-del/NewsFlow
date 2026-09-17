from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ProductionIntegrityRunnerTests(unittest.TestCase):
    def test_isolated_runner_fails_when_a_child_targets_declared_production_storage(self):
        """The parent guard must override a passing child result after a write incident."""
        repository = Path(__file__).resolve().parents[1]
        runner = repository / "tests" / "run_isolated.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            production_local_appdata = root / "production-local-appdata"
            production_storage = production_local_appdata / "NewsFlow"
            production_storage.mkdir(parents=True)
            (production_storage / "settings.json").write_text('{"schema_version":4}', encoding="utf-8")
            test_module = root / "test_bad_writer.py"
            test_module.write_text(
                "import os\n"
                "from pathlib import Path\n"
                "from unittest import TestCase\n"
                "class BadWriter(TestCase):\n"
                "    def test_bad_writer(self):\n"
                "        target = Path(os.environ['NEWSFLOW_PRODUCTION_LOCALAPPDATA']) / 'NewsFlow' / 'settings.json'\n"
                "        target.write_text('{\\\"schema_version\\\":0}', encoding='utf-8')\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["LOCALAPPDATA"] = str(production_local_appdata)
            result = subprocess.run(
                [sys.executable, str(runner), "discover", "-s", str(root), "-q"],
                cwd=repository,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 91, result.stdout + result.stderr)
        self.assertIn("PRODUCTION_WRITE_GUARD=FAIL changed=settings.json", result.stderr)

