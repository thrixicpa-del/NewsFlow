from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptRange:
    start: int
    end: int
    prompt: str
    target_chars: int = 0
    allowed_min: int = 0
    allowed_max: int = 0

    def __post_init__(self):
        if self.start < 1 or self.end < self.start:
            raise ValueError("Некорректный диапазон")
        if any(value < 0 for value in (self.target_chars, self.allowed_min, self.allowed_max)):
            raise ValueError("Длина сценария не может быть отрицательной")
        if self.allowed_min and self.allowed_max and self.allowed_min > self.allowed_max:
            raise ValueError("Минимальная длина больше максимальной")


@dataclass(frozen=True)
class ScenarioRequest:
    index: int
    title: str
    prompt: str
    # The title can be edited, duplicated or normalised; descendants use the
    # immutable ProductionItem ID when it is available.
    production_item_id: str = ""
    target_chars: int = 0
    allowed_min: int = 0
    allowed_max: int = 0


def _normalise_character_contract(target: int = 0, minimum: int = 0,
                                  maximum: int = 0) -> tuple[int, int, int] | None:
    """Return a usable target/bounds tuple without inventing unrelated limits."""
    target = max(0, int(target or 0))
    minimum = max(0, int(minimum or 0))
    maximum = max(0, int(maximum or 0))
    if minimum and maximum and minimum > maximum:
        raise ValueError("Минимальная длина больше максимальной")
    if target:
        minimum = minimum or max(1, int(target * .9))
        maximum = maximum or max(minimum, int(target * 1.1))
        if target < minimum or target > maximum:
            raise ValueError("Целевая длина должна находиться внутри допустимого диапазона")
    elif minimum and maximum:
        target = (minimum + maximum) // 2
    elif minimum:
        target = minimum
    elif maximum:
        target = maximum
    else:
        return None
    return target, minimum, maximum


def _explicit_character_contract(prompt: str) -> tuple[int, int, int] | None:
    """Read an explicit human character contract without treating arbitrary numbers as one.

    Structured Prompt Studio fields have priority. This compatibility bridge
    supports both an explicit range and a single target such as 10 000 symbols.
    A single target receives the same +/-10% tolerance as the structured control.
    """
    text = str(prompt or "")
    for match in re.finditer(r"(?P<minimum>\d[\d\s\u00a0]{0,8})\s*(?:-|–|—|to)\s*(?P<maximum>\d[\d\s\u00a0]{0,8})", text, re.IGNORECASE):
        nearby = text[max(0, match.start() - 120):match.end() + 120].casefold()
        if not re.search(r"символ|знак|character", nearby):
            continue
        minimum = int(re.sub(r"\D", "", match.group("minimum")))
        maximum = int(re.sub(r"\D", "", match.group("maximum")))
        if 0 < minimum <= maximum:
            return (minimum + maximum) // 2, minimum, maximum
    for match in re.finditer(
        r"(?P<target>\d[\d\s\u00a0]{0,8})\s*(?:символ(?:ов|а)?|знак(?:ов|а)?|characters?)",
        text,
        re.IGNORECASE,
    ):
        target = int(re.sub(r"\D", "", match.group("target")))
        if target > 0:
            return _normalise_character_contract(target)
    return None


def read_text_file(path: Path | str) -> str:
    file_path = Path(path)
    if file_path.suffix.lower() != ".txt":
        raise ValueError("Можно перетаскивать только TXT-файлы")
    raw = file_path.read_bytes()
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Не удалось определить кодировку TXT-файла")


def parse_titles(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    titles = [re.sub(r"\s+", " ", line).strip() for line in normalized.split("\n")]
    titles = [title for title in titles if title]
    return titles


def build_requests(titles: list[str], template: str, ranges: list[PromptRange],
                   default_target_chars: int = 0, default_allowed_min: int = 0,
                   default_allowed_max: int = 0) -> list[ScenarioRequest]:
    if not template.strip():
        raise ValueError("Заполните общий шаблон")
    result = []
    default_contract = _normalise_character_contract(
        default_target_chars, default_allowed_min, default_allowed_max,
    )
    for position, title in enumerate(titles, start=1):
        base = template.replace("{title}", title) if "{title}" in template else f"{template.rstrip()}\n\nНазвание сценария: {title}"
        applicable = [item for item in ranges if item.start <= position <= item.end]
        extras = [item.prompt.strip() for item in applicable if item.prompt.strip()]
        length_range = next((item for item in reversed(applicable)
                             if item.target_chars or item.allowed_min or item.allowed_max), None)
        if length_range:
            contract = _normalise_character_contract(
                length_range.target_chars, length_range.allowed_min, length_range.allowed_max,
            )
        elif default_contract:
            contract = default_contract
        else:
            contract = _explicit_character_contract(template)
        if contract:
            target, minimum, maximum = contract
            bounds = (
                f"{minimum}–{maximum}" if minimum and maximum
                else f"не менее {minimum}" if minimum
                else f"не более {maximum}"
            )
            extras.append(
                f"Runtime-проверка длины: цель {target} символов; "
                f"допустимо строго {bounds} символов."
            )
        prompt = base + ("\n\nДополнительные требования:\n" + "\n".join(extras) if extras else "")
        result.append(ScenarioRequest(
            position - 1, title, prompt,
            target_chars=contract[0] if contract else 0,
            allowed_min=contract[1] if contract else 0,
            allowed_max=contract[2] if contract else 0,
        ))
    return result


def safe_filename(title: str, fallback: str = "Сценарий") -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    name = re.sub(r"\s+", " ", name).strip(" .")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if not name or name.upper() in reserved:
        name = fallback
    return name[:120].rstrip(" .")


def write_exports(folder: Path, results: list[tuple[str, str]]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    used: set[str] = set()
    sections = []
    for number, (title, content) in enumerate(results, start=1):
        stem = safe_filename(title, f"Сценарий {number}")
        candidate = stem
        suffix = 2
        while candidate.casefold() in used:
            candidate = f"{stem} ({suffix})"
            suffix += 1
        used.add(candidate.casefold())
        path = folder / f"{candidate}.txt"
        path.write_text(content.strip() + "\n", encoding="utf-8")
        paths.append(path)
        sections.append(f"{title}\n{'=' * len(title)}\n\n{content.strip()}")
    combined = folder / "Все сценарии.txt"
    combined.write_text("\n\n\n".join(sections) + "\n", encoding="utf-8")
    paths.append(combined)
    return paths
