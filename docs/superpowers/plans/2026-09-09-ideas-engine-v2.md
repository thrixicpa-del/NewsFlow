# Ideas Engine V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Ideas flow produce evidence-aware, creative and
non-duplicative ProductionItems for a Russian-speaking CIS audience.

**Architecture:** `scriptor/idea_engine.py` owns pure framing, audience,
score, duplicate and portfolio decisions. `scriptor/bridge.py` uses those
decisions for both agent and ChatGPT generation, persists them through
`Settings`, exposes them to the existing UI, and hands the whole item to the
scenario generator.

**Tech Stack:** Python 3.12, unittest, JSON-safe Settings data, React/
TypeScript/Electron.

**Spec:** `docs/superpowers/specs/2026-09-09-ideas-engine-v2-design.md`

## Global Constraints

- Keep `RAW SIGNAL → EVENT → MACRO EVENT → DIRECTION → TOPIC → ANGLE → TITLE → PRODUCTION ITEM`.
- Change only Ideas/Topic Planning and its direct scenario hand-off.
- Editorial is the default; hypothetical must be visibly uncertain in data,
  title and script contract.
- Title length is `len(title) <= 100`, never model-reported or mechanically truncated.
- Preserve legacy title-only project data as explicitly marked legacy data.
- Return shortages rather than create paraphrased filler.
- Do not work on another NewsFlow subsystem after `IDEAS_ENGINE_REVIEW_V2.md`.

---

### Task 1: V2 framing and quality contracts

**Files:**
- Modify: `scriptor/idea_engine.py`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- Produces `validate_framing`, `assess_cis_audience`, `score_production_item`
  and V2-shaped records from `build_production_item(seed, title, events)`.
- Consumes a JSON-safe seed, final title and source event dictionaries.

- [ ] **Step 1: Write the failing framing and title tests.**

```python
def test_hypothetical_requires_visible_uncertainty_and_forecast_contract(self):
    rejected = idea_engine.build_production_item(HYPOTHETICAL_SEED, "Москва нанесла новый удар", [EVENT])
    accepted = idea_engine.build_production_item(HYPOTHETICAL_SEED, "Что будет, если Москва решится на новый удар", [EVENT])
    self.assertIsNone(rejected)
    self.assertEqual(accepted["framing_type"], "HYPOTHETICAL")
    self.assertIn("сценарий является предположением", " ".join(accepted["script_requirements"]))

def test_editorial_keeps_event_but_allows_reasonable_amplification(self):
    item = idea_engine.build_production_item(EDITORIAL_SEED, "Трамп поднял ставки: мирная сделка может выйти боком Украине", [EVENT])
    self.assertEqual(item["framing_type"], "EDITORIAL")
    self.assertIn(item["factual_risk_score"], {"LOW", "MEDIUM", "HIGH"})
    self.assertGreater(item["creative_amplification_score"], 0)
```

- [ ] **Step 2: Run the focused tests and confirm RED.**

Run: `python -m unittest tests.test_ideas.IdeaProductionEngineTests.test_hypothetical_requires_visible_uncertainty_and_forecast_contract`

- [ ] **Step 3: Implement only the pure framing validation and score derivation.**

```python
def validate_framing(seed: dict, title: str, events: list[dict]) -> tuple[bool, str, list[str]]:
    # Return whether a candidate is valid, its factual-risk tier, and
    # framing-specific script requirements. Hypothetical titles need a marker.

def assess_cis_audience(seed: dict, events: list[dict]) -> dict:
    # Return numeric relevance/stakes plus a concise, evidence-aware reason.
```

- [ ] **Step 4: Run the focused and full ideas tests.**

Run: `python -m unittest tests.test_ideas`

### Task 2: Semantic duplicate and portfolio quality gate

**Files:**
- Modify: `scriptor/idea_engine.py`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- Produces enriched `select_production_portfolio(candidates, events,
  requested_count)` accepted/rejected output with duplicate diagnostics,
  diversity summary and shortage.

- [ ] **Step 1: Write failing regression tests for paraphrases and diversity.**

```python
def test_same_event_same_information_payload_is_rejected_even_when_words_differ(self):
    accepted, report = idea_engine.select_production_portfolio(PARAPHRASED_CANDIDATES, EVENTS, 3)
    self.assertEqual(len(accepted), 1)
    self.assertEqual(report["rejected"][0]["reason"], "duplicate")

def test_portfolio_reports_shortage_instead_of_filler_and_calibrates_scores(self):
    accepted, report = idea_engine.select_production_portfolio(WEAK_BATCH, EVENTS, 10)
    self.assertLess(len(accepted), 10)
    self.assertGreater(report["deficit"], 0)
    self.assertLess(sum(item["novelty_score"] >= 90 for item in accepted), len(accepted))
```

- [ ] **Step 2: Run the two tests and confirm RED.**

Run: `python -m unittest tests.test_ideas.IdeaProductionEngineTests.test_same_event_same_information_payload_is_rejected_even_when_words_differ`

