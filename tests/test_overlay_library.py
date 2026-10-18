"""The folder picker reads local metadata without traversing linked libraries."""
import hashlib
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class OverlayLibraryTests(unittest.TestCase):
    def setUp(self):
        self.scan = importlib.import_module("scriptor.overlay_library").scan_overlay_library
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_recursive_supported_files_sorted_without_decoding_or_modifying(self):
        for name in ("b.MP4", "nested/a.PNG", "nested/z.jpeg", "ignored.txt", "clip.webm"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"metadata only, deliberately not decodable media")
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob("*") if p.is_file()}
        value = self.scan(str(self.root))
        self.assertEqual(value["folder"], str(self.root.resolve()))
        self.assertEqual(value["count"], 4)
        self.assertEqual([a["name"] for a in value["assets"]], ["b.MP4", "clip.webm", "a.PNG", "z.jpeg"])
        self.assertEqual([a["kind"] for a in value["assets"]], ["video", "video", "image", "image"])
        self.assertTrue(all(Path(a["path"]).is_absolute() for a in value["assets"]))
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})

    def test_invalid_paths_and_nonfolders_fail_visibly(self):
        file = self.root / "file.png"
        file.touch()
        for folder in ("", ".", "https://example.com/assets", "file:///tmp/assets", r"\\server\assets", str(file), str(self.root / "missing"), None):
            with self.subTest(folder=folder), self.assertRaises(ValueError):
                self.scan(folder)

    def test_empty_folder_is_valid(self):
        self.assertEqual(self.scan(str(self.root))["assets"], [])

    def test_linked_files_and_directories_are_skipped(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.png").touch()
        selected = self.root / "selected"
        selected.mkdir()
        (selected / "safe.jpg").touch()
        try:
            (selected / "link").symlink_to(outside, target_is_directory=True)
            (selected / "linked.png").symlink_to(outside / "secret.png")
        except OSError as error:
            self.skipTest(f"Local symlink creation unavailable: {error}")
        value = self.scan(str(selected))
        self.assertEqual([a["name"] for a in value["assets"]], ["safe.jpg"])
        self.assertEqual(value["skippedSymlinks"], 2)

    def test_windows_reparse_point_detection_is_not_only_symlink_detection(self):
        module = importlib.import_module("scriptor.overlay_library")
        fake = type("Stat", (), {"st_file_attributes": 0x400})()
        with patch.object(Path, "lstat", return_value=fake), patch.object(Path, "is_symlink", return_value=False):
            self.assertTrue(module._is_link(self.root))

    def test_inaccessible_directory_is_error_not_silent_partial_success(self):
        with patch("os.scandir", side_effect=PermissionError("denied")), self.assertRaisesRegex(ValueError, "прочитать"):
            self.scan(str(self.root))


if __name__ == "__main__":
    unittest.main()
