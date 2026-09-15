# Topic Engine

## Active Light path

`Ideas → generate-ideas → bridge.generate_ideas → _generate_for_vectors → select_idea_title_candidates → build_generated_production_items → idea_engine.select_production_portfolio → Settings.idea_*`.

The model may propose candidates, but title acceptance is Python-owned. `valid_idea_title()` normalizes whitespace/quotes and rejects empty/short, more-than-100-character, unresolved-template, all-caps, repeated-punctuation and generic non-story titles. `select_idea_title_candidates()` then checks the bounded recent title memory for exact, opening and semantic duplicates before the production engine validates event context, entities/action/object, framing and scriptability.

## Durable identity and deletion

An approved topic is a ProductionItem with a stable `id`, event/context fields and a script contract. `idea_deleted_production_ids` is authoritative over stale Settings rows and legacy title projections; loading projects deleted items out without writing. No generated candidate can reactivate a deleted ProductionItem.

## Regression evidence — 2026-09-11

- `test_title_validation_rejects_a_generic_world_crisis_without_a_story`
- `test_title_validation_rejects_long_caps_and_unfinished_templates`
- `test_candidate_selection_skips_recent_opening_and_keeps_metadata`
- Production-engine action/event, duplicate and deleted-ProductionItem cases in `tests.test_ideas`.

The active behavior is source/test verified only. No external idea-provider request was run for this Light phase.
