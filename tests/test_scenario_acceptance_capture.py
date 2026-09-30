import tempfile
import unittest
from pathlib import Path

from scripts.capture_scenario_acceptance import _write_text


class ScenarioAcceptanceCaptureTests(unittest.TestCase):
    def test_visible_evidence_text_keeps_its_original_newline_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario.txt"
            _write_text(path, "Первая строка\nВторая строка\n")
            self.assertEqual(
                path.read_bytes(),
                "Первая строка\nВторая строка\n".encode(),
            )


if __name__ == "__main__":
    unittest.main()
