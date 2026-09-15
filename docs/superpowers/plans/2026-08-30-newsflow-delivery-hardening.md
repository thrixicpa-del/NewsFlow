# NewsFlow Delivery Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a testable, visible NewsFlow workflow from channel connection through private YouTube draft preparation, without hidden controls or misleading completion states.

**Architecture:** Keep the Electron UI as a command client and implement state-changing publication rules in Python. Persist only operator-controlled publication metadata in `Settings`; OAuth credentials remain in the existing per-profile token store. Use the existing cover contract and FastGen tests as a regression boundary rather than replacing cover generation.

**Tech Stack:** Electron, React, TypeScript, Python 3.12, `unittest`, YouTube Data/Analytics OAuth client, FastGen integration.

**Spec:** `docs/superpowers/specs/2026-08-30-newsflow-delivery-hardening-design.md`

## Global Constraints

- Preserve channels, OAuth tokens, Chrome profiles, analytics history, allocation presets and publication queue across restarts.
- Do not perform public publishing without a separate explicit user confirmation.
- A Community post is a prepared manual Studio hand-off, not an API-published action.
- Keep YouTube scenario titles at 100 characters or fewer and tag strings at 500 characters or fewer.
- FastGen cover prompts retain the existing realistic news-photo contract and never overwrite original uploaded reference files.
- Do not add automated audience engagement, fake views, likes, or comments.

---

### Task 1: Remove retired controls and expose only active UI paths

**Files:**
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Test: `studio-ui-remotion-verify/src/ui/App.tsx` static UI command audit

**Interfaces:**
- Consumes: the `Page` union and routed `AnalyticsDashboard`.
- Produces: a single analytics component and visible publication forms instead of `window.prompt`.

- [ ] **Step 1: Write a failing UI audit assertion**

Add a static test or audit script assertion that the retired `function Analytics(` and fallback `function Workspace(` do not remain in `App.tsx`, and that no `<Button>` without `onClick` exists in active routed components.

- [ ] **Step 2: Run the audit and verify it fails**

Run: `pnpm typecheck` and the UI audit command.

Expected: the audit reports the retired components and four inert buttons.

- [ ] **Step 3: Remove the retired components and replace dialog state**

Delete the un-routed Analytics and Workspace component definitions. Add React state for per-job schedule editing and allocation preset naming, then render it as inline publication form controls.

- [ ] **Step 4: Run the audit and typecheck**

Run: `pnpm typecheck` and the UI audit command.

Expected: no active disabled buttons without a documented prerequisite and no retired component names.

### Task 2: Normalize tags at the YouTube limit

**Files:**
- Modify: `scriptor/youtube_publisher.py`
- Modify: `scriptor/bridge.py`
- Test: `tests/test_youtube_publisher.py`

**Interfaces:**
- Produces: `normalize_youtube_tags(tags: Iterable[str], limit: int = 500) -> list[str]`.
- Consumes: ready package tags and existing `publication_job_from_result` / upload payload builders.

- [ ] **Step 1: Write failing tests**

Add tests proving that duplicate and blank tags are removed, that a 500-character comma-separated tag representation is allowed, that the next whole tag is removed when it would exceed 500, and that normalization is applied both while reading a ready package and immediately before building an upload body.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests -v`.

Expected: the new tag-limit assertions fail because no normalizer exists.

- [ ] **Step 3: Implement the normalizer at the publication boundary**

Add `normalize_youtube_tags` in `youtube_publisher.py`. Trim each tag, compare duplicates case-insensitively, and append only entire tags while `len(','.join(result + [tag])) <= 500`. Apply it when queue records are produced and in the final Data API request builder.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests -v`.

Expected: all publication tests pass, including tags exactly at and just over the limit.

### Task 3: Make long-title correction and post hand-off visible

**Files:**
- Modify: `scriptor/youtube_publisher.py`
- Modify: `scriptor/bridge.py`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/publication.css`
- Test: `tests/test_youtube_publisher.py`

**Interfaces:**
- Produces: `rewrite_publication_title(payload: dict) -> dict`, `mark_publication_post_done(payload: dict) -> dict`, and `open_publication_post_studio(payload: dict) -> dict`.
- Consumes: a publication job ID, operator-provided rewritten title, prepared post record, and channel profile ID.

- [ ] **Step 1: Write failing backend tests**

Add tests that a valid rewritten title changes a blocked job from `needs-title-rewrite` to `ready` or `scheduled`, that an over-100-character replacement is rejected, and that marking the prepared post complete persists a `post.status == 'published-manually'` event without changing video status.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests -v`.

Expected: missing bridge commands or UI-facing record transitions fail.

- [ ] **Step 3: Implement explicit backend commands**

Validate the job ID and title with `apply_rewritten_title`, persist the replaced record, and append an activity item. Build a Creator Studio URL using the job channel's persistent profile for the manual post hand-off. Mark completion only when the operator presses the visible control.

- [ ] **Step 4: Render clear publication actions**

