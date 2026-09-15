# YouTube Studio Engagement Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically schedule a linked Community post, cards, and an end screen for each uploaded scheduled YouTube video using its dedicated NewsFlow Chrome profile.

**Architecture:** Keep selection and persisted state in pure local modules. A browser adapter owns only Studio UI operations, receives a channel-owned profile directory and an idempotent task record, and saves a result after every atomic Studio step. The existing API upload path enqueues the automation after receiving the real video ID.

**Tech Stack:** Python 3.12, Playwright sync API, existing NewsFlow Settings/bridge command dispatcher, unittest, React/TypeScript snapshot types.

**Spec:** `docs/superpowers/specs/2026-09-01-youtube-posts-cards-end-screens-design.md`

## Global Constraints

- Use only `YouTubeChannelProfiles/<profile_id>` derived by `_youtube_channel_profile_dir`; never copy or inspect cookies, passwords, or sessions.
- One active Studio worker per profile; browser stays open until the active atomic task completes.
- A repeat run must not duplicate a post, card, or end-screen element.
- Community post text is the SEO description without hashtags and is scheduled at the exact video `publishAt`.
- Cards are at 35% and 65%, never in the final 20 seconds; end screen starts 20 seconds before the end for videos at least 25 seconds long.
- The repository has no `.git`; verify changes but do not create commit steps.

---

### Task 1: Add pure engagement policy and idempotent task records

**Files:**
- Create: `scriptor/youtube_engagement.py`
- Modify: `scriptor/youtube_publisher.py: PublicationJob and publication_job_record`
- Test: `tests/test_youtube_engagement.py`

**Interfaces:**
- Produces `build_engagement_plan(job: Mapping[str, object], catalog: Sequence[Mapping[str, object]], playlists: Sequence[Mapping[str, object]]) -> dict`.
- Produces `new_engagement_state(job_id: str, channel_id: str) -> dict`, `transition_engagement_step(state: dict, step: str, status: str, **fields) -> dict`, and `is_terminal(state: Mapping[str, object]) -> bool`.
- Consumes persisted job fields `id`, `channelId`, `videoId`, `videoUrl`, `publishAt`, `durationSeconds`, `seoDescription`.

- [ ] **Step 1: Write the failing policy tests**

```python
def test_plan_uses_two_previous_public_videos_and_a_twenty_second_end_screen():
    plan = build_engagement_plan(
        {"id": "new", "channelId": "channel-a", "videoId": "current", "durationSeconds": 600},
        [
            {"videoId": "current", "channelId": "channel-a", "privacyStatus": "public", "publishedAt": "2026-09-01T10:00:00+00:00"},
            {"videoId": "related", "channelId": "channel-a", "privacyStatus": "public", "publishedAt": "2026-08-31T10:00:00+00:00", "score": 0.9},
            {"videoId": "latest", "channelId": "channel-a", "privacyStatus": "public", "publishedAt": "2026-08-30T10:00:00+00:00", "score": 0.1},
        ], [],
    )
    assert [card["atSeconds"] for card in plan["cards"]] == [210, 390]
    assert [card["videoId"] for card in plan["cards"]] == ["related", "latest"]
    assert plan["endScreen"]["startSeconds"] == 580

def test_state_transition_refuses_terminal_step_regression():
    state = transition_engagement_step(new_engagement_state("job", "channel"), "post", "scheduled")
    with pytest.raises(ValueError, match="заверш"):
        transition_engagement_step(state, "post", "pending")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3 -m unittest tests.test_youtube_engagement -v`

Expected: FAIL because `scriptor.youtube_engagement` does not exist.

- [ ] **Step 3: Implement the minimal pure planner**

```python
def build_engagement_plan(job, catalog, playlists):
    duration = float(job.get("durationSeconds") or 0)
    eligible = [item for item in catalog if item.get("channelId") == job.get("channelId")
                and item.get("privacyStatus") == "public" and item.get("videoId") != job.get("videoId")]
    eligible.sort(key=lambda item: (-float(item.get("score", 0)), str(item.get("publishedAt", ""))), reverse=False)
    cards = [{"videoId": item["videoId"], "atSeconds": round(duration * ratio)}
             for ratio, item in zip((.35, .65), eligible[:2])]
    end_screen = {"status": "skipped", "reason": "Видео короче 25 секунд"} if duration < 25 else {
        "startSeconds": round(duration - 20), "items": []
    }
    return {"cards": cards, "endScreen": end_screen}
```

