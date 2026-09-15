"""Pure data contracts and deterministic quality checks for NewsFlow Ideas.

The bridge owns desktop commands; this module deliberately has no filesystem,
network, model or UI dependencies so its editorial decisions are testable.
"""

from __future__ import annotations

import re
import hashlib
import math
from collections import Counter
from typing import Any


TITLE_MAX_CHARS = 100
TITLE_TARGET_MIN_CHARS = 55
TITLE_TARGET_MAX_CHARS = 95
_ABSTRACT_TITLE_PATTERNS = (
    "ситуация изменилась", "начался новый этап", "что это значит для региона",
    "почему всё пошло не так", "неожиданный поворот", "последствия могут быть серьёзными",
    "европа в шоке", "всё резко изменилось",
)
_WEAK_HEADLINE_PATTERNS = (
    "почему", "снова в центре внимания", "что дальше", "что происходит вокруг",
    "какие меры обсуждают", "что важно не упустить", "главный вопрос темы",
)
_FRAMING_TYPES = {"FACTUAL", "EDITORIAL", "HYPOTHETICAL"}
_HYPOTHETICAL_MARKERS = (
    "что будет, если", "что произойдёт, если", "что произойдет, если",
    "может ли", "возможен ли", "если ", "может ", "на что может",
    "следующий удар может", "что ждёт", "что ждет",
)
_CIS_SIGNALS = (
    "россия", "украин", "беларус", "белорус", "снг", "москва", "киев",
    "путин", "зеленск", "нато", "польша", "литв", "европа", "санкц",
    "газ", "нефт", "миграц", "депортац", "протест", "границ", "иран",
    "ормуз", "судоход",
)
_STAKES_SIGNALS = (
    "удар", "угроз", "конфликт", "давлен", "риск", "провал", "побед",
    "потер", "скандал", "санкц", "переговор", "ультиматум", "взрыв",
    "пожар", "дефиц", "закрыт", "запрет", "рост цен", "эскалац",
)
_HOOK_PATTERNS = (
    ("WHAT_IF", ("что будет, если", "что произойдёт, если", "что произойдет, если", "может ли", "если ")),
    ("ULTIMATUM", ("ультиматум", "последнее условие")),
    ("PRESSURE", ("давлен", "повышает ставки", "ставки растут")),
    ("ESCALATION", ("эскалац", "массирован", "новый удар")),
    ("RESPONSE", ("ответ", "ответный")),
    ("BORDER_CONFLICT", ("границ", "погран")),
    ("POLITICAL_PRICE", ("цена", "заплатит", "потер")),
    ("DEAL_TRAP", ("ловуш", "сделка выйдет боком")),
    ("HIDDEN_RISK", ("скрыт", "риск", "угроз")),
    ("REVERSAL", ("поворот", "разворот", "меняет тон")),
    ("POWER_SHIFT", ("кто выигра", "кто проигра", "рычаг")),
    ("ECONOMIC_PAIN", ("цены", "дороже", "дефиц", "экспорт")),
    ("INTERNATIONAL_REACTION", ("европа", "нато", "сша", "международ")),
    ("CONSEQUENCE", ("последств", "что изменит", "кому станет")),
    ("BREAKING_EVENT", ("срочно", "впервые", "после ночной")),
)
def normalise_title(value: object) -> str:
    """Return a display-ready title without trusting a model's formatting."""
    title = re.sub(r"\s+", " ", str(value or "").strip().strip('"“”«»')).strip()
    return title[:1].upper() + title[1:] if title else ""


def _words(value: object) -> set[str]:
    return {word.casefold() for word in re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", str(value or ""))}


def _semantic_words(value: object) -> set[str]:
    """Small deterministic stem proxy for Russian case and plural endings.

    This is deliberately not a claim of full linguistic semantics.  It only
    prevents evidence matching from rejecting an otherwise grounded title
    because ``давление`` and ``давления`` differ by an ending.
    """
    return {word[:5] for word in _words(value) if len(word) >= 5}


def _semantic_overlap(first: object, second: object) -> set[str]:
    return _semantic_words(first) & _semantic_words(second)


def _stable_id(prefix: str, *parts: object) -> str:
    content = "|".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}_{hashlib.sha1(content.encode('utf-8')).hexdigest()[:12]}"


