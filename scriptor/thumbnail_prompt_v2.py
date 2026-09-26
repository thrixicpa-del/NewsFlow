"""The single runtime core for NewsFlow FastGen thumbnail prompts.

This module deliberately owns the visual contract used by both the prompt
writer and the FastGen adapter.  Keeping one renderer prevents a UI preview
from drifting away from the provider payload.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

_LAYOUTS = ("IMPACT", "SPLIT", "DIAGONAL", "STACKED", "ALERT", "CLEAN DRAMA")


def _clean(value: object, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _context(item: Mapping[str, object], *names: str) -> str:
    for name in names:
        value = item.get(name)
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(part) for part in value if str(part).strip())
        text = " ".join(str(value or "").split())
        if text:
            return text
    return ""


def _topic_scene_defaults(title: str, source: str) -> dict[str, str]:
    """Return a concrete, neutral scene plan when structured facts are absent.

    This is a semantic fallback, not a second prompt builder: each string is a
    renderable subject, action, evidence, setting or emotional read.  It keeps
    a provider from receiving the former meta-instructions such as "choose a
    concrete action" when a newly created topic has not yet been enriched.
    """
    fallback = {
        "main_subject": title,
        "visible_action": f"The central people and objects named in “{title}” are shown in an immediate visible response.",
        "visual_evidence": f"The frame visibly anchors the development named in “{title}” with its named people, object or location.",
        "environment": f"The real-world location directly connected to “{title}”.",
        "emotion": "Focused news tension tied to the visible development.",
    }
    if any(term in source for term in ("карабах", "karabakh", "армени", "armenia", "азербайдж", "azerbaijan")):
        return {
            "main_subject": "Armenian and Azerbaijani officials in the Karabakh peace process",
            "visible_action": "Delegations study documents and a regional map during direct negotiations",
            "visual_evidence": "Karabakh map, negotiation papers, microphones and Armenian/Azerbaijani flags",
            "environment": "Real diplomatic negotiation room in the South Caucasus",
            "emotion": "Tense consequential bargaining",
        }
    if any(term in source for term in ("трамп", "trump")) and any(term in source for term in ("путин", "putin")):
        return {
            "main_subject": "Donald Trump and Vladimir Putin in high-level political contact",
            "visible_action": "The two leaders speak or confer while aides and press observe",
            "visual_evidence": "Trump, Putin, official flags, briefing papers and press cameras",
            "environment": "Real presidential meeting or diplomatic contact setting",
            "emotion": "High-stakes geopolitical tension",
        }
    if any(term in source for term in ("wildberries", "вайлдберриз", "warehouse", "склад")):
        return {
            "main_subject": "The Wildberries warehouse incident and its immediate operational impact",
            "visible_action": "Warehouse staff and emergency responders work around the affected logistics site",
            "visual_evidence": "Warehouse racks, parcels, loading bays, staff and emergency response details",
            "environment": "Real e-commerce warehouse and logistics loading area",
            "emotion": "Operational urgency and disruption",
        }
    if any(term in source for term in ("томат", "помидор", "tomato")):
        return {
            "main_subject": "Tomato supply and the produce market affected by the reported change",
            "visible_action": "Growers, wholesalers or shoppers inspect tomato crates as supply changes become visible",
            "visual_evidence": "Tomato crates, produce labels, wholesale pallets and market counters",
            "environment": "Real produce market, greenhouse or wholesale distribution setting",
            "emotion": "Visible concern about food supply and prices",
        }
    if any(term in source for term in ("ормуз", "hormuz", "ormuz")):
        return {
            "main_subject": "Iranian pressure on oil shipping routes",
            "visible_action": "Oil tankers affected near Strait of Hormuz",
            "visual_evidence": "Tankers, maritime tension, naval presence, crisis atmosphere",
            "environment": "Strait of Hormuz shipping lane and nearby port infrastructure",
            "emotion": "Urgent maritime tension and market shock",
        }
    if any(term in source for term in ("нато", "nato")):
        return {
            "main_subject": "NATO and EU consultation on escalation risk",
            "visible_action": "Officials and journalists reacting during a NATO or EU consultation",
            "visual_evidence": "Official NATO and EU fabric flags, press cameras, security and briefing documents",
            "environment": "NATO summit, headquarters press zone or consultation room",
            "emotion": "Visible diplomatic tension and urgent public scrutiny",
        }
    if any(term in source for term in ("евросоюз", "европа", "eu ", " eu", "санкц")):
        return {
            "main_subject": "EU or NATO consultation on an international decision",
            "visible_action": "EU or NATO officials consult around briefing documents while press cameras record the meeting",
            "visual_evidence": "EU and NATO flags, officials, consultation papers and press cameras",
            "environment": "EU or NATO consultation room and press zone",
            "emotion": "Visible diplomatic pressure during a decision meeting",
        }
    if (any(term in source for term in ("порт", "port", "контейнер", "container", "мост", "bridge", "трубопровод", "pipeline", "газ", "gas", "завод", "plant", "электростанц", "power station"))
            and not any(term in source for term in ("мэр", "mayor", "президент", "president", "заяв", "said", "объяв", "announce"))):
        subject = "Port operations and container traffic" if any(term in source for term in ("порт", "port", "контейнер", "container")) else "The infrastructure site named in the topic"
        evidence = "Container stacks, cargo cranes and a terminal operations board" if any(term in source for term in ("порт", "port", "контейнер", "container")) else "The named infrastructure, work crews, safety equipment and a visible operations detail"
        environment = "Working port terminal and container loading zone" if any(term in source for term in ("порт", "port", "контейнер", "container")) else "The real infrastructure location named in the topic"
        return {
            "main_subject": subject,
            "visible_action": "Operations pause or crews respond at the affected site while the consequence remains visible",
            "visual_evidence": evidence,
            "environment": environment,
            "emotion": "Operational urgency around a disrupted essential service",
        }
    if any(term in source for term in (
        "нефт", "oil", "баррел", "barrel", "opec", "опек", "топлив", "fuel",
        "энергорын", "energy market",
    )):
        return {
            "main_subject": "Oil price movement and the supply decision behind it",
            "visible_action": "Energy traders react to changing oil prices on live market boards",
            "visual_evidence": "Oil price charts, trading screens, supply-route map and tanker or barrel details",
            "environment": "Energy-market trading floor with oil logistics context",
            "emotion": "Immediate market alarm as prices and supply expectations move",
        }
    if any(term in source for term in ("мэр", "mayor", "президент", "president", "заяв", "said", "объяв", "announce", "переговор", "negotiat", "правительств", "government")):
        person = "mayor" if any(term in source for term in ("мэр", "mayor")) else "president" if any(term in source for term in ("президент", "president")) else "official"
        object_detail = "bridge repair plans" if any(term in source for term in ("мост", "bridge", "ремонт", "repair")) else "official briefing documents"
        return {
            "main_subject": f"The {person}'s public announcement",
            "visible_action": f"The {person} speaks at a live press briefing while reporters record the announcement",
            "visual_evidence": f"Press microphones, cameras, reporters and {object_detail}",
            "environment": "Official press briefing room with a visible public-information backdrop",
            "emotion": "Concentrated public attention during a consequential statement",
        }
    if any(term in source for term in ("конфликт", "conflict", "эскалац", "escalat", "военн", "military", "границ", "border")):
        return {
            "main_subject": "The named international confrontation and its affected participants",
            "visible_action": "Officials, security personnel and civilians respond to the visible situation at the named location",
            "visual_evidence": "The named border, official vehicles, security presence and on-the-ground reporting equipment",
            "environment": "The real border or diplomatic location named in the topic",
            "emotion": "Tense uncertainty around a visible international confrontation",
        }
    return fallback


def visual_brief(item: Mapping[str, object] | None = None) -> dict[str, str]:
    """Derive semantic scene values; this function never adds visual style rules."""
    row = item or {}
    title = _clean(row.get("title"), "current news topic")
    source = " ".join((title, _context(row, "script", "event_context", "supporting_context"))).casefold()
    selected_people = _context(row, "face_reference_label", "selected_people", "primary_entities", "primary_entity", "entities")
    defaults = _topic_scene_defaults(title, source)
    main_subject = _context(row, "main_subject", "topic", "angle") or defaults["main_subject"]
    action = _context(row, "visible_action", "action", "event_context", "conflict")
    evidence = _context(row, "visual_evidence", "main_consequence", "consequence", "object", "topic")
    environment = _context(row, "environment", "geography", "location")
    emotion = _context(row, "emotion", "tension", "framing")
    identity = _context(row, "production_item_id", "id", "title")
    digest = int(hashlib.sha256(identity.casefold().encode("utf-8")).hexdigest()[:8], 16)
    return {
        "title": title,
        "main_subject": _clean(main_subject, title),
        "selected_people": selected_people or "None selected",
        "visible_action": _clean(action, defaults["visible_action"]),
        "visual_evidence": _clean(evidence, defaults["visual_evidence"]),
        "environment": _clean(environment, defaults["environment"]),
        "emotion": _clean(emotion, defaults["emotion"]),
        "headline": _context(row, "cover_headline"),
        "subheadline": _context(row, "cover_subheadline"),
        "layout": _LAYOUTS[digest % len(_LAYOUTS)],
    }


_SCENE_STYLE_MARKERS = (
    "newsflow fastgen", "clickability", "drama =", "action =", "emotion =", "photoreal",
    "16:9", "youtube", "headline", "subheadline", "typography", "render this exact",
    "breaking-news", "breaking news", "no explosions", "no missiles", "no drones",
    "no military vehicles", "no logos", "no watermark", "artistic artwork", "digital art",
    "illustration", "cinematic", "negative rules", "red edge", "outer edges",
)


def _semantic_scene(value: object, fallback: str) -> str:
    """Keep only scene facts from an old prompt; all treatment belongs to V2 below."""
    raw = str(value or "")
    # A prior final V2 payload is structured.  Reusing it as a scene draft must
    # take only its STORY CONTEXT block; flattening it first leaves a bare
    # ``CORE STYLE:`` label after the V2 treatment is stripped.
    structured = re.search(
        r"(?ims)^\s*STORY CONTEXT:\s*(.*?)(?=^\s*(?:MAIN SUBJECT|SELECTED PEOPLE|VISIBLE ACTION|VISUAL EVIDENCE|ENVIRONMENT|EMOTION|SELECTED COMPOSITION|IDENTITY / REFERENCES|HEADLINE|SUBHEADLINE|TYPOGRAPHY|RED EDGE ACCENTS|FINAL NEGATIVE RULES):|\Z)",
        raw,
    )
    if structured:
        return _clean(structured.group(1), fallback)
    text = " ".join(raw.split())
    if "SCENE DETAILS:" in text:
        text = text.split("SCENE DETAILS:", 1)[1]
    text = re.sub(r"NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2\..*?(?=SCENE DETAILS:|$)", "", text,
                  flags=re.IGNORECASE)
    candidates = re.split(r"(?<=[.!?])\s+", text)
    semantic = [
        sentence.strip(" .") for sentence in candidates
        if sentence.strip() and not any(marker in sentence.casefold() for marker in _SCENE_STYLE_MARKERS)
    ]
    return _clean(". ".join(semantic), fallback)


_STRUCTURED_SCENE_FIELDS = (
    ("MAIN SUBJECT", "main_subject"),
    ("SELECTED PEOPLE", "selected_people"),
    ("VISIBLE ACTION", "visible_action"),
    ("VISUAL EVIDENCE", "visual_evidence"),
    ("ENVIRONMENT", "environment"),
    ("EMOTION", "emotion"),
)
_STRUCTURED_PROMPT_LABELS = (
    "CORE STYLE", "STORY CONTEXT", *[name for name, _key in _STRUCTURED_SCENE_FIELDS],
    "SELECTED COMPOSITION", "IDENTITY / REFERENCES", "HEADLINE", "SUBHEADLINE",
    "TYPOGRAPHY", "RED EDGE ACCENTS", "FINAL NEGATIVE RULES",
)


def _structured_scene_values(value: object) -> dict[str, str]:
    """Read planner scene slots from a multiline V2 draft without style leakage."""
    raw = str(value or "")
    if not re.search(r"(?im)^\s*STORY CONTEXT:\s*", raw):
        return {}
    next_label = "|".join(re.escape(label) for label in _STRUCTURED_PROMPT_LABELS)
    values: dict[str, str] = {}
    for label, key in _STRUCTURED_SCENE_FIELDS:
        match = re.search(
            rf"(?ims)^\s*{re.escape(label)}:\s*(.*?)(?=^\s*(?:{next_label}):|\Z)", raw,
        )
        if match and (text := " ".join(match.group(1).split())):
            values[key] = text
    return values


def prompt_sources_debug() -> dict[str, str]:
    """Human-readable provenance stored with a render, outside the provider prompt."""
    return {
        "CORE STYLE": "Universal V2",
        "SCENE": "Topic Planner",
        "PEOPLE": "Reference Resolver",
        "TEXT": "Thumbnail Text Engine",
        "NEGATIVE": "Universal V2",
    }


def build_final_provider_prompt(
    scene_prompt: str,
    item: Mapping[str, object] | None = None,
    *,
    identity_notes: str = "",
    reference_notes: str = "",
    composition_notes: str = "",
    text_mode: str = "fastgen",
) -> str:
    """Build the one immutable FastGen payload from semantic values and V2 rules."""
    scene_values = _structured_scene_values(scene_prompt)
    brief = visual_brief({**dict(item or {}), **scene_values})
    scene = _semantic_scene(scene_prompt, brief["title"])
    identity = "; ".join(part for part in (identity_notes, reference_notes) if part.strip()) or "No additional identity or reference instruction."
    composition = "; ".join(part for part in (brief["layout"], composition_notes) if part.strip())
    if brief["headline"] and text_mode == "fastgen":
        headline = (
            f"<exact-text>{brief['headline']}</exact-text>\n"
            "Render only the characters inside <exact-text>; do not render the tags. "
            "Do not add punctuation, translate, rewrite or add words."
        )
        subheadline = (
            f"<exact-text>{brief['subheadline']}</exact-text>\n"
            "Render only the characters inside <exact-text>; do not render the tags. "
            "Do not add punctuation, translate, rewrite or add words."
            if brief["subheadline"] else "None supplied."
        )
        typography = (
            "Act as the thumbnail art director: choose the strongest readable composition for this exact photograph, "
            "never thin, horror-style, low-contrast or decorative lettering. Use ultra-heavy condensed Cyrillic, "
            "large at phone size, with a thick black outer stroke and hard dark shadow. Prefer yellow lettering on a red panel; "
            "when it creates stronger separation from the scene, use red lettering on a yellow panel instead. "
            "The panel must sit behind every headline word, keep the lettering within its bounds, and leave most of the photograph visible."
        )
    else:
        headline = "None supplied; do not generate words."
        subheadline = "None supplied; do not generate words."
        typography = "Reserve a clean high-contrast area for supplied overlay text; do not generate words."
    blocks = (
        ("CORE STYLE", "NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2. CLICKABILITY = HIGH. DRAMA = HIGH. ACTION = HIGH. EMOTION = HIGH. PHOTOREALISM = MAXIMUM. Produce one coherent, high-impact editorial thumbnail as a professional real-world camera photograph with natural optics, anatomy, scale, materials, depth and topic-grounded light."),
        ("STORY CONTEXT", scene),
        ("MAIN SUBJECT", brief["main_subject"]),
        ("SELECTED PEOPLE", brief["selected_people"]),
        ("VISIBLE ACTION", brief["visible_action"]),
        ("VISUAL EVIDENCE", brief["visual_evidence"]),
        ("ENVIRONMENT", brief["environment"]),
        ("EMOTION", brief["emotion"]),
        ("SELECTED COMPOSITION", f"{composition}. Make the exact action readable in one second at phone size."),
        ("IDENTITY / REFERENCES", identity),
        ("HEADLINE", headline),
        ("SUBHEADLINE", subheadline),
        ("TYPOGRAPHY", typography),
        ("RED EDGE ACCENTS", "Use one bold vivid red curved-corner frame with no words around all four outer edges of the image: continuous perimeter treatment, flush to the boundary, zero inset and zero empty margin. It must read as a deliberate red arc/frame, never as two thin side stripes."),
        ("FINAL NEGATIVE RULES", "Do not invent an ungrounded specific attack at an identifiable landmark. No artwork, illustration, painting, concept art, poster art, surreal art, fantasy, sci-fi, CGI, 3D render, cartoon, anime, collage, logos or watermarks."),
    )
    final_prompt = "\n\n".join(f"{name}:\n{content}" for name, content in blocks)
    collision_source = " ".join((
        str(scene_prompt or ""),
        str((item or {}).get("title", "")),
        str((item or {}).get("topic", "")),
        str((item or {}).get("script", "")),
    )).casefold()
    explicit_energy = any(term in collision_source for term in (
        "нефт", "oil", "баррел", "barrel", "opec", "опек", "топлив", "fuel",
        "энергорын", "energy market",
    ))
    final_lower = final_prompt.casefold()
    oil_collision = (
        "energy traders react to changing oil prices" in final_lower
        or "energy-market trading floor" in final_lower
    )
    if oil_collision and not explicit_energy:
        raise ValueError("FastGen prompt conflict: oil-market scene contradicts the current topic")
    return final_prompt


def universal_thumbnail_core_v2(item: Mapping[str, object] | None = None) -> str:
    """Compatibility renderer for a complete V2 provider prompt without a scene draft."""
    return build_final_provider_prompt("", item)


def append_universal_thumbnail_core_v2(scene_prompt: str, item: Mapping[str, object] | None = None) -> str:
    """Compatibility entry point for legacy callers; it now returns the final provider prompt."""
    return build_final_provider_prompt(scene_prompt, item)


def strip_legacy_thumbnail_phrases(value: str) -> str:
    """Remove legacy category boilerplate before semantic scene extraction."""
    text = " ".join(str(value or "").split())
    return re.sub(r"\b(?:breaking[ -]?news(?:room)?|political news thumbnail|geopolitical news image)\b", "", text, flags=re.IGNORECASE).replace("  ", " ").strip()
