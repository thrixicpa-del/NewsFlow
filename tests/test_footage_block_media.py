"""A curated block without shortages must retain its final video frames."""

import unittest

from scriptor.timeline import TimelineClip, TimelineProject, render_project
from tests import test_stock_render as fixture


class FootageBlockMediaTests(unittest.TestCase):
    setUp = fixture.StockRenderTests.setUp
    write_receipt = fixture.StockRenderTests.write_receipt
    run_media = fixture.StockRenderTests.run_media
    make_video = fixture.StockRenderTests.make_video
    probe = fixture.StockRenderTests.probe
    pcm = fixture.StockRenderTests.pcm

    def test_block_without_holds_has_video_until_voice_end(self):
        source = self.root / "curated.mp4"
        self.make_video(source, "blue")
        voice = self.root / "voice.wav"
        self.run_media(
            [
                self.ffmpeg,
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=3",
                str(voice),
            ]
        )
        project = TimelineProject(
            "Block tail",
            clips=[TimelineClip(str(source), "N", "Q", duration=3)],
            voiceover_path=str(voice),
            source_policy={"mode": "block", "productionItemId": "test-p"},
        )
        output = self.evidence / "block-tail.mp4"
        render_project(project, output, renderer="ffmpeg")
        video = next(
            row for row in self.probe(output)["streams"] if row["codec_type"] == "video"
        )
        self.assertEqual(
            int(video["nb_frames"]),
            90,
            "Every scene frame must survive final audio mux",
        )
        self.assertGreaterEqual(float(video["duration"]), 3)
        self.assertGreaterEqual(len(self.pcm(output)), 3 * 48000)


if __name__ == "__main__":
    unittest.main()
