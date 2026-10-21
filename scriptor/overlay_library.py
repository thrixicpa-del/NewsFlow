"""Read-only discovery for explicitly selected local overlay directories."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from .overlays import _local_path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _is_link(path: Path) -> bool:
    """Windows junctions/reparse points must also be excluded from recursion."""
    return path.is_symlink() or bool(
        getattr(path.lstat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def scan_overlay_library(folder) -> dict:
    """List supported files without decoding media or mutating the directory.

    Directory errors are explicit rather than returning an apparently complete
    partial pool. Nested links (including Windows junctions) are never followed.
    """
    value = _local_path(folder)
    root = Path(value)
    if not value or not root.is_absolute() or not root.is_dir():
        raise ValueError("Наложения: выберите существующую локальную корневую папку")
    root = root.resolve()
    # Reject network targets even when the user selected a local directory link.
    _local_path(str(root))
    assets, skipped = [], 0
    pending = [root]
    try:
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                paths = sorted((Path(entry.path) for entry in entries), key=lambda p: (p.name.casefold(), p.name))
            for path in paths:
                if _is_link(path):
                    skipped += 1
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(root):
                    skipped += 1
                    continue
                if path.is_dir():
                    pending.append(path)
                elif path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                    assets.append({"path": str(resolved), "name": path.name,
                                   "kind": "image" if path.suffix.lower() in IMAGE_EXTENSIONS else "video"})
    except OSError as error:
        raise ValueError(f"Наложения: не удалось прочитать папку: {error}") from error
    assets.sort(key=lambda item: (item["path"].casefold(), item["path"]))
    return {"folder": str(root), "assets": assets, "count": len(assets), "skippedSymlinks": skipped}