def _as_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _infer_entities(title: str) -> list[str]:
    known = ("Россия", "Украина", "Трамп", "Зеленский", "Путин", "Москва", "Киев", "ЕС", "НАТО", "Иран", "США")
    lowered = title.casefold()
    return [item for item in known if item.casefold() in lowered]


def normalise_signal(source: str, row: dict) -> dict:
    """Turn one source row into a stable raw-signal record."""
    title = normalise_title(row.get("title", ""))
    entities = _as_list(row.get("primary_entities")) or _infer_entities(title)
    geography = _as_list(row.get("geography"))
    signal_id = _stable_id("sig", source, row.get("url", ""), title)
    return {
        "signal_id": signal_id,
        "source": str(source or "manual"),
        "title": title,
        "url": str(row.get("url", "")),
        "channel": str(row.get("channel", "")),
        "views": max(0, int(row.get("views") or 0)),
        "views_hour": max(0.0, float(row.get("viewsHour") or 0)),
        "age_hours": max(0.0, float(row.get("ageHours") or 0)),
        "event_core": str(row.get("event_core") or title).strip(),
        "primary_entities": entities,
        "secondary_entities": _as_list(row.get("secondary_entities")),
        "action": str(row.get("action", "")).strip(),
        "object": str(row.get("object", "")).strip(),
        "event_family": str(row.get("event_family", "other")).strip() or "other",
        "geography": geography,
        "event_time": row.get("event_time"),
    }


def _signal_similarity(first: dict, second: dict) -> float:
    first_entities = {value.casefold() for value in first.get("primary_entities", [])}
    second_entities = {value.casefold() for value in second.get("primary_entities", [])}
    entity_overlap = len(first_entities & second_entities)
    first_words = _words(f"{first.get('event_core', '')} {first.get('object', '')}")
    second_words = _words(f"{second.get('event_core', '')} {second.get('object', '')}")
    word_overlap = len(first_words & second_words) / max(1, len(first_words | second_words))
    return min(1.0, entity_overlap * 0.35 + word_overlap)


def cluster_events(signals: list[dict]) -> list[dict]:
    """Merge signals of one story; never create a separate event per title."""
    clusters: list[list[dict]] = []
    for signal in signals:
        if not signal or not signal.get("event_core"):
            continue
        target = next((group for group in clusters if _signal_similarity(signal, group[0]) >= 0.45), None)
        if target is None:
            clusters.append([signal])
        else:
            target.append(signal)
    events: list[dict] = []
    for group in clusters:
        group.sort(key=lambda item: (item.get("views_hour", 0), item.get("views", 0)), reverse=True)
        lead = group[0]
        entities = list(dict.fromkeys(value for item in group for value in item.get("primary_entities", [])))
        geography = list(dict.fromkeys(value for item in group for value in item.get("geography", [])))
        actions = list(dict.fromkeys(str(item.get("action", "")).strip() for item in group if item.get("action")))
        objects = list(dict.fromkeys(str(item.get("object", "")).strip() for item in group if item.get("object")))
        source_ids = [item["signal_id"] for item in group]
        core = str(lead.get("event_core", "")).strip()
        events.append({
            "event_id": _stable_id("evt", *sorted(source_ids)),
            "event_core": core,
            "primary_entities": entities,
            "secondary_entities": list(dict.fromkeys(value for item in group for value in item.get("secondary_entities", []))),
            "action": actions[0] if actions else "",
            "object": objects[0] if objects else "",
            "event_family": str(lead.get("event_family", "other")),
            "geography": geography,
            "event_time": lead.get("event_time"),
            "source_signal_ids": source_ids,
            "youtube_signal_count": sum(item.get("source") in {"youtube", "reference"} for item in group),
            "confidence": round(min(1.0, 0.45 + 0.12 * len(group)), 2),
            "demand_inputs": {"views_hour": sum(float(item.get("views_hour", 0)) for item in group),
                              "views": sum(int(item.get("views", 0)) for item in group)},
        })
    return events


