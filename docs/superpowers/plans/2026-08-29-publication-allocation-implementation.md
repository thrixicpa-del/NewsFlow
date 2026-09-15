# Publication allocation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent, operator-controlled constructor that distributes ready NewsFlow videos among YouTube channels using the 3/2/1 rules, duration ranges, analytics signals, and explicit manual overrides.

**Architecture:** Keep allocation rules and calculations in a pure Python module so recommendations and assignments are deterministic and fully unit-testable. Store JSON-safe profiles, presets, assignments, and production-reset state in `Settings`; `bridge.py` validates commands and persists changes. Extend the Electron publication screen and idea-generation header to show counters and permit explicit refresh, apply, and manual edits.

**Tech Stack:** Python 3.12, dataclasses, `unittest`, Electron/React/TypeScript, existing NewsFlow desktop bridge.

**Spec:** `docs/superpowers/specs/2026-08-29-publication-allocation-design.md`

## Global constraints

- A monetized channel receives a recommended quota of exactly **3** videos per cycle.
- A non-monetized channel with a factual growth signal receives **2**; an ordinary/new channel receives **1**.
- A manually locked quota is never changed by refresh or apply-recommendations commands.
- Recommendations never silently move already assigned videos; assignment is an explicit command.
- A video without a measured duration is not auto-assigned and exposes its blocking reason.
- New Issue / Clear Production Queue deletes production metadata only; it never removes physical files, channels, OAuth tokens, API keys, analytics history, roles, or presets.
- OAuth tokens and API keys remain protected by the existing settings encryption path and must not be returned in snapshots.

---

### Task 1: Add pure allocation domain and duration metadata

**Files:**
- Create: `scriptor/youtube_allocation.py`
- Modify: `scriptor/youtube_publisher.py:22-280`
- Test: `tests/test_youtube_publisher.py`

**Interfaces:**
- Produces `ChannelAllocationProfile`, `AllocationSummary`, `recommend_quota()`, `build_allocation_summary()`, and `allocate_ready_jobs()` for bridge commands.
- Extends `PublicationJob` and `publication_job_record()` with `duration_seconds: float | None`, exported as `durationSeconds`.
- Consumes only normalized dictionaries and `PublicationJob` records; no Google or filesystem calls occur in `youtube_allocation.py`.

- [ ] **Step 1: Write the failing allocation tests**

```python
from scriptor.youtube_allocation import build_allocation_summary, recommend_quota

def test_recommendation_prioritises_monetisation_growth_and_default():
    assert recommend_quota({"monetized": True, "growthSignal": True}) == 3
    assert recommend_quota({"monetized": False, "growthSignal": True}) == 2
    assert recommend_quota({"monetized": False, "growthSignal": False}) == 1

def test_locked_quota_is_preserved_and_missing_duration_is_not_assigned():
    channels = [{"id": "a", "monetized": True, "quota": 4, "quotaLocked": True,
                 "minDurationSeconds": 600, "maxDurationSeconds": 1800}]
    jobs = [{"id": "known", "durationSeconds": 720, "status": "ready"},
            {"id": "unknown", "durationSeconds": None, "status": "ready"}]
    summary = build_allocation_summary(channels, jobs)
    assert summary["channels"][0]["recommendedQuota"] == 4
    assert summary["missingDurationJobIds"] == ["unknown"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests.test_recommendation_prioritises_monetisation_growth_and_default tests.test_youtube_publisher.PublicationJobTests.test_locked_quota_is_preserved_and_missing_duration_is_not_assigned -v`

Expected: FAIL because `scriptor.youtube_allocation` does not exist.

- [ ] **Step 3: Implement minimal allocation primitives and duration serialization**

```python
def recommend_quota(profile: Mapping[str, object]) -> int:
    if bool(profile.get("quotaLocked")):
        return max(0, int(profile.get("quota") or 0))
    if bool(profile.get("monetized")):
        return 3
    if bool(profile.get("growthSignal")):
        return 2
    return 1

def duration_matches(job: Mapping[str, object], profile: Mapping[str, object]) -> bool:
    duration = job.get("durationSeconds")
    return isinstance(duration, (int, float)) and float(profile["minDurationSeconds"]) <= duration <= float(profile["maxDurationSeconds"])
```

Add `duration_seconds` to `PublicationJob`, pass it through `create_publication_job()`, serialize it as `durationSeconds`, and read rendered MP4 duration with existing `probe_media_duration(Path(video_path))`. Catch only media-probe errors at this boundary and preserve `None`; never invent a duration.

- [ ] **Step 4: Run focused tests to verify it passes**

Run: `python -m unittest tests.test_youtube_publisher -v`

Expected: PASS, including existing publication and OAuth tests.

