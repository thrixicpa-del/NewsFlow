"""Direct Remotion invocations must never silently discard requested layers."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "studio-ui-remotion-verify/remotion/render.mjs"


@unittest.skipUnless(
    shutil.which("node")
    and (ROOT / "studio-ui-remotion-verify/node_modules/@remotion/renderer").exists(),
    "Node/Remotion runtime unavailable",
)
class StandaloneOverlayContractTests(unittest.TestCase):
    def test_inactive_source_layers_preserve_the_remotion_fast_path(self):
        for source in ({"enabled": False, "kind": "all"}, {"enabled": True, "kind": "video"}):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest, output = root / "manifest.json", root / "output.mp4"
                manifest.write_text(json.dumps({"fps": 30, "aspectRatio": "16:9", "durationInFrames": 1,
                    "sequences": [], "voiceover": {"src": "", "from": 0}, "requiresOverlayFinishing": False,
                    "overlayTemplate": {"version": 1, "librarySources": [{"id": "disabled", **source}],
                        "layouts": {"16:9": [{"enabled": True, "kind": "image", "librarySourceId": "disabled", "path": "missing.png"}]}}}), encoding="utf-8")
                result = subprocess.run([shutil.which("node"), str(RUNNER), str(manifest), str(output)],
                    check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
                self.assertNotIn("OVERLAY_FINISHING_REQUIRED", result.stdout + result.stderr)
                self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-2000:])
                self.assertTrue(output.is_file())

    def check_rejected(self, extra):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "manifest.json"
            output = root / "output.mp4"
            payload = {
                "fps": 30,
                "aspectRatio": "16:9",
                "durationInFrames": 1,
                "sequences": [],
                "voiceover": {"src": "", "from": 0},
                **extra,
            }
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [shutil.which("node"), str(RUNNER), str(manifest), str(output)],
                check=False, capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            )
            self.assertNotEqual(
                result.returncode, 0, "Requested layers were silently discarded"
            )
            self.assertIn("OVERLAY_FINISHING_REQUIRED", result.stdout + result.stderr)
            self.assertFalse(
                output.exists(), "Must reject before publishing an incomplete output"
            )

    def test_enabled_layer_requires_shared_finishing_even_without_marker(self):
        self.check_rejected(
            {
                "overlayTemplate": {
                    "version": 1,
                    "layouts": {
                        "16:9": [{"enabled": True, "path": "example.png"}],
                        "9:16": [],
                    },
                }
            }
        )

    def test_legacy_layer_is_not_silently_lost(self):
        self.check_rejected({"overlay": {"src": "example.mp4"}})

    def test_explicit_finishing_marker_is_honoured(self):
        self.check_rejected({"requiresOverlayFinishing": True})
