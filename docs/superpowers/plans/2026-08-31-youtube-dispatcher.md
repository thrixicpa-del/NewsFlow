# YouTube Dispatcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` task by task. Steps use checkbox syntax for tracking.

**Goal:** Make NewsFlow's YouTube channel, allocation, publication, and analytics workflows clear, durable, and testable without releasing a new executable.

**Architecture:** The bridge remains the single trusted command boundary. Dedicated browser profiles are created only below `LOCALAPPDATA/NewsFlow/YouTubeChannelProfiles/<profile-id>`; the UI receives only public channel metadata and action outcomes. Allocation and calendar calculation remain deterministic Python helpers and expose explanatory results to React.

**Tech Stack:** Python 3.12, Google OAuth desktop flow, YouTube Data/Analytics APIs, React/TypeScript, Electron bridge, unittest.

**Spec:** User-approved plan in this Codex task, 2026-08-31.

## Global Constraints

- Do not build or release an `.exe` unless the user explicitly asks.
- Never use the primary Chrome profile for a YouTube OAuth flow.
- Store OAuth tokens only in protected settings; never return tokens to the UI.
- Revenue requires the separate monetary OAuth scope and must have an explicit empty state.
- Default calendar: first-then-batches, 15-minute slot step, batch capacity 1.
- Manual channel quotas override recommendations.

### Task 1: Dedicated OAuth profiles and account switching

**Files:**
- Modify: `scriptor/youtube_oauth.py`, `scriptor/bridge.py`
- Test: `tests/test_youtube_publisher.py`

- [ ] Write failing tests for passing a per-channel Chrome profile to OAuth, binding returned metadata, and safely resetting one profile only.
- [ ] Run the targeted tests and confirm they fail for the missing browser/profile behaviour.
- [ ] Implement one shared profile-path and Chrome-command builder, profile-scoped OAuth, and archived profile reset.
- [ ] Run the targeted tests and confirm they pass.

### Task 2: Analytics data contract

**Files:**
- Modify: `scriptor/youtube_api.py`, `scriptor/config.py`, `scriptor/bridge.py`, `studio-ui-remotion-verify/src/ui/desktop.d.ts`
- Test: `tests/test_youtube_publisher.py`

- [ ] Write failing tests for public metadata refresh, video/topic metrics binding, and revenue/no-scope empty states.
- [ ] Implement safe YouTube Analytics query adapters and persist only normalized metrics.
- [ ] Update bridge snapshot status/messages and verify tests.

### Task 3: Allocation and 15-minute calendar engine

**Files:**
- Modify: `scriptor/youtube_allocation.py`, `scriptor/youtube_publisher.py`, `scriptor/bridge.py`
- Test: `tests/test_youtube_publisher.py`

- [ ] Write failing tests for quota `5 of 5`, reasons for skipped jobs, all three calendar modes, 15-minute slots, and manual move.
- [ ] Implement deterministic allocation explanations and scheduler modes while keeping saved legacy presets compatible.
- [ ] Run targeted tests.

### Task 4: React dispatcher UI

**Files:**
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`, `studio-ui-remotion-verify/src/ui/analytics.css`, `studio-ui-remotion-verify/src/ui/desktop.d.ts`
- Test: `tests/test_ui_delivery.py`, TypeScript typecheck

- [ ] Rework channel onboarding to three visible steps and add account-switch controls.
- [ ] Rework publishing into plan, allocation, calendar, and upload/post blocks with controlled quota controls, counters, card actions, drag/drop and keyboard move alternative.
- [ ] Add three-level analytics states/cards and accessible labels/live action feedback.
- [ ] Run UI contract tests, typecheck, and current web guideline audit.

### Task 5: Verification and manual OAuth handoff

**Files:**
- Test: all targeted tests and the full suite in its project runtime

- [ ] Run full automated verification, report unrelated environment failures separately.
- [ ] Do not open or publish to a real channel automatically.
- [ ] Ask the user to click the explicit OAuth action for `Взгляд сверху`, then validate returned name/avatar/subscribers and a private draft only.
