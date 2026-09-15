# Ideas Engine Production Design

## Goal

Make the existing **Генерация идей** screen produce a smaller, genuinely
diverse and scriptable production portfolio instead of reworded titles from a
direction. The work is limited to the Ideas / Topic Planning flow and its
handoff to scenarios.

## Current flow and gap

Current sources (`suggest_topics`, reference-channel analysis and YouTube
keyword research) return strings. The plan stores `{topic, count, provider}`.
`generate_ideas` sends each row directly to the title model and persists a
title string plus source direction. The scenario queue receives that string
only. It cannot distinguish a source signal, event, topic, angle, or script
promise.

## Target hierarchy

```text
RAW SIGNAL → EVENT → MACRO EVENT → DIRECTION → TOPIC → ANGLE → TITLE → PRODUCTION ITEM
```

`RawSignal` is one public donor video, YouTube search video, news item, agent
discovery result, or manual direction marker. `Event` is a concrete,
source-backed occurrence. `MacroEvent` clusters one ongoing story. `Direction`
is a broad editorial line; `Topic` is one independently scriptable video;
`Angle` is an editorial treatment; `Title` packages the topic plus angle.

Manual directions are preserved even when they have no source event. They
receive a `manual` signal and empty `event_ids`; the title model must use an
editorial/question framing and may not state a new concrete fact.

## Data model

All records are JSON-safe dictionaries persisted in `Settings`.

```json
{
  "event_id": "evt_<stable-hash>",
  "event_core": "summary independent of donor wording",
  "primary_entities": ["..."],
  "secondary_entities": ["..."],
  "action": "...",
  "object": "...",
  "event_family": "diplomacy|military|economy|sanctions|trade|internal-politics|infrastructure|social|other",
  "geography": ["..."],
  "event_time": null,
  "source_signal_ids": ["sig_<stable-hash>"],
  "youtube_signal_count": 0,
  "confidence": 0
}
```

```json
{
  "direction_id": "dir_<stable-hash>",
  "direction": "broad line",
  "macro_event_id": "macro_<stable-hash>",
  "event_ids": ["evt_..."],
  "topic_potential": "high|medium|low",
  "recommended_count": 1,
  "demand_score": 0,
  "competition_score": 0,
  "angle_saturation": 0
}
```

```json
{
  "direction": "...",
  "topic": "...",
  "angle": "...",
  "title": "...",
  "event_ids": ["evt_..."],
  "supporting_context": ["source-backed context"],
  "core_event": "...",
  "core_claim": "...",
  "conflict": "...",
  "promised_question": "...",
  "script_requirements": ["..."],
  "click_score": 0,
  "novelty_score": 0,
  "scriptability_score": 0,
  "char_count": 0,
  "macro_event_id": "macro_...",
  "primary_entity": "...",
  "geography": ["..."],
  "topic_family": "...",
  "angle_family": "..."
}
```

`idea_results` and `idea_result_sources` remain as compatibility projections
of production items. Existing projects without new records are upgraded in
memory to production items with legacy direction/title context; no existing
field is deleted.

## Source ingestion and ranking

Every automatic source first emits raw signals. Public counters are preserved
as evidence, not copied as titles. Demand combines normalised views/hour,
recency and relative channel outlier where a channel sample provides a
baseline. Competition is the number and strength of matching signals. Angle
saturation is calculated per event/topic/angle family from current signals and
recent production items. A hot event with a saturated angle requires a
different angle or is rejected; it is never accepted as a synonym.

Signals are deterministically clustered by normalised entities, action,
object, geography and token similarity. The LLM may propose structured event
records, but code validates IDs and merges/rejects duplicates. Agent,
reference and YouTube paths call this same ingestion function.

## Generation pipeline

For each selected planned direction:

1. Resolve its source events or build a safe manual editorial context.
2. Generate structured topic candidates, each with topic core, subject,
   action, object, consequence and family.
3. Reject same-event, same-topic-core and high-similarity candidates against
   the current batch, the direction and recent production history.