- [ ] **Step 3: Add deterministic comparison signatures and portfolio counters.**

```python
def production_similarity(first: dict, second: dict) -> float:
    # Combine event IDs, topic/information tokens, angle family, entities,
    # consequence and script-requirement overlap.

def portfolio_diversity(items: list[dict]) -> dict:
    # Count macro events, entities, geography, topic/angle/hook families and framing types.
```

- [ ] **Step 4: Run all Ideas tests.**

Run: `python -m unittest tests.test_ideas`

### Task 3: Structured generation and persistence migration

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `scriptor/config.py`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- `build_generated_production_items` and `_generate_for_vectors` preserve
  framing and all structured candidates through Settings.
- `ensure_idea_production_items` migrates legacy rows without treating them as
  V2-approved items.

- [ ] **Step 1: Write failing bridge and migration tests.**

```python
def test_generated_candidate_preserves_full_v2_context_on_reload(self):
    snapshot = bridge.generate_ideas({"topics": ["Переговоры"], "onlyRequested": True})
    item = snapshot["ideaProductionItems"][0]
    self.assertIn("cis_audience_relevance_score", item)
    self.assertIn("framing_type", item)
    self.assertEqual(bridge.snapshot()["ideaProductionItems"][0]["title"], item["title"])

def test_legacy_title_migration_is_visible_but_not_v2_validated(self):
    # Build legacy settings and assert legacy=True plus explicit unknown scores.
```

- [ ] **Step 2: Run the tests and confirm RED.**

Run: `python -m unittest tests.test_ideas.IdeaDirectionHandoffTests.test_generated_candidate_preserves_full_v2_context_on_reload`

- [ ] **Step 3: Extend parser/prompt/bridge state and migration.**

```python
def _title_generation_prompt(...):
    # Request topic, angle, framing_type, information payload and script requirements.

def build_generated_production_items(...):
    # Carry model metadata to pure V2 validation; persist rejected diagnostics.
```

- [ ] **Step 4: Run full Python regression.**

Run: `python -m unittest discover -s tests -p "test_*.py"`

### Task 4: Scenario handoff and Ideas diagnostics UI

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/*.css`
- Modify: `tests/test_ideas.py`

**Interfaces:**
- `production_item_prompt(item)` includes the framing-aware script contract.
- Snapshot and UI show accepted/rejected diagnostic fields without changing
  existing command names or hiding legacy results.

- [ ] **Step 1: Write the failing scenario and snapshot tests.**

```python
def test_hypothetical_scenario_prompt_prohibits_reporting_forecast_as_fact(self):
    prompt = bridge.production_item_prompt(HYPOTHETICAL_ITEM)
    self.assertIn("предположением", prompt)
    self.assertIn("не выдавай прогноз за уже произошедшее событие", prompt)
```

- [ ] **Step 2: Run and confirm RED.**

Run: `python -m unittest tests.test_ideas.IdeaDirectionHandoffTests.test_hypothetical_scenario_prompt_prohibits_reporting_forecast_as_fact`

- [ ] **Step 3: Implement compact diagnostics and framing-aware writer context.**

```tsx
<small>{item.framingType} · СНГ: {item.cisAudienceRelevanceScore} · клик: {item.clickScore}</small>
<small>Риск фактичности: {item.factualRiskScore}</small>
```

- [ ] **Step 4: Verify bridge and UI contracts.**

Run: `python -m unittest tests.test_ideas && pnpm typecheck && pnpm verify:custom-direction-ui`

### Task 5: Real regression batch and external review

**Files:**
- Create: `IDEAS_ENGINE_REVIEW_V2.md`
- Modify: `tests/test_ideas.py`

- [ ] **Step 1: Add an end-to-end controlled regression fixture.**

```python
def test_v2_batch_has_contextual_framing_and_no_synthetic_filler(self):
    items, report = idea_engine.select_production_portfolio(REALISTIC_BATCH, EVENTS, 30)
    self.assertTrue(all(item["char_count"] <= 100 for item in items))
    self.assertTrue(all(item["why_cis_audience_cares"] for item in items))
    self.assertEqual(report["accepted"] + report["deficit"], report["requested"])
```

- [ ] **Step 2: Run all Python/UI checks.**

Run: `python -m unittest discover -s tests -p "test_*.py"`

Run: `pnpm typecheck; pnpm build:web; pnpm verify:custom-direction-ui`

- [ ] **Step 3: Run a live representative batch and produce the review.**

Include at least 30 generated candidates across accepted, rejected and
hypothetical groups. Every accepted record lists all V2 fields from the spec;
rejected records list a concrete reason. Include OLD RESULT versus NEW RESULT
on comparable input and do not cherry-pick only strong results.

- [ ] **Step 4: Stop for external review.**

Do not modify another FlowNews subsystem after `IDEAS_ENGINE_REVIEW_V2.md` is
created.
