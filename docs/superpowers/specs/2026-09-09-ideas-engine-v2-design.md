# Ideas Engine V2 Design

## Goal

Turn NewsFlow's existing Ideas/Topic Planning flow into a quality-first
production planner for a Russian-speaking CIS audience. It must derive a
structured, script-ready `ProductionItem` from evidence and an editorial
direction without filling a batch with cosmetic rewrites.

## Scope

Only the existing Ideas/Topic Planning flow and its direct hand-off to the
scenario writer are in scope. Thumbnail, gallery, voice, publication, OAuth,
channels and montage behaviour are unchanged.

## Existing pipeline

The pipeline is retained, not rebuilt:

`RAW SIGNAL → EVENT → MACRO EVENT → DIRECTION → TOPIC → ANGLE → TITLE → PRODUCTION ITEM`

`scriptor/idea_engine.py` remains the pure, deterministic quality layer.
`scriptor/bridge.py` remains the persistence, model and desktop-command layer.

## ProductionItem V2 contract

Every new item stores at least:

- `direction`, `topic`, `angle`, `title`;
- `event_ids`, `macro_event_id`, `supporting_context`, `information_payload`;
- `primary_entities`, `geography`, `conflict`, `main_consequence`;
- `framing_type`: `FACTUAL`, `EDITORIAL` or `HYPOTHETICAL`;
- `script_requirements`;
- `cis_audience_relevance_score`, `why_cis_audience_cares`;
- `emotional_stakes_score`, `creative_amplification_score`;
- `click_score`, `novelty_score`, `scriptability_score`, `direction_fit_score`;
- `demand_score`, `competition_score`, `angle_saturation`;
- `factual_risk_score`: `LOW`, `MEDIUM` or `HIGH`;
- `hook_family`, `title_structure`, `topic_family`, `angle_family`;
- `char_count`, `nearest_duplicate`, `similarity` and `status`.

Legacy title-only items remain usable but carry `legacy: true`; migration must
not silently erase them or claim that they passed V2 validation.

## Framing policy

`EDITORIAL` is the default for new generated items. It requires a real base
event but may amplify a reasonable conflict, winner/loser, pressure, risk,
political price or plausible consequence. It must preserve evidence and record
its factual risk; the model is not required to quote the editorial phrasing
from a source.

`FACTUAL` uses only claims directly supported by the event bundle.

`HYPOTHETICAL` may create a compelling possible scenario, but its title must
contain an explicit uncertainty marker (for example “Что будет, если…”,
“Может ли…”, “возможен ли…”, “может…”). Its script contract must explain the
real starting point, label the scenario as a forecast, state prerequisites and
never report the prediction as an event that already happened.

## Quality gates

1. A deterministic CIS-audience gate scores relevance, recognisable entities,
   conflict, consequences, Russia/Ukraine/Belarus/CIS connection, relevant
   Europe linkage, visual potential and click potential. Low relevance is
   rejected unless an exceptional supported event qualifies as an explicit
   exception.
2. Emotional-stakes and creative-amplification scores distinguish a genuinely
   strong concept from a dry administrative rewrite.
3. Code, not the LLM, normalises the first letter and measures title length.
   The hard limit is `len(title) <= 100`; preferred length is 55–95. Titles
   longer than 100 are rejected for rewrite, never mechanically truncated.
4. Semantic duplicate prevention compares event bundle, topic core, entities,
   action/object, consequence, angle family, information payload, script
   requirements, normalized title and opening phrase. Close candidates are
   merged/rejected rather than counted as separate videos.
5. The portfolio selector observes macro events, directions, entities,
   geography, topic/angle/hook families and framing types. It returns a
   shortage instead of manufacturing weak filler for a requested count.
6. Scores are calibrated: 50–60 ordinary, 60–70 workable, 70–80 strong,
   80–90 very strong, and 90+ exceptional rather than routine.

## Model boundary

The title prompt asks the model for structured candidate concepts, including
framing, evidence-grounded topic/angle, hook and script implications. The
model may propose many alternatives; Python owns validation, scoring,
deduplication, selection and persistence.

## UI and persistence

The Ideas UI will expose the production-item fields that explain acceptance or
rejection: framing, CIS relevance, emotional stakes, clickability, novelty,
scriptability, factual risk and duplicate diagnostics. It will keep legacy
entries readable. Settings load/save migrates missing V2 fields to safe,
explicit legacy/default values and survives a desktop reload.

## Validation and review

Tests cover framing boundaries, title rules, audience gate, score calibration,
semantic duplicates, portfolio shortages, migration, persistence and
Title→Scenario context. After implementation, run a real regression batch and
create `IDEAS_ENGINE_REVIEW_V2.md` with at least 30 representative generated
candidates, accepted and rejected examples, and a dedicated hypothetical
section. Stop after creating that review file for external editorial review.