4. Calculate topic potential. High permits 4–5 recommended topics, medium
   permits 2–3 and low permits one. A user count above the recommendation is
   retained as an override and exposed as a duplicate-risk warning.
5. Generate several different angle concepts for each accepted topic, choose
   one unsaturated family, then request several headline concepts for that
   topic plus angle plus event context.
6. Apply deterministic title, duplicate, question-ratio, clickability and
   scriptability quality gates. If no candidate passes, retry the topic/angle
   concept stage once; do not pad the requested count with paraphrases.
7. Build and persist only accepted production items. The UI states the gap
   between requested and quality-accepted count.

The shared pipeline is used for `agent` and `openai` routes. Prompts request
JSON candidates but every model result has a defensive parsing fallback.

## Quality gates

Titles are normalised in code: surrounding whitespace is removed and the first
character is uppercased. A title is accepted only if `1 <= len(title) <= 100`;
55–95 is preferred. Long model output is regenerated, never mechanically
truncated. Full-title CAPS, unresolved templates, repeated punctuation and
abstract bait without subject/event/conflict are rejected.

Question titles may make up no more than 20% of a final batch. The selector
tracks openings, title structures, macro events, entities, geography, topic
families and angle families. Exact repeats, repeated openings, high token
similarity and the same event/topic/angle combination are rejected.

`click_score` combines hook strength, specificity, conflict, stakes, novelty,
clarity, channel fit and scriptability. `scriptability_score` is a hard gate:
the item must name a supported event or safe editorial subject, a conflict or
question, and concrete script requirements. No requirement may claim an event
absent from supporting context.

## Scenario handoff

The selected production item's title remains the visible queue title. A
durable `production_item` payload is saved with its scenario request. Scenario
prompt construction includes its script requirements, supporting context and
promised question. Legacy title-only entries continue using the previous
scenario prompt.

## UI and button contract

Keep the existing visual hierarchy. Plan rows show recommended count, selected
count, trend/demand state and a duplicate-risk warning. Result rows continue
to show title and direction; expanded diagnostics show topic, angle, scores,
event count and character count. Technical scores are not shown by default.

All existing buttons remain on the common pipeline: manual direction, agent
suggestion, reference channels, YouTube keyword search, add to plan, generate,
regenerate, delete, clear production, save/reload and transfer to scenarios.
Counters continue to count planned directions and planned/accepted videos
without confusing these with raw signals or angles.

## Acceptance and regression checks

- A fixture with at least five directions produces at least twenty candidates
  and contains no title over 100 characters, lower-case first character,
  repeated opening, unresolved template or more than 20% questions.
- The fixture rejects the supplied weak examples such as “Ситуация изменилась”
  and “Европа в шоке: начинается новый этап”.
- Portfolio validation reports over-concentrated macro events/entities/angles
  rather than accepting reworded duplicates.
- A requested count larger than independent high-quality topics returns the
  smaller accepted count and a deficit.
- Button-level bridge tests cover state mutation, persistence projection,
  delete/regenerate and legacy-item migration.
- A real generated batch is evaluated after tests for clickability and
  scriptability before release; OLD vs NEW examples appear in the final
  report.

## External quality review package

The first working version is not editorially accepted when its automated tests
pass. It must create `IDEAS_ENGINE_REVIEW.md` in the project root and then
stop; no other FlowNews work starts until the user returns external editorial
review.

The file contains a representative, unedited selection of 20–30 actually
generated production items across directions and angle families. For each it
lists direction, topic, angle, title, character count, hook family, click,
novelty and scriptability scores, compact supporting event/context, script
requirements, nearest duplicate and similarity. It also includes a comparable
OLD RESULT and NEW RESULT section, plus rejected candidates with one explicit
reason: `duplicate`, `weak hook`, `vague`, `low scriptability`, `> 100
characters`, `too similar` or `factual support insufficient`.

The selection must include strong and medium accepted items, rejected items,
multiple directions and different angle families. It must not be hand-picked
to show only successful examples.

## Scope boundary

No redesign of other FlowNews pages, media studio, animation, Reels, Blender,
DaVinci, distributed workers or unrelated agent system is part of this work.
