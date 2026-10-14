"""Small local visual-intent rules. No provider calls or identity inference.

The person registry is an alias vocabulary, not a face recognizer. Evidence
about who is visible belongs to the selected file interval, never its folder.
"""
from __future__ import annotations

import re
from pathlib import Path

PERSON_ALIASES = (
    ("putin", "Vladimir Putin", r"путин\w*|(?:vladimir\s+)?putin"),
    ("zelensky", "Volodymyr Zelensky", r"зеленск\w*|(?:volodymyr\s+)?zelensk(?:y|yy|iy|i)"),
    ("trump", "Donald Trump", r"трамп\w*|(?:donald\s+)?trump"),
    ("pashinyan", "Nikol Pashinyan", r"пашинян\w*|(?:nikol\s+)?pashinyan"),
    ("tokayev", "Kassym-Jomart Tokayev", r"токаев\w*|(?:kassym.jomart\s+)?to(?:k|q)ayev"),
    ("aliyev", "Ilham Aliyev", r"алиев\w*|(?:ilham\s+)?aliyev"),
    ("macron", "Emmanuel Macron", r"макрон\w*|(?:emmanuel\s+)?macron"),
)


def named_people(text: str) -> list[str]:
    positions = []
    for identity, _name, expression in PERSON_ALIASES:
        match = re.search(rf"(?<!\w)(?:{expression})(?!\w)", str(text), re.IGNORECASE)
        if match:
            positions.append((match.start(), identity))
    return [identity for _position, identity in sorted(positions)]


def person_name(identity: str) -> str:
    return next((name for key, name, _ in PERSON_ALIASES if key == identity), identity)


def person_evidence(query: str, item, start: float = 0, duration: float = 6) -> dict:
    """Report curated evidence for this exact file/window; names are hints."""
    targets = named_people(query)
    result = {"targets": targets, "status": "not_requested" if not targets else "unknown",
              "visible": [], "source": "none", "event_confirmed": False}
    if not targets:
        return result
    stored = getattr(item, "person_evidence", None) or {}
    if not stored:
        hints = named_people(" ".join((item.name, " ".join(item.tags or []))).replace("_", " "))
        if hints:
            result.update(visible=hints, source="unverified-metadata",
                          status="probable" if set(targets) & set(hints) else "contradiction_hint")
        return result
    try:
        stat = Path(item.path).stat()
        fresh = stat.st_size == stored.get("size") and stat.st_mtime_ns == stored.get("mtime_ns")
    except OSError:
        fresh = False
    overlapping = [value for value in stored.get("observations", [])
                    if fresh and value.get("source") in {"manual", "curated"}
                    and float(value.get("start", 0)) < start + duration - .001
                    and float(value.get("end", 0)) > start + .001]
    observations = [value for value in overlapping
                    if float(value.get("start", 0)) <= start + .001
                    and float(value.get("end", 0)) >= start + duration - .001]
    visible = list(dict.fromkeys(value["person_id"] for value in observations))
    if visible:
        result.update(visible=visible, source="curated-interval")
        if set(targets) & set(visible):
            result["status"] = "confirmed"
        elif any(value.get("complete") for value in observations):
            result["status"] = "contradiction"
    # A complete contradictory annotation covering even part of the selected
    # beat is evidence against it. Confirmation still requires full coverage.
    for value in overlapping:
        if not value.get("complete") or value["person_id"] in targets:
            continue
        overlap_start = max(start, float(value["start"]))
        overlap_end = min(start + duration, float(value["end"]))
        target_covers_overlap = any(
            entry["person_id"] in targets and float(entry["start"]) <= overlap_start + .001
            and float(entry["end"]) >= overlap_end - .001 for entry in overlapping
        )
        if not target_covers_overlap:
            result.update(status="contradiction", visible=list(dict.fromkeys(
                entry["person_id"] for entry in overlapping)), source="curated-interval")
            return result
    return result


def person_window(query: str, item, duration: float = 6) -> float:
    """Find a fully covered curated window, without inventing an identity."""
    targets = set(named_people(query))
    for observation in (getattr(item, "person_evidence", None) or {}).get("observations", []):
        if observation.get("person_id") not in targets:
            continue
        start = float(observation.get("start", 0))
        if person_evidence(query, item, start, duration)["status"] == "confirmed":
            return start
    return 0.0


def term_matches(stem: str, text: str) -> bool:
    expression = {
        "арм": r"арм(?:и[яиюей]\w*|ейск\w*)",
        "танк": r"танк(?:а|и|у|ом|ов|ам|ами|ах)?",
        "поезд": r"поезд(?:а|у|ом|е|ов|ам|ами|ах|ы)?",
    }.get(stem, re.escape(stem) + r"\w*")
    return bool(re.search(rf"(?<!\w){expression}(?!\w)", text, re.IGNORECASE))


