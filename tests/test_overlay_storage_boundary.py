"""The canonical runner isolates render caches as well as settings storage."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests import run_isolated


class OverlayStorageBoundaryTests(unittest.TestCase):
    def test_render_workspace_never_inherits_the_production_cache(self):
        for arguments in (["tests.test_overlay_library"], ["--pytest", "-q"]):
            with self.subTest(arguments=arguments), tempfile.TemporaryDirectory() as temporary:
                production = Path(temporary) / "production"
                cache = production / "render-cache"

                def child(command, *, env, check, cache=cache, production=production, arguments=arguments):
                    root = Path(env["NEWSFLOW_TEST_ROOT"])
                    target = Path(env["NEWSFLOW_RENDER_TEMP_ROOT"])
                    self.assertTrue(root.is_absolute())
                    self.assertTrue(target.is_relative_to(root))
                    self.assertNotEqual(target, cache)
                    self.assertEqual(Path(env["LOCALAPPDATA"]), root)
                    self.assertEqual(Path(env["TMPDIR"]), root)
                    self.assertEqual(env["NEWSFLOW_PRODUCTION_LOCALAPPDATA"], str(production))
                    self.assertFalse(check)
                    self.assertEqual(command[2], "pytest" if arguments[0] == "--pytest" else "unittest")
                    return SimpleNamespace(returncode=0)

                with patch.dict(os.environ, {"LOCALAPPDATA": str(production), "NEWSFLOW_RENDER_TEMP_ROOT": str(cache), "TMPDIR": str(cache)}), \
                     patch.object(run_isolated.subprocess, "run", side_effect=child):
                    self.assertEqual(run_isolated.main(arguments), 0)
                self.assertFalse(production.exists(), "Test must not create a production render/cache directory")
