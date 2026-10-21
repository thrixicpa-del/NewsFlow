"""Actual source Electron -> trusted IPC -> Python -> protected settings smoke."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "studio-ui-remotion-verify"


@unittest.skipUnless(os.environ.get("NEWSFLOW_RUN_ELECTRON_E2E") == "1", "set NEWSFLOW_RUN_ELECTRON_E2E=1")
class StockSourcesUISmokeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1")
        self.assertTrue(os.environ.get("NEWSFLOW_PRODUCTION_LOCALAPPDATA"), "Use tests/run_isolated.py")
        outer = Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()
        self.root = Path(tempfile.mkdtemp(prefix="stock-sources-ui-", dir=outer)).resolve()
        self.local = self.root / "local-app-data"
        self.artifacts = self.root / "artifacts"
        for name in ("local-app-data", "roaming-app-data", "io", "artifacts"):
            (self.root / name).mkdir()
        self.env = {**os.environ, "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": str(self.root),
                    "LOCALAPPDATA": str(self.local), "APPDATA": str(self.root / "roaming-app-data"),
                    "TEMP": str(self.root / "io"), "TMP": str(self.root / "io"), "TMPDIR": str(self.root / "io"),
                    "NEWSFLOW_PYTHON": sys.executable, "PYTHONIOENCODING": "utf-8"}
        self.env.pop("ELECTRON_RUN_AS_NODE", None)
        self.electron = UI_ROOT / "node_modules/electron/dist" / ("electron.exe" if os.name == "nt" else "electron")
        for required in (self.electron, UI_ROOT / "dist/index.html", UI_ROOT / "dist-electron/main.js", UI_ROOT / "dist-electron/preload.cjs"):
            self.assertTrue(required.is_file(), f"Build source prerequisites first: {required}")
        self.evidence = ROOT / ".superpowers/stock-sources/electron" / uuid.uuid4().hex
        self.addCleanup(self._preserve_evidence)

    def _preserve_evidence(self):
        self.evidence.mkdir(parents=True)
        shutil.copytree(self.artifacts, self.evidence, dirs_exist_ok=True)
        print(f"STOCK_SOURCES_UI_EVIDENCE={self.evidence}", flush=True)

    def _stage(self, stage):
        process = subprocess.Popen([str(self.electron), str(UI_ROOT / "scripts/verify-stock-sources-ui.mjs"), stage],
                                   cwd=UI_ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace")
        try:
            stdout, stderr = process.communicate(timeout=150)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15, check=False)
            else:
                process.kill()
            stdout, stderr = process.communicate(timeout=15)
            (self.artifacts / f"{stage}.timeout.stdout.log").write_text(stdout, encoding="utf-8")
            (self.artifacts / f"{stage}.timeout.stderr.log").write_text(stderr, encoding="utf-8")
            self.fail(f"Owned Electron stage timed out: {stage}\n{stdout[-3000:]}\n{stderr[-3000:]}")
        (self.artifacts / f"{stage}.stdout.log").write_text(stdout, encoding="utf-8")
        (self.artifacts / f"{stage}.stderr.log").write_text(stderr, encoding="utf-8")
        self.assertEqual(process.returncode, 0, stdout[-6000:] + stderr[-6000:])
        result = json.loads((self.artifacts / f"{stage}.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "PASS", result.get("error"))
        self.assertEqual(result["unexpectedCommands"], [])
        self.assertEqual(result["externalRequests"], [])
        return result

    def test_sources_trim_and_protected_keys_survive_full_process_restart(self):
        subprocess.run([sys.executable, "-c", "import os; from pathlib import Path; from scriptor.config import Settings,save_settings; output=Path(os.environ['NEWSFLOW_TEST_ROOT'])/'io'/'outputs'; output.mkdir(); save_settings(Settings(montage_renderer='ffmpeg', montage_output_folder=str(output), pipeline_target_count=137, cover_rate_auto_resume=False))"],
                       cwd=ROOT, env=self.env, capture_output=True, check=True, timeout=30)
        seed = """
import os
from pathlib import Path
from types import SimpleNamespace
from scriptor.config import app_data_root
from scriptor.stock_downloads import StockDownloadQueue
root = Path(os.environ['NEWSFLOW_TEST_ROOT'])
def fetch(candidate, *, progress, **kwargs):
    progress(1048576)
    return root / 'synthetic-original.mp4'
service = SimpleNamespace(root=root, fetch=fetch)
candidate = SimpleNamespace(provider='nasa', kind='video', asset_id='offline')
with StockDownloadQueue(7, app_data_root() / 'stock-download-status.json') as queue:
    queue.result(queue.submit(service, candidate))
"""
        subprocess.run([sys.executable, "-B", "-c", seed], cwd=ROOT, env=self.env,
                       capture_output=True, check=True, timeout=10)
        configured = self._stage("configure")
        restarted = self._stage("restart")
        self.assertEqual(configured['downloadStatus']['runId'], restarted['downloadStatus']['runId'])
        self.assertEqual(restarted['downloadStatus']['completed'], 1)
        self.assertEqual(configured["finalSettings"], restarted["finalSettings"])
        self.assertEqual(restarted["finalSettings"]["sourceMode"], "stock")
        self.assertEqual(restarted["finalSettings"]["stockSources"], ["pexels", "wikimedia", "nasa"])
        self.assertFalse(restarted["finalSettings"]["stockTrim"])
        self.assertFalse(restarted["finalSettings"]["stockUseLibrary"])
        self.assertTrue(Path(restarted["finalSettings"]["stockLibraryFolder"]).is_relative_to(self.root))
        rows = restarted["finalSettings"]["stockKeys"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(key["active"] for key in rows), 2)
        raw = (self.local / "NewsFlow/settings.json").read_text(encoding="utf-8")
        for secret in ("synthetic-pexels-one", "synthetic-pexels-two", "synthetic-pixabay-one", "synthetic-pixabay-two"):
            self.assertNotIn(secret, raw)
            for artifact in self.artifacts.glob("*.json"):
                self.assertNotIn(secret, artifact.read_text(encoding="utf-8"))
