from __future__ import annotations

import random
import subprocess
import sys
import tempfile
from pathlib import Path

from .core import safe_filename
from .timeline import ffmpeg_executable


def make_mix_plans(clips: list[str], clips_per_video: int, output_count: int, seed: int | None = None) -> list[list[str]]:
    pool = list(dict.fromkeys(str(Path(path).resolve()) for path in clips if Path(path).is_file()))
    if clips_per_video < 1 or clips_per_video > len(pool):
        raise ValueError("Количество клипов в варианте должно быть от 1 до числа доступных клипов")
    if output_count < 1 or output_count > 1000:
        raise ValueError("Количество вариаций должно быть от 1 до 1000")
    generator = random.Random(seed)
    plans: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    attempts = 0
    while len(plans) < output_count and attempts < output_count * 50:
        attempts += 1
        plan = generator.sample(pool, clips_per_video)
        generator.shuffle(plan)
        signature = tuple(plan)
        if signature not in seen:
            seen.add(signature)
            plans.append(plan)
    if len(plans) < output_count:
        raise ValueError("Недостаточно уникальных сочетаний для указанного числа вариаций")
    return plans


def render_mixes(plans: list[list[str]], output_folder: Path, progress=None) -> list[Path]:
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    created: list[Path] = []
    for number, plan in enumerate(plans, 1):
        target = output_folder / f"Вариация {number:03d}.mp4"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as handle:
            listing = Path(handle.name)
            for path in plan:
                safe_path = str(Path(path).resolve()).replace("'", "'\\''")
                handle.write(f"file '{safe_path}'\n")
        try:
            command = [ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                       "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(target)]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    creationflags=flags)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout or "FFmpeg завершился с ошибкой")[-2500:])
            created.append(target)
            if progress:
                progress({"done": number, "total": len(plans), "path": str(target)})
        finally:
            listing.unlink(missing_ok=True)
    return created
