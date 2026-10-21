"""Real source Electron creation/reset/re-add/restart with empty scenarios."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from scriptor import config, session
from tests import test_production_reset as fixtures

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "studio-ui-remotion-verify"
ELECTRON = APP / "node_modules/electron/dist/electron.exe"


@unittest.skipUnless(ELECTRON.exists() and (APP / "dist/index.html").exists(), "Build source Electron/web first")
class StandaloneCoverUITests(unittest.TestCase):
    def test_real_ui_empty_topics_reset_readd_and_restart(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1")
        root = Path(os.environ["NEWSFLOW_TEST_ROOT"])
        settings = fixtures.ProductionResetTests()._settings(root)
        settings.idea_production_items = []
        settings.idea_results = []
        settings.cover_queue = []
        config.save_settings(settings)
        session.save_session([], [])
        evidence = ROOT / ".superpowers/covers-standalone/ui"
        evidence.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "NEWSFLOW_PYTHON": sys.executable,
               "NEWSFLOW_STANDALONE_COVER_REPORT": str(evidence / "result.json"),
               "NEWSFLOW_STANDALONE_COVER_RESTART_REPORT": str(evidence / "restart.json")}
        env.pop("ELECTRON_RUN_AS_NODE", None)
        for stage in ("initial", "restart"):
            env["NEWSFLOW_STANDALONE_COVER_STAGE"] = stage
            result = subprocess.run([str(ELECTRON), str(APP / "scripts/verify-standalone-cover-topics.mjs")],
                                    cwd=APP, env=env, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=90, check=False)
            (evidence / f"{stage}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-9000:])
        initial = json.loads((evidence / "result.json").read_text())
        restarted = json.loads((evidence / "restart.json").read_text())
        self.assertEqual(restarted["ids"], initial["newIds"])
        saved = config.load_settings()
        self.assertTrue(set(initial["oldIds"]).issubset(saved.deleted_scenario_production_ids))
        self.assertEqual(saved.youtube_oauth_tokens, {"channel": "preserved-token"})
