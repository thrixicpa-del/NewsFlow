"""Contrastive evidence for a selected interval, never identity/event recognition.

CLIP values below are cosine similarities, not calibrated probabilities. The
small taxonomy distinguishes compatible context from close visual negatives.
Rules are fixed from development examples, independently of the holdout pool.
"""
from __future__ import annotations

import math
import re
from statistics import median

TAXONOMY_VERSION = 6
RULES_VERSION = 8
MIN_SIMILARITY = .20
CLEAR_MARGIN = .012

TAXONOMY = {
    "port": ("a cargo ship in a seaport with cranes loading containers on the dock",
             "oil tanker ship at sea or docked at a marine terminal"),
    "rail": ("freight train carrying cargo on railway tracks",
             "grain cargo railway wagons at a railway freight terminal"),
    "farm": ("harvesting wheat crops in agricultural fields with a combine harvester",
             "farm grain storage silos agriculture tractor and crops",
             "vegetable seedlings growing in trays at a greenhouse plant nursery"),
    "factory": ("workers manufacturing products in an industrial factory with machinery",),
    "official": ("government official giving a formal statement behind a podium with microphones and flags",
                 "president in a formal government office with national flags giving an official address"),
    "meeting": ("government delegations seated together around a conference table for diplomatic negotiations",
                "two government leaders meeting seated together in a formal diplomatic room"),
    "government_building": ("exterior of parliament government institution with national flags",),
    "peaceful_protest": ("peaceful street protest rally march with civilians holding placards and banners",),
    "worker_picket": ("striking workers standing on a picket line outside a factory holding union placards protest banners",),
    "farmer_protest": ("farmers protesting with tractors blocking a road holding protest placards and banners",),
    "police_guard": ("police officers standing peacefully guarding a street demonstration behind barriers without violence",),
    "clashes": ("violent street riot police beating demonstrators tear gas burning barricades protesters throwing stones",),
    "combat": ("actual footage of soldiers in battlefield trenches military fighting",
               "artillery cannon firing at a battlefield military vehicles in combat",
               # Crop fields alone do not establish agricultural activity.
               # These compete with farm descriptions using the same margins;
               # neither country nor a specific battle/event is inferred.
               "military rocket launchers firing on a green agricultural field",
               "camouflaged army trucks with rocket launchers firing from a green farm field"),
    "map": ("television graphic map of battlefield front lines with arrows and colored territories",
            "animated infographic diagram map with text graphics and colored areas"),
    "interview": ("close up of an ordinary person being interviewed on the street by a reporter with a microphone",
                  "television studio presenter talking to camera or a close up news interview"),
    "leisure": ("people talking and drinking in a pub bar restaurant with bottles and tables",
                "music entertainment party in a bar cafe nightclub",
                "people swimming bathing in the sea at a beach with sunbathers on the shore"),
    "concert": ("crowd at a music concert with a singer band stage lights",),
    "sports_fans": ("football supporters cheering in a sports stadium",),
    "religious": ("religious procession with priests and people carrying icons",),
    "queue": ("people waiting in a queue standing in line outside a store",),
    "digital": ("computer servers in a data center with racks and network equipment",),
    "finance": ("bank financial business stock market trading screens and money",),
    "city": ("ordinary city streets buildings traffic and pedestrians urban footage",),
    "warehouse": ("grain cargo storage warehouse with sacks and forklifts",),
    "aircraft": ("airplane at an airport runway or airport terminal",),
    "road_cargo": ("cargo trucks transporting freight on a highway",),
    "energy": ("oil refinery pipelines power station industrial energy infrastructure",),
    # Development-only cached-vector comparison separated naval deck/guns
    # from commercial port/loading footage. This is a close negative for a
    # port scene, never evidence of loading or a confirmed combat event.
    "military_naval": (
        "military naval warship deck with large naval guns turrets missiles sailors at sea",
        "navy destroyer frigate battleship military vessel with naval gun turrets on deck",
    ),
    "maritime_display": (
        "fireboat ship spraying powerful water jets in a maritime parade display",
    ),
}


