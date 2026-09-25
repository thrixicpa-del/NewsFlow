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


def _normalise_character_contract(target_chars: int = 0, allowed_min: int = 0,
                                  allowed_max: int = 0) -> tuple[int, int, int]:
    """Return a deterministic target/min/max contract without inventing hidden hard bounds."""
    target = max(0, int(target_chars or 0))
    minimum = max(0, int(allowed_min or 0))
    maximum = max(0, int(allowed_max or 0))
    has_explicit_minimum = bool(minimum)
    if minimum and maximum and minimum > maximum:
        raise ValueError("Минимальная длина больше максимальной")
    if target:
        if not minimum:
            minimum = max(1, int(round(target * .9)))
        # A broad storage ceiling is not a useful length contract when the
        # operator selected a concrete target.  Without an explicit minimum,
        # make the target actionable as the same +/-10% band used by presets.
        if not maximum or not has_explicit_minimum:
            maximum = max(minimum, int(round(target * 1.1)))
    elif minimum and maximum:
        target = (minimum + maximum) // 2
    elif minimum:
        target = minimum
    elif maximum:
        target = maximum
    return target, minimum, maximum


def _explicit_character_contract(prompt: str) -> tuple[int, int, int] | None:
    """Read an unambiguous human length rule without treating arbitrary numbers as one.

    Structured preset fields are authoritative. This compatibility bridge
    recognises a character range such as 9 000–11 000 символов and a single
    approximate target such as 10 000 символов.
    """
    text = str(prompt or "")
    for match in re.finditer(
        r"(?P<minimum>\d[\d\s\u00a0]{0,8})\s*(?:-|–|—|to)\s*(?P<maximum>\d[\d\s\u00a0]{0,8})",
        text,
        re.IGNORECASE,
    ):
        nearby = text[max(0, match.start() - 120):match.end() + 120].casefold()
        if not re.search(r"символ|знак|character", nearby):
            continue
        minimum = int(re.sub(r"\D", "", match.group("minimum")))
        maximum = int(re.sub(r"\D", "", match.group("maximum")))
        if 0 < minimum <= maximum:
            return _normalise_character_contract((minimum + maximum) // 2, minimum, maximum)

    single_patterns = (
        r"(?P<target>\d[\d\s\u00a0]{0,8})\s*(?:символ(?:ов|а)?|знак(?:ов|а)?|characters?)",
        r"(?:символ(?:ов|а)?|знак(?:ов|а)?|characters?)\s*[:=]?\s*(?P<target>\d[\d\s\u00a0]{0,8})",
    )
    for pattern in single_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
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
    has_default_contract = bool(default_target_chars or default_allowed_min or default_allowed_max)
    default_contract = (
        _normalise_character_contract(default_target_chars, default_allowed_min, default_allowed_max)
        if has_default_contract else None
    )
    for position, title in enumerate(titles, start=1):
        base = template.replace("{title}", title) if "{title}" in template else f"{template.rstrip()}\n\nНазвание сценария: {title}"
        applicable = [item for item in ranges if item.start <= position <= item.end]
        extras = [item.prompt.strip() for item in applicable if item.prompt.strip()]
        length_range = next(
            (item for item in reversed(applicable)
             if item.target_chars or item.allowed_min or item.allowed_max),
            None,
        )
        if length_range:
            contract = _normalise_character_contract(
                length_range.target_chars, length_range.allowed_min, length_range.allowed_max,
            )
        elif default_contract:
            contract = default_contract
        else:
            contract = _explicit_character_contract(template)

        target = minimum = maximum = 0
        length_priority = ""
        if contract:
            target, minimum, maximum = contract
            if minimum and maximum:
                bounds = f"{minimum}–{maximum}"
            elif minimum:
                bounds = f"не менее {minimum}"
            else:
                bounds = f"не более {maximum}"
            length_priority = (
                "ПРИОРИТЕТНЫЙ КОНТРАКТ ОБЪЕМА NEWSFLOW:\n"
                f"- Целевой объем: {target} символов.\n"
                f"- Допустимый итоговый диапазон: {bounds} символов.\n"
                "- Планируй детализацию и количество абзацев сразу под этот объем; не выдавай заведомо "
                "короткий черновик с обещанием расширить его позже.\n"
                "- До написания молча распредели материал по последовательным разным смысловым блокам; "
                "каждый следующий блок должен развивать новый аспект темы, а не пересказывать уже раскрытые тезисы.\n"
                "- ОБЯЗАТЕЛЬНО сам контролируй количество символов по мере написания сценария.\n"
                "- ПЕРЕД ОТПРАВКОЙ ФИНАЛЬНОГО ОТВЕТА сам проверь длину готового сценария по правилу Python "
                "len(text.strip()) и убедись, что результат находится в указанном допустимом диапазоне.\n"
                "- Считай именно символы итогового текста после strip(), а не слова, токены или приблизительный объем.\n"
                "- NewsFlow после получения ответа независимо повторно проверит тот же результат на Python "
                "через len(text.strip()); эта проверка является контрольной.\n"
                "- Не печатай подсчет символов, служебный отчет о длине или этот контракт в готовом сценарии.\n"
                "- В вопросах количества символов этот контракт имеет приоритет над любыми конфликтующими "
                "числами ниже в пользовательском шаблоне или дополнительных требованиях.\n\n"
                "ПОЛНЫЙ ПОЛЬЗОВАТЕЛЬСКИЙ ШАБЛОН:\n"
            )
        user_prompt = base + ("\n\nДополнительные требования:\n" + "\n".join(extras) if extras else "")
        prompt = length_priority + user_prompt
        result.append(ScenarioRequest(
            position - 1,
            title,
            prompt,
            target_chars=target,
            allowed_min=minimum,
            allowed_max=maximum,
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