def assess_direction(event: dict, recent_items: list[dict]) -> dict:
    """Score a story's usable depth without turning popularity into duplicates."""
    inputs = event.get("demand_inputs", {}) if isinstance(event.get("demand_inputs"), dict) else {}
    views_hour = max(0.0, float(inputs.get("views_hour", 0)))
    views = max(0, int(inputs.get("views", 0)))
    demand = min(100, round(math.log10(views_hour + 1) * 25 + math.log10(views + 1) * 8, 1))
    competition = min(100, round(len(event.get("source_signal_ids", [])) * 18 + math.log10(views_hour + 1) * 8, 1))
    matching = [item for item in recent_items if event.get("event_id") in item.get("event_ids", [])]
    saturation = min(100, round(len(matching) * 35, 1))
    potential = "high" if demand >= 55 and saturation < 60 else "medium" if demand >= 25 and saturation < 80 else "low"
    recommended = {"high": 4, "medium": 2, "low": 1}[potential]
    return {
        "demand_score": demand,
        "competition_score": competition,
        "angle_saturation": saturation,
        "topic_potential": potential,
        "recommended_count": recommended,
        "duplicate_risk": saturation >= 60,
    }


def _title_is_caps(title: str) -> bool:
    letters = "".join(re.findall(r"[A-Za-zА-Яа-яЁё]", title))
    return len(letters) >= 12 and letters.isupper()


def title_quality(title: object) -> dict[str, Any]:
    normalised = normalise_title(title)
    lowered = normalised.casefold()
    reasons: list[str] = []
    if not normalised:
        reasons.append("empty")
    if len(normalised) > TITLE_MAX_CHARS:
        reasons.append("> 100 characters")
    if _title_is_caps(normalised):
        reasons.append("all caps")
    if re.search(r"([!?.,:;])\1+", normalised):
        reasons.append("repeated punctuation")
    if any(pattern in lowered for pattern in _ABSTRACT_TITLE_PATTERNS):
        reasons.append("vague")
    return {
        "title": normalised,
        "valid": not reasons,
        "reasons": reasons,
        "char_count": len(normalised),
        "preferred_length": TITLE_TARGET_MIN_CHARS <= len(normalised) <= TITLE_TARGET_MAX_CHARS,
        "question": "?" in normalised,
    }


def is_weak_headline(title: object) -> bool:
    lowered = normalise_title(title).casefold()
    return any(pattern in lowered for pattern in _WEAK_HEADLINE_PATTERNS)


def _event_context(events: list[dict]) -> tuple[list[str], set[str]]:
    context = []
    vocabulary: set[str] = set()
    for event in events:
        event_core = str(event.get("event_core", "")).strip()
        if event_core:
            context.append(event_core)
            vocabulary |= _words(event_core)
        vocabulary |= _words(event.get("action", ""))
        vocabulary |= _words(event.get("object", ""))
        vocabulary |= {str(value).casefold() for value in event.get("primary_entities", []) if str(value).strip()}
    return context, vocabulary


def classify_hook_family(title: object, seed: dict | None = None) -> str:
    """Classify the editorial promise instead of reducing it to punctuation."""
    lowered = str(title or "").casefold()
    for family, markers in _HOOK_PATTERNS:
        if any(marker in lowered for marker in markers):
            return family
    if "?" in lowered:
        return "WHAT_IF"
    if ":" in lowered:
        return "BREAKING_EVENT"
    return "PERSONAL_CONFLICT" if any(marker in lowered for marker in ("трамп", "путин", "зеленск")) else "CONSEQUENCE"


def _script_requirements(seed: dict, events: list[dict], manual: bool,
                         framing_type: str = "EDITORIAL") -> list[str]:
    requirements = [f"объяснить тему: {seed['topic']}"]
    if events:
        event = events[0]
        entities = [str(value) for value in event.get("primary_entities", []) if str(value).strip()]
        if entities:
            requirements.append(f"назвать участников: {', '.join(entities)}")
        if event.get("event_core"):
            requirements.append(f"раскрыть подтверждённый контекст: {event['event_core']}")
        if event.get("object"):
            requirements.append(f"объяснить предмет конфликта: {event['object']}")
    elif manual:
        requirements.append("отделить проверенные данные от редакционных оценок")
    requirements.append(f"раскрыть угол: {seed['angle']}")
    if framing_type == "FACTUAL":
        requirements.extend([
            "использовать только подтверждённые факты из Event Context",
            "не добавлять редакционных причин и последствий без подтверждения",
        ])
    elif framing_type == "EDITORIAL":
        requirements.extend([
            "сначала отделить подтверждённый контекст от редакционной трактовки",
            "построить агрессивную редакционную трактовку через конфликт, цену, риск или проигрыш",
            "не выдавать редакционную интерпретацию за подтверждённый факт",
        ])
    elif framing_type == "HYPOTHETICAL":
        requirements.extend([
            "объяснить реальное исходное положение",
            "явно указать, что дальнейший сценарий является предположением",
            "показать условия реализации сценария и возможные последствия",
            "не выдавать прогноз за уже произошедшее событие",
        ])
    return requirements


