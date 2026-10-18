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
    ("lukashenko", "Alexander Lukashenko", r"лукашенко|(?:alexander\s+)?lukashenk[oa]"),
)

# Exact subject forms for the bounded Russian speaker rule. Broad aliases
# deliberately also match indirect cases, which cannot establish a speaker.
PERSON_SUBJECT_FORMS = {
    "putin": "путин", "zelensky": "зеленский", "trump": "трамп",
    "pashinyan": "пашинян", "tokayev": "токаев", "aliyev": "алиев", "macron": "макрон",
    "lukashenko": "лукашенко",
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


def _physical_places(text: str, associations: dict[str, str]) -> list[str]:
    """Country hints already expressed by the local vocabulary, never proof."""
    matched = ", ".join(english for stem, english in associations.items()
                        if stem not in {"европ", "евросоюз"} and term_matches(stem, text))
    places = [place for place in ("Ukraine", "Russia", "Belarus", "Iran", "Armenia", "Azerbaijan", "Israel", "Lebanon")
              if re.search(rf"\b{place}\b", matched)]
    if re.search(r"\b(?:евросоюз\w*|европейск\w*\s+союз\w*)", text, re.IGNORECASE):
        places.append("European Union")
    return places


def _positive_route_text(text: str) -> str:
    """Exclude a bounded denied destination, keeping the original narration."""
    return re.sub(
        r"\bне\s+(?:к|ко|в|во|на|через|по)\s+"
        r"(?:(?!(?:а|но|затем)\b)[а-яё-]+\s+){0,3}?"
        r"(?:порт\w*|границ\w*|железн\w*\s+дорог\w*)\b"
        r"(?:\s+черн\w*\s+мор\w*)?",
        " ", text,
    )


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
    lowered = _positive_route_text(text.casefold().replace("ё", "е"))
    people = named_people(text)
    industrial = bool(re.search(r"\b(?:завод\w*|производств\w*|мост\w*|ремонт\w*|урожа\w*|порт\w*)", lowered))
    reporting_reference = not people and bool(re.search(
        r"\b(?:таки\w*|эти\w*|официальн\w*)\s+заявлен\w*|\bпо\s+заявлен\w*", lowered,
    ))
    speech = (not reporting_reference
              and bool(re.search(rf"\b(?:{_SPEECH_VERBS}|заяв\w*|обращени\w*|журналист\w*)", lowered)))
    # A council is a meeting only when its local predicate asserts one.
    # A past council mentioned after an advance, or a cancelled/conditional
    # council, must not turn the current action into a meeting.
    council = any(
        re.search(r"\b(?:провел\w*|провод(?:ят|ит|или|ил[ао]?)|начал\w*|состоял\w*|собрал\w*)"
                  r"(?:\s+(?!после\b|до\b|перед\b)\w+){0,5}\s+совещан\w*"
                  r"|\bсовещан\w*(?:\s+(?!после\b|до\b|перед\b)\w+){0,5}\s+"
                  r"(?:состоял(?:ось|ись)|начал(?:ось|ись)|проход(?:ит|ят|ило|или)|прошл(?:о|и))\b", clause)
        and not re.search(r"\bесли\b|отмен\w*|предотврат\w*|\bне\s+(?:(?:будет|будут|было|были)\s+)?"
                          r"(?:провел\w*|провод\w*|нач\w*|состоя\w*|собрал\w*|проход\w*|прошл\w*)", clause)
        for original in re.split(r"[,;.!?]", lowered)
        # A temporal reference is not the subject of a later predicate.
        for clause in [re.sub(r"\b(?:после|до|перед)\s+(?:\w+(?:ого|его|ым|им|ом|ем|ых|их)\s+){0,2}совещан\w*",
                              "", original)]
    )
    joint = council or bool(re.search(r"\b(?:обсуд\w*|обсужден\w*|переговор\w*|встреч\w*|встрет\w*|консультаци\w*)", lowered))
    indirect = bool(re.search(r"\b(?:по\s+решени\w*|по\s+указ\w*|поручени\w*)", lowered))
    primary = [] if industrial and (indirect or not speech) else people[:1]
    speech_action = re.search(rf"\b{_SPEECH_VERBS}", lowered)
    if primary and len(people) > 1 and speech_action:
        # An indeclinable surname after a reported statement is still its
        # author unless coordinated nominatives assert a plural response.
        nominatives = "|".join(PERSON_SUBJECT_FORMS.values())
        coordinated = re.search(
            rf"\bлукашенко\s+и\s+(?:{nominatives})\s+(?P<verb>{_SPEECH_VERBS})", lowered,
        )
        subject_text = lowered if coordinated and coordinated["verb"].endswith(("ли", "ют", "ут", "ят", "ат")) else re.sub(
            r"\b(?:заявлени\w*|слов\w*|обращени\w*|высказывани\w*)"
            r"(?:\s+александра)?\s+лукашенко\b", " ", lowered,
        )
        subjects = [identity for identity in people
                    if re.search(rf"\b{PERSON_SUBJECT_FORMS[identity]}\b", subject_text)]
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
    if protest:
        # A protest against a leader does not assert their visible presence.
        # Remove only those occurrences before resolving an explicit visitor.
        participant_text = lowered
        for _identity, _name, expression in PERSON_ALIASES:
            participant_text = re.sub(
                rf"\bпротив\s+(?:(?:президент\w*|александра)\s+){{0,2}}(?:{expression})(?!\w)",
                " ", participant_text,
            )
        attendees = [identity for identity in people if re.search(
            rf"\b{PERSON_SUBJECT_FORMS[identity]}\s+посетил\w*\b"
            rf"|\bпосетил\w*\s+{PERSON_SUBJECT_FORMS[identity]}\b", participant_text,
        )]
        primary = attendees or [identity for identity in primary if identity in named_people(participant_text)]
    ceasefire = bool(re.search(r"прекращени\w*\s+огня|перемири\w*", lowered))
    actual_kinetic = bool(re.search(r"(?:обстрел\w*|артилл\w*|удар\w*)", lowered)
                          and re.search(r"несмотря|продолж\w*|начал\w*|произош\w*", lowered))
    rail = (term_matches("поезд", lowered) or term_matches("железнодорож", lowered)
            or bool(re.search(r"\bжелезн\w*\s+дорог\w*|\bвагон(?:ы|а|ов|ами|ах|е|у|ом)?\b", lowered)))
    military_naval = bool(re.search(
        r"\bвоенн\w*\s+(?:корабл\w*|судн\w*|флот\w*)|\bпатрульн\w*\s+(?:катер\w*|корабл\w*)"
        r"|\bвм[сф]\b|\bвоенно[-\s]морск\w*", lowered,
    ))
    # Plural court/vessel forms are ambiguous. Require local maritime words
    # and exclude a local judicial predicate, rather than matching by suffix.
    ambiguous_vessel = any(
        re.search(r"\bсуд(?:а|ов|ами|ах)\b", clause)
        and re.search(r"морск\w*|судоход\w*|канал\w*|терминал\w*|порт\w*|грузов\w*|товар\w*|достав\w*|загруж\w*|загруз\w*", clause)
        and not re.search(
            r"\b(?:апелляц\w*|постановлен\w*|судебн\w*|иск(?:а|и|ов|ами)?|дел[аоу])\b"
            r"|\bрешени\w*(?:\s+\w+){0,2}\s+суд(?:а|ов|ами|ах)\b"
            r"|\bвынес\w*(?:\s+\w+){0,3}\s+судами\b", clause,
        )
        for clause in re.split(r"[,;.!?]", lowered)
    )
    shipping = bool(re.search(r"\bсудоходств\w*|\bсуд(?:но|на|ну|ном|не)\b", lowered)
                    or ambiguous_vessel
                    or (re.search(r"\bзерновоз\w*", lowered)
                        and re.search(r"\b(?:заход\w*|порт\w*|морск\w*|канал\w*|судоход\w*)", lowered))
                    or re.search(r"морск\w*\s+логист\w*", lowered)
                    or (re.search(r"\bрек(?:а|е|у|ой|и)\b", lowered)
                        and re.search(r"\b(?:груз\w*|товар\w*|продукци\w*)", lowered)))
    logistics_routes = bool(re.search(r"\bмаршрут\w*", lowered)
                            and re.search(r"логист\w*|альтернатив\w*|перевоз\w*|достав\w*", lowered))
    grain = bool(re.search(r"\b(?:зерн\w*|пшениц\w*|кукуруз\w*)", lowered))
    agricultural = bool(re.search(r"\bаграр\w*", lowered))
    oil = term_matches("нефт", lowered)
    export = bool(re.search(r"\b(?:экспорт\w*|выв(?:ез|оз)\w*)|внешн\w*\s+рын\w*", lowered))
    commodity_subject = "oil" if oil else ("grain" if grain else ("agricultural" if agricultural else ""))
    physical_export = export and bool(commodity_subject) and not protest and not primary
    crop = grain or term_matches("урож", lowered)
    harvesting = bool(re.search(
        r"\b(?:уборк\w*|сбор\w*|собир(?!\w*с[яь]\b)\w*|собрал(?!\w*с[яь]\b)\w*|комбайн\w*|жатв\w*)",
        lowered,
    ))
    logistics_routes = logistics_routes or bool(re.search(r"\bмаршрут\w*", lowered) and crop)
    loading = term_matches("погрузк", lowered) or bool(
        re.search(r"\b(?:загруж\w*|загруз\w*|погруз\w*)", lowered)
        and (shipping or crop or re.search(r"\b(?:груз\w*|товар\w*|контейнер\w*|терминал\w*)", lowered))
    )
    cargo_crop = (crop and not harvesting and not protest and not primary
                  and (shipping or rail or logistics_routes or loading
                       or (not physical_export and re.search(r"\bхран\w*", lowered))
                       or term_matches("порт", lowered) or term_matches("склад", lowered)
                       or re.search(r"\bзерновоз\w*", lowered)
                       or re.search(r"\b(?:груз\w*|проход\w*|парти\w*|покупател\w*|перевоз\w*|достав\w*)", lowered)))
    kinetic = {"удар", "обстрел", "артилл", "наступлен", "ракет", "танк", "арм", "войск", "солдат", "фронт", "военн"}
    reported_kinetic_claim = (not primary
                              and bool(re.search(r"\b(?:заяв(?:ля|и)\w*|сообщ\w*|утвержд\w*|по\s+версии)\b", lowered))
                              and any(term_matches(stem, lowered) for stem in kinetic))
    terms = []
    report_context_terms = []
    for stem, english in associations.items():
        if not term_matches(stem, lowered):
            continue
        if named_people(stem):
            continue
        if military_naval and stem in {"кораб", "военн"}:
            continue
        if stem == "кораб":
            english = "commercial cargo ship maritime navigation shipping vessel"
        if stem == "склад":
            if not re.search(r"\bсклад(?:ы|а|е|у|ом|ов|ам|ами|ах)?\b", lowered):
                continue
            # Storage is a physical object; fire/emergency requires its own
            # narrated event rather than the legacy dictionary's association.
            english = ("warehouse fire emergency workers"
                       if re.search(r"\b(?:пожар\w*|возгорани\w*|загорел\w*|горит|горят)\b", lowered)
                       else "warehouse cargo storage logistics")
        if physical_export and stem in {"эконом", "рынк", "торгов", "зерн", "пшениц"}:
            continue
        if cargo_crop and stem in {"зерн", "пшениц", "урож"}:
            continue
        # A continent/union mention supplies geographic context, not evidence
        # of a parliament, a Brussels venue, or an institutional event.
        if stem in {"европ", "евросоюз"}:
            european_union = stem == "евросоюз" or re.search(r"европейск\w*\s+союз\w*", lowered)
            terms.append("European Union regional context" if european_union else "Europe regional context")
            continue
        # Contextual event rules replace ambiguous dictionary associations.
        if re.search(_PROTEST_WORDS, stem) or stem in {"демонстр", "беспоряд", "фермер"}:
            if stem == "фермер" and protest_mode == "none":
                terms.append("agriculture farming fields farm workers")
            continue
        if (protest or (speech and primary and protest_mode != "none")) and stem not in {
            "иран", "тегеран", "украин", "росси", "москв", "беларус", "белорус", "минск",
            "вашингтон", "киев", "брюссел", "армени", "азербайдж",
        }:
            continue
        if stem in kinetic:
            if joint and stem in {"арм", "войск", "солдат", "военн"}:
                # Military participants do not themselves assert combat.
                continue
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
        if stem not in kinetic:
            report_context_terms.append(english)
    if reported_kinetic_claim:
        # The narration attributes this action to a claim. Keep its explicit
        # place/physical context without presenting an observed attack or
        # turning an unnamed report into a speaking politician's portrait.
        terms = [*report_context_terms, "government building exterior illustrative context"]
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
    if military_naval:
        terms.append("military naval warship patrol vessel navy")
    elif shipping:
        terms.append("cargo ship maritime navigation shipping sea freight")
    if logistics_routes:
        terms.append("cargo transport logistics warehouse alternative freight routes")
    if re.search(r"\bсухопутн\w*\s+(?:разворот\w*|маршрут\w*|перевоз\w*|логист\w*|пут\w*)", lowered):
        terms.append("overland rail road freight cargo transport warehouse logistics")
    if (harvesting and not protest
            and re.search(r"\bжатв\w*", lowered)
            and not re.search(r"\b(?:harvest|harvesting|combine)\b", ", ".join(terms), re.IGNORECASE)):
        terms.append("agriculture grain harvest combine farming fields")
    if physical_export:
        terms.append({
            "grain": "grain cargo export warehouse storage logistics",
            "oil": "oil tanker export terminal refinery logistics",
            "agricultural": "agricultural products cargo export warehouse logistics",
        }[commodity_subject])
    elif agricultural and not protest:
        terms.append("agriculture farming fields agricultural products")
    if cargo_crop:
        terms.append("grain cargo warehouse storage logistics" if grain else "crop cargo warehouse storage logistics")
        commodity_subject = commodity_subject or "agricultural"
    if loading:
        terms.append("cargo loading freight terminal warehouse")
    if term_matches("выгрузк", lowered):
        terms.append("cargo unloading freight terminal warehouse")
    if re.search(r"\bгрузовик\w*", lowered):
        terms.append("cargo trucks road freight transport logistics")
    if re.search(r"\bдуна(?:й\w*|[яюе])\b", lowered):
        terms.append("Danube river cargo ship shipping navigation logistics")
    if re.search(r"черн\w*\s+мор\w*", lowered):
        terms.append("Black Sea maritime cargo ship shipping navigation")
    if re.search(r"\bевропейск\w*\s+парламент\w*", lowered):
        terms.append("European Parliament institutions")
    if term_matches("сервер", lowered) or re.search(r"дата[-\s]?центр\w*", lowered):
        terms.append("data center servers computer network infrastructure")
    if speech and primary:
        terms.append("press conference statement journalists cameras")
    if not terms and (speech or _negated_attack(lowered)):
        terms.append("official statement government briefing illustrative context")
    inherited_subject_depth = 0
    carrier_reference = bool(re.search(r"\bперевозчик\w*", lowered)
                             and re.search(r"\b(?:заход\w*|маршрут\w*|услов\w*)", lowered))
    abstract_logistics = bool(re.search(r"\bтонн\w*", lowered) or (
        re.search(r"\b(?:стоимост\w*|цен[аыуе]\w*|прибыл[ьи]|срок\w*|длительност\w*)", lowered)
        and re.search(r"\b(?:достав\w*|перевоз\w*|это|этого|где)\b", lowered)
    ) or (re.search(r"\b(?:его|их|этого)\b", lowered)
          and re.search(r"\b(?:предел\w*|ограничени\w*|возможност\w*)", lowered)))
    grain_intro = bool(re.fullmatch(r"\s*для\s+(?:зерн\w*|пшениц\w*|кукуруз\w*)\s*[,;:]?\s*", lowered))
    economic_evaluation = bool(re.search(r"экономическ\w*\s+смысл", lowered))
    duration_unit = bool(re.search(r"\b(?:недел\w*|месяц\w*|сут\w*|дн\w*|час\w*)", lowered))
    delivery_duration = duration_unit and bool(re.search(r"\bдостав\w*", lowered))
    duration_continuation = duration_unit and bool(re.search(r"\b(?:растянул\w*|занимал\w*|длил\w*)", lowered))
    commodity_reference = bool((previous or {}).get("commodity_subject") and (
        re.search(r"\b(?:прода\w*|продаж\w*)", lowered)
        and re.search(r"\b(?:его|ее|их|дисконт\w*)\b", lowered)
        or re.search(r"\b(?:логистическ\w*|транспортн\w*)\s+дисконт\w*", lowered)
        or re.search(r"\b(?:хран\w*|выв(?:ез|оз)\w*)", lowered)
        and re.search(r"\b(?:его|ее|их|субсиди\w*)\b", lowered)
    ))
    prior_depth = int((previous or {}).get("inherited_subject_depth", 0))
    prior_words = int((previous or {}).get("inherited_subject_words", 0))
    prior_open_clause = not re.search(r"[.!?][\"'»”)]*\s*$", str((previous or {}).get("text", "")))
    # The ordinary rule remains one hop. Explicitly linked logistics clauses
    # may continue within a finite paragraph budget; a completed abstract
    # sentence alone cannot renew that context indefinitely.
    linked_continuation = prior_depth > 0 and (prior_open_clause or delivery_duration or reporting_reference
                                              or commodity_reference)
    abstract_logistics = (abstract_logistics or grain_intro or economic_evaluation or duration_continuation
                          or carrier_reference or reporting_reference or commodity_reference)
    prior_topics = visual_topics(str((previous or {}).get("visual_query", "")))
    inherited_subject_words = 0
    abstract_economic_only = (economic_evaluation and linked_continuation
                              and not industrial and not speech and not joint
                              and protest_mode == "none" and not term_matches("банк", lowered)
                              and not visual_topics(", ".join(terms)) - {"economy"})
    if ((not terms or grain_intro or abstract_economic_only)
            and not primary and not people and abstract_logistics
            and prior_topics & {"shipping", "rail", "logistics"}
            and not prior_topics - {"shipping", "rail", "logistics", "agriculture"}
            and (not prior_depth or linked_continuation) and prior_depth < 6
            and prior_words + len(text.split()) <= 64):
        terms = [str(previous["visual_query"])]
        inherited_subject_depth = prior_depth + 1
        inherited_subject_words = prior_words + len(text.split())
        commodity_subject = commodity_subject or str((previous or {}).get("commodity_subject", ""))
    prior_report_remaining = int((previous or {}).get("reported_context_remaining", 0))
    prior_report_query = str((previous or {}).get("reported_context_query", ""))
    if reporting_reference and not terms and prior_report_remaining and prior_report_query:
        terms = [prior_report_query, "government building exterior illustrative context"]
    reported_context_query = ""
    reported_context_remaining = 0
    if speech and re.search(rf"\b(?:{_SPEECH_VERBS}|заяв(?:ля|и)\w*)", lowered) and report_context_terms:
        reported_context_query = ", ".join(dict.fromkeys(report_context_terms))
        reported_context_remaining = 2
    elif (prior_report_remaining > 1 and not industrial and protest_mode == "none"
          and not visual_topics(", ".join(terms)) - {"combat"}):
        reported_context_query = prior_report_query
        reported_context_remaining = prior_report_remaining - 1
    volume_continuation = bool(re.search(r"\bобъем\w*|эт\w*\s+продукци\w*", lowered))
    export_outlet = bool(re.search(r"\bвыход\w*.*внешн\w*\s+рын\w*", lowered))
    prior_commodity = str((previous or {}).get("commodity_subject", ""))
    # A quantity-only export predicate omits its already named product. Carry
    # that identity into the existing cargo role, never its old harvest query.
    number_words = (
        r"од(?:ин|на|но|ни|ного|ной|ному|ним|ну|ними|них)|дв(?:а|е|ух|ум|умя)|тр(?:и|ех|ем|емя)|четыр(?:е|ех|ем|ьмя)"
        r"|(?:пят|шест|сем|восем|девят|десят)(?:ь|и|ью|ая|ой|ую|ое|ые|ых|ым|ыми)"
        r"|двадцат(?:ь|и|ью)|тридцат(?:ь|и|ью)|сорок(?:а)?|девяност(?:о|а)"
        r"|(?:пять|шесть|семь|восемь)десят|(?:пяти|шести|семи|восьми)десяти|сто|ста|сот"
        r"|тысяч(?:а|и|у|е|ей|ам|ами|ах)?|миллион(?:а|ов|у|ом|е|ы|ам|ами|ах)?|миллиард(?:а|ов|у|ом|е|ы|ам|ами|ах)?"
        r"|цел(?:ая|ой|ую|ое|ые|ых|ым|ыми|ого|ому)|н[оу]л(?:ь|я|ю|ем|е)"
    )
    quantity_words = rf"(?:выв(?:ез|оз)\w*|экспортир\w*|около|примерно|порядка|более|менее|почти|всего|свыше|тонн(?:а|ы|у|е|ой|ами|ах)?|\d+(?:[.,]\d+)?|{number_words})"
    quantified_export = bool(
        prior_commodity in {"grain", "oil", "agricultural"} and export and re.search(r"\bтонн(?:а|ы|у|е|ой|ами|ах)?\b", lowered)
        and re.fullmatch(rf"\s*{quantity_words}(?:\s+{quantity_words})*\s*[,;:.!?]?\s*", lowered)
        and not primary and not people and not industrial and not speech and not joint
        and protest_mode == "none" and prior_depth < 6 and prior_words + len(text.split()) <= 64
    )
    if quantified_export:
        terms = [{"grain": "grain cargo export warehouse storage logistics",
                  "oil": "oil tanker export terminal refinery logistics",
                  "agricultural": "agricultural products cargo export warehouse logistics"}[prior_commodity]]
        commodity_subject = prior_commodity
        inherited_subject_depth = prior_depth + 1
        inherited_subject_words = prior_words + len(text.split())
    # An explicitly named physical product keeps its identity through a short
    # anaphoric export summary. A financial institution/new action resets it.
    if (not physical_export and not quantified_export and prior_commodity and (volume_continuation or export_outlet)
            and not primary and not people and not industrial and not speech and not joint
            and protest_mode == "none" and not term_matches("банк", lowered)
            and not visual_topics(", ".join(terms)) - {"economy"}
            and prior_depth < 6 and prior_words + len(text.split()) <= 64):
        terms = [str(previous["visual_query"])]
        commodity_subject = prior_commodity
        inherited_subject_depth = prior_depth + 1
        inherited_subject_words = prior_words + len(text.split())
    # A destination fragment describes the preceding vehicle/product, rather
    # than starting a police/guard scene. A denied destination alone keeps that
    # same subject; its excluded port is never added back to the query.
    route_source = text.casefold().replace("ё", "е")
    route_ellipsis = bool(re.match(
        r"\s*(?:(?:теперь|в|первую|очередь|он|она|оно|они|и|а)\s+)*"
        r"(?:движ\w*|направля\w*|следу\w*|идет|идут)\b", lowered)
        and re.search(r"\b(?:границ\w*|западн\w*|маршрут\w*)\b", lowered))
    denied_route_only = (_positive_route_text(route_source) != route_source
                         and not re.sub(r"\b(?:а|но|и)\b|[^\w]", "", lowered))
    prior_route_query = str((previous or {}).get("visual_query", ""))
    denied_port = bool(re.search(r"\bне\s+(?:к|ко|в|во|на|через|по)\s+(?:\w+\s+){0,3}порт\w*", route_source))
    if denied_port:
        # Rail remains the asserted mode. Retaining its old warehouse/port
        # union would allow the denied port back as secondary cargo context.
        if "rail" in prior_topics:
            prior_route_query = ("rail freight train " + ("grain " if re.search(r"\bgrain\b", prior_route_query) else "")
                                 + "cargo transport logistics")
        elif re.search(r"\b(?:cargo|freight|transport|logistics|warehouse)\b", prior_route_query):
            prior_route_query = "warehouse cargo storage logistics, not seaport"
        else:
            prior_route_query = ""
    if ((route_ellipsis or denied_route_only) and prior_topics & {"rail", "logistics", "shipping"}
            and not prior_topics - {"rail", "logistics", "shipping", "agriculture"}
            and not primary and not people and not industrial and not speech and not joint
            and protest_mode == "none" and prior_depth < 6 and prior_words + len(text.split()) <= 64
            and not visual_topics(", ".join(terms)) and prior_route_query):
        terms = [prior_route_query, *terms]
        commodity_subject = commodity_subject or prior_commodity
        inherited_subject_depth = prior_depth + 1
        inherited_subject_words = prior_words + len(text.split())
    # Cost/revenue statements can describe an existing cargo product without
    # asserting a new crop or harvesting action. They consume the same finite
    # context budget. Explicit current logistics costs retain a cargo role
    # independently of that antecedent, without claiming its old commodity.
    producer_revenue = bool(agricultural and re.search(r"\bполуч\w*.*\b(?:денег|доход\w*)\b", lowered)
                            and not re.search(r"\b(?:выращ\w*|саж\w*|уборк\w*|собира\w*)", lowered))
    trader_cost = bool(re.search(r"\bтрейдер\w*", lowered) and re.search(r"\b(?:денег|времен\w*|расход\w*)\b", lowered))
    product_cost = bool(re.search(r"\b(?:его|ее|их)\s+продукци\w*", lowered)
                        and re.search(r"\b(?:логистическ\w*|транспортн\w*)\s+расход\w*", lowered))
    cost_continuation = bool(prior_commodity and (producer_revenue or trader_cost) and not product_cost
                             and not physical_export and (not commodity_subject or commodity_subject == prior_commodity)
                             and (not visual_topics(", ".join(terms)) - {"economy"}
                                  or producer_revenue and terms == ["agriculture farming fields agricultural products"])
                             and prior_topics & {"shipping", "rail", "logistics"}
                             and not prior_topics - {"shipping", "rail", "logistics", "agriculture"}
                             and not primary and not people and not speech and not joint and not harvesting
                             and protest_mode == "none" and not term_matches("банк", lowered)
                             and (not industrial or producer_revenue and not re.search(r"\b(?:завод\w*|ремонт\w*|мост\w*)", lowered)))
    if cost_continuation and prior_depth < 6 and prior_words + len(text.split()) <= 64:
        terms = [str(previous["visual_query"])]
        commodity_subject = prior_commodity
        inherited_subject_depth = prior_depth + 1
        inherited_subject_words = prior_words + len(text.split())
    if (product_cost and not primary and not people and not speech and not joint and not harvesting
            and protest_mode == "none" and not industrial and not physical_export and not commodity_subject):
        terms = ["cargo transport warehouse storage logistics"]
        commodity_subject = ""
    # A transport subject can continue through a short enumeration. A place
    # on its second action (use river ports AND seek capacity in another
    # country) must not relocate the first action. Keep both places visible
    # to existing country guards, without carrying every country in a story.
    physical_subject_places = []
    subject_place_depth = subject_place_words = 0
    current_topics = visual_topics(", ".join(terms))
    prior_places = list((previous or {}).get("physical_subject_places", []))
    prior_place_depth = int((previous or {}).get("subject_place_depth", 0))
    prior_place_words = int((previous or {}).get("subject_place_words", 0))
    transport_topics = {"shipping", "rail", "logistics"}
    explicit_places = _physical_places(lowered, associations)
    place_scope = (not primary and not speech and not joint and not protest
                   and not military_naval and not harvesting and not reported_kinetic_claim
                   and not current_topics - (transport_topics | {"agriculture"})
                   and (bool(current_topics & transport_topics)
                        or not current_topics and (explicit_places or abstract_logistics)
                        and (prior_places or prior_topics & transport_topics)))
    if place_scope:
        continuing_place = (prior_places and prior_place_depth < 6
                            and prior_place_words + len(text.split()) <= 64)
        capacity_action = re.search(r"\b(?:и|а)\s+(?:ищ\w*|иск\w*|подбира\w*|аренду\w*)\b", lowered)
        secondary_place = bool(
            capacity_action and explicit_places
            and not _physical_places(lowered[:capacity_action.start()], associations)
            and any(term_matches(stem, lowered[:capacity_action.start()])
                    for stem in ("порт", "дуна", "причал", "терминал", "перевоз", "железнодорож", "судоход"))
        )
        if continuing_place and (not explicit_places or secondary_place):
            physical_subject_places = prior_places
            subject_place_depth = prior_place_depth + 1
            subject_place_words = prior_place_words + len(text.split())
            if secondary_place:
                terms.extend(f"{place} regional context" for place in prior_places)
        elif explicit_places:
            physical_subject_places = explicit_places
    terms = [person_name(identity) for identity in primary] + terms
    query = ", ".join(dict.fromkeys(terms))
    return {
        "version": 1, "text": text, "visual_query": query,
        "target_people": primary, "mentioned_people": people,
        "person_role": "speaker" if primary and speech else ("participant" if primary else "none"),
        "provenance": "local-lexical-context", "confidence": "rule-based",
        "illustrative_only": True,
        "inherited_subject_depth": inherited_subject_depth,
        "inherited_subject_words": inherited_subject_words,
        "commodity_subject": commodity_subject if not protest else "",
        "physical_subject_places": physical_subject_places,
        "subject_place_depth": subject_place_depth,
        "subject_place_words": subject_place_words,
        "reported_context_query": reported_context_query,
        "reported_context_remaining": reported_context_remaining,
        "reported_action_claim": reported_kinetic_claim,
        "protest_mode": protest_mode if not (speech and primary) else "mentioned-by-speaker",
    }


def visual_topics(query: str) -> set[str]:
    vocabularies = {
        "agriculture": r"harvest|agricultur\w*|farming|wheat|grain",
        "protest": r"protest|rally|picket|labor strike",
        "diplomacy": r"diplomatic|negotiations|summit",
        "combat": r"artillery|shelling|battlefield|frontline|tanks|explosion",
        "digital": r"cyber|servers|computer network|data center",
        "economy": r"economy|economic|finance|banking|markets",
        "shipping": r"tanker|seaport|port|refinery|cargo ship|shipping|maritime",
        "rail": r"rail|train",
        "logistics": r"warehouse|cargo loading|cargo unloading",
    }
    return {topic for topic, expression in vocabularies.items()
            if re.search(rf"\b(?:{expression})\b", query, re.IGNORECASE)}