- [ ] **Step 5: Commit**

```powershell
git add scriptor/youtube_allocation.py scriptor/youtube_publisher.py tests/test_youtube_publisher.py
git commit -m "feat: add deterministic publication allocation rules"
```

### Task 2: Persist allocation profiles, presets, and safe production reset

**Files:**
- Modify: `scriptor/config.py:318-337, 680-880`
- Modify: `scriptor/bridge.py:7300-7600, 8260-8290`
- Test: `tests/test_youtube_publisher.py`

**Interfaces:**
- Consumes `build_allocation_summary()` and `allocate_ready_jobs()` from Task 1.
- Produces bridge commands `refresh-publication-allocation`, `apply-publication-recommendations`, `save-publication-allocation-preset`, `assign-publication-jobs`, `update-channel-allocation`, and `clear-production-queue`.
- Adds `youtube_publication_allocation_profiles`, `youtube_publication_allocation_presets`, and `youtube_publication_allocation_updated_at` to `Settings`.

- [ ] **Step 1: Write failing persistence and reset tests**

```python
def test_allocation_profiles_and_presets_survive_restart():
    settings = Settings(
        youtube_publication_allocation_profiles=[{"channelId": "a", "quota": 3, "quotaLocked": True}],
        youtube_publication_allocation_presets=[{"name": "Основной", "channelIds": ["a"]}],
    )
    save_settings(settings)
    restored = load_settings()
    self.assertEqual(restored.youtube_publication_allocation_profiles[0]["quota"], 3)
    self.assertEqual(restored.youtube_publication_allocation_presets[0]["name"], "Основной")

def test_clear_production_queue_preserves_accounts_secrets_analytics_and_presets():
    bridge.clear_production_queue({"confirmed": True})
    self.assertEqual(settings.analytics_channels, original_channels)
    self.assertEqual(settings.youtube_oauth_tokens, original_tokens)
    self.assertEqual(settings.youtube_publication_allocation_presets, original_presets)
    self.assertEqual(settings.youtube_publication_jobs, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_youtube_publisher.PublicationJobTests.test_allocation_profiles_and_presets_survive_restart tests.test_youtube_publisher.PublicationJobTests.test_clear_production_queue_preserves_accounts_secrets_analytics_and_presets -v`

Expected: FAIL because settings fields and bridge commands are missing.

- [ ] **Step 3: Implement storage and explicit bridge commands**

```python
@dataclass
class Settings:
    youtube_publication_allocation_profiles: list[dict] = field(default_factory=list)
    youtube_publication_allocation_presets: list[dict] = field(default_factory=list)
    youtube_publication_allocation_updated_at: str = ""

def clear_production_queue(payload: dict) -> dict:
    if payload.get("confirmed") is not True:
        raise ValueError("Подтвердите очистку производственной очереди.")
    settings.youtube_publication_jobs = []
    settings.youtube_publication_activity = []
    settings.montage_task_statuses = {}
    # retain analytics_channels, youtube_oauth_tokens, youtube_api_key,
    # youtube_analytics_metric_points, allocation profiles and presets
```

`refresh-publication-allocation` calculates growth only from two stored metric points for the same channel and preserves locked quotas. `apply-publication-recommendations` changes only unlocked profile quotas. `assign-publication-jobs` accepts explicit job IDs and channel IDs, assigns only duration-compatible ready jobs, returns skipped IDs/reasons, and never uploads or schedules a job. Add every mutation to the activity log.

- [ ] **Step 4: Run bridge and persistence tests**

Run: `python -m unittest tests.test_youtube_publisher -v`

Expected: PASS; settings restore allocation state and reset has no access to protected connection state.

- [ ] **Step 5: Commit**

```powershell
git add scriptor/config.py scriptor/bridge.py tests/test_youtube_publisher.py
git commit -m "feat: persist publication allocation and safe new issue reset"
```

### Task 3: Return typed allocation data to Electron and extend the publication UI

**Files:**
- Modify: `scriptor/bridge.py:780-850`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts:49-65`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx:1192-1500`
- Modify: `studio-ui-remotion-verify/src/ui/publication.css`
- Modify: `studio-ui-remotion-verify/src/ui/publication-scheduling.css`

**Interfaces:**
- Consumes `snapshot().publication.allocation` fields: `channels`, `counters`, `unassignedJobs`, `missingDurationJobIds`, `updatedAt`.
- Invokes the explicit bridge commands from Task 2 via `command(name, payload)`.
- Displays no OAuth token, API key, or credential file contents.

- [ ] **Step 1: Add the TypeScript contract**

