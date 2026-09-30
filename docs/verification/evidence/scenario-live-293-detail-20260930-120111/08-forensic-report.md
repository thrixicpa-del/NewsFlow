# Forensic trace — scenario-live-293-detail-20260930-120111

## Evidence classification

- **CAPTURED:** metrics, persisted Story Map, saved writer parts and assembled scenario from the disposable test profile.
- **RECONSTRUCTED_OFFLINE:** planner/writer prompt strings and OpenAI request payload shape, generated from historical source `bb6b31a44456adf3f55b99008afa3cb85c70dc5f`; every prompt hash and character count matches captured telemetry.
- **MISSING:** raw Planner response, captured HTTP request bodies/headers, provider request/response IDs, SDK retry trace, raw Writer response before `.strip()`, hidden reasoning. No defaults are inferred for these fields.

## Captured input and fact provenance

- Title: `МИР ОПЯТЬ ОТКЛАДЫВАЕТСЯ? — РОССИЯ УСИЛИЛА УДАРЫ ПО УКРАИНЕ — КИЕВ СНОВА ОКАЗАЛСЯ ПОД МАССИРОВАННОЙ АТАКОЙ`
- ScenarioRequest target/min/max: `12000/11500/12500`
- Full safe ScenarioRequest prompt, template, range configuration, and the only available ProductionItem context are in `00-input-captured-safe.json`.
- The ProductionItem context is manual and contains title/id only. It supplies no supporting factual record. Therefore every map atom labelled SUPPORTED is not independently evidenced by this profile.

## Historical adapter path (source-audited, not captured HTTP telemetry)

- Bridge route: `scenario_provider=openai`; `HybridTextPool`; `OpenAITextClient`.
- Client sends `POST /v1/responses` with `{model, input, max_output_tokens}`. No `instructions`, tools, images, roles, or messages were supplied for these calls; input was a single raw string.
- Configured/sent model is reconstructed as `gpt-5.4-mini`; no model name was captured in telemetry response.
- Authorization/cookies/keys are deliberately omitted and never entered this evidence export.

## Captured / reconstructed call ledger

| order | kind | telemetry prompt chars/SHA | max output | response chars/SHA | finish | usage | request/response IDs | retries |
|---:|---|---|---:|---|---|---|---|---|
| 1 | PLANNER | 10168 / `b7531640d29d78b3115472f8e5370bf0fa34fb784a03c8b59c7c15955ed25387` | 6144 | 13274 / `9c902ccc37e1b64e79c341344a83997b2c7dc4b63eaef1f116ccda17d0d0fd2b` | completed | input=2318, output=2594, total=4912 | MISSING | logical calls=1; SDK retries=MISSING |
| 2 | WRITER_P1 | 14391 / `0739082f7fc632a577073b8b8eec6ddae1c0fc47312a7eb59a373e875b08cebe` | 5120 | 2472 / `e23fda70d706ace2ace2eababe188f1557e29107eec5288d08ba01899e0e5eb0` | completed | input=3106, output=603, total=3709 | MISSING | logical calls=1; SDK retries=MISSING |
| 3 | WRITER_P2 | 14217 / `e4b6cd871b5fb73348b5acfe2b01ce435034f90b69720832016e9ef6649829e8` | 5120 | 3363 / `cf7a5404eaba76dbe626a8c06cf23a7b80072c64f59dfd0402e8f99c18c7f506` | completed | input=3058, output=787, total=3845 | MISSING | logical calls=1; SDK retries=MISSING |
| 4 | WRITER_P3 | 13931 / `e78b3b6130c9eb07ffb81978be7c2c1092e8e773b38aa34be6b5dcb4f359ddbc` | 5120 | 3302 / `8b3c930a6534f07ddce6556df5864be5909bf90da9262a8804aefeaf14f34aa9` | completed | input=3012, output=803, total=3815 | MISSING | logical calls=1; SDK retries=MISSING |

No structural repair, fresh Planner, Writer regeneration, content rewrite, or recorded retry occurred in this run. `provider_call_total=4` is a logical-call count, not evidence that the SDK made exactly four HTTP attempts.

## Story Map transformations

- Raw visible Planner response: **MISSING**. A field-by-field raw-to-parsed comparison is therefore impossible.
- Parsed/persisted map: captured verbatim in `05-story-map-persisted.json`; it matches the story map embedded in session.
- Demonstrably added after parsing: `length_contract={target_chars:12000, allowed_min:11500, allowed_max:12500}`; historical Runner adds it after `plan.to_dict()`.
- Roles/targets/ownership were accepted: P1 OPENING / P2 MIDDLE / P3 FINAL, targets 3999/3999/3998, three owned atoms each. Whether empty loops/default `transition_direction` values were provider-supplied or normalised is **MISSING** without raw Planner JSON.
- No truncation of writer_material occurred in this historical map: joined lengths A1..A9 were 524, 428, 427, 427, 389, 406, 333, 356, 382 — each below the then-640 aggregate cap.

