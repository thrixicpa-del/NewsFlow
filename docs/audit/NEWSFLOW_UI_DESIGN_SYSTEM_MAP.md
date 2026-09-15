# NEWSFLOW UI DESIGN SYSTEM MAP

## Source-derived visual system

The renderer is a desktop-first dark NewsFlow Studio shell: fixed sidebar, header/stat strip, content panels, toolbar actions, cards, tables, drawer/sheet primitives and status badges. Source imports establish a broad local CSS system: `styles.css`, `dashboard.css`, `ideas.css`, `scenarios.css`, `covers.css`, `footage.css`, `editor.css`, `voice.css`, `analytics.css`, multiple `publication-*.css`, plus template/session/agent styles.

## Tokens and primitives observed

| Primitive | Location | Usage |
|---|---|---|
| `Button` | `App.tsx` plus component primitive | Core actions with kinds including primary/success/danger. |
| `UiButton` | publication components | Publication action variants including destructive/secondary/primary. |
| `Badge` | `components/badge.tsx` | Status visualization. |
| `DataTable` | `components/data-table.tsx` | Publication queue/history tables and expandable details. |
| `Sheet` | `components/sheet.tsx` | Receipt/modal-like detail presentation. |
| `Tabs` / `Tooltip` | shared components | Local navigation / explanation controls. |
| Lucide icons | `App.tsx`, publication UI | Action and page iconography. |

## Navigation and information architecture

`App.tsx` holds a union of 25 valid page IDs and navigation groups. It renders a header for non-publication pages, a common notice toast-like bar, and conditional page components. Publication, allocation and automation resolve to the same `PublicationPage`, creating a context mismatch risk: three page IDs do not select visibly distinct top-level views in the route shell.

## Interaction grammar

* **Mutations:** most controls call `command(name, payload)` and display a generic success notice if any state returns.
* **Long tasks:** labels explicitly cover idea/scenario/cover/SEO/voice/index/montage actions. Actual progress relies on later snapshot fields; no single frontend task protocol is evident.
* **Native paths:** preload offers folder/video/image/audio/JSON/prompt/save dialogs.
* **Destructive actions:** some are guarded with `window.confirm`; audit did not interact with them.
* **Loading/error:** global `notice` flattens many operation outcomes to a message. Individual complex panels add own statuses.

## Static accessibility and usability review

| Finding | Evidence | Impact |
|---|---|---|
| Giant composite screen module | `App.tsx` accounts for 646 static interactive occurrences | Higher regression risk; difficult to test individual focus/loading/empty states. |
| Native labels are present for many fields | `<label>` wraps inputs/selects in inspected screens | Positive baseline, but full accessibility tree is **NOT VERIFIED**. |
| Icon buttons sometimes include visible text | Dashboard/publication controls | Good discoverability; controls that are icon-only require live audit. |
| Multiple publication UX generations remain | `PublicationPage` plus `LegacyPublicationDashboard*` source | Risk of duplicate/obsolete copy and inconsistent user flow. |
| Generic success notice | command wrapper says “Сохранено…” after any returned state | Can overstate completion of background/partial actions. |
| Dense covers/analytics/publication screens | Large conditionals and many controls in App.tsx | Requires screenshot and keyboard review; **NOT VERIFIED**. |

## Required visual verification not performed

No NewsFlow native window was launched by the audit automation because source shows `snapshot()` may write migration/recovery state. However, 43 real screenshots from the user-supplied DOCX were extracted and inspected. They confirm the shell, major pages, static/default controls, visible empty states, one montage failure/retry presentation and dense configuration cards. They do **not** verify focus order, modal stacking, disabled semantics, color contrast, imagery resolution, tooltips, provider selectors, live loading, OAuth, queue execution or external error behavior. See `NEWSFLOW_SCREENSHOT_UI_ATLAS.md` and `NEWSFLOW_SCREENSHOT_COVERAGE_GAPS.md`.

## Screenshot-led UX findings

The visual evidence shows a consistent dark desktop product and recognisable primary blue actions. It also shows very dense cover, voice, montage and publication surfaces, where configuration controls and action groups compete for attention. The actionable issue is not a claim that the UI is broken: it is a forensic finding that the visual hierarchy and runtime completion semantics need state-specific testing. In particular, a montage card visibly pairs `100%` with an error/stopped state, so percentage cannot stand alone as a completion signal.

## Design-system consolidation opportunity

Keep the existing component primitives but move domain screens out of `App.tsx`, use one typed command registry and one task-status component, and retire/flag legacy publication components. This is a recommendation, not an implemented change.
