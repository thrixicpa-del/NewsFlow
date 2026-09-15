# Ideas Engine Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Ideas screen into a structured, diverse and scriptable production-item generator without changing unrelated FlowNews subsystems.

**Architecture:** A focused `idea_engine` module owns signal/event normalisation, semantic-like deterministic dedupe, portfolio scoring and production-item validation. `bridge.py` remains the command adapter, config persists new records alongside legacy string fields, and scenario handoff receives the production item while retaining title-only compatibility.

**Tech Stack:** Python 3.12, dataclass-style JSON dictionaries, unittest, React/TypeScript/Electron.

**Spec:** `docs/superpowers/specs/2026-09-08-ideas-engine-production-design.md`

## Global Constraints

- Work only in Ideas / Topic Planning and its direct scenario handoff.
- Retain `idea_results`, `idea_result_sources` and title-only legacy projects.
- Never claim an unverified event as fact; manual directions use editorial framing.
- Hard title maximum is 100 Python characters; normalise first letter in code.
- Do not fill requested counts with semantic duplicates.
- Question titles are limited to 20% of the accepted batch.
- Keep current UI visual language and existing command names.

---

### Task 1: Regression fixture and pure production-item contracts

**Files:**
- Create: `scriptor/idea_engine.py`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- Produces `normalise_signal`, `cluster_events`, `evaluate_portfolio`, `build_production_item` and `validate_production_portfolio`.
- Consumes plain dictionaries so bridge, test fixtures and migration code share one format.

- [ ] **Step 1: Write failing regression tests**

```python
def test_rejects_abstract_bait_and_accepts_scriptable_item(self):
    rejected = idea_engine.build_production_item({"direction": "Переговоры", "topic": "Условия", "angle": "конфликт"}, "Ситуация изменилась", [])
    accepted = idea_engine.build_production_item({"direction": "Переговоры", "topic": "Главное условие", "angle": "конфликт"}, "Переговоры зашли в тупик: спор идёт вокруг главного условия", [EVENT])
    self.assertIsNone(rejected)
    self.assertGreaterEqual(accepted["scriptability_score"], 60)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest tests.test_ideas.IdeaProductionEngineTests.test_rejects_abstract_bait_and_accepts_scriptable_item`

Expected: failure because `idea_engine` is absent.

- [ ] **Step 3: Implement pure validators**

```python
def build_production_item(seed, title, events):
    # normalise title, reject abstract/missing-context claims, derive script requirements
    # return a JSON-safe production dictionary or None
```

- [ ] **Step 4: Run focused tests and then all ideas tests**

Run: `python -m unittest tests.test_ideas`

Expected: PASS.

### Task 2: Signal, event and direction model

**Files:**
- Modify: `scriptor/idea_engine.py`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- Produces stable `sig_`, `evt_`, `macro_` and `dir_` IDs plus demand, competition, saturation and recommended count.
- Consumes donor/YouTube row dictionaries and manual directions.

- [ ] **Step 1: Write failing tests for clustered event records and potential**

```python
def test_similar_signals_cluster_and_hot_saturated_angle_is_warned(self):
    events = idea_engine.cluster_events([SIGNAL_A, SIGNAL_B])
    assessment = idea_engine.assess_direction(events[0], recent_items=[ITEM_WITH_SAME_ANGLE])
    self.assertEqual(len(events), 1)
    self.assertGreater(assessment["demand_score"], 0)
    self.assertGreater(assessment["angle_saturation"], 0)
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_ideas.IdeaProductionEngineTests.test_similar_signals_cluster_and_hot_saturated_angle_is_warned`

Expected: failure because event clustering is missing.

- [ ] **Step 3: Implement deterministic extraction and assessment**

```python
def cluster_events(signals):
    # group by entity/action/object/geography token overlap and produce one event

def assess_direction(event, recent_items):
    # calculate demand, competition, angle saturation and high/medium/low potential
```

- [ ] **Step 4: Verify GREEN**

Run: `python -m unittest tests.test_ideas`

Expected: PASS.

### Task 3: Bridge persistence, migration and common source ingestion

**Files:**
- Modify: `scriptor/config.py`
- Modify: `scriptor/bridge.py`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- Adds `idea_raw_signals`, `idea_events`, `idea_directions`, `idea_production_items` and `idea_portfolio_summary` to `Settings` and snapshot.
- `ingest_idea_signals(settings, source, rows)` creates structured records while keeping current source commands and plan rows.

- [ ] **Step 1: Write failing migration and source tests**

```python
def test_legacy_results_are_projected_to_production_items(self):
    settings = Settings(idea_results=["Точный заголовок"], idea_result_sources={"Точный заголовок": "Направление"})
    bridge.ensure_idea_production_items(settings)
    self.assertEqual(settings.idea_production_items[0]["title"], "Точный заголовок")
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_ideas.IdeaDirectionHandoffTests.test_legacy_results_are_projected_to_production_items`

