# Title Generator Diversity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both NewsFlow Agent and direct ChatGPT produce short, varied, non-duplicated political-news YouTube titles from the release plan.

**Architecture:** The bridge owns one editorial policy, deterministic validation, candidate selection, and persistent diversity memory. The UI renders the resulting title metadata but never stores API secrets or delegates validation to a model.

**Tech Stack:** Python 3.12, existing `HybridTextPool`, JSON settings, React/TypeScript.

**Spec:** `C:\Users\borov\.codex\attachments\1590c42e-9c07-48e2-870a-a1d68ce6926b\pasted-text.txt`

## Global Constraints

- Title length is calculated with Python `len(title)` and must be 1–100 characters.
- The desired range is 55–95 characters; shorter titles may remain when strong.
- Never invent events, crimes, casualties, quotes, or actions by real people as confirmed news.
- The old hook-action-consequence formula is not mandatory; title forms must rotate.
- Both `agent` and `openai` plan routes use the same policy and validation.

---

### Task 1: Deterministic title validation and selection

**Files:**
- Modify: `scriptor/bridge.py`
- Test: `tests/test_ideas.py`

- [ ] Write failing tests for a title longer than 100 characters, all-CAPS text, repeated opening words, and duplicate candidate rejection.
- [ ] Add `validate_title`, normalized-token similarity, title metadata extraction, and candidate selection that chooses only valid unique titles.
- [ ] Run `py -3 -m unittest tests.test_ideas -v` and confirm every new test passes.

### Task 2: Shared policy and diversity memory

**Files:**
- Modify: `scriptor/config.py`
- Modify: `scriptor/bridge.py`
- Test: `tests/test_ideas.py`

- [ ] Write failing tests that prove saved memory prevents a repeated opening and that both provider routes receive the editorial policy.
- [ ] Persist the last 500 title metadata records in `Settings.idea_title_memory`; feed recent records into each generated prompt.
- [ ] Request varied candidates, classify hook and angle, programmatically keep the planned count, and save metadata for selected titles.
- [ ] Run the focused tests and then the full suite.

### Task 3: Explain generated title provenance in the UI

**Files:**
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/footage.css`
- Test: `studio-ui-remotion-verify/scripts/verify-custom-direction-ui.mjs`

- [ ] Write a failing source contract for character count, hook type, and source direction on each result.
- [ ] Render metadata alongside generated results without exposing API keys or raw model payloads.
- [ ] Run `pnpm typecheck` and the UI source contract.

### Task 4: Delivery verification

**Files:**
- Verify: `tests/`
- Verify: `studio-ui-remotion-verify/`

- [ ] Run `py -3 -m unittest discover -s tests -q`.
- [ ] Rebuild the core and portable executable only after all unit and UI checks pass.
- [ ] Verify the portable package and launch the generated executable once.
