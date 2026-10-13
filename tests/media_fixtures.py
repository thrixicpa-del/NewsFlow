"""Small real video fixtures for source/proxy validation contracts."""
import subprocess
from pathlib import Path

from scriptor.timeline import ffmpeg_executable


def write_readable_video(path: Path, duration: float = 8.0) -> None:
    subprocess.run([
        ffmpeg_executable(), "-y", "-v", "error", "-f", "lavfi", "-i",
        f"color=c=blue:s=64x64:r=30:d={duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], check=True, capture_output=True, timeout=30)
