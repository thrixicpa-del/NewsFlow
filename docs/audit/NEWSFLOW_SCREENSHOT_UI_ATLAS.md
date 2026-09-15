# NEWSFLOW SCREENSHOT UI ATLAS

## Capture result

**Actual NewsFlow screenshots analyzed: 43.** The user-supplied DOCX contains 43 inline PNG images, extracted byte-for-byte to `screenshots/docx-evidence-20260911/` as `image1.png` through `image43.png`. Five audit-only contact sheets were used to review the set; conclusions use the original full-resolution PNGs, not contact-sheet scale.

The audit did not launch a build: source inspection shows that the first renderer refresh invokes `bridge.snapshot()`, which can persist recovery/migration changes. Launching it against the canonical user store would violate the requested read-only constraint. No placeholder, synthetic or reconstructed screenshot was created.

## Logical screen evidence index

`Visible controls` is a compact label set. If a small caption is not legible at original resolution it is marked `UNREADABLE`; it is not reconstructed from source.

| Screenshot/page ID → PNG | Page / React component | UI section and visible controls | Command/IPC → backend/core | Queue/provider/persistence → visible state |
|---|---|---|---|---|
| V-01 → 1,2 | `dashboard` → `Dashboard` | Центр управления: target, save, automatic toggle/stage chips, start pipeline, step cards | `save-settings`, `run-auto-pipeline` → bridge | Settings/pipeline; ready dashboard. |
| V-02 → 3 | `ideas` → `Ideas` | Маршрут генерации: preset selector/save, agent selector, apply selected, Generate, TXT/MD import, clear prompt, transfers/download/regenerate/delete | idea commands → bridge generators | idea state/settings; empty results shown. |
| V-03 → 4,5 | `scenarios` → `Scenarios` | Новости и сценарии: provider/route controls, list, generation/import/transfer controls; lower continuation | scenario commands → bridge | scenarios/session state; details partly `UNREADABLE`. |
| V-04 → 6 | `templates` → `TemplateEditor` | Шаблоны и промпты: template selection, editor textarea, save/delete/preset actions | template/range commands → bridge | settings template collections. |
| V-05 → 7 | `agents` → `Agents` | Агенты NewsFlow: agent cards and navigation | local navigation | no task/worker state visible. |
| V-06 → 8,9,10 | `covers` → `Covers` | Обложки YouTube / FastGen Lab: key checkboxes, step guide, variant/text/face options, counters and create/process controls | cover settings/prompt/text/generation → `generate_covers` | FastGen pool, cover queue/library; 84 waiting shown; request not proven. |
| V-07 → 11,12 | `scripts` → `FinishedScripts` | Готовые сценарии: list rows, selection, transfer/download/action buttons | export/transfer/voice/montage → bridge | session scripts/downstream refs. |
| V-08 → 13,14,15,16 | `coverGallery` → `CoverGallery` | Gallery configuration/reference/face panels, variants and selectors | reference/face/regenerate → bridge | queue/library/local files; some labels `UNREADABLE`. |
| V-09 → 17,43 | `coverGallery` → `CoverGallery` | Gallery cards: keep/delete, repeat current, new prompts, headline/subheadline, face selector, FastGen rerender | select/remove/regenerate → bridge | a 100%/ready item is visible; actual file operation not proven. |
| V-10 → 18 | `media` → `Media` | Картинки и видео: style/prompt and generate, empty results | `generate-media` → bridge | media output/provider; empty state. |
| V-11 → 19 | `footage` → `Footage` | Футажи: folders, index/status, inspect/search/download | footage commands → `ClipIndex` | settings + SQLite; no active index state. |
| V-12 → 20 | `cutter` → `Cutter` | Нарезка футажей: sources, output folder, process controls | cutter commands → bridge/cutter | source/output paths; empty sources. |
| V-13 → 21,22 | `voice` → `VoiceQueue` | Очередь озвучки: Chrome/login, selected/all, pause, imports, results, range preview, provider selector | voice/range/import → bridge TTS | WProject shown; rows/counters visible, execution not proven. |
| V-14 → 23,24,25 | `voices` → `VoiceProfilesScreen` / `VoiceProfiles` | Профили голосов: add, save, cards/forms, sliders | profile/settings → bridge | settings voice profiles. |
| V-15 → 26 | `audio` → `Audio` | Готовые MP3: output folder and empty list | local navigation/open | voice output path; empty state. |
| V-16 → 27,28,29 | `editor` → `MontageLiveStatus` + `Editor` | Монтаж: queue summary, project controls/diagnostics; image 29 has error cards, 100%, `Повторить с начала` | montage → bridge worker | task status/projects; stopped/failed recovery is visible, not live execution proof. |
| V-17 → 30,31 | `seo` → `Seo` | SEO-описание: settings/prompt, generate and result rows | SEO commands → bridge | SEO queue/output. |
| V-18 → 32,33 | `tags` → `Tags` | Теги: generate, clear, export, settings/list | tag commands → bridge | tag/SEO persistence. |
| V-19 → 34,35 | `analytics` → `AnalyticsDashboard` | Каналы: add, refresh, OAuth/revenue/Studio/remove controls | direct OAuth IPC + analytics → bridge | OAuth/channel settings + YouTube; no-access label visible. |
| V-20 → 36 | `outputs` → `Outputs` | Результаты: package/result area and empty message | package/export/open path | output path/package state; empty state. |
| V-21 → 37,38 | `keys` → `Keys` | API-ключи: provider pools, add/activate/notes/metadata rows | key/refresh → bridge/provider clients | protected settings; values not exposed. |
| V-22 → 39 | `publication` → `PublicationPage` | Publication V2: readiness/distribution/start, counters, tabs, search/filter, selectable records/overflow | V2 commands → publication_v2 | 84 records, 3 MP4 ready, 81 attention visually shown. |
| V-23 → 40,41,42 | `publication` → `PublicationPage` | allocation rules/presets, scheduling/settings and queue/empty lower views | allocation/rules/queue → bridge | publication settings/queues; no open dropdown/receipt. |

