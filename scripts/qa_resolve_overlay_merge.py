"""Isolated QA merge conflict resolver. Never ship this transient helper."""
from pathlib import Path
import re

EXPECTED = {
    ".github/workflows/windows-native.yml",
    "scriptor/bridge.py",
    "scriptor/config.py",
    "scriptor/timeline.py",
    "studio-ui-remotion-verify/electron/allowed-core-commands.ts",
    "studio-ui-remotion-verify/src/contracts/newsflowCommands.ts",
    "studio-ui-remotion-verify/src/desktop.d.ts",
    "studio-ui-remotion-verify/src/ui/App.tsx",
}
CHUNKS = {}
def resolve(path: str, ours: str, theirs: str):
    pair = (ours[:145].replace("\n", " | "), theirs[:145].replace("\n", " | "))
    CHUNKS.setdefault(path, []).append(pair)
    if path == ".github/workflows/windows-native.yml":
        # Preserve original coverage and append only one overlay acceptance.
        source = theirs[theirs.find("      - name: Isolated actual overlay UI"):]
        assert "test_overlay_source_ui" in source
        return ours + source
    if path == "scriptor/bridge.py":
        if "from copy import copy" in ours and "from copy import deepcopy" in theirs:
            return "from copy import copy, deepcopy\n"
        if "def save_montage_stock_keys" in ours and "def _montage_overlay_edit_lock" in theirs:
            return ours + theirs
        if "if settings.montage_export_davinci_xml" in ours and "overlay_layers" in theirs:
            s = theirs.replace("if settings.montage_export_davinci_xml:", "if settings.montage_export_davinci_xml and not project.manual_replacements:")
            return s
        if "manualReplacements" in ours and '"warning"' in theirs:
            return ours + theirs
        if "tail_added = 0 if project.source_policy" in ours and "if render_only:" in theirs:
            return theirs.replace("tail_added = _complete_project_visual_tail(", "tail_added = 0 if project.source_policy else _complete_project_visual_tail(")
    if path == "scriptor/config.py":
        if '"montage_use_footage_blocks"' in ours and '"montage_overlay_template"' in theirs:
            return ours + theirs
    if path == "scriptor/timeline.py":
        if "source_policy:" in ours and "overlay_template:" in theirs:
            return ours + theirs
        if "if project.manual_replacements:" in ours and "def _render_project_base" in theirs:
            assert "    layers = overlay_layers(" in theirs
            return theirs.replace("    layers = overlay_layers(", '    if project.manual_replacements:\n        raise ValueError("Требуется ручная замена отмеченных сцен")\n    layers = overlay_layers(', 1)
    if path == "studio-ui-remotion-verify/electron/allowed-core-commands.ts":
        if "save-footage-block" in ours and "save-montage-overlays" in theirs:
            return ours.replace('"save-montage-settings",', '"save-montage-settings", "save-montage-overlays", "scan-montage-overlays",')
    if path == "studio-ui-remotion-verify/src/contracts/newsflowCommands.ts":
        if "save-footage-block" in ours and "save-montage-overlays" in theirs:
            return ours.replace('"save-montage-settings",', '"save-montage-settings", "save-montage-overlays", "scan-montage-overlays",')
        if "save-browser-topic-scenario-settings" in ours and "scan-montage-overlays" in theirs:
            new = '\n'.join(l for l in theirs.splitlines() if '"scan-montage-overlays"' in l or '"save-montage-overlays"' in l) + '\n'
            return new + ours
        if '"run-montage-queue"' in ours and "renderOnly?: boolean" in theirs:
            return ours.replace('replaceOutput?: boolean', 'replaceOutput?: boolean; renderOnly?: boolean')
        if "preparedProject?:" in ours and "skippedIndices?:" in theirs:
            return ours.replace("preparedProject?: { title:", "preparedProject?: { warning?: string; title:").replace("operationResult?: { previewToken?: string;", 'operationResult?: { previewToken?: string; skippedIndices?: number[]; assets?: Array<{ path: string; kind: "image" | "video"; name: string }>; skippedSymlinks?: number;')
    if path == "studio-ui-remotion-verify/src/desktop.d.ts":
        # Keep each new declaration, dedup only the common selected property.
        ol=ours.splitlines(keepends=True)
        ts=theirs.splitlines(keepends=True)
        extra=[line for line in ts if line.strip() and line not in ol]
        return ours + ''.join(extra)
    if path == "studio-ui-remotion-verify/src/ui/App.tsx":
        if "pendingMontageLaunches" in ours and "overlayExportWatch" in theirs and "queueActive" not in ours:
            return ours + theirs
        if "const queueActive" in ours and "overlayExportWatch" in theirs:
            without_queue='\n'.join(theirs.splitlines(keepends=True)[1:])
            return ours.replace("pendingMontageLaunches.length > 0", "pendingMontageLaunches.length > 0 || overlayExportWatch !== null") + without_queue
        if "projectContinuitySummary" in ours and "individualOverlayTask" in theirs:
            return ours + theirs
    raise RuntimeError(f"UNREVIEWED conflict {path}: OURS {pair[0]} THEIRS {pair[1]}")

def apply(path: str):
    raw=Path(path).read_text(encoding="utf-8")
    pat=re.compile(r"(?m)^<<<<<<< HEAD\n(.*?)^=======\n(.*?)^>>>>>>> origin/codex/montage-overlays\n",re.S|re.M)
    matches=list(pat.finditer(raw))
    if not matches:
        raise RuntimeError(f"No Git conflict markers: {path}")
    rewritten=pat.sub(lambda match: resolve(path, match.group(1), match.group(2)), raw)
    if "<<<<<<<" in rewritten or ">>>>>>>" in rewritten or "=======" in rewritten and path not in {".github/workflows/windows-native.yml"}:
        if "<<<<<<<" in rewritten or ">>>>>>>" in rewritten:
            raise RuntimeError(f"Unresolved marker in {path}")
    Path(path).write_text(rewritten,encoding="utf-8")
    print(f"QA_RESOLVED={path} hunks={len(matches)}")

if __name__ == "__main__":
    import sys
    received=set(sys.argv[1:])
    assert received == EXPECTED, f"Unexpected conflicts: {received ^ EXPECTED}"
    for path in sorted(received):
        apply(path)
    for path,chunks in CHUNKS.items():
        print(f"QA_REVIEW={path} {len(chunks)} hunk(s)")