Expected: failure because migration adapter is absent.

- [ ] **Step 3: Persist records and route all discovery buttons through ingestion**

```python
def ingest_idea_signals(settings, source, rows):
    signals = [idea_engine.normalise_signal(source, row) for row in rows]
    settings.idea_raw_signals.extend(signals)
    settings.idea_events = idea_engine.cluster_events(settings.idea_raw_signals)
```

- [ ] **Step 4: Verify command and persistence tests**

Run: `python -m unittest tests.test_ideas`

Expected: PASS.

### Task 4: Topic → angle → title pipeline

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `scriptor/idea_engine.py`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- Replaces direct direction-to-title generation inside `_generate_for_vectors` with `generate_production_items`.
- Produces items only after topic, angle and final title validation.

- [ ] **Step 1: Write failing batch test**

```python
def test_generation_returns_deficit_instead_of_semantic_rewordings(self):
    items, summary = bridge.generate_production_items_for_plan(SETTINGS, PLAN_OF_FIVE, fake_candidates=REPEATED_TOPICS)
    self.assertLess(len(items), 20)
    self.assertGreater(summary["deficit"], 0)
    self.assertEqual(len({item["topic"] for item in items}), len(items))
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_ideas.IdeaProductionPipelineTests.test_generation_returns_deficit_instead_of_semantic_rewordings`

Expected: failure because the pipeline entry point is absent.

- [ ] **Step 3: Implement generation, retry and portfolio selection**

```python
def generate_production_items_for_plan(settings, plan, requirements=""):
    # topics → topic dedupe → angles → headline concepts → quality gates → portfolio selection
    # retain fewer than requested items when candidates are not independently scriptable
```

- [ ] **Step 4: Verify regression batch**

Run: `python -m unittest tests.test_ideas`

Expected: PASS with 5+ directions / 20+ candidates fixture.

### Task 5: Scenario contract and UI diagnostics

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `scriptor/session.py`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/footage.css`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- Scenario handoff persists `production_item` keyed by scenario title/index.
- Snapshot exposes portfolio summary and production item fields for simple row diagnostics.

- [ ] **Step 1: Write failing handoff test**

```python
def test_selected_idea_handoff_preserves_script_requirements(self):
    bridge.add_ideas_to_scenarios({"ideas": [ITEM["title"]]})
    self.assertEqual(settings.idea_scenario_context[ITEM["title"]]["script_requirements"], ITEM["script_requirements"])
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_ideas.IdeaProductionPipelineTests.test_selected_idea_handoff_preserves_script_requirements`

Expected: failure because handoff only saves a title string.

- [ ] **Step 3: Save scenario context and add compact UI indicators**

```tsx
<small>{item.recommended_count} рекомендовано · {item.trend_label}</small>
{item.duplicate_risk ? <small>Проверьте похожесть</small> : null}
```

- [ ] **Step 4: Verify UI and handoff**

Run: `python -m unittest tests.test_ideas && pnpm typecheck && pnpm verify:custom-direction-ui`

Expected: PASS.

### Task 6: End-to-end verification and release evidence

**Files:**
- Modify: `tests/test_ideas.py`
- Modify: `docs/superpowers/specs/2026-09-08-ideas-engine-production-design.md`

- [ ] **Step 1: Add button/state regression matrix tests**

```python
def test_manual_agent_reference_youtube_plan_generate_delete_and_reload_share_pipeline(self):
    # invoke each bridge command with controlled data and assert persisted projections
```

- [ ] **Step 2: Run full verification**

Run: `python -m unittest discover -s tests -p "test_*.py" && pnpm typecheck && pnpm verify:core-runtime`

Expected: all tests and contracts pass.

- [ ] **Step 3: Produce controlled OLD vs NEW report**

Use the regression fixture to report duplicate count, question ratio, abstract-title rejections and accepted production-item examples. Do not call the result done until all accepted titles have a valid script contract.

- [ ] **Step 4: Create the external review package and stop**

Create `IDEAS_ENGINE_REVIEW.md` at the project root from a real 20–30 item
batch. Include representative accepted strong/medium items, rejected candidates
and varied directions/angle families; do not hand-pick only the best output.
For every accepted item print direction, topic, angle, title, character count,
hook family, click/novelty/scriptability scores, compact supporting context,
script requirements, nearest duplicate and similarity. Include OLD RESULT,
NEW RESULT and explicit rejected reasons: duplicate, weak hook, vague, low
scriptability, >100 characters, too similar or factual support insufficient.
Stop after writing the package and wait for the user's external editorial
review before changing another FlowNews area or calling the first version
editorially accepted.
