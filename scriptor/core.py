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


def _resolved_character_contract(target: int = 0, minimum: int = 0,
                                 maximum: int = 0) -> tuple[int, int, int] | None:
    """Normalize one structured character-length contract.

    A target by itself means "about this length" and receives a conservative
    +/-10% runtime band. Explicit min/max always win. A min/max pair without a
    target uses its midpoint so the repair prompt has a useful target too.
    """
    target = max(0, int(target or 0))
    minimum = max(0, int(minimum or 0))
    maximum = max(0, int(maximum or 0))
    if not target and not minimum and not maximum:
        return None
    if target:
        minimum = minimum or max(1, int(target * .9))
        maximum = maximum or max(minimum, int(target * 1.1))
    elif minimum and maximum:
        target = (minimum + maximum) // 2
    elif minimum:
        target = minimum
    elif maximum:
        target = maximum
    if minimum and maximum and minimum > maximum:
        raise ValueError("Минимальная длина больше максимальной")
    if minimum and target < minimum:
        target = minimum
    if maximum and target > maximum:
        target = maximum
    return target, minimum, maximum


def parse_character_length_spec(value: str) -> tuple[int, int, int] | None:
    """Parse an operator length field such as 10000 or 10 000–15 000.

    A single number is an approximate target and receives +/-10% bounds for
    reporting. A range keeps the exact requested min/max and uses its midpoint
    as the prompt orientation target.
    """
    text = " ".join(str(value or "").replace("\u00a0", " ").split()).strip()
    if not text:
        return None
    range_match = re.fullmatch(
        r"(?P<minimum>\d[\d ]{0,12})\s*(?:-|–|—|to)\s*(?P<maximum>\d[\d ]{0,12})(?:\s*(?:символ(?:ов|а)?|знак(?:ов|а)?|characters?))?",
        text,
        re.IGNORECASE,
    )
    if range_match:
        minimum = int(re.sub(r"\D", "", range_match.group("minimum")))
        maximum = int(re.sub(r"\D", "", range_match.group("maximum")))
        if not minimum or not maximum or minimum > maximum:
            raise ValueError("Некорректный диапазон длины сценария")
        return _resolved_character_contract(0, minimum, maximum)
    target_match = re.fullmatch(
        r"(?P<target>\d[\d ]{0,12})(?:\s*(?:символ(?:ов|а)?|знак(?:ов|а)?|characters?))?",
        text,
        re.IGNORECASE,
    )
    if target_match:
        target = int(re.sub(r"\D", "", target_match.group("target")))
        if target <= 0:
            raise ValueError("Длина сценария должна быть больше нуля")
        return _resolved_character_contract(target)
    raise ValueError("Укажите длину как 10000 или диапазон 10000-15000")


def _format_character_count(value: int) -> str:
    return f"{max(0, int(value or 0)):,}".replace(",", " ")


def _explicit_character_contract(prompt: str) -> tuple[int, int, int] | None:
    """Read a legacy free-form character requirement from the writer prompt."""
    text = str(prompt or "")
    for match in re.finditer(
        r"(?P<minimum>\d[\d\s\u00a0]{0,12})\s*(?:-|–|—|to)\s*(?P<maximum>\d[\d\s\u00a0]{0,12})\s*(?:символ(?:ов|а)?|знак(?:ов|а)?|characters?)",
        text,
        re.IGNORECASE,
    ):
        try:
            return parse_character_length_spec(
                f"{match.group('minimum')}-{match.group('maximum')}"
            )
        except ValueError:
            continue
    for match in re.finditer(
        r"(?P<target>\d[\d\s\u00a0]{0,12})\s*(?:символ(?:ов|а)?|знак(?:ов|а)?|characters?)",
        text,
        re.IGNORECASE,
    ):
        try:
            return parse_character_length_spec(match.group("target"))
        except ValueError:
            continue
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


def build_requests(titles: list[str], template: str, ranges: list[PromptRange]) -> list[ScenarioRequest]:
    if not template.strip():
        raise ValueError("Заполните общий шаблон")
    result = []
    for position, title in enumerate(titles, start=1):
        base = template.replace("{title}", title) if "{title}" in template else f"{template.rstrip()}\n\nНазвание сценария: {title}"
        applicable = [item for item in ranges if item.start <= position <= item.end]
        extras = [item.prompt.strip() for item in applicable if item.prompt.strip()]
        length_range = next((item for item in reversed(applicable) if item.target_chars or item.allowed_min or item.allowed_max), None)
        structured_contract = (
            _resolved_character_contract(
                length_range.target_chars, length_range.allowed_min, length_range.allowed_max,
            )
            if length_range else None
        )
        inferred_contract = _explicit_character_contract(template) if structured_contract is None else None
        length_contract = structured_contract or inferred_contract
        if length_contract:
            target, minimum, maximum = length_contract
            if minimum and maximum:
                bounds = f"{minimum}–{maximum}"
            elif minimum:
                bounds = f"не меньше {minimum}"
            else:
                bounds = f"не больше {maximum}"
            formatted_target = _format_character_count(target)
            if minimum and maximum:
                requested = (
                    f"от {_format_character_count(minimum)} до "
                    f"{_format_character_count(maximum)} символов с пробелами"
                )
            elif minimum:
                requested = f"не меньше {_format_character_count(minimum)} символов с пробелами"
            else:
                requested = f"не больше {_format_character_count(maximum)} символов с пробелами"
            extras.append(
                "ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ К ДЛИНЕ: "
                f"требуемый объём готового сценария — {requested}; "
                f"ориентир — около {formatted_target} символов. "
                "Для подсчёта количества символов используй Python. "
                "Сразу верни только готовый сценарий нужного объёма без служебного текста. "
                "NewsFlow после ответа независимо пересчитает фактическое количество символов Python."
            )
        prompt = base + ("\n\nДополнительные требования:\n" + "\n".join(extras) if extras else "")
        result.append(ScenarioRequest(
            position - 1, title, prompt,
            target_chars=length_contract[0] if length_contract else 0,
            allowed_min=length_contract[1] if length_contract else 0,
            allowed_max=length_contract[2] if length_contract else 0,
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
