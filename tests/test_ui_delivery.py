import json
from pathlib import Path
import unittest


APP_PATH = Path(__file__).resolve().parents[1] / "studio-ui-remotion-verify" / "src" / "ui" / "App.tsx"


class ActiveInterfaceTests(unittest.TestCase):
    def test_active_app_has_no_retired_components_or_system_prompt_dialogs(self):
        source = APP_PATH.read_text(encoding="utf-8")

        self.assertNotIn("function Analytics(", source)
        self.assertNotIn("function Workspace(", source)
        publication_start = source.index("function PublicationDashboard(")
        publication_end = source.index("function VoiceQueue(")
        self.assertNotIn("window.prompt(", source[publication_start:publication_end])

    def test_portable_core_uses_the_electron_bridge_entry_point(self):
        spec = (APP_PATH.parents[3] / "Scriptor.spec").read_text(encoding="utf-8")

        self.assertIn('["bridge_main.py"]', spec)
        self.assertNotIn('["main.py"]', spec)
        self.assertIn('console=True', spec)

    def test_operator_errors_hide_electron_ipc_prefix(self):
        source = APP_PATH.read_text(encoding="utf-8")

        self.assertIn("function humanCommandError(error: unknown)", source)
        self.assertIn("Error invoking remote method 'newsflow:command'", source)
        self.assertIn("const detail = humanCommandError(error);", source)

    def test_cover_screen_exposes_rate_wait_and_manual_resume_controls(self):
        source = APP_PATH.read_text(encoding="utf-8")

        self.assertIn("Продолжить очередь", source)
        self.assertIn("Автопродолжение после лимита", source)
        self.assertIn("Лимит изображений в час", source)

    def test_packaging_requires_current_runtime_contract_verification(self):
        """An EXE command must reject stale core/version/lock/runtime markers before packaging."""
        app_root = APP_PATH.parents[2]
        package = json.loads((app_root / "package.json").read_text(encoding="utf-8"))
        guard = app_root / "scripts" / "verify-build-runtime.mjs"

        self.assertIn("verify:build-runtime", package["scripts"])
        self.assertIn("pnpm verify:build-runtime", package["scripts"]["package:preview"])
        self.assertIn("pnpm verify:build-runtime", package["scripts"]["package:release"])
        source = guard.read_text(encoding="utf-8")
        self.assertIn("pnpm-lock.yaml", source)
        self.assertIn("SETTINGS_SCHEMA_VERSION", source)
        self.assertIn("thumbnail_prompt_v2.py", source)
        self.assertIn("legacyBundledCore", source)

    def test_montage_queue_spawn_failure_reaches_the_ui_command_error_path(self):
        """A failed background worker start must not be reported as a successful snapshot."""
        main = (APP_PATH.parents[2] / "electron" / "main.ts").read_text(encoding="utf-8")

        self.assertIn("function startMontageQueue(payload: unknown = {}): Promise<void>", main)
        self.assertIn("child.once('error'", main)
        self.assertIn("await startMontageQueue(payload)", main)

    def test_packaged_runtime_never_falls_back_to_a_previous_core_layout(self):
        """A current package must fail clearly instead of booting an older embedded core."""
        main = (APP_PATH.parents[2] / "electron" / "main.ts").read_text(encoding="utf-8")

        self.assertIn("const bundledCore = path.join(process.resourcesPath, 'core-bin', 'NewsFlowCore.exe');", main)
        self.assertNotIn("legacyBundledCore", main)

    def test_active_oauth_handoff_surfaces_start_and_poll_errors(self):
        """The current analytics screen must turn a rejected direct IPC call into a visible failed state."""
        source = APP_PATH.read_text(encoding="utf-8")
        active = source[source.index("function AnalyticsDashboard("):source.index("function LegacyAnalyticsDashboard(")]

        self.assertIn('state: "failed", message: humanCommandError(error)', active)
        self.assertIn('if (!current) throw new Error("Сессия входа в Google не найдена.")', active)

    def test_packaged_window_allows_the_current_narrow_workstation_layout(self):
        """The Electron host must not block the responsive AppShell before CSS can reflow it."""
        main = (APP_PATH.parents[2] / "electron" / "main.ts").read_text(encoding="utf-8")

        self.assertIn("minWidth: 720", main)
        self.assertNotIn("minWidth: 1120", main)


if __name__ == "__main__":
    unittest.main()
