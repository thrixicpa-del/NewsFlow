import unittest
import tempfile
from pathlib import Path

from scriptor.mixer import make_mix_plans


class MixerTests(unittest.TestCase):
    def test_plans_are_unique_and_use_requested_number_of_clips(self):
        with tempfile.TemporaryDirectory() as temporary:
            clips = []
            for index in range(8):
                path = Path(temporary) / f"{index}.mp4"
                path.touch()
                clips.append(str(path))
            plans = make_mix_plans(clips, 3, 5, seed=7)
            self.assertEqual(len(plans), 5)
            self.assertTrue(all(len(plan) == 3 for plan in plans))
            self.assertEqual(len({tuple(plan) for plan in plans}), 5)
