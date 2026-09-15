import sys
import tempfile
import traceback


def self_test() -> int:
    import subprocess
    import tempfile
    from pathlib import Path
    from scriptor.ai_index import ClipIndex
    from scriptor.timeline import ffmpeg_executable

    with tempfile.TemporaryDirectory(prefix="newsflow-self-test-") as folder:
        root = Path(folder)
        clips = root / "clips"
        clips.mkdir()
        for color in ("red", "blue"):
            subprocess.run([
                ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d=1:r=30",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clips / f"{color}.mp4"),
            ], check=True)
        index = ClipIndex(root / "index.sqlite3")
        index.index_folders([str(clips)])
        red = index.search("solid bright red background", limit=1)
        blue = index.search("solid bright blue background", limit=1)
        if not red or not blue:
            raise RuntimeError("ИИ-индекс не вернул результаты")
        if Path(red[0].item.path).name != "red.mp4" or Path(blue[0].item.path).name != "blue.mp4":
            raise RuntimeError("ИИ-индекс неверно сопоставил тестовые кадры")
    print("NEWSFLOW_SELF_TEST_OK")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        try:
            raise SystemExit(self_test())
        except SystemExit:
            raise
        except Exception:
            log_path = tempfile.gettempdir() + "\\NewsFlow-self-test.log"
            with open(log_path, "w", encoding="utf-8") as log:
                traceback.print_exc(file=log)
            raise SystemExit(1)
    from scriptor.app import ScriptorApp
    ScriptorApp().run()