Implement explicit state records for `post`, `cards`, and `endScreen`, with statuses `pending`, `running`, `scheduled`, `done`, `failed`, `skipped`; retain only safe error strings and timestamps.

- [ ] **Step 4: Run the policy tests to verify they pass**

Run: `py -3 -m unittest tests.test_youtube_engagement tests.test_youtube_publisher -v`

Expected: PASS.

### Task 2: Persist per-channel automation policies and expose task state

**Files:**
- Modify: `scriptor/config.py: Settings, load_settings, save_settings`
- Modify: `scriptor/bridge.py: snapshot and publication job helpers`
- Test: `tests/test_youtube_engagement.py`

**Interfaces:**
- Adds `Settings.youtube_engagement_policies: dict[str, dict]` and `Settings.youtube_engagement_tasks: dict[str, dict]`.
- Snapshot job includes `post` and `engagement` without OAuth token, browser profile contents, or cookie values.
- Produces bridge command `save-channel-engagement-policy(payload: dict) -> dict`.

- [ ] **Step 1: Write failing persistence and redaction tests**

```python
def test_engagement_policy_round_trips_and_snapshot_redacts_browser_data():
    settings = Settings(youtube_engagement_policies={"profile-a": {"posts": True, "cards": True}})
    save_settings(settings)
    restored = load_settings()
    assert restored.youtube_engagement_policies["profile-a"]["posts"] is True
    payload = bridge.snapshot()
    assert "cookies" not in json.dumps(payload).lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3 -m unittest tests.test_youtube_engagement.EngagementPersistenceTests -v`

Expected: FAIL because the Settings fields and bridge command do not exist.

- [ ] **Step 3: Add Settings defaults and validation**

Add normalized policy defaults `{posts: True, cards: True, endScreen: True}` per profile. Save a bounded task map keyed by job ID; reject policy updates for unknown profiles. Add `engagement` to `snapshot()["publication"]["jobs"]` with only task status, selected IDs, timestamps, and error messages.

- [ ] **Step 4: Run persistence and bridge tests**

Run: `py -3 -m unittest tests.test_youtube_engagement tests.test_youtube_publisher -v`

Expected: PASS.

### Task 3: Implement the isolated YouTube Studio browser adapter

**Files:**
- Create: `scriptor/youtube_studio_automation.py`
- Modify: `scriptor/bridge.py: _youtube_channel_profile_dir and publication worker integration`
- Test: `tests/test_youtube_studio_automation.py`

**Interfaces:**
- Defines `StudioPage` protocol with `open_channel`, `schedule_post`, `set_cards`, and `set_end_screen` methods.
- Defines `YouTubeStudioAutomation(profile_dir: Path, expected_channel_id: str)` and `run_engagement_task(job: dict, task: dict, plan: dict) -> dict`.
- `run_engagement_task` returns a new task record after each safe step, never raw Playwright objects.

- [ ] **Step 1: Write a fake-page contract test**

```python
def test_runner_records_post_before_cards_and_resumes_after_post():
    page = FakeStudioPage(channel_id="UC-a")
    runner = YouTubeStudioAutomation(Path("C:/profiles/a"), "UC-a", page_factory=lambda _: page)
    result = runner.run_engagement_task(job_record(), new_engagement_state("job", "profile-a"), engagement_plan())
    assert page.calls == ["schedule_post", "set_cards", "set_end_screen"]
    assert result["post"]["status"] == "scheduled"
    resumed = runner.run_engagement_task(job_record(), result, engagement_plan())
    assert page.calls == ["schedule_post", "set_cards", "set_end_screen"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3 -m unittest tests.test_youtube_studio_automation -v`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Build the adapter around one persistent context**

Reuse the project pattern in `scriptor/voicer.py`: `sync_playwright().start()` plus `launch_persistent_context(str(profile_dir), executable_path=str(chrome_path()), headless=False)`. Validate the current Studio channel ID before every mutating step. Map login/channel mismatch/UI-selector failure into persisted `failed` state; always close the context only after the atomic current step returns.

