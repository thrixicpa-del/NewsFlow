from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class FeatureFlagTests(unittest.TestCase):
    def test_flags_default_to_stable_and_require_explicit_known_name(self):
        from scriptor.feature_flags import FeatureFlagError, enabled_flags, is_enabled

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(frozenset(), enabled_flags())
            self.assertFalse(is_enabled("montage_v3"))

        with patch.dict(os.environ, {"NEWSFLOW_FEATURE_FLAGS": "montage_v3"}, clear=True):
            self.assertTrue(is_enabled("montage_v3"))

        with (
            patch.dict(os.environ, {"NEWSFLOW_FEATURE_FLAGS": "unknown_experiment"}, clear=True),
            self.assertRaises(FeatureFlagError),
        ):
            enabled_flags()
