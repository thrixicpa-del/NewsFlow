# NEWSFLOW SCREENSHOT MANIFEST

## Manifest status: PARTIALLY COMPLETE — USER-SUPPLIED REAL UI EVIDENCE

| Field | Value |
|---|---|
| Audit timestamp | 2026-09-11, Europe/Minsk |
| Build launched by audit | None |
| Native NewsFlow window launched by audit | No |
| Original screenshots extracted from DOCX | 43 PNG |
| Synthetic/placeholder captures | 0 (prohibited) |
| Audit contact sheets | 5 PNG (review aids, not evidence replacement) |
| Production state modified | No audit-induced modification |
| Reason | DOCX supplied real UI evidence; no audit launch because `snapshot()` may write recovery/migration state. |

## Expected file naming when capture is authorized

`S-<screen>-<state>-<YYYYMMDDTHHMMSS>-<build>.png`

Examples (patterns only, not files): `S-04-covers-paused-…png`, `S-09-publication-receipt-…png`.

## Per-capture metadata schema

| Field | Meaning |
|---|---|
| Screenshot ID | Matches `NEWSFLOW_SCREENSHOT_UI_ATLAS.md` screen/state ID |
| File | Relative path beneath `docs/audit/screenshots/` |
| Build/runtime | Version, packaged/dev, controlled test root identifier |
| Screen / state | Visible page and exact state/modal |
| Controls | numbered visible controls with labels and enabled state |
| Dependency | `command`, direct preload IPC, local-only state or external provider |
| Result | visual success/error/progress evidence |
| Redaction | what was masked and why |

## Files and provenance

* `screenshots/docx-evidence-20260911/image1.png` … `image43.png`: original inline images from the supplied DOCX.
* `screenshots/docx-contact-sheets-20260911/sheet-01.png` … `sheet-05.png`: audit review aids only.
* Page/component/control mapping is in `NEWSFLOW_SCREENSHOT_UI_ATLAS.md`.

The 23 evidence groups do not cover modal/dropdown/loading/OAuth/queue/error/confirmation states; see `NEWSFLOW_SCREENSHOT_COVERAGE_GAPS.md`.

## Coverage totals

* Screenshots/pages analyzed: **43**.
* Logical screens: **23**.
* Readable visible controls: **268**; code-mapped at component/handler family: **210**; no one-to-one code match: **58**.
* Static code interactive occurrences without this screenshot evidence: **455**.
* Important missing UI states: **20**.

These are evidence-audit counts, not runtime usage counters.