```ts
allocation: {
  counters: { required: number; ready: number; assigned: number; missing: number; reserve: number };
  channels: Array<{ channelId: string; name: string; thumbnailUrl?: string; subscribers: string;
    monetized: boolean; growthSignal: boolean; recommendedQuota: number; quota: number;
    quotaLocked: boolean; minDurationSeconds: number; maxDurationSeconds: number; assignedJobIds: string[] }>;
  unassignedJobs: Array<{ id: string; title: string; durationSeconds?: number; thumbnailPath?: string; reason?: string }>;
  missingDurationJobIds: string[];
  updatedAt: string;
}
```

- [ ] **Step 2: Add constructor controls**

Render a `Конструктор выпуска` card above the existing timeline: five counter tiles, buttons `Обновить рекомендации`, `Применить рекомендации`, `Сохранить пресет`, and explicit `Распределить совместимые`. Render one row per channel with avatar, name, subscribers, monetization/growth badges, editable quota, lock checkbox, minimum/maximum duration inputs, and assigned videos. Render reserve jobs with thumbnail, title, formatted duration, plus an exact reason for missing duration or range mismatch.

- [ ] **Step 3: Wire explicit mutations and snapshot refresh**

```ts
await command('update-channel-allocation', { channelId, quota, quotaLocked, minDurationSeconds, maxDurationSeconds });
await command('refresh-publication-allocation', {});
await command('apply-publication-recommendations', {});
await command('assign-publication-jobs', { jobIds: selectedJobIds, channelIds: selectedChannelIds });
```

After each successful command, replace UI state from the returned snapshot. Disable only the action currently in progress; do not hide unrelated publication controls.

- [ ] **Step 4: Add safe New Issue action on the ideas page**

Show the allocation counter widget near generation controls. The `Новый выпуск / очистить производственную очередь` action shows a local confirm dialog naming only production metadata and explicitly says files, channels, OAuth, API keys, analytics, roles, and presets remain. On confirmation call `clear-production-queue` with `{ confirmed: true }`.

- [ ] **Step 5: Run TypeScript verification**

Run: `pnpm typecheck`

Expected: PASS with `NewsFlowSnapshot` and publication components typed.

- [ ] **Step 6: Commit**

```powershell
git add studio-ui-remotion-verify/src/desktop.d.ts studio-ui-remotion-verify/src/ui/App.tsx studio-ui-remotion-verify/src/ui/publication.css studio-ui-remotion-verify/src/ui/publication-scheduling.css scriptor/bridge.py
git commit -m "feat: add publication allocation constructor UI"
```

### Task 4: Verify end-to-end contracts and package the tested build

**Files:**
- Modify: `tests/test_youtube_publisher.py`
- Modify: `NewsFlowCore.spec`
- Modify: `studio-ui-remotion-verify/package.json`
- Create: `docs/verification/2026-08-29-publication-allocation.md`

**Interfaces:**
- Consumes the allocation bridge/API/UI contracts from Tasks 1–3.
- Produces the installer in `studio-ui-remotion-verify/release-<version>-publication-allocation/`.

- [ ] **Step 1: Add regression tests for every allocation branch**

```python
def test_auto_assignment_respects_quota_duration_and_keeps_overflow_in_reserve():
    result = allocate_ready_jobs(profiles, ready_jobs)
    self.assertEqual(result["counters"], {"required": 6, "ready": 8, "assigned": 6, "missing": 0, "reserve": 2})
    self.assertEqual(result["assignments"]["monetized"], ["long-1", "long-2", "long-3"])

def test_refresh_only_recommends_until_operator_applies():
    before = bridge.snapshot()["publication"]["allocation"]["channels"]
    bridge.refresh_publication_allocation({})
    self.assertEqual(bridge.snapshot()["publication"]["allocation"]["channels"], before)
```

- [ ] **Step 2: Run backend and UI checks**

Run: `python -m unittest tests.test_youtube_publisher -v`

Expected: PASS.

Run: `pnpm typecheck`

Expected: PASS.

- [ ] **Step 3: Build the core and portable Electron release**

Run: `python -m PyInstaller NewsFlowCore.spec --noconfirm`

Expected: a core executable containing `scriptor.youtube_allocation` and existing Google-client dependencies.

Run: `pnpm package:preview`

Expected: a versioned installer/release folder with the new core runtime.

- [ ] **Step 4: Run portable runtime checks and record evidence**

Run: `pnpm verify:portable; node scripts/verify-core-runtime.mjs; node scripts/verify-remotion-runtime-contract.mjs`

Expected: all three checks exit 0.

Write commands, outputs, build path, and a manual UI checklist in `docs/verification/2026-08-29-publication-allocation.md`.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_youtube_publisher.py NewsFlowCore.spec studio-ui-remotion-verify/package.json docs/verification/2026-08-29-publication-allocation.md
git commit -m "test: verify publication allocation release"
```