def query_topic(query: str) -> tuple[str, frozenset[str], frozenset[str]] | None:
    """Return direct/context kinds for this topic, with bounded bilingual rules."""
    text = str(query).casefold().replace("ё", "е").replace("_", " ")
    def has(expression):
        return bool(re.search(expression, text))
    # A speaker's statement about a ship/map is still a speaking scene. The
    # role is explicit in the query; no person's identity is inferred here.
    if has(r"press conference|formal statement|official address|government (?:statement|briefing)|пресс.?конференц|заяв(?:ил|лен|ля)|выступлен|обращени"):
        return "official", frozenset({"official"}), frozenset({"government_building", "meeting"})
    if has(r"\bmap\b|карта\w*|карт[еу]\b|infographic|инфограф"):
        return "map", frozenset({"map"}), frozenset()
    # A protest topic must be resolved before factories/fields or official
    # buildings mentioned as the location of a gathering.
    if has(r"protest|placard|picket|rally|митинг|протест|забастов|бастующ|пикет|шестви"):
        conflict = has(r"clash|dispersal|violent|riot|столкнов|разгон|беспоряд")
        negated = has(r"peaceful|without violence|no clashes|без столкнов|не было столкнов|мирн")
        if conflict and not negated:
            return "clashes", frozenset({"clashes"}), frozenset({"peaceful_protest", "police_guard"})
        if has(r"farmers|фермер"):
            return "farmers_protest", frozenset({"farmer_protest"}), frozenset({"peaceful_protest", "police_guard", "farm"})
        if has(r"labor|workers|union|рабочи|забастов|бастующ"):
            return "labor_protest", frozenset({"worker_picket"}), frozenset({"peaceful_protest", "police_guard", "factory"})
        return "protest", frozenset({"peaceful_protest", "worker_picket", "farmer_protest"}), frozenset({"police_guard"})
    if has(r"military naval|naval warship|\bnavy\b|военн\w* корабл|патрульн\w* катер|\bвм[сф]\b"):
        return "military_naval", frozenset({"military_naval"}), frozenset()
    if has(r"seaport|\bport\b|tanker|cargo ship|marine terminal|порт\w*|танкер|морск.*терминал"):
        return "port", frozenset({"port"}), frozenset({"warehouse", "rail", "road_cargo"})
    if has(r"government building|institutional (?:venue|context)|(?:parliament|institution)\w* exterior|правительствен\w* здан|здан\w* правительств"):
        # An institutional exterior/reporting context is a visible role.
        # A single official's portrait cannot establish that role or identity.
        return "institutional_context", frozenset({"government_building"}), frozenset({"meeting"})
    if has(r"negotiat|meeting|delegation|summit|переговор|встреч|делегаци|саммит"):
        return "meeting", frozenset({"meeting"}), frozenset({"official", "government_building"})
    harvesting = has(r"harvest|combine|farming fields|wheat field|уборк\w* урож|комбайн|жатв")
    cargo_warehouse = (not harvesting and has(r"warehouse|склад")
                       and has(r"cargo|export|freight|storage|logistics|груз|экспорт|логист"))
    if (not cargo_warehouse
            and has(r"official|government|president|formal statement|press conference|под[иу]ум|заявлен|выступлен|президент|правительств")):
        return "official", frozenset({"official"}), frozenset({"government_building", "meeting"})
    for topic, expression, contexts in (
        ("rail", r"rail|freight train|железнодорож|поезд\w*", {"warehouse", "road_cargo"}),
        ("combat", r"combat|battlefield|frontline|artillery|military|soldier|armou?r|войск|фронт|артилл|солдат|боев|наступлен|танк(?:и|а|ов)?\b", set()),
        ("farm", r"harvest|agricultur|farming|\bfarm\b|crops|урожа|сельхоз|ферм|пшениц|комбайн", {"warehouse"}),
        ("energy", r"refinery|pipeline|power station|energy|нефт|энерг|электростанц|трубопровод|\bнпз\b", set()),
        ("factory", r"factory|manufactur|industrial|завод|производств", {"warehouse"}),
        ("digital", r"cyber|server|data center|кибер|сервер|хакер", set()),
        ("finance", r"finance|sanction|bank|stock market|эконом|санкц|банк|бирж", {"government_building"}),
        ("aircraft", r"aircraft|aviation|airplane|airport|авиа|самолет|аэропорт", set()),
        ("road_cargo", r"cargo trucks|road freight|грузовик|автоперевоз", {"warehouse", "rail"}),
        ("warehouse", r"warehouse|склад", {"rail", "road_cargo", "port"}),
        ("interview", r"interview|интервью", set()),
    ):
        # Crop/market nouns can describe freight rather than an action. Keep
        # explicit rail, truck, combat, energy and factory roles ahead of its
        # warehouse destination; actual harvesting retains its normal role.
        if has(expression) and not (cargo_warehouse and topic in {"farm", "finance"}):
            return topic, frozenset({topic}), frozenset(contexts)
    return None


