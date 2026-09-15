# Thumbnail, Gallery and Finished Audio Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the thumbnail flow observable and durable from production item context through generation, gallery selection and reload; import finished nested audio safely without changing the source folder.

**Architecture:** Keep the existing `Settings.cover_queue` and `Settings.voice_scenario_outputs` contracts. Add small, testable helpers in the Python bridge for gallery file-state and recursive audio discovery/matching; expose their status in the existing snapshot and Electron/React UI. Preserve all persisted paths and never delete missing thumbnail entries or source audio.

**Tech Stack:** Python 3 bridge and `unittest`, Electron IPC, React/TypeScript, Vite typecheck.

**Spec:** `C:\Users\borov\.codex\attachments\d1f340d1-c263-427d-8a76-7af07e905ad3\pasted-text.txt` and the user's approved 2026-09-09 scope message.

## Global Constraints

- Do not modify Ideas Engine V2 or its specification.
- Do not alter or delete any source file in `C:\Users\borov\Downloads\84_scenariev`.
- Missing thumbnail paths remain persisted and get a visible state; they are never automatically deleted.
- Audio auto-attach is allowed only for a unique high-confidence match; ambiguous candidates remain unattached.
- Existing single-file and ZIP audio import must keep working.

---

### Task 1: Gallery file-state and full thumbnail context

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `tests/test_covers.py`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/covers.css`

**Interfaces:**
- Produces `cover_file_state(path: str) -> dict` for persisted gallery path status.
- Extends snapshot cover rows with per-path availability/error information while retaining raw paths.

- [ ] **Step 1: Write failing tests** for an existing valid image, a missing path, and a corrupt/non-image file. Assert that state says `ready`, `missing`, and `invalid`, without mutating the queue.
- [ ] **Step 2: Run `python -m unittest tests.test_covers`** and confirm the new tests fail because the state helper/snapshot field does not exist.
- [ ] **Step 3: Implement the smallest bridge helper** using `Path.is_file()` and Pillow verification; include Direction, Topic, Angle, title, event context, entities, geography, conflict, consequence and framing when rendering prompt context is available.
- [ ] **Step 4: Run `python -m unittest tests.test_covers`** and confirm it passes.
- [ ] **Step 5: Render the state in Gallery**: actual image for ready; distinct missing/invalid card with its stored path and retry affordance; do not remove the row.
- [ ] **Step 6: Run `pnpm typecheck`** in `studio-ui-remotion-verify`.

### Task 2: Thumbnail generation reliability and context-aware prompts

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `tests/test_covers.py`

**Interfaces:**
- Keeps `regenerate_covers(payload) -> dict` and saved queue path semantics.
- Produces topic-specific visual prompt additions only when backed by event/context fields.

- [ ] **Step 1: Write failing tests** that assert conflict/war context adds topic-appropriate dramatic visual cues and non-conflict migration/economy context explicitly avoids unrelated military imagery.
- [ ] **Step 2: Run `python -m unittest tests.test_covers`** and confirm those tests fail on the old prompt logic.
- [ ] **Step 3: Implement minimal context classifier/prompt builder**: use only available structured fields and maintain no-invented-fact wording; preserve provider errors, generation retry state, variants, selection, and persistence.
- [ ] **Step 4: Run `python -m unittest tests.test_covers`** and confirm it passes.
- [ ] **Step 5: Add and run an end-to-end bridge test** using a deterministic image-provider fake to prove generate → save → gallery snapshot → select → reload.

### Task 3: Recursive finished-audio discovery and safe matching

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `tests/test_voicer.py`
- Modify: `studio-ui-remotion-verify/electron/main.ts`
- Modify: `studio-ui-remotion-verify/electron/preload.mts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`

**Interfaces:**
- Produces `scan_voiceover_folder(root: Path, titles: list[str]) -> dict` with found folder/audio counts and exact/high/medium/ambiguous/unmatched records.
- Adds a folder-picker IPC and a bridge command that imports only uniquely matched managed copies.

- [ ] **Step 1: Write failing tests** with nested Russian folder names and numbered `*_narration.mp3`; assert unique parent-folder match, ambiguous non-attach, unmatched record, source preservation, and reload persistence.
- [ ] **Step 2: Run `python -m unittest tests.test_voicer`** and confirm failure because recursive folder import does not exist.
- [ ] **Step 3: Implement recursive discovery** for `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`, `.flac`; normalise Cyrillic, punctuation, dash variants, numeric export prefixes and Windows-safe filenames. Use parent folder then filename as matching evidence.
- [ ] **Step 4: Implement safe attachment** by copying only high-confidence unique matches into the managed output directory, preserving all originals and retaining review data in settings.
- [ ] **Step 5: Run `python -m unittest tests.test_voicer`** and confirm it passes.
- [ ] **Step 6: Add folder-selection UI and summary**: folders found, audio found, matched, requires choice, unmatched, errors. Keep existing file/ZIP actions.
- [ ] **Step 7: Run `pnpm typecheck`** in `studio-ui-remotion-verify`.

### Task 4: Regression and real-folder validation

**Files:**
- Test: `tests/test_covers.py`
- Test: `tests/test_voicer.py`

- [ ] **Step 1: Run focused unit tests** for covers and voice.
- [ ] **Step 2: Read-only scan `C:\Users\borov\Downloads\84_scenariev`** with the actual matcher; report counts without importing or changing source files.
- [ ] **Step 3: Run full Python suite** with `python -m unittest discover -s tests -p "test_*.py"`.
- [ ] **Step 4: Run `pnpm typecheck` and the established UI delivery checks**.
- [ ] **Step 5: Stop and report the verified findings. Do not start Ideas Engine V2.**
