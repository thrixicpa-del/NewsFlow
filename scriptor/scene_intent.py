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

# Exact subject forms for the bounded Russian speaker rule. Broad aliases
# deliberately also match indirect cases, which cannot establish a speaker.
PERSON_SUBJECT_FORMS = {
    "putin": "путин", "zelensky": "зеленский", "trump": "трамп",
    "pashinyan": "пашинян", "tokayev": "токаев", "aliyev": "алиев", "macron": "макрон",
}


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


def _negated_attack(text: str, stem: str | None = None) -> bool:
    # Clause-local bounded rules: do not erase a later real attack after a
    # refused proposal. This deliberately stops short of a linguistic parser.
    text = re.sub(r"\bне\s+(?:отмен\w*|предотврат\w*)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bтак\s+и\s+не\b", "не", text, flags=re.IGNORECASE)
    event = re.escape(stem) + r"\w*" if stem else r"(?:удар\w*|обстрел\w*|атак\w*|наступлен\w*)"
    return bool(re.search(
        r"(?:отказ\w*|отмен\w*|предотврат\w*|не\s+(?:было|будет|начал\w*|начн\w*|нанес\w*|нанос\w*|атак\w*|обстрел\w*))"
        rf"(?:\s+(?!и\b)\w+){{0,5}}\s+{event}"
        rf"|{event}(?:\s+(?!и\b)\w+){{0,5}}\s+(?:отмен\w*|предотврат\w*|не\s+(?:состоя\w*|нача\w*|начн\w*))"
        rf"|\bесли\s+(?:\w+\s+){{0,3}}{event}",
        text, re.IGNORECASE,
    ))


_PROTEST_WORDS = r"(?:митинг\w*|протест\w*|демонстран\w*|демонстраци\w*|шестви\w*|пикет\w*|забастов\w*|бастующ\w*|беспоряд\w*)"
_SPEECH_VERBS = r"(?:ответи\w*|выступи\w*|заяви\w*|сказа\w*|прокомментир\w*|комментир\w*|отверг\w*|подтверд\w*)"


def _protest_intent(text: str, protest_context: bool = False) -> str:
    """Bounded local event rules, not a universal language classifier."""
    # Resolve each explicit event locally. A cancelled event must not erase a
    # later gathering, and a diplomatic protest must not hide a street rally.
    clauses = re.split(r"[,;.!?]|\b(?:но|затем)\b", text)
    if len(clauses) > 1:
        modes = []
        for clause in clauses:
            if clause.strip():
                mode = _protest_intent(clause, protest_context=protest_context)
                modes.append(mode)
                protest_context = protest_context or mode in {"peaceful", "labor", "farmers", "conflict"}
        active = [mode for mode in modes if mode != "none"]
        if active:
            return active[-1]
    if re.search(r"дипломатическ\w*\s+протест", text):
        return "diplomatic"
    if re.search(r"демонстраци\w*(?:\s+\w+){0,3}\s+(?:оборудован\w*|техник\w*|продук\w*)", text):
        return "equipment"
    contextual_conflict = bool(re.search(r"разгон\w*|столкнов\w*", text)
                               and (protest_context or re.search(r"полиц\w*", text)))
    if not (contextual_conflict or re.search(rf"\b{_PROTEST_WORDS}", text) or
            re.search(r"участник\w*\s+акци\w*.*(?:собрал\w*|площад\w*)", text)):
        return "none"
    event_clauses = [clause for clause in re.split(r"[,;.!?]|\b(?:но|затем)\b", text)
                     if re.search(_PROTEST_WORDS, clause)]
    def inactive(clause):
        clause = re.sub(r"\bне\s+(?:отмен\w*|предотврат\w*)", "", clause)
        return bool(re.search(r"отмен\w*|предотврат\w*|не\s+нач\w*|угрожа\w*|обсужда\w*|\bесли\b", clause))
    if event_clauses and all(inactive(clause) for clause in event_clauses):
        return "inactive"
    conflict_clauses = [clause for clause in re.split(r"[,;.!?]|\b(?:но|затем)\b", text)
                        if re.search(r"разгон\w*|столкнов\w*|беспоряд\w*", clause)]
    conflict = any(not re.search(r"не\s+(?:было|нач\w*|произош\w*)|без\s+(?:столкнов\w*|беспоряд\w*)", clause)
                   for clause in conflict_clauses)
    if conflict:
        return "conflict"
    if re.search(r"забастов\w*|бастующ\w*|пикет\w*|рабочи\w*", text):
        return "labor"
    if re.search(r"фермер\w*", text):
        return "farmers"
    return "peaceful"