def classify_window(query: str, frame_scores: list[dict[str, float]]) -> dict:
    topic = query_topic(query)
    result = {"relation": "unknown", "reason": "no-applicable-topic",
              "dominant_kind": "", "supported_kinds": [], "event_confirmed": False,
              "motion_verified": False}
    if topic is None:
        return result
    topic_name, direct, context = topic
    allowed = direct | context
    result["topic"] = topic_name
    if len(frame_scores) != 3 or any(not scores for scores in frame_scores):
        result["reason"] = "incomplete-three-frame-window"
        return result
    if any(not math.isfinite(float(value)) for scores in frame_scores for value in scores.values()):
        result["reason"] = "nonfinite-model-scores"
        return result
    kinds = set().union(*(scores.keys() for scores in frame_scores))
    aggregates = {kind: median(float(scores.get(kind, 0)) for scores in frame_scores) for kind in kinds}
    dominant = max(aggregates, key=aggregates.get)
    result.update(dominant_kind=dominant, class_scores=aggregates)
    frame_relations = []
    supported = set()
    for scores in frame_scores:
        best = max((float(scores.get(kind, 0)) for kind in allowed), default=0)
        negative = max((float(value) for kind, value in scores.items() if kind not in allowed), default=0)
        if best < MIN_SIMILARITY or negative > best + CLEAR_MARGIN:
            frame_relations.append("contradiction" if negative >= MIN_SIMILARITY and negative > best + CLEAR_MARGIN else "unknown")
            continue
        # A near negative winning the frame is ambiguous evidence, even when
        # its lead is too small to justify a contradiction. Compatibility
        # needs an actual positive winner; no new score threshold is added.
        if negative > best:
            frame_relations.append("unknown")
            continue
        # Manufacturing halls and cargo warehouses share roofs, crates and
        # cranes. A near-tied factory interpretation cannot establish storage
        # or loading. Keep genuine factory scenes and clear warehouse windows.
        warehouse = float(scores.get("warehouse", 0))
        if ("warehouse" in allowed and "factory" not in allowed
                and warehouse >= best and warehouse >= MIN_SIMILARITY
                and float(scores.get("factory", 0)) >= warehouse - CLEAR_MARGIN):
            frame_relations.append("unknown")
            continue
        best_kinds = {kind for kind in allowed if float(scores.get(kind, 0)) >= max(MIN_SIMILARITY, best - CLEAR_MARGIN)}
        supported.update(best_kinds)
        frame_relations.append("direct" if best_kinds & direct else "context")
    result["supported_kinds"] = sorted(supported)
    if all(value == "direct" for value in frame_relations):
        result.update(relation="direct", reason="consistent-compatible-frames")
    elif all(value in {"direct", "context"} for value in frame_relations):
        result.update(relation="context", reason="consistent-topic-context")
    elif frame_relations.count("contradiction") >= 2:
        result.update(relation="contradiction", reason="consistent-close-negative")
    else:
        result["reason"] = "inconsistent-or-weak-window"
    result["frame_relations"] = frame_relations
    return result
