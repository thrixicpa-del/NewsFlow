# Thumbnail Word Engine V2 Implementation Plan

> For inline execution: use TDD task-by-task. No parallel workers: all tasks share the same cover state.

**Goal:** Implement only the approved Word Engine V2: topic-grounded headline/subheadline generation before visual prompts, diverse semantic structure pairing, validation, repair, persistence and UI state.

**Architecture:** A Word Engine layer derives a structured semantic plan from ProductionItem facts, selects a deterministic headline/subheadline structure pair, builds strict provider prompts, validates the returned JSON and persists independent line state. It does not read visual layout, face references or FastGen prompt assembly.

**Tech Stack:** Python 3, unittest, existing scriptor.bridge settings persistence.

**Spec:** C:\Users\borov\.codex\attachments\6ea3f0ab-ad9f-4d13-b655-20f1a50e66c6\pasted-text.txt

## Global Constraints

- Touch word-engine code, cover UI state and its tests only.
- Do not modify FastGen visual prompt assembly, image generation, faces, providers, montage, publication, TTS, ideas, scripts or footage.
- Ready and manual values are immutable to ordinary batch generation.
- Exactly two controlled repair calls maximum, then a truthful failed state.
- Build a separate test application; do not overwrite production installations or library data.

---

### Task 1: Structured semantic plan and V2 structure pairing

**Files:** Modify scriptor/bridge.py. Test scriptor/test_cover_library.py.

**Produces:** _cover_word_semantic_plan(item), _cover_word_structure_pair(item, variation_index).

- [ ] Write failing tests for a stable title selecting the same H/S pair, variation selecting a different compatible pair, and at least 18 H and 18 S definitions.
- [ ] Run only those tests and confirm the missing V2 interface is the failure.
- [ ] Add fact-only semantic slots and deterministic complementary pairing.
- [ ] Run the cover suite.

### Task 2: Word validation and controlled repair

**Files:** Modify scriptor/bridge.py. Test scriptor/test_cover_library.py.

**Produces:** _validate_cover_word_result and reason-coded repair prompts.

- [ ] Write failing tests for malformed JSON, length, generic-only phrase, foreign entity, unsupported number, claim strength, word duplicate, semantic duplicate and non-complementary pair.
- [ ] Verify failures before implementation.
- [ ] Implement validation plus two bounded repair attempts. Emergency guards never mark a truncated result ready.
- [ ] Run the cover suite.

### Task 3: Persisted line state, manual protection and batch diversity

**Files:** Modify scriptor/bridge.py. Test scriptor/test_cover_library.py.

**Produces:** persisted source, status, structure id, variation index, attempts, repair history and used slots.

- [ ] Write failing tests for ready skip, manual protection, restart hydration, isolated failed item and 30-topic structure/pattern diversity.
- [ ] Implement the smallest state migration and generation path changes.
- [ ] Run the cover suite and relevant UI tests.

### Task 4: Build and workflow verification

**Files:** Modify COVER_PROMPTS_AND_STYLE.md only if actual behavior needs documenting.

- [ ] Run relevant automated tests and repair failures.
- [ ] Create a separate test build using the existing official packaging command.
- [ ] Launch the packaged app, smoke test topic to words to visual-prompt handoff, then test persistence and regenerate behavior.
- [ ] Mark real provider work blocked only if authentication or external service access actually blocks it.
