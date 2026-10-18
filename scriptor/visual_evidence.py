"""Contrastive evidence for a selected interval, never identity/event recognition.

CLIP values below are cosine similarities, not calibrated probabilities. The
small taxonomy distinguishes compatible context from close visual negatives.
Rules are fixed from development examples, independently of the holdout pool.
"""
from __future__ import annotations

import math
import re
from statistics import median

TAXONOMY_VERSION = 8
RULES_VERSION = 12
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
    "equipment_display": (
        "agricultural manure spreader trailer with large rear spreading beaters inside a machinery exhibition hall",
        "stationary farm trailers and fertilizer spreading machinery displayed at an indoor agricultural trade show",
    ),
    "vessel_incident": (
        "damaged cargo ship listing heavily to one side sinking in the sea",
        "shipwreck cargo vessel capsized and partially submerged in water",
    ),
    # National symbols are a separate facet, not competing visual roles and
    # never proof of a location. Only an explicit incompatible institution
    # request can use their contrast as negative evidence.
    "institution_ukraine": (
        "government building exterior flying a blue and yellow Ukrainian national flag",
        "Ukrainian government institution with the blue yellow national flag on the roof",
    ),
    "institution_russia": (
        "government building exterior flying a white blue red Russian national flag",
        "Russian government institution with the white blue red national flag on the roof",
    ),
}

_INSTITUTION_SYMBOL_PATTERNS = {
    "institution_ukraine": r"ukrain|\bkyiv\b|\bkiev\b|украин|киев",
    "institution_russia": r"\brussia\w*\b|\bmoscow\b|\bkremlin\b|росси|москв|кремл",
}

# A child cannot compete against a parent containing the identical prompt.
# Partition wheat-field evidence from every remaining FARM interpretation;
# these facets stay outside ordinary role competition. Grain-specific FARM
# eligibility and bounded grain-rail context use them without proving transport.
_CONTEXT_FACET_PROMPTS = {
    "grain_field": (TAXONOMY["farm"][0],),
    "non_grain_agriculture": (
        *TAXONOMY["farm"][1:],
        "workers harvesting apples in an orchard with fruit trees",
        "machines harvesting grapes in a vineyard",
        "crates of broccoli vegetables at an outdoor produce market",
        "tractor plowing bare soil in an empty agricultural field without crops",
    ),
}
TAXONOMY.update(_CONTEXT_FACET_PROMPTS)
_NON_ROLE_FACETS = frozenset(_INSTITUTION_SYMBOL_PATTERNS) | frozenset(_CONTEXT_FACET_PROMPTS)


def _has_positive_occurrence(text: str, expression: str, *, clause_negation: bool = False) -> bool:
    """An excluded occurrence must not erase another positive occurrence."""
    for match in re.finditer(expression, text):
        prefix = re.split(r"[,;.!?]|\b(?:but|however|но|однако)\b", text[:match.start()])[-1]
        negated = (re.search(r"\b(?:no|not|without|без|не)\b", prefix) if clause_negation else
                   re.search(r"(?:\bno\b|\bnot\b|\bwithout\b|без|\bне\b)\s+(?:\w+\s+){0,2}$", prefix))
        if not negated:
            return True
    return False


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
    incident = r"shipwreck|\bsinking\b|\bcapsiz\w*|damaged cargo (?:ship|vessel)|затонувш\w*|затонул\w*|тонущ\w* (?:суд|кораб)"
    vessel_context = has(r"\b(?:ships?|vessels?|tanker|shipwreck)\b|судно|судна|судов|кораб|танкер")
    if vessel_context and _has_positive_occurrence(text, incident):
        return "vessel_incident", frozenset({"vessel_incident"}), frozenset({"port"})
    port_expression = r"seaport|\bport\b|tanker|cargo ship|marine terminal|порт\w*|танкер|морск.*терминал"
    # Denying damage does not deny the commercial vessel or its location.
    # Scope the remaining negation to the port phrase, not the whole clause.
    port_text = re.sub(r"\b(?:no|not|without)\s+damage(?:d)?(?:\s+to)?\b", " ", text)
    positive_port = _has_positive_occurrence(port_text, port_expression)
    denied_port = bool(has(r"\b(?:not|no|without)\s+(?:\w+\s+){0,2}(?:seaport|port)\b")
                       and not positive_port)
    if positive_port:
        return "port", frozenset({"port"}), frozenset({"warehouse", "rail", "road_cargo"})
    if has(r"government building|institutional (?:venue|context)|(?:parliament|institution)\w* exterior|правительствен\w* здан|здан\w* правительств"):
        # An institutional exterior/reporting context is a visible role.
        # A single official's portrait cannot establish that role or identity.
        return "institutional_context", frozenset({"government_building"}), frozenset({"meeting"})
    if has(r"negotiat|meeting|delegation|summit|переговор|встреч|делегаци|саммит"):
        return "meeting", frozenset({"meeting"}), frozenset({"official", "government_building"})
    if _has_positive_occurrence(text, r"(?:machinery|equipment|agricultural)\s+(?:exhibition|showroom|trade show)|выставк\w*.*(?:техник|машин)"):
        return "equipment_display", frozenset({"equipment_display"}), frozenset({"factory"})
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
            # A grain-warehouse clause already permits commercial port context.
            # Keep that secondary context when rail is the primary role, without
            # treating a port as evidence of a train or broadening rail alone.
            if (topic == "rail" and cargo_warehouse
                    and _has_positive_occurrence(text, r"\brail(?:way|road)?s?\b|\bfreight trains?\b|железнодорож\w*|\bпоезд\w*", clause_negation=True)
                    and not _has_positive_occurrence(text, r"combat|battlefield|frontline|artillery|military|soldier|armou?r|войск|фронт|артилл|солдат|боев|наступлен|танк(?:и|а|ов)?\b")
                    and _has_positive_occurrence(text, r"\bgrain\b|зерн\w*", clause_negation=True)
                    and _has_positive_occurrence(text, r"\bwarehouse\b|склад\w*", clause_negation=True)
                    and _has_positive_occurrence(text, r"\b(?:cargo|export|freight|storage|logistics)\b|груз|экспорт|логист", clause_negation=True)):
                contexts = contexts | {"port"}
            if denied_port:
                contexts = contexts - {"port"}
            return topic, frozenset({topic}), frozenset(contexts)
    return None


