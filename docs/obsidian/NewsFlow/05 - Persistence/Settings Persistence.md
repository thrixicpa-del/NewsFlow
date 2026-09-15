# Settings Persistence

**Canonical root:** `%LOCALAPPDATA%\\NewsFlow` via `scriptor.config.app_data_root()`.

`Settings` currently owns application preferences, provider selection and protected credentials, OAuth/channel data, folders, topic/scenario/ProductionItem state, voice jobs and MP3 mappings, cover settings/queues/library links, footage configuration, montage configuration and outputs, SEO/tags, and publication V2 records.

Existing positive controls are a settings write lock, atomic replacement, pre-write snapshots, queue/status merges and a last-known-good copy. Two root causes are open:

1. `load_settings()` converts a JSON read exception to an empty dictionary and later catches schema errors by returning a default `Settings`. A subsequent ordinary save can replace recoverable user state.
2. `bridge.snapshot()` is a UI read path but invokes recovery/migration/normalization functions and calls `save_settings()`.

## Light implementation record — 2026-09-11

- **NF-L-001 fixed:** `SettingsFileCorruptError` now rejects unreadable/non-object settings in both `load_settings()` and `save_settings()`. The raw original remains in place; it cannot be overwritten by an empty/default Settings object.
- **NF-L-002 fixed:** `snapshot()` is now a projection-only route: it does not save Settings, run migrations, recover legacy queue rows, create a montage project folder or rewrite stale footage-index status. The explicit `reconcile-runtime-state` bridge command owns bounded recovery persistence.
- Automated evidence: isolated `CorruptSettingsSafetyTests` and `SnapshotReadSafetyTests`, then 94 persistence/channel/montage/publication regression tests passed.

- **NF-L-006 fixed:** scenario requests and durable session rows now retain the immutable `production_item_id` where present. Script deletion merges bounded `deleted_scenario_production_ids`; backup recovery rejects that ID even if the historical title was renamed. Pre-ID sessions retain a title tombstone only as a legacy compatibility guard. Regression: `ScenarioDeletionRecoveryTests`.
- **NF-L-007 fixed:** Topic deletion merges bounded `idea_deleted_production_ids`. `load_settings()` immediately projects stale tombstoned rows out of `idea_production_items` and its legacy title projections without writing; the next explicit save compacts them. Regression: `IdeaPersistenceTests`.

No production data was reset or migrated in place. These protections operate on the existing canonical storage and are covered with isolated temporary-state tests.
