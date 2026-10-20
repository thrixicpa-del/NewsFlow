"""Actual isolated React -> Electron IPC -> Python persistence/cancel smoke.

Build source web/desktop first, then run through tests/run_isolated.py with
NEWSFLOW_RUN_ELECTRON_E2E=1. This suite never starts browser generation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "studio-ui-remotion-verify"
pytestmark = pytest.mark.integration


@unittest.skipUnless(os.environ.get("NEWSFLOW_RUN_ELECTRON_E2E") == "1", "set NEWSFLOW_RUN_ELECTRON_E2E=1")
class BrowserDocumentsUISmokeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1")
        outer_root = Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()
        outer_root.mkdir(parents=True, exist_ok=True)
        # Keep evidence under the runner's disposable root, never another
        # suite's profile. Every restart deliberately reuses only this root.
        self.root = Path(tempfile.mkdtemp(prefix="browser-documents-ui-", dir=outer_root)).resolve()
        self.local = self.root / "local-app-data"
        self.roaming = self.root / "roaming-app-data"
        self.io = self.root / "io"
        self.artifacts = self.root / "artifacts"
        fixtures = self.root / "fixtures"
        for directory in (self.local, self.roaming, self.io, self.artifacts, fixtures):
            directory.mkdir()
        self.files = [fixtures / name for name in ("требования.txt", "structure.txt", "style.md")]
        for index, path in enumerate(self.files):
            path.write_text(f"Synthetic offline requirement {index}. No provider calls.\n", encoding="utf-8")
        production = os.environ.get("NEWSFLOW_PRODUCTION_LOCALAPPDATA")
        self.assertTrue(production, "run through tests/run_isolated.py to establish the production boundary")
        self.env = {**os.environ, "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": str(self.root),
                    "LOCALAPPDATA": str(self.local), "APPDATA": str(self.roaming), "TEMP": str(self.io), "TMP": str(self.io),
                    "TMPDIR": str(self.io), "NEWSFLOW_PYTHON": sys.executable, "PYTHONIOENCODING": "utf-8",
                    "NEWSFLOW_BROWSER_DOCUMENTS_FIXTURES": json.dumps([str(path) for path in self.files]),
                    "NEWSFLOW_BROWSER_DOCUMENTS_OWNER": str(os.getpid())}
        self.env.pop("ELECTRON_RUN_AS_NODE", None)
        self.electron = UI_ROOT / "node_modules" / "electron" / "dist" / ("electron.exe" if os.name == "nt" else "electron")
        for required in (self.electron, UI_ROOT / "dist" / "index.html", UI_ROOT / "dist-electron" / "main.js", UI_ROOT / "dist-electron" / "preload.cjs"):
            self.assertTrue(required.is_file(), f"Build/install source Electron prerequisites first: {required}")
        self.owner_token = uuid.uuid4().hex
        self.lock = self.local / "NewsFlow" / "browser-topic-scenarios.lock"
        self.addCleanup(self._remove_owned_lock)

    def _remove_owned_lock(self):
        if self.lock.exists():
            owner = json.loads(self.lock.read_text(encoding="utf-8"))
            self.assertEqual(owner.get("pid"), os.getpid())
            self.assertEqual(owner.get("testOwner"), self.owner_token)
            self.lock.unlink()  # Exact fixture path only; no recursive deletion.

    def _stage(self, stage: str) -> dict:
        process = subprocess.Popen(
            [str(self.electron), str(UI_ROOT / "scripts" / "verify-browser-documents.mjs"), stage],
            cwd=UI_ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
        try:
            stdout, stderr = process.communicate(timeout=150)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                # Kill only this exact spawned Electron process tree.
                subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=15, check=False)
            else:
                process.kill()
            stdout, stderr = process.communicate(timeout=15)
            self.fail(f"Owned Electron stage timed out: {stage}\n{stdout[-3000:]}\n{stderr[-3000:]}")
        (self.artifacts / f"{stage}.stdout.log").write_text(stdout, encoding="utf-8")
        (self.artifacts / f"{stage}.stderr.log").write_text(stderr, encoding="utf-8")
        self.assertEqual(process.returncode, 0, stdout[-6000:] + stderr[-6000:])
        evidence = json.loads((self.artifacts / f"{stage}.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["unexpectedCommands"], [])
        self.assertEqual(evidence["externalRequests"], [])
        return evidence

    def _saved_files(self) -> tuple[list[str], str]:
        settings = json.loads((self.local / "NewsFlow" / "settings.json").read_text(encoding="utf-8"))
        saved = settings["browser_topic_scenarios"]
        return saved["requirements_files"], saved["requirements_file"]

    def test_choose_persist_restart_remove_clear_and_cancel_without_generation(self):
        # Seed only disposable storage and explicitly disable unrelated auto work.
        subprocess.run([sys.executable, "-c",
                        ("from scriptor.config import Settings,save_settings; "
                         "save_settings(Settings(montage_renderer='ffmpeg', cover_rate_auto_resume=False))")],
                       cwd=ROOT, env=self.env, check=True, capture_output=True, timeout=30)
        self.lock.write_text(json.dumps({"pid": os.getpid(), "testOwner": self.owner_token, "cancelled": False}), encoding="utf-8")
        selected = self._stage("choose-and-cancel")
        self.assertTrue(selected["initialRunning"])
        self.assertEqual(selected["chooserCalls"], 1)
        self.assertEqual(self._saved_files(), ([str(path) for path in self.files], str(self.files[0])))
        self.assertTrue(json.loads(self.lock.read_text(encoding="utf-8"))["cancelled"])
        self._remove_owned_lock()

        restarted = self._stage("restart-remove")
        self.assertFalse(restarted["initialRunning"])
        self.assertEqual(restarted["initialFiles"], [str(path) for path in self.files])
        self.assertEqual(self._saved_files(), ([str(path) for path in self.files[1:]], str(self.files[1])))

        self._stage("restart-clear")
        self.assertEqual(self._saved_files(), ([], ""))
        empty = self._stage("restart-empty")
        self.assertEqual(empty["initialFiles"], [])
        self.assertEqual(empty["finalFiles"], [])
        self.assertEqual(self._saved_files(), ([], ""))