def visual_intent(text: str, associations: dict[str, str], *, previous: dict | None = None) -> dict:
    sequence = re.split(r"\b(?:затем|после этого)\b", text, flags=re.IGNORECASE)
    if len(sequence) > 1 and sequence[-1].strip():
        # A single VoiceMap segment may contain an explicit action switch.
        # Resolve the later action; preserve only a valid pronoun antecedent.
        prior = visual_intent(sequence[0], associations, previous=previous)
        for clause in sequence[1:]:
            if clause.strip():
                prior = visual_intent(clause, associations, previous=prior)
        return {**prior, "text": text, "mentioned_people": named_people(text)}
    lowered = text.casefold().replace("ё", "е")
    people = named_people(text)
    industrial = bool(re.search(r"\b(?:завод\w*|производств\w*|мост\w*|ремонт\w*|урожа\w*|порт\w*)", lowered))
    speech = bool(re.search(rf"\b(?:{_SPEECH_VERBS}|заяв\w*|обращени\w*|журналист\w*)", lowered))
    joint = bool(re.search(r"\b(?:обсуд\w*|обсужден\w*|переговор\w*|встреч\w*|встрет\w*|консультаци\w*)", lowered))
    indirect = bool(re.search(r"\b(?:по\s+решени\w*|по\s+указ\w*|поручени\w*)", lowered))
    primary = [] if industrial and (indirect or not speech) else people[:1]
    speech_action = re.search(rf"\b{_SPEECH_VERBS}", lowered)
    if primary and len(people) > 1 and speech_action:
        subjects = [identity for identity in people
                    if re.search(rf"\b{PERSON_SUBJECT_FORMS[identity]}\b", lowered)]
        if len(subjects) > 1:
            before_action = lowered[:speech_action.start()]
            main_subjects = [identity for identity in subjects
                            if re.search(rf"\b{PERSON_SUBJECT_FORMS[identity]}\b", before_action)]
            # Both coordinated speakers remain eligible. A subordinate quote
            # after the main predicate does not become a second main speaker.
            primary = main_subjects
        else:
            primary = subjects
    if joint and not speech and not indirect:
        primary = people
    if not people and not industrial and re.search(r"\b(?:он|его|президент)\b", lowered):
        prior = list((previous or {}).get("target_people", []))
        if len(prior) == 1:
            primary = prior
    economic = any(term_matches(stem, lowered) for stem in ("санкц", "эконом", "рынк", "банк"))
    cyber = any(term_matches(stem, lowered) for stem in ("кибер", "хакер", "сервер"))
    protest_mode = _protest_intent(lowered, protest_context=(previous or {}).get("protest_mode") in {
        "peaceful", "labor", "farmers", "conflict",
    })
    if joint and re.search(r"(?:затем|после этого).*?(?:переговор\w*|встрет\w*|консультаци\w*)", lowered):
        protest_mode = "none"
    protest = protest_mode in {"peaceful", "labor", "farmers", "conflict"} and not (speech and primary)
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
        # Contextual event rules replace ambiguous dictionary associations.
        if re.search(_PROTEST_WORDS, stem) or stem in {"демонстр", "беспоряд", "фермер"}:
            if stem == "фермер" and protest_mode == "none":
                terms.append("agriculture farming fields farm workers")
            continue
        if (protest or (speech and primary and protest_mode != "none")) and stem not in {
            "иран", "тегеран", "украин", "росси", "москв", "вашингтон", "киев", "брюссел", "армени", "азербайдж",
        }:
            continue
        if stem in kinetic:
            clauses = re.split(r"[,;.!?]|\b(?:но|затем)\b", lowered)
            matching = [clause for clause in clauses if term_matches(stem, clause)]
            if stem in {"удар", "обстрел", "артилл", "наступлен"} and matching and all(_negated_attack(clause, stem) for clause in matching):
                continue
            if stem == "удар" and economic:
                continue
            if (cyber or (ceasefire and not actual_kinetic) or (speech and primary)) and stem in {"удар", "обстрел", "артилл"}:
                continue
        if protest and stem in {"урож", "картош", "сельхоз", "пшениц", "зерн", "комбайн"}:
            continue
        if rail and stem in {"зерн", "пшениц"}:
            continue
        terms.append(english)
    if protest:
        terms.append({
            "peaceful": "peaceful civilian protest crowd placards street rally march",
            "farmers": "peaceful farmers protest tractors placards government demonstration",
            "labor": "peaceful workers labor strike picket line union protest factory gate",
            "conflict": "civilian protest police dispersal clashes street unrest",
        }[protest_mode])
    elif protest_mode in {"inactive", "diplomatic"}:
        terms.append("diplomatic official statement government building exterior" if protest_mode == "diplomatic"
                     else "official statement government building exterior venue illustrative context")
    elif protest_mode == "equipment":
        terms.append("industrial equipment exhibition technology demonstration")
    if re.search(r"реклам\w*\s+акци\w*|стоимост\w*.*акци\w*", lowered):
        terms.append("company business finance advertising markets")
    if joint and not protest and not (speech and primary):
        terms.append("diplomatic negotiations delegations meeting consultations")
    if ceasefire and not actual_kinetic:
        terms.append("diplomatic negotiations delegations statements ceasefire")
    if rail:
        terms.append("rail freight train grain transport cargo logistics")
    if term_matches("сервер", lowered) or re.search(r"дата[-\s]?центр\w*", lowered):
        terms.append("data center servers computer network infrastructure")
    if speech and primary:
        terms.append("press conference statement journalists cameras")
    if not terms and (speech or _negated_attack(lowered)):
        terms.append("official statement government briefing illustrative context")
    terms = [person_name(identity) for identity in primary] + terms
    query = ", ".join(dict.fromkeys(terms))
    return {
        "version": 1, "text": text, "visual_query": query,
        "target_people": primary, "mentioned_people": people,
        "person_role": "speaker" if primary and speech else ("participant" if primary else "none"),
        "provenance": "local-lexical-context", "confidence": "rule-based",
        "illustrative_only": True,
        "protest_mode": protest_mode if not (speech and primary) else "mentioned-by-speaker",
    }


def visual_topics(query: str) -> set[str]:
    vocabularies = {
        "agriculture": r"harvest|agriculture|farming|wheat",
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