def _framing_type(seed: dict) -> str:
    value = str(seed.get("framing_type", "EDITORIAL")).strip().upper()
    return value if value in _FRAMING_TYPES else "EDITORIAL"


def validate_framing(seed: dict, title: str, events: list[dict]) -> tuple[bool, str, list[str]]:
    """Validate declared framing without collapsing editorial work into facts."""
    framing_type = _framing_type(seed)
    lowered = title.casefold()
    if not events:
        return False, "HIGH", ["Нужен базовый Event Context для нового ProductionItem"]
    if framing_type == "HYPOTHETICAL":
        if not any(marker in lowered for marker in _HYPOTHETICAL_MARKERS):
            return False, "HIGH", ["Hypothetical title requires an explicit uncertainty marker"]
        return True, "MEDIUM", ["Сценарий должен оставаться прогнозом, а не сообщением о факте"]
    if framing_type == "FACTUAL":
        return True, "LOW", ["Все основные утверждения должны быть подтверждены Event Context"]
    speculative = any(marker in lowered for marker in ("может", "риск", "цена", "ловуш", "давлен", "выйти боком"))
    return True, "MEDIUM" if speculative else "LOW", [
        "Редакционная трактовка допустима только поверх подтверждённого базового события"
    ]


def assess_cis_audience(seed: dict, events: list[dict]) -> dict:
    """Score relevance and emotional stakes for the intended CIS audience."""
    text = " ".join([
        str(seed.get("direction", "")), str(seed.get("topic", "")), str(seed.get("angle", "")),
        *[" ".join((str(event.get("event_core", "")), str(event.get("object", "")))) for event in events],
    ]).casefold()
    direct_markers = ("россия", "украин", "беларус", "белорус", "снг", "москва", "киев", "путин", "зеленск")
    cis_hits = sum(marker in text for marker in direct_markers)
    stakes_hits = sum(marker in text for marker in _STAKES_SIGNALS)
    entities = [str(entity) for event in events for entity in event.get("primary_entities", []) if str(entity).strip()]
    has_causal_export_link = any(marker in text for marker in ("российск", "экспорт", "санкц", "поставк", "цены", "энергет")) \
        and any(marker in text for marker in ("россия", "европа", "ормуз", "нефт", "газ"))
    if cis_hits:
        relevance = min(95, 58 + cis_hits * 8 + min(14, len(set(entities)) * 4) + (8 if events else 0))
        why = "Тема напрямую связана с русскоязычной СНГ-повесткой: " + ", ".join(
            marker for marker in direct_markers if marker in text
        ) + "."
    elif has_causal_export_link:
        relevance = min(78, 52 + min(12, len(set(entities)) * 4) + (8 if events else 0))
        why = "Изменение ситуации может влиять на цены, поставки или положение российских экспортёров."
    else:
        relevance = min(55, 24 + min(10, len(set(entities)) * 3) + (6 if events else 0))
        why = "Это общемировая история без подтверждённой прямой связи с интересами СНГ-аудитории."
    stakes = min(100, 18 + stakes_hits * 13 + (10 if "EDITORIAL" == _framing_type(seed) else 0)
                 + (12 if "HYPOTHETICAL" == _framing_type(seed) else 0))
    return {
        "cis_audience_relevance_score": relevance,
        "why_cis_audience_cares": why,
        "emotional_stakes_score": stakes,
    }