For each job, show editable title correction only when blocked, show title count, thumbnail, duration, SEO description, phrases and normalized tags, plus `Копировать пост`, `Открыть Studio`, and `Отметить пост опубликованным` when the post is prepared. Use inline controls and copied text through the desktop bridge; do not use browser prompt dialogs.

- [ ] **Step 5: Run focused and UI checks**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests -v`.

Run: `pnpm typecheck` from `studio-ui-remotion-verify`.

Expected: backend tests and TypeScript check pass.

### Task 4: Complete the visible channel lifecycle

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/analytics.css`
- Test: `tests/test_youtube_publisher.py`

**Interfaces:**
- Consumes: existing `add_channel`, `connect_youtube_channel`, `open_analytics_channel`, and `update_analytics_channel_metadata` commands.
- Produces: an inline channel creation form, actual channel identity after OAuth, operator tag persistence, and profile-specific Studio navigation.

- [ ] **Step 1: Keep and extend failing lifecycle tests**

Retain the existing tests for visible channel row creation, Studio URL and profile, and operator-tag storage. Add assertions that an unconnected row reports `Ожидает входа Google` and a connected one serializes `channelId`, `thumbnailUrl`, `subscribers`, and operator tag together.

- [ ] **Step 2: Run focused tests and verify failure for new snapshot field assertion**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests -v`.

Expected: the added contract test exposes any missing snapshot mapping.

- [ ] **Step 3: Make snapshot and UI state complete**

Return every identity field from the same analytics row in snapshot, retain the form after validation errors, and present OAuth/Studio actions with their prerequisites. Ensure the OAuth JSON call never claims a channel was connected before the user completes OAuth.

- [ ] **Step 4: Run focused tests and typecheck**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests -v`.

Run: `pnpm typecheck` from `studio-ui-remotion-verify`.

Expected: all lifecycle assertions and the client compile pass.

### Task 5: Lock in cover/FastGen regressions and test dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `tests/test_covers.py` only if a missing contract test is identified
- Test: `tests/test_covers.py`, `tests/test_youtube_publisher.py`

**Interfaces:**
- Consumes: existing cover instruction, retry, reference normalization, face composition, and text overlay implementations.
- Produces: an installable test environment and regression coverage for realistic prompts, reference size normalization, requested counts, and retry route preservation.

- [ ] **Step 1: Record the current environment failure**

Run: `python -m unittest discover -s tests -v`.

Expected: image-related tests fail during import because `Pillow` and NumPy are unavailable in the current Python environment, not because their assertions fail.

- [ ] **Step 2: Add explicit test dependencies**

Add `numpy` to `requirements.txt` alongside `pillow`; keep their versions compatible with Python 3.12. Do not change production cover logic unless a cover test fails after dependencies are installed.

- [ ] **Step 3: Install dependencies into the isolated build/test dependency directory**

Run the project dependency installation command used by the portable build, without replacing the system Python packages.

- [ ] **Step 4: Run cover and full test suites**

Run: `python -m unittest tests.test_covers -v`.

Run: `python -m unittest discover -s tests -v`.

Expected: realistic-photo contract, per-prompt count, reference normalization, face fit, retries, and all other available tests pass.

### Task 6: Assemble and exercise the portable release

**Files:**
- Modify: `studio-ui-remotion-verify/package.json`
- Build output: `studio-ui-remotion-verify/release-2.1.103-delivery-hardening/`

**Interfaces:**
- Consumes: validated Python core and TypeScript bundle.
- Produces: a versioned portable `NewsFlow Studio.exe` with matching core resources.

- [ ] **Step 1: Build the Python core into a new versioned output directory**

Run the existing PyInstaller command from the project `work` directory with a distinct `core-bin-2.1.103` output and work folder. Do not overwrite an earlier release folder.

- [ ] **Step 2: Point Electron packaging to the matching core output and bump the version**

Update package metadata and core resource paths to `2.1.103` and `core-bin-2.1.103`.

- [ ] **Step 3: Run portable verification**

Run: `pnpm typecheck`, `pnpm verify:core-runtime`, `pnpm verify:remotion-runtime`, and `pnpm package:preview` from `studio-ui-remotion-verify`.

Expected: all commands succeed and create a new portable executable.

- [ ] **Step 4: Exercise the release as an operator**

Launch the new portable executable only after asking the user for launch permission. Check the Add channel form, channel row rendering, tag/title validation, prepared-post actions, mass scheduling selection, selected cover repeat controls, and output-folder open action. If the user has connected OAuth, any real upload test must use one private test draft and stop before public publication.

## Plan Self-Review

- Spec coverage: Tasks 1–4 cover interface, channel, title, post, and tag requirements; Task 5 covers cover/FastGen contract and complete test dependencies; Task 6 covers build and operator verification.
- Placeholder scan: no unspecified implementation tasks or deferred validation steps remain.
- Type consistency: all new bridge commands take `{ jobId, ... }` payloads and return snapshot plus operation result, consistent with existing command dispatch.
