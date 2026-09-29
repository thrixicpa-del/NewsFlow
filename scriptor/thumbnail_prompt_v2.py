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


def _topic_scene_defaults(title: str, _source: str) -> dict[str, str]:
    """Universal fallback used only when the planner has no structured scene.

    Runtime deliberately contains no named news story, politician, country,
    company, product, industry or event routing.  The current topic/context is
    the authority; the agent chooses the concrete visual interpretation.
    """
    subject = _clean(title, "current news topic")
    return {
        "main_subject": subject,
        "visible_action": (
            f"A concrete real-world action, reaction or immediate consequence that follows directly from “{subject}”. "
            "Choose it from the current topic/context; do not substitute a memorised news template."
        ),
        "visual_evidence": (
            f"The strongest visible evidence supported by “{subject}” and the current production context: relevant people, "
            "objects, documents, locations or consequences only."
        ),
        "environment": (
            f"The real-world setting supported by “{subject}” and its context. If no specific location is known, choose a "
            "neutral documentary environment that fits the actual subject instead of inventing a different event."
        ),
        "emotion": (
            "Choose the strongest truthful emotional tone implied by the current story—tension, urgency, shock, concern, "
            "conflict or restraint—without inventing unsupported violence, destruction or panic."
        ),
    }


def visual_brief(item: Mapping[str, object] | None = None) -> dict[str, str]:
    """Derive semantic scene values; this function never adds visual style rules."""
    row = item or {}
    title = _clean(row.get("title"), "current news topic")
    source = " ".join((title, _context(row, "script", "event_context", "supporting_context"))).casefold()
    selected_people = _context(row, "portrait_subject", "face_reference_label", "selected_people", "primary_entities", "primary_entity", "entities")
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
    allow_varied_text_palette: bool = False,
) -> str:
    """Build the one immutable FastGen payload from semantic values and V2 rules."""
    scene_values = _structured_scene_values(scene_prompt)
    current_item = dict(item or {})
    prompt_values = {**current_item, **scene_values}
    current_identity = _context(current_item, "portrait_subject", "selected_people")
    if current_identity:
        # A stored V2 draft can describe an old identity. The render-time
        # Covers resolver is the only authority for SELECTED PEOPLE.
        prompt_values["selected_people"] = current_identity
    brief = visual_brief(prompt_values)
    scene = _semantic_scene(scene_prompt, brief["title"])
    # ``_semantic_scene`` has already extracted only the old draft's STORY
    # CONTEXT.  Keep that concise scene narrative intact; the structured slots
    # below remain authoritative for their own labelled fields.  Rebuilding
    # STORY CONTEXT from all slots made the final provider payload needlessly
    # repetitive and could turn an old V2 prompt into a different scene.
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
        palette = (
            "You may choose a different contrasting text and panel colour pair when it fits the scene better; "
            "keep deliberate red/yellow accents and preserve the mandatory red outer frame."
            if allow_varied_text_palette else
            "Use yellow or light lettering on a red panel with deliberate red/yellow accents."
        )
        typography = (
            "Act as a professional YouTube thumbnail designer and art director. Choose varied, expressive, immediately readable "
            "typography and the strongest hierarchy for this exact photograph; vary font treatment, panel shape and text placement "
            "to suit this topic rather than repeating one template. Never use thin, horror-style, low-contrast or decorative lettering. "
            "Use an ultra-heavy Cyrillic display face, large at phone size, with a thick dark outer stroke or hard shadow where needed. "
            f"{palette} The contrasting solid panel must sit behind every headline word, keep the lettering within its bounds, "
            "and leave the central evidence and recognisable faces visible."
        )
    else:
        headline = "None supplied; do not generate words."
        subheadline = "None supplied; do not generate words."
        typography = "Reserve a clean high-contrast area for supplied overlay text; do not generate words."
    blocks = (
        ("CORE STYLE", "Create a realistic, highly clickable, photorealistic YouTube news thumbnail image. You are a professional YouTube thumbnail designer and art director. NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2. CLICKABILITY = HIGH. DRAMA = HIGH. ACTION = HIGH. EMOTION = HIGH. PHOTOREALISM = MAXIMUM. Produce one coherent, high-impact editorial thumbnail as a professional real-world camera photograph with natural optics, anatomy, scale, materials, depth and topic-grounded light. Every visible story element must be traceable to the current topic, structured scene or supplied context; never replace the subject with a memorised category scene."),
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
        ("RED EDGE ACCENTS", "Always draw one straight vivid red frame around the complete outer perimeter: equal thickness on all four edges, square corners, flush to the image boundary, zero inset and zero empty margin. It must be a clean rectangular border, never arcs, side stripes or decorative corner marks."),
        ("FINAL NEGATIVE RULES", "Do not invent an ungrounded specific attack at an identifiable landmark. Use crowds, soldiers, fear, damage or destruction only when the title or scenario supports them. No circles, ovals, circular frames or rings. No meaningless icons. No artwork, illustration, painting, concept art, poster art, surreal art, fantasy, sci-fi, CGI, 3D render, cartoon, anime, collage, logos or watermarks."),
    )
    final_prompt = "\n\n".join(f"{name}:\n{content}" for name, content in blocks)
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