def _negated_attack(text: str) -> bool:
    # Clause-local bounded rules: do not erase a later real attack after a
    # refused proposal. This deliberately stops short of a linguistic parser.
    text = re.sub(r"\bне\s+(?:отмен\w*|предотврат\w*)", "", text, flags=re.IGNORECASE)
    return bool(re.search(
        r"(?:отказ\w*|отмен\w*|предотврат\w*|не\s+(?:было|будет|нанес\w*|нанос\w*|атак\w*|обстрел\w*))"
        r"(?:\s+\w+){0,5}\s+(?:удар\w*|обстрел\w*|атак\w*)"
        r"|(?:удар\w*|обстрел\w*|атак\w*)(?:\s+\w+){0,5}\s+(?:отмен\w*|предотврат\w*|не\s+состоя\w*)",
        text, re.IGNORECASE,
    ))


def visual_intent(text: str, associations: dict[str, str], *, previous: dict | None = None) -> dict:
    lowered = text.casefold().replace("ё", "е")
    people = named_people(text)
    industrial = bool(re.search(r"\b(?:завод\w*|производств\w*|мост\w*|ремонт\w*|урожа\w*|порт\w*)", lowered))
    speech = bool(re.search(r"\b(?:заяв\w*|ответ\w*|выступ\w*|обращени\w*|журналист\w*|сказ\w*)", lowered))
    joint = bool(re.search(r"\b(?:обсуд\w*|переговор\w*|встрет\w*)", lowered))
    indirect = bool(re.search(r"\b(?:по\s+решени\w*|по\s+указ\w*|поручени\w*)", lowered))
    primary = [] if industrial and (indirect or not speech) else people[:1]
    if joint and not speech and not indirect:
        primary = people
    if not people and not industrial and re.search(r"\b(?:он|его|президент)\b", lowered):
        prior = list((previous or {}).get("target_people", []))
        if len(prior) == 1:
            primary = prior
    economic = any(term_matches(stem, lowered) for stem in ("санкц", "эконом", "рынк", "банк"))
    cyber = any(term_matches(stem, lowered) for stem in ("кибер", "хакер", "сервер"))
    protest = any(term_matches(stem, lowered) for stem in ("протест", "митинг", "забастов"))
    ceasefire = bool(re.search(r"прекращени\w*\s+огня|перемири\w*", lowered))
    actual_kinetic = bool(re.search(r"(?:обстрел\w*|артилл\w*|удар\w*)", lowered)
                          and re.search(r"несмотря|продолж\w*|начал\w*|произош\w*", lowered))
    rail = term_matches("поезд", lowered) or term_matches("железнодорож", lowered)
    kinetic = {"удар", "обстрел", "артилл", "наступлен", "ракет", "танк", "арм", "войск", "солдат", "фронт"}
    terms = []
    for stem, english in associations.items():
        if not term_matches(stem, lowered):
            continue
        if named_people(stem):
            continue
        if stem in kinetic:
            clauses = re.split(r"[,;.!?]|\b(?:но|затем)\b", lowered)
            matching = [clause for clause in clauses if term_matches(stem, clause)]
            if stem in {"удар", "обстрел", "артилл", "наступлен"} and matching and all(_negated_attack(clause) for clause in matching):
                continue
            if stem == "удар" and economic:
                continue
            if (cyber or (ceasefire and not actual_kinetic) or (speech and primary)) and stem in {"удар", "обстрел", "артилл"}:
                continue
        if stem == "фермер":
            if not protest:
                terms.append("agriculture farming fields farm workers")
            continue
        if protest and stem in {"урож", "картош", "сельхоз", "пшениц", "зерн", "комбайн"}:
            continue
        if rail and stem in {"зерн", "пшениц"}:
            continue
        terms.append(english)
    if ceasefire and not actual_kinetic:
        terms.append("diplomatic negotiations delegations statements ceasefire")
    if rail:
        terms.append("rail freight train grain transport cargo logistics")
    if term_matches("сервер", lowered) or re.search(r"дата[-\s]?центр\w*", lowered):
        terms.append("data center servers computer network infrastructure")
    if speech and primary:
        terms.append("press conference statement journalists cameras")
    terms = [person_name(identity) for identity in primary] + terms
    query = ", ".join(dict.fromkeys(terms))
    return {
        "version": 1, "text": text, "visual_query": query,
        "target_people": primary, "mentioned_people": people,
        "person_role": "speaker" if primary and speech else ("participant" if primary else "none"),
        "provenance": "local-lexical-context", "confidence": "rule-based",
        "illustrative_only": True,
    }


def visual_topics(query: str) -> set[str]:
    vocabularies = {
        "agriculture": r"harvest|agriculture|farming|wheat|tractor",
        "protest": r"protest|rally|picket|labor strike",
        "diplomacy": r"diplomatic|negotiations|summit",
        "combat": r"artillery|shelling|battlefield|frontline|tanks|explosion",
        "digital": r"cyber|servers|computer network|data center",
        "economy": r"economy|economic|finance|banking|markets",
        "shipping": r"tanker|seaport|port|refinery",
        "rail": r"rail|train",
    }
    return {topic for topic, expression in vocabularies.items()
            if re.search(rf"\b(?:{expression})\b", query, re.IGNORECASE)}
