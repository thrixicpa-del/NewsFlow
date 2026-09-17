"""Audit that every required simulated failure class has a concrete regression test."""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


class FailureMatrixTests(unittest.TestCase):
    def test_controlled_failure_matrix_points_to_real_test_methods(self):
        root = Path(__file__).resolve().parents[1]
        matrix = json.loads((Path(__file__).with_name("failure-matrix.json")).read_text(encoding="utf-8"))
        self.assertEqual(1, matrix["format"])
        required = {
            "openai-timeout-or-quota", "fastgen-429-or-timeout", "voice-provider-timeout",
            "youtube-downstream-failure", "invalid-audio", "invalid-footage", "ffmpeg-failure",
            "restart-during-job", "missing-output", "partial-provider-response",
        }
        self.assertEqual(required, {row["id"] for row in matrix["scenarios"]})
        for row in matrix["scenarios"]:
            source = root / row["source"]
            self.assertTrue(source.is_file(), row)
            functions = {
                node.name for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            self.assertIn(row["test"], functions, row)


if __name__ == "__main__":
    unittest.main()