def _grain_rail_commodity_context(query: str, frame_scores: list[dict[str, float]]) -> dict | None:
    """A last-resort grain illustration, never a claim of rail transport."""
    text = str(query).casefold().replace("ё", "е").replace("_", " ")
    if not all(_has_positive_occurrence(text, expression, clause_negation=True) for expression in (
            r"\brail(?:way|road)?s?\b|\bfreight trains?\b|железнодорож\w*|\bпоезд(?:а|ы|ов|у|ом|е|ами|ах)?\b",
            r"\bgrain\b|\bзерн(?:о\w*|а|у|е|ом|ами|ах)\b|\bзерен\b",
            r"\b(?:cargo|export|freight|transport|logistics)\b|груз|экспорт|логист|перевоз")):
        return None
    # Keep explicit actions, incidents and excluded field imagery fail-closed.
    if re.search(r"combat|battlefield|frontline|artillery|military|harvest|derail|collision|accident"
                 r"|\b(?:loading|unloading|cross\w*|arriv\w*|depart\w*|moving|moves|approach\w*)\b|over a bridge"
                 r"|\b(?:fire|burn\w*|explod\w*|explos\w*|attack\w*|bomb\w*)\b|горит|горят|взры|атак|бомб"
                 r"|\bin motion\b|\b(?:running|travell?ing|goes|going|rolling|speeding|hauling|pulling|pass(?:es|ing)|driv\w*|leav\w*)\b"
                 r"|движущ\w*|\bв движении\b|поезд\w*(?:\s+\w+){0,3}\s+(?:движ|прибы|отправ|едет|едут|идет|идут|ехал|следует|следуют|проезж)"
                 r"|боев|фронт|артилл|войск|уборк|жатв|крушени|погруз|разгруз|пересек"
                 r"|\b(?:no|not|without)\b[^,;.!?]{0,60}\b(?:fields?|crops?)\b"
                 r"|\b(?:без|не)\b[^,;.!?]{0,60}\b(?:пол(?:е|я|ю|ях|ей)|посев\w*)\b", text):
        return None
    grain, alternatives = [], []
    for scores in frame_scores:
        if any(kind not in scores for kind in _CONTEXT_FACET_PROMPTS):
            return None
        positive = float(scores["grain_field"])
        other = max(float(scores["non_grain_agriculture"]),
                    max((float(value) for kind, value in scores.items()
                         if kind != "farm" and kind not in _NON_ROLE_FACETS), default=0))
        if positive < MIN_SIMILARITY or positive <= other + CLEAR_MARGIN:
            return None
        grain.append(positive)
        alternatives.append(other)
    return {"kind": "grain_field", "scores": grain, "alternative_scores": alternatives,
            "scope": "commodity-illustration-only"}