## Atom/beat → prompt → visible prose

| atom | Story Map material | visible result location | trace finding |
|---|---|---|---|
| A1 | Renewed mass attack; five beats instruct attack/emergency/responder framing. | P1 paragraphs 1–2 | Reached prompt in full (524 chars < old 640 cap); response adds ungrounded ‘night/early morning’ and ‘reports from scene’. |
| A2 | Intensified Russian strikes; five beats restate escalation/pressure/PVO burden. | P1 paragraphs 3–4 | Reached prompt in full (428 chars); overlaps A1/A3 and becomes explanatory pressure. |
| A3 | Dramatized emergency response. | P1 paragraphs 1, 2 and 4 | Reached prompt in full (427 chars); it overlaps A1 resulting_state and is not separately developed as a distinct action sequence. |
| A4 | Operational strain on defenses/infrastructure. | P2 paragraphs 1–2 | Reached prompt in full (427 chars); transformed into generic analysis of systems rather than a new documented operation/result. |
| A5 | Peace expectations weaken; no negotiation event is supplied. | P2 paragraphs 3–4 | Reached prompt in full (389 chars); replaced by analysis of ‘window for negotiations’ and ‘trust’, not a new event. |
| A6 | Story/framing shifts to political-security cost. | P2 paragraph 5 | Reached prompt in full (406 chars); the atom itself is an editorial framing instruction, then prose says ‘story becomes a story of…’. |
| A7 | Kyiv remains on alert. | P3 paragraphs 1–2 | Reached prompt in full (333 chars); repeats ongoing alert/emergency already used in P1, with no new observed status event. |
| A8 | No peace breakthrough visible. | P3 paragraphs 3–4 | Reached prompt in full (356 chars); repeats A5’s delayed peace conclusion, no settlement action or missed deadline. |
| A9 | Russian pressure remains active. | P3 paragraphs 5–6 | Reached prompt in full (382 chars); repeats A2/A4 and provides a closing summary, not terminal development. |

Five `writer_material` strings are coverage instructions, not five independent events. A5/A6/A8/A9 already contain outlook/framing/repeated final-state claims in the map; their repetition in P2/P3 is not a transport loss.

## Quality observations — editorial only, not runtime gates

- **Analytical/literary drift:** P1 paragraph 2 begins `Смысл этой атаки не в одном эпизоде`; P2 paragraph 5 says `история ... становится историей о том`; P3 paragraph 4 uses `Это и есть текущая точка: не мир, а его отсутствие`.
- **Repetition:** A5’s delayed peace conclusion appears in P2 paragraphs 3–4; A8 repeats it in P3 paragraphs 3–4. A2/A4/A9 repeat pressure on defense/security.
- **Event continuity:** P1 moves attack → response and P2/P3 follow its broad consequence, but later sections mostly restate state rather than introduce distinct developments.
- **Final development:** A9/P3 conclude with continued pressure; no concrete new terminal event is present.
- **DRAMATIZED disclosure:** P1 paragraph 1 has one disclosure (`Это реконструкция по доступным сообщениям…`), but it also states `уже зафиксированную картину` despite no supporting record in the captured context. The profile cannot establish those assertions as factual.

## Assembly

- P1/P2/P3 visible-response hashes: e23fda70d706ace2ace2eababe188f1557e29107eec5288d08ba01899e0e5eb0, cf7a5404eaba76dbe626a8c06cf23a7b80072c64f59dfd0402e8f99c18c7f506, 8b3c930a6534f07ddce6556df5864be5909bf90da9262a8804aefeaf14f34aa9
- Historical assembly rule: '\n\n'.join(record['text'].strip() for record in accepted_parts if text.strip()).strip()
- Separator characters: 4 (two `\n\n` separators).
- Reassembled text equals captured scenario: True.
- Python chars / SHA-256: 9141 / `864af5554c49fb75abac961965aed8b52c2a9ca3eb144c8c2edad455360df613`.
- Python length verification occurred after the provider response was received; this does not mean the Writer had Python access while writing.

## Acceptance separation

- Transport: logical calls completed and emitted non-empty output; raw transport retry count is MISSING.
- Schema/topology: READY, valid P1/P2/P3 ownership in persisted map.
- Material transmission: every historical writer prompt reconstructs byte-for-byte to telemetry; no material in this map crossed the old 640-character truncation threshold.
- Length: DONE with `SHORT`, 9141 chars; this is not a 12K acceptance.
- Editorial quality: NOT ACCEPTED; the observed event scarcity/repetition must not create QUALITY_UNUSABLE or Writer rewrite behavior.