## Visual / code mismatches

| ID | Evidence level | Mismatch |
|---|---|---|
| VM-01 | screenshot + source | Current Electron UI is visible, while source retains legacy Tk (`scriptor/app.py`) and legacy publication/analytics components. |
| VM-02 | screenshot + source | Covers shows active primary flow/counters; screenshots cannot prove FastGen request, rate recovery or image output. |
| VM-03 | screenshot + source | Montage image 29 shows 100% and `Ошибка`/stopped queue together; progress is not a completion guarantee. |
| VM-04 | screenshot + source | Publication V2 visual totals are projections while source retains legacy and V2 structures. |
| VM-05 | screenshot + source | No completed Channel Research screen is visible although source has per-profile research state/import helpers. |
| VM-06 | screenshot + source | Visible global “Сохранено в проекте NewsFlow” can follow any returned state; source does not make it a durable completion receipt. |

## UX forensic review

* Consistent dark shell, left navigation, titles, counters and strong blue primary buttons are evidenced.
* Covers, voice, montage, publication and API keys are dense; long forms/cards require substantial scrolling.
* Dashboard/publication make primary actions clearest. In dense cards, primary, retry, import, export and destructive actions compete.
* Image 29 proves `100%` can coexist with error/stopped state. Loading, paused and provider-selector states are absent.
* Red destructive styling is visible, but no confirmation dialog is evidenced.
* Modern Publication V2 and large legacy-style App screens have inconsistent density/layout treatment.

See `NEWSFLOW_SCREENSHOT_COVERAGE_GAPS.md` for all missing state evidence.

## Required capture plan for a safe follow-up run

Use a disposable copy of the canonical application state and a controlled test `LOCALAPPDATA` root. Do not connect providers, OAuth, FastGen, YouTube, or external file exports. Capture each item below after the app visibly reaches the state; annotate source control label/role and state transition.

| ID | Screen/state to capture | Expected controls from source | Status |
|---|---|---|---|
| S-01 | Control center default | target input, save, stage toggles, auto pipeline | NOT CAPTURED |
| S-02 | Ideas default + source/plan panels | topic CRUD, generate, transfer, export | NOT CAPTURED |
| S-03 | Scenario editor + import/export states | generate/save/remove/transfer/import | NOT CAPTURED |
| S-04 | Covers ready / empty / running / paused | create, resume/pause, prompt/text/face settings | NOT CAPTURED |
| S-05 | Cover gallery selection and destructive confirmation | variants, render text, remove/export | NOT CAPTURED |
| S-06 | SEO/tags/media empty and result views | settings/generate/export/remove | NOT CAPTURED |
| S-07 | Footage index idle/running/error | folder, inspect, index, web search/download | NOT CAPTURED |
| S-08 | Montage editor, queue running and finished | prepare/render/queue/output/export | NOT CAPTURED |
| S-09 | Publication V2 allocation/queue/receipt sheet | preview/confirm/start/pause/retry/cancel | NOT CAPTURED |
| S-10 | Voice queue, profiles and pools | generate/pause/import/range/provider controls | NOT CAPTURED |
| S-11 | Analytics channel/OAuth card | add, OAuth, revenue, Studio, refresh, metadata | NOT CAPTURED |
| S-12 | Sessions, keys and knowledge | credentials, profile/session, Obsidian controls | NOT CAPTURED |

## Screenshot quality requirements

* Native application window only; keep address bars, secrets, user file paths, OAuth details and personal data out of captures.
* Record viewport/window dimensions and app build identifier.
* Capture every modal, sheet, menu, empty, loading, error, disabled and confirmation state encountered.
* Annotate control number, visible label, source component, backend/direct IPC dependency, whether it mutates state and expected completion signal.
* Store only real PNG captures under `docs/audit/screenshots/`; do not infer visual appearance from source.

## Source-only visual findings pending screenshots

See `NEWSFLOW_UI_DESIGN_SYSTEM_MAP.md`: 25 page IDs, 665 interactive JSX occurrences and a strong concentration in `App.tsx`. None of those numbers validates a rendered control.