Implement the real page adapter with page-visible Studio controls only. Do not inspect browser storage. Schedule the post by selecting the exact job video, its cleaned text, and the existing `publishAt`; record the post URL when Studio provides it. Make cards/end-screen operations explicit, selector-scoped and independently retryable.

- [ ] **Step 4: Run fake-page tests**

Run: `py -3 -m unittest tests.test_youtube_studio_automation tests.test_youtube_engagement -v`

Expected: PASS.

### Task 4: Queue engagement work after successful API upload

**Files:**
- Modify: `scriptor/bridge.py: upload_publication_jobs and command dispatcher`
- Modify: `scriptor/youtube_publisher.py: build_linked_community_post`
- Test: `tests/test_youtube_publisher.py`, `tests/test_youtube_engagement.py`

**Interfaces:**
- Adds bridge command `run-publication-engagement(payload: dict) -> dict` and `retry-publication-engagement(payload: dict) -> dict`.
- Successful upload initializes `post.status == "pending"` and `engagement` task state when the assigned channel policy enables automation.

- [ ] **Step 1: Write a failing upload-to-engagement test**

```python
def test_successful_upload_enqueues_automatic_post_without_manual_confirmation():
    result = bridge.upload_publication_jobs({"jobIds": ["job-a"]})
    job = result["publication"]["jobs"][0]
    assert job["post"]["status"] == "pending"
    assert job["post"]["requiresManualConfirmation"] is False
    assert job["engagement"]["cards"]["status"] == "pending"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3 -m unittest tests.test_youtube_publisher.PublicationJobTests.test_successful_upload_enqueues_automatic_post_without_manual_confirmation -v`

Expected: FAIL because upload produces only a manually-confirmed prepared post.

- [ ] **Step 3: Enqueue and execute with per-profile serialization**

After `upload_private_video` returns, retain the real `videoId` and `videoUrl`, build the cleaned post record with `pending` status, create the engagement task, persist first, then dispatch `run_publication_engagement`. Use one `threading.Lock` per profile ID. Retry commands must continue only steps not already terminal.

- [ ] **Step 4: Run upload integration tests**

Run: `py -3 -m unittest tests.test_youtube_publisher tests.test_youtube_engagement tests.test_youtube_studio_automation -v`

Expected: PASS.

### Task 5: Show automation status and recovery actions in publication UI

**Files:**
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx: page union, navigation, PublicationDashboard`
- Modify: `studio-ui-remotion-verify/src/ui/publication-delivery.css`
- Test: `studio-ui-remotion-verify/src/ui/App.test.tsx` (create if project test runner exists; otherwise browser smoke checklist in `tests/manual-ui-checks.md`)

**Interfaces:**
- Job `post` type includes statuses `pending | running | scheduled | failed | skipped`.
- Job `engagement` type exposes `cards` and `endScreen` status/error safely.

- [ ] **Step 1: Add a failing UI state test or manual checklist case**

```tsx
render(<PublicationDashboard data={snapshotWithFailedPost} command={command} />)
expect(screen.getByText("Пост: нужна сессия")).toBeVisible()
expect(screen.getByRole("button", {name: "Повторить неудачные"})).toBeEnabled()
```

- [ ] **Step 2: Run the selected test/checklist to verify the missing state**

Run: `npm test -- --runInBand` from `studio-ui-remotion-verify`, or record the absent UI state in `tests/manual-ui-checks.md` if no test runner is configured.

Expected: FAIL or missing behavior.

- [ ] **Step 3: Render three compact status chips and recovery controls**

Show `Пост`, `Подсказки`, and `Конечная заставка` per job; use text plus semantic color. Add a separate `Автоправила` sidebar route for per-channel post/card/end-screen toggles and its recent task log. Wire `Повторить неудачные`, `Открыть профиль канала`, and policy toggles to the bridge commands. Do not expose browser profile paths.

- [ ] **Step 4: Verify UI and Python regression suites**

Run: `py -3 -m unittest tests.test_youtube_publisher tests.test_youtube_engagement tests.test_youtube_studio_automation -v`

Expected: PASS. Run the configured frontend build/test command and verify a failed task, successful task, and disabled policy visually.