def build_production_item(seed: dict, title: object, events: list[dict]) -> dict | None:
    """Build one safe Title→Script contract, or reject an unsafe weak title."""
    quality = title_quality(title)
    if not quality["valid"]:
        return None
    direction = str(seed.get("direction", "")).strip()
    topic = str(seed.get("topic", "")).strip()
    angle = str(seed.get("angle", "")).strip()
    if not direction or not topic or not angle:
        return None
    context, vocabulary = _event_context(events)
    manual = not events
    overlap = _semantic_overlap(quality["title"], " ".join(vocabulary))
    # A finished Production Item must be grounded in the evidence bundle.
    # Direction-only drafts can stay in the UI as planning material, but they
    # cannot reach scenarios because even a seemingly cautious headline can
    # smuggle in an unverified causal claim.
    framing_type = _framing_type(seed)
    framing_valid, factual_risk, _framing_notes = validate_framing(seed, quality["title"], events)
    if manual or not framing_valid:
        return None
    minimum_overlap = 2 if framing_type == "FACTUAL" else 1
    if framing_type != "HYPOTHETICAL" and events and len(overlap) < minimum_overlap:
        return None
    event_ids = [str(event.get("event_id", "")).strip() for event in events if event.get("event_id")]
    core_event = context[0] if context else f"Редакционная тема: {direction}"
    event = events[0] if events else {}
    subject = next((str(value) for value in event.get("primary_entities", []) if str(value).strip()), "")
    conflict = str(event.get("object") or topic).strip()
    audience = assess_cis_audience(seed, events)
    if audience["cis_audience_relevance_score"] < 50:
        return None
    scriptability = 45 + min(20, len(overlap) * 5) + (15 if events else 5) + (10 if conflict else 0)
    hook = classify_hook_family(quality["title"], seed)
    creative_amplification = min(100, 30 + (24 if framing_type == "EDITORIAL" else 0)
                                 + (35 if framing_type == "HYPOTHETICAL" else 0)
                                 + min(20, audience["emotional_stakes_score"] // 5))
    hook_weight = {
        "ULTIMATUM": 16, "PRESSURE": 15, "ESCALATION": 15, "DEAL_TRAP": 15,
        "POWER_SHIFT": 14, "HIDDEN_RISK": 13, "WHAT_IF": 12, "BORDER_CONFLICT": 10,
        "POLITICAL_PRICE": 10, "ECONOMIC_PAIN": 10, "REVERSAL": 9, "RESPONSE": 9,
        "BREAKING_EVENT": 8, "CONSEQUENCE": 6, "INTERNATIONAL_REACTION": 6,
    }.get(hook, 5)
    click_score = round(26 + hook_weight + min(12, len(overlap) * 3) + (5 if conflict else 0)
                        + (4 if quality["preferred_length"] else 0)
                        + min(14, audience["emotional_stakes_score"] // 6)
                        + min(16, creative_amplification // 6)
                        + (5 if subject else 0))
    if creative_amplification < 70 and audience["emotional_stakes_score"] < 60:
        click_score = min(click_score, 89)
    click_score = min(95, click_score)
    direction_words = _words(direction)
    direction_fit = min(100, 45 + min(30, len(direction_words & (_words(topic) | _words(quality["title"]))) * 10)
                        + (15 if events else 0))
    novelty = min(88, 52 + (9 if hook != "statement" else 0) + min(18, len(_words(angle)) * 3)
                  + (8 if framing_type == "HYPOTHETICAL" else 0))
    consequence = str(seed.get("main_consequence") or seed.get("consequence") or conflict).strip()
    information_payload = (dict(seed.get("information_payload", {}))
                           if isinstance(seed.get("information_payload"), dict) else {})
    information_payload.setdefault("event_core", core_event)
    information_payload.setdefault("subject", subject)
    information_payload.setdefault("action", str(event.get("action", "")))
    information_payload.setdefault("object", str(event.get("object", "")))
    information_payload.setdefault("consequence", consequence)
    declared_requirements = _as_list(seed.get("script_requirements"))
    if framing_type == "EDITORIAL":
        declared_requirements = [value for value in declared_requirements
                                 if not any(marker in value.casefold() for marker in (
                                     "нейтральн", "не превращать", "сдержанн"))]
    script_requirements = list(dict.fromkeys([
        *_script_requirements({"topic": topic, "angle": angle}, events, manual, framing_type),
        *declared_requirements,
    ]))
    return {
        "direction": direction,
        "topic": topic,
        "angle": angle,
        "title": quality["title"],
        "event_ids": event_ids,
        "supporting_context": context or [f"Ручное направление: {direction}"],
        "core_event": core_event,
        "core_claim": quality["title"],
        "conflict": conflict,
        "promised_question": f"Что необходимо понять о теме «{topic}» через угол «{angle}»",
        "script_requirements": script_requirements,
        "framing_type": framing_type,
        "factual_risk_score": factual_risk,
        **audience,
        "click_score": click_score,
        "creative_amplification_score": creative_amplification,
        "novelty_score": novelty,
        "scriptability_score": min(100, scriptability),
        "direction_fit_score": direction_fit,
        "char_count": quality["char_count"],
        "hook_family": hook,
        "macro_event_id": str(seed.get("macro_event_id", "")),
        "primary_entity": subject,
        "primary_entities": list(event.get("primary_entities", [])),
        "geography": list(event.get("geography", [])) if events else [],
        "main_consequence": consequence,
        "information_payload": information_payload,
        "information_payload_source": "declared" if isinstance(seed.get("information_payload"), dict) else "derived",
        "topic_family": str(seed.get("topic_family", angle)),
        "angle_family": str(seed.get("angle_family", angle)),
        "manual": manual,
        "status": "APPROVED",
    }


def _topic_signature(value: str) -> set[str]:
    return {word[:5] for word in _words(value)}


def _topic_similarity(first: str, second: str) -> float:
    left, right = _topic_signature(first), _topic_signature(second)
    return len(left & right) / max(1, len(left | right))


def _title_similarity(first: str, second: str) -> float:
    """Conservative lexical semantic proxy for headline rewordings.

    A topic naturally repeats across independent angles of the same event, so
    comparing ``topic`` would incorrectly collapse a logistics story and an
    insurance story into one.  The finished headline is the correct unit for
    the duplicate gate until an embedding service is introduced.
    """
    left, right = _words(first), _words(second)
    return len(left & right) / max(1, len(left | right))


def production_similarity(first: dict, second: dict) -> float:
    """Compare the future information payload, not only headline wording."""
    left_events = {str(value) for value in first.get("event_ids", []) if str(value)}
    right_events = {str(value) for value in second.get("event_ids", []) if str(value)}
    event_overlap = bool(left_events & right_events)
    left_payload = first.get("information_payload", {}) if isinstance(first.get("information_payload"), dict) else {}
    right_payload = second.get("information_payload", {}) if isinstance(second.get("information_payload"), dict) else {}
    left_core = _topic_signature(" ".join(str(value) for value in left_payload.values()))
    right_core = _topic_signature(" ".join(str(value) for value in right_payload.values()))
    payload_similarity = len(left_core & right_core) / max(1, len(left_core | right_core))
    title_similarity = _title_similarity(str(first.get("title", "")), str(second.get("title", "")))
    same_declared_payload = (
        first.get("information_payload_source") == "declared"
        and second.get("information_payload_source") == "declared"
        and left_payload == right_payload
    )
    if event_overlap and same_declared_payload:
        return 1.0
    if not event_overlap:
        return round(max(payload_similarity * .55, title_similarity), 3)
    return round((payload_similarity * .55) + (title_similarity * .45), 3)


def _value_similarity(first: object, second: object) -> float:
    left, right = _semantic_words(first), _semantic_words(second)
    return len(left & right) / max(1, len(left | right))


def _list_similarity(first: object, second: object) -> float:
    left = _semantic_words(" ".join(_as_list(first)))
    right = _semantic_words(" ".join(_as_list(second)))
    return len(left & right) / max(1, len(left | right))


def script_overlap(first: dict, second: dict) -> dict[str, float]:
    """Compare the eventual video explanation, not merely headline wording."""
    first_events = {str(value) for value in first.get("event_ids", []) if str(value)}
    second_events = {str(value) for value in second.get("event_ids", []) if str(value)}
    event_bundle_overlap = len(first_events & second_events) / max(1, len(first_events | second_events))
    first_payload = first.get("information_payload", {}) if isinstance(first.get("information_payload"), dict) else {}
    second_payload = second.get("information_payload", {}) if isinstance(second.get("information_payload"), dict) else {}
    payload_overlap = _value_similarity(" ".join(str(value) for value in first_payload.values()),
                                        " ".join(str(value) for value in second_payload.values()))
    core_facts_overlap = _value_similarity(
        f"{first.get('core_event', '')} {first.get('conflict', '')}",
        f"{second.get('core_event', '')} {second.get('conflict', '')}",
    )
    actors_overlap = _list_similarity(first.get("primary_entities", []), second.get("primary_entities", []))
    requirements_overlap = _list_similarity(first.get("script_requirements", []), second.get("script_requirements", []))
    consequence_overlap = _value_similarity(first.get("main_consequence", ""), second.get("main_consequence", ""))
    payoff_overlap = _value_similarity(first_payload.get("core", ""), second_payload.get("core", ""))
    score = (event_bundle_overlap * .28 + core_facts_overlap * .20 + payload_overlap * .17
             + requirements_overlap * .15 + actors_overlap * .08 + consequence_overlap * .06
             + payoff_overlap * .06)
    return {
        "script_overlap": round(min(1.0, score), 3),
        "event_bundle_overlap": round(event_bundle_overlap, 3),
        "payload_overlap": round(payload_overlap, 3),
    }


def _bundle_key(item: dict) -> str:
    macro = str(item.get("macro_event_id", "")).strip()
    if macro:
        return macro
    event_ids = sorted(str(value) for value in item.get("event_ids", []) if str(value))
    return "|".join(event_ids) or f"direction:{str(item.get('direction', '')).casefold()}"


def _production_strength(item: dict) -> float:
    return (float(item.get("click_score", 0)) * .32
            + float(item.get("creative_amplification_score", 0)) * .24
            + float(item.get("emotional_stakes_score", 0)) * .18
            + float(item.get("scriptability_score", 0)) * .16
            + float(item.get("novelty_score", 0)) * .10)


def rewrite_title_structure(title: object, seed: dict) -> str | None:
    """Give a strong question a different headline concept before rejecting it."""
    original = normalise_title(title)
    topic = str(seed.get("topic", "")).strip()
    angle = str(seed.get("angle", "")).strip()
    framing_type = _framing_type(seed)
    lowered = original.casefold().rstrip("?").strip()
    if not topic or not angle:
        return None
    if framing_type == "HYPOTHETICAL" and lowered.startswith("что будет, если "):
        scenario = original.rstrip("?").strip()[len("Что будет, если "):].strip()
        rewritten = f"Если {scenario} — последствия могут изменить расстановку сил"
    elif framing_type == "HYPOTHETICAL":
        rewritten = f"Если {topic.casefold()} сорвётся — {angle.casefold()} изменит расстановку сил"
    else:
        rewritten = f"{topic}: {angle} — кому это может выйти боком"
    quality = title_quality(rewritten)
    return quality["title"] if quality["valid"] else None


def _independently_evidenced(first: dict, second: dict, overlap: dict[str, float]) -> bool:
    first_events = {str(value) for value in first.get("event_ids", []) if str(value)}
    second_events = {str(value) for value in second.get("event_ids", []) if str(value)}
    return bool(first_events - second_events) and bool(second_events - first_events) \
        and overlap["script_overlap"] < .48 and overlap["payload_overlap"] < .45


def _candidate_events(candidate: dict, events: list[dict]) -> list[dict]:
    declared_event_ids = {str(value).strip() for value in candidate.get("event_ids", [])
                          if str(value).strip()} if isinstance(candidate.get("event_ids"), list) else set()
    if declared_event_ids:
        return [event for event in events if str(event.get("event_id", "")).strip() in declared_event_ids]
    matches = []
    for event in events:
        event_words = _semantic_words(f"{event.get('event_core', '')} {event.get('object', '')}")
        if len(_semantic_words(f"{candidate.get('topic', '')} {candidate.get('title', '')}") & event_words) >= 2:
            matches.append(event)
    return matches


def _rejection_reason(candidate: dict, events: list[dict]) -> str:
    """Return a reviewable rejection reason before dropping a candidate."""
    quality = title_quality(candidate.get("title", ""))
    if not quality["valid"]:
        return quality["reasons"][0]
    if not events:
        return "factual support insufficient"
    title = quality["title"]
    framing_valid, _risk, _notes = validate_framing(candidate, title, events)
    if not framing_valid:
        return "factual support insufficient"
    context_words = _event_context(events)[1]
    required_overlap = 2 if _framing_type(candidate) == "FACTUAL" else 1
    if len(_semantic_overlap(title, " ".join(context_words))) < required_overlap:
        return "factual support insufficient"
    if assess_cis_audience(candidate, events)["cis_audience_relevance_score"] < 50:
        return "low CIS relevance"
    return "low scriptability"


def _count_values(items: list[dict], field: str) -> dict[str, int]:
    values = [str(item.get(field, "")).strip() for item in items if str(item.get(field, "")).strip()]
    return dict(sorted(Counter(values).items()))


def _portfolio_diversity(items: list[dict]) -> dict[str, dict[str, int]]:
    """Persist the actual batch composition for editorial review and balancing."""
    return {
        "macro_events": _count_values(items, "macro_event_id"),
        "directions": _count_values(items, "direction"),
        "primary_entities": _count_values(items, "primary_entity"),
        "topic_families": _count_values(items, "topic_family"),
        "angle_families": _count_values(items, "angle_family"),
        "hook_families": _count_values(items, "hook_family"),
        "framing_types": _count_values(items, "framing_type"),
        "geographies": dict(sorted(Counter(
            str(geography).strip()
            for item in items for geography in item.get("geography", [])
            if str(geography).strip()
        ).items())),
    }


def select_production_portfolio(candidates: list[dict], events: list[dict], requested_count: int) -> tuple[list[dict], dict]:
    """Accept independently scriptable items and report quality deficit.

    The selector intentionally returns fewer than requested items rather than
    making a cosmetic rewrite of the same topic or angle.
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    question_limit = max(1, math.floor(max(1, requested_count) * 0.2))
    question_count = 0
    evaluable: list[dict] = []
    for candidate in candidates:
        candidate = dict(candidate)
        if is_weak_headline(candidate.get("title", "")):
            rewritten_title = rewrite_title_structure(candidate.get("title", ""), candidate)
            if rewritten_title:
                candidate["title"] = rewritten_title
            else:
                rejected.append({"candidate": candidate, "reason": "weak hook after rewrite"})
                continue
        related = _candidate_events(candidate, events)
        item = build_production_item(candidate, candidate.get("title", ""), related)
        if item is None:
            reason = _rejection_reason(candidate, related)
            rejected.append({"candidate": dict(candidate), "reason": reason})
            continue
        if item["scriptability_score"] < 60:
            rejected.append({"candidate": dict(candidate), "reason": "low scriptability"})
            continue
        evaluable.append(item)
    evaluable.sort(key=_production_strength, reverse=True)
    for item in evaluable:
        duplicate = next((previous for previous in accepted
                          if (set(previous["event_ids"]) & set(item["event_ids"]))
                          and (previous["angle_family"] == item["angle_family"]
                               or _title_similarity(previous["title"], item["title"]) >= 0.60
                               or production_similarity(previous, item) >= 0.78)), None)
        if duplicate:
            rejected.append({"candidate": {"title": item["title"], "topic": item["topic"], "angle": item["angle"],
                                            "direction": item["direction"]}, "reason": "production_duplicate",
                             "nearest_duplicate": duplicate["title"],
                             "similarity": production_similarity(duplicate, item),
                             **script_overlap(duplicate, item)})
            continue
        bundle_items = [previous for previous in accepted if _bundle_key(previous) == _bundle_key(item)]
        if bundle_items:
            nearest = max(bundle_items, key=lambda previous: script_overlap(previous, item)["script_overlap"])
            overlap = script_overlap(nearest, item)
            if not _independently_evidenced(nearest, item, overlap):
                rejected.append({"candidate": {"title": item["title"], "topic": item["topic"], "angle": item["angle"],
                                                "direction": item["direction"]}, "reason": "production_duplicate",
                                 "nearest_duplicate": nearest["title"], "similarity": production_similarity(nearest, item),
                                 **overlap, "rejection_detail": "same narrow Event Bundle without independent evidence"})
                continue
            if len(bundle_items) >= 2 and not all(_independently_evidenced(previous, item, script_overlap(previous, item))
                                                  for previous in bundle_items):
                rejected.append({"candidate": {"title": item["title"], "topic": item["topic"], "angle": item["angle"],
                                                "direction": item["direction"]}, "reason": "production_duplicate",
                                 "nearest_duplicate": nearest["title"], "similarity": production_similarity(nearest, item),
                                 **overlap, "rejection_detail": "third item needs a separately evidenced subevent"})
                continue
        if title_quality(item["title"])["question"] and question_count >= question_limit:
            rewritten_title = rewrite_title_structure(item["title"], item)
            related_events = [event for event in events if str(event.get("event_id", "")) in set(item["event_ids"])]
            rewritten = build_production_item(item, rewritten_title, related_events) if rewritten_title else None
            if rewritten and not title_quality(rewritten["title"])["question"]:
                item = rewritten
            else:
                rejected.append({"candidate": {"title": item["title"], "topic": item["topic"], "angle": item["angle"],
                                                "direction": item["direction"]}, "reason": "question limit after rewrite"})
                continue
        if title_quality(item["title"])["question"]:
            question_count += 1
        accepted.append(item)
        if len(accepted) >= requested_count:
            break
    return accepted, {
        "requested": requested_count,
        "accepted": len(accepted),
        "deficit": max(0, requested_count - len(accepted)),
        "question_count": question_count,
        "diversity": _portfolio_diversity(accepted),
        "rejected": rejected,
    }