def classify_window(query: str, frame_scores: list[dict[str, float]]) -> dict:
    topic = query_topic(query)
    result = {"relation": "unknown", "reason": "no-applicable-topic",
              "dominant_kind": "", "supported_kinds": [], "event_confirmed": False,
              "motion_verified": False}
    if topic is None:
        return result
    topic_name, direct, context = topic
    grain_farm = topic_name == "farm" and _has_positive_occurrence(
        str(query).casefold().replace("ё", "е").replace("_", " "),
        r"\b(?:grain|wheat)\b|\bзерн(?:о\w*|а|у|е|ом|ами|ах)\b|\bзерен\b|\bпшениц\w*",
        clause_negation=True,
    )
    allowed = direct | context
    result["topic"] = topic_name
    if len(frame_scores) != 3 or any(not scores for scores in frame_scores):
        result["reason"] = "incomplete-three-frame-window"
        return result
    if any(not math.isfinite(float(value)) for scores in frame_scores for value in scores.values()):
        result["reason"] = "nonfinite-model-scores"
        return result
    kinds = set().union(*(scores.keys() for scores in frame_scores)) - _NON_ROLE_FACETS
    if not kinds:
        result["reason"] = "no-visual-role-features"
        return result
    aggregates = {kind: median(float(scores.get(kind, 0)) for scores in frame_scores) for kind in kinds}
    dominant = max(aggregates, key=aggregates.get)
    result.update(dominant_kind=dominant, class_scores=aggregates)
    # The generic institution role cannot erase a clear incompatible symbol.
    # Require two frames, the existing absolute floor/margin, a building role
    # and exactly one requested country. Joint meetings and country-neutral
    # context remain eligible; a matching symbol does not confirm geography.
    requested_symbols = {kind for kind, expression in _INSTITUTION_SYMBOL_PATTERNS.items()
                         if re.search(expression, str(query).casefold())}
    if (topic_name in {"official", "institutional_context"}
            and dominant == "government_building" and len(requested_symbols) == 1):
        wanted = next(iter(requested_symbols))
        opposite = next(kind for kind in _INSTITUTION_SYMBOL_PATTERNS if kind != wanted)
        conflicts = [float(scores.get(opposite, 0)) >= MIN_SIMILARITY
                     and float(scores.get(opposite, 0)) > float(scores.get(wanted, 0)) + CLEAR_MARGIN
                     for scores in frame_scores]
        if sum(conflicts) >= 2:
            result.update(relation="contradiction", reason="institutional-national-symbol-conflict",
                          frame_relations=["contradiction" if value else "unknown" for value in conflicts])
            return result
    frame_relations = []
    supported = set()
    for scores in frame_scores:
        best = max((float(scores.get(kind, 0)) for kind in allowed), default=0)
        negative = max((float(value) for kind, value in scores.items()
                        if kind not in allowed and kind not in _NON_ROLE_FACETS), default=0)
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
        # A parked exhibition machine can resemble a cargo truck. Near-tied
        # display evidence cannot establish freight movement or storage.
        display = float(scores.get("equipment_display", 0))
        if (topic_name in {"port", "rail", "road_cargo", "warehouse"}
                and display >= MIN_SIMILARITY and display >= best - CLEAR_MARGIN):
            frame_relations.append("unknown")
            continue
        best_kinds = {kind for kind in allowed if float(scores.get(kind, 0)) >= max(MIN_SIMILARITY, best - CLEAR_MARGIN)}
        # FARM includes vegetables/nursery/silos. A grain-specific request
        # needs its existing commodity facet before FARM can be direct.
        # A clear warehouse winner remains ordinary contextual evidence;
        # a near-tied warehouse cannot erase a contradictory crop facet.
        if grain_farm and "farm" in best_kinds:
            if any(kind not in scores for kind in _CONTEXT_FACET_PROMPTS):
                frame_relations.append("unknown")
                continue
            grain = float(scores["grain_field"])
            nongrain = float(scores["non_grain_agriculture"])
            if grain < MIN_SIMILARITY or grain <= nongrain + CLEAR_MARGIN:
                frame_relations.append("contradiction" if nongrain >= MIN_SIMILARITY
                                       and nongrain > grain + CLEAR_MARGIN else "unknown")
                continue
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
    if topic_name == "rail" and result["relation"] not in {"direct", "context"}:
        facet = _grain_rail_commodity_context(query, frame_scores)
        if facet is not None:
            result.update(relation="context", reason="consistent-grain-commodity-context",
                          supported_kinds=["grain_field"], frame_relations=["context"] * 3,
                          context_facet=facet)
    return result
