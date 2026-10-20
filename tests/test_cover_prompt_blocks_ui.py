"""Actual UI import -> offline real-core rendering -> UI process restart."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge, config, session

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "studio-ui-remotion-verify"
ELECTRON = APP / "node_modules/electron/dist/electron.exe"


@unittest.skipUnless(ELECTRON.exists() and (APP / "dist/index.html").exists(), "Build source Electron/web first")
class CoverPromptBlocksUITests(unittest.TestCase):
    def test_actual_ui_import_queue_offline_images_and_restart(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1")
        with TemporaryDirectory(prefix="blocks-ui-", dir=os.environ["NEWSFLOW_TEST_ROOT"]) as directory, \
                patch.dict(os.environ, {"NEWSFLOW_TEST_ROOT": directory, "LOCALAPPDATA": directory,
                                        "TEMP": str(Path(directory) / "io"), "TMP": str(Path(directory) / "io")}):
            self.exercise_profile(Path(directory))

    def exercise_profile(self, root):
        (root / "io").mkdir()
        evidence = root / "blocks-ui"
        evidence.mkdir()
        settings = config.Settings(
            cover_output_folder=str(root / "covers"), cover_variant_count=1,
            cover_build_mode="fastgen-full", cover_auto_overlay_text=False,
            cover_api_keys=[config.FastGenKey(label="offline", secret="offline")],
            fastgen_capabilities_cache={"image": [{"id": "nano_banana_2_image_generate", "inputs": {"min": 0, "max": 10}}]},
            cover_operation="nano_banana_2_image_generate",
        )
        config.save_settings(settings)
        session.save_session([], [])
        env = {**os.environ, "NEWSFLOW_PYTHON": sys.executable, "NEWSFLOW_BLOCKS_REPORT": str(evidence / "result.json")}
        env.pop("ELECTRON_RUN_AS_NODE", None)

        def run_ui(stage):
            result = subprocess.run([str(ELECTRON), str(APP / "scripts/verify-cover-prompt-blocks.mjs")],
                                    cwd=APP, env={**env, "NEWSFLOW_BLOCKS_STAGE": stage},
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=105, check=False)
            print(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0)

        run_ui("initial")
        initial = json.loads((evidence / "result.json").read_text(encoding="utf-8"))

        def offline_image(_prompt, output, stem, *_args, **_kwargs):
            from PIL import Image
            target = Path(output) / (stem + ".png")
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (16, 16), "green").save(target)
            return [target]

        # Separate source integration stage; NOT a paid UI provider acceptance.
        with patch.object(bridge.FastGenPool, "generate_media", side_effect=offline_image) as provider, \
                patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            bridge.generate_covers({"buildMode": "fastgen-full", "productionItemIds": initial["ids"]})
            self.assertEqual(provider.call_count, 7)
        run_ui("restart")
        restarted = json.loads((evidence / "result.json.restart.json").read_text(encoding="utf-8"))
        self.assertEqual(restarted["ids"], initial["ids"])
        self.assertEqual(restarted["imageCounts"], [4, 2, 1])
        saved = config.load_settings()
        self.assertTrue(all(Path(path).is_file() for row in saved.cover_queue for path in row["paths"]))
        print("BLOCKS_UI=PASS; source offline provider=7; restart IDs/variants/images/checkbox=PASS")
