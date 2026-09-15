# Channel Research Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a channel-scoped public-source research workspace with isolated Chrome profiles, persistent queues, graceful controls, analysis results, and exports.

**Architecture:** A pure-Python `channel_research` module owns validation, queue state transitions, discovery normalization, result construction, and exports. `channel_research_browser` reuses the bundled Playwright pattern to open one queued public source in its channel's persistent Chrome profile and return public text/visual hints without reading browser secrets or interacting with external accounts. `bridge.py` is the only stateful desktop command boundary: it persists channel-scoped records in `Settings`, launches one background worker per selected profile, and returns redacted snapshots. React renders a dedicated page from those snapshots and invokes only bridge commands.

**Tech Stack:** Python 3.12, standard-library `urllib`/`xml.etree`/`html`, existing NewsFlow settings persistence and Windows Chrome launcher, Electron/React/TypeScript, Vitest/TypeScript compiler, Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-01-channel-research-agents-design.md`

## Global Constraints

- Use public search/feed data and operator-provided links only; do not implement automated engagement, cookie warming, publishing, comments, likes, subscriptions, or anti-fraud evasion.
- A channel profile ID owns exactly one Chrome profile, research queue, result set, and agent status; never copy browser data between profiles.
- OAuth tokens, cookies, passwords, and other secrets must never occur in research snapshots, exports, action results, or logs.
- `Стоп и показать результаты` dispatches no new work, lets already-started atomic steps reach a checkpoint, flushes state, and then exposes results.
- Persist after every terminal source transition. Restart recovery may resume only unfinished source tasks.
- This checkout is not a Git repository. Do not invent commits; record the changed-file list in the handoff instead.

---

## File structure

| File | Responsibility |
| --- | --- |
| `scriptor/channel_research.py` | Pure models, URL/TXT parsing, de-duplication, queue transition validation, public-feed parsing, compact analysis records, and CSV/JSON/Markdown serialization. |
| `scriptor/channel_research_browser.py` | One-source Playwright browser adapter bound to a NewsFlow channel profile; returns only public page text and visual hints. |
| `scriptor/config.py` | Persist channel-scoped research configuration, tasks, results, and statuses in `Settings`. |
| `scriptor/bridge.py` | Command handlers, safe snapshot projection, per-channel worker lifecycle, Chrome profile launching, durable state updates, and export file writing. |
| `tests/test_channel_research.py` | Unit tests for pure parsing, state transitions, imports, isolation, and export redaction. |
| `tests/test_youtube_publisher.py` | Bridge-level settings/snapshot tests alongside existing channel profile tests. |
| `studio-ui-remotion-verify/src/desktop.d.ts` | Typed snapshot and command response fields for research state. |
| `studio-ui-remotion-verify/src/ui/ChannelResearchDashboard.tsx` | New channel selector, source import/configuration, controls, queue status, results, exports, and delete confirmation. |
| `studio-ui-remotion-verify/src/ui/channel-research.css` | Scoped responsive styles for the research workspace. |
| `studio-ui-remotion-verify/src/ui/App.tsx` | New navigation route, snapshot defaults, and dashboard mounting only. |

### Task 1: Define pure research records, intake parsing, and redacted exports

**Files:**
- Create: `scriptor/channel_research.py`
- Test: `tests/test_channel_research.py`

**Interfaces:**
- Produces `normalize_source_url(value: str) -> str`, `parse_txt_sources(text: str) -> tuple[list[str], list[dict[str, str]]]`, `dedupe_sources(urls: list[str]) -> list[str]`.
- Produces `new_task(channel_id: str, url: str, origin: str) -> dict[str, object]`, `transition_task(task: dict[str, object], target: str, *, detail: str = "") -> dict[str, object]`.
- Produces `public_result(task: dict[str, object], *, title: str, summary: str, topic: str, hook: str, idea: str, publisher: str = "", published_at: str = "") -> dict[str, str]` and `serialize_results(results: list[dict[str, str]], format_name: str) -> tuple[str, str]`.
- Consumes only standard-library types. The projected records contain no credential, cookie, password, header, or browser-profile field.

- [ ] **Step 1: Write failing tests for valid imports, invalid lines, and de-duplication**

```python
from scriptor.channel_research import dedupe_sources, parse_txt_sources


def test_txt_import_normalizes_valid_http_lines_and_retains_line_errors():
    sources, errors = parse_txt_sources(
        "https://www.youtube.com/@news\\nnot a url\\nhttps://example.org/story\\n"
    )
    assert sources == ["https://www.youtube.com/@news", "https://example.org/story"]
    assert errors == [{"line": "2", "message": "Нужна HTTP(S)-ссылка"}]


def test_dedupe_sources_keeps_first_normalized_url_only():
    assert dedupe_sources([
        "https://example.org/story/",
        "https://example.org/story",
        "https://example.org/next",
    ]) == ["https://example.org/story", "https://example.org/next"]
```

- [ ] **Step 2: Run the focused tests and verify that they fail because the module does not exist**

Run: `py -3 -m unittest tests.test_channel_research -v`

Expected: import failure for `scriptor.channel_research`.

- [ ] **Step 3: Implement source normalization and TXT parsing**

```python
def normalize_source_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Нужна HTTP(S)-ссылка")
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.casefold(), path, parsed.query, ""))


def parse_txt_sources(text: str) -> tuple[list[str], list[dict[str, str]]]:
    sources, errors = [], []
    for number, raw in enumerate(str(text).splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            sources.append(normalize_source_url(raw))
        except ValueError as exc:
            errors.append({"line": str(number), "message": str(exc)})
    return dedupe_sources(sources), errors
```

- [ ] **Step 4: Add failing tests for legal transitions and redacted exports**

```python
from scriptor.channel_research import new_task, public_result, serialize_results, transition_task


def test_stop_transition_never_serializes_secret_browser_data():
    task = new_task("profile-a", "https://example.org/story", "txt")
    running = transition_task(task, "running")
    completed = transition_task(running, "completed")
    result = public_result(completed, title="Story", summary="Summary", topic="News", hook="Hook", idea="Idea")
    content_type, body = serialize_results([result], "json")
    assert content_type == "application/json"
    assert "profile-a" not in body
    assert "token" not in body.casefold()
    assert "cookie" not in body.casefold()
```

- [ ] **Step 5: Implement task transitions and the three export formats**

```python
TASK_STATES = {"waiting", "running", "paused", "stopping", "completed", "failed", "skipped"}
ALLOWED_TRANSITIONS = {
    "waiting": {"running", "paused", "skipped"},
    "running": {"paused", "stopping", "completed", "failed", "skipped"},
    "paused": {"waiting", "stopping"},
    "stopping": {"completed", "failed", "skipped"},
}

def transition_task(task: dict[str, object], target: str, *, detail: str = "") -> dict[str, object]:
    current = str(task.get("status", "waiting"))
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Недопустимый переход очереди: {current} → {target}")
    return {**task, "status": target, "detail": detail, "updatedAt": now_iso()}
```

Implement `serialize_results` with `csv.DictWriter`, `json.dumps(..., ensure_ascii=False, indent=2)`, and a Markdown table. Include only `title`, `url`, `publisher`, `publishedAt`, `topic`, `summary`, `hook`, `idea`, and `status`.

- [ ] **Step 6: Run pure-module tests and verify pass**

Run: `py -3 -m unittest tests.test_channel_research -v`

Expected: PASS for parsing, de-duplication, transitions, and redacted exports.

### Task 2: Persist channel-scoped configuration and recover queues safely

**Files:**
- Modify: `scriptor/config.py:246-350, 741-748, 931-938`
- Modify: `tests/test_channel_research.py`

**Interfaces:**
- Adds `Settings.channel_research: dict[str, dict] = field(default_factory=dict)`.
- Each key is a stable analytics-channel `profile_id`; each value has only `config`, `tasks`, `results`, `status`, and `updatedAt`.
- Produces `channel_research_state(settings: Settings, profile_id: str) -> dict` in `scriptor/channel_research.py`.

- [ ] **Step 1: Write a failing persistence/reload test**

```python
def test_research_state_survives_settings_reload_without_credentials(tmp_path, monkeypatch):
    settings = Settings()
    settings.channel_research["profile-a"] = {
        "config": {"queries": ["latest news"], "languages": ["ru"], "regions": ["BY"]},
        "tasks": [{"id": "task-a", "url": "https://example.org", "status": "waiting"}],
        "results": [],
        "status": {"state": "paused"},
        "updatedAt": "2026-09-01T10:00:00+00:00",
    }
    save_settings(settings)
    restored = load_settings()
    assert restored.channel_research["profile-a"]["status"]["state"] == "paused"
    assert "youtube_oauth_tokens" not in restored.channel_research["profile-a"]
```

- [ ] **Step 2: Run the persistence test and verify it fails because the field is absent**

Run: `py -3 -m unittest tests.test_channel_research.ChannelResearchPersistenceTests.test_research_state_survives_settings_reload_without_credentials -v`

Expected: FAIL with `AttributeError` for `channel_research`.

- [ ] **Step 3: Add the dataclass field and JSON round-trip**

```python
channel_research: dict[str, dict] = field(default_factory=dict)
```

Load only mapping values with string profile IDs; clamp each `tasks` and `results` list to 20,000 records; serialize as the public `channel_research` JSON field. Do not protect it with DPAPI because it deliberately contains no secrets.

- [ ] **Step 4: Add failing restart-recovery tests**

```python
def test_recovery_requeues_only_unfinished_tasks():
    state = {
        "tasks": [
            {"id": "one", "status": "running"},
            {"id": "two", "status": "completed"},
            {"id": "three", "status": "skipped"},
        ],
        "status": {"state": "running"},
    }
    recovered = recover_research_state(state)
    assert [item["status"] for item in recovered["tasks"]] == ["waiting", "completed", "skipped"]
    assert recovered["status"]["state"] == "paused"
```

- [ ] **Step 5: Implement recovery and unique default state**

```python
def channel_research_state(settings: Settings, profile_id: str) -> dict:
    return settings.channel_research.setdefault(profile_id, {
        "config": {"queries": [], "languages": ["ru", "en"], "regions": [], "manualUrls": []},
        "tasks": [], "results": [], "status": {"state": "idle", "processed": 0, "skipped": 0, "message": "Не запускался"},
        "updatedAt": now_iso(),
    })
```

Make `recover_research_state` convert `running` tasks to `waiting`, preserve terminal tasks, and set a formerly running agent to `paused` with a clear restart message.

- [ ] **Step 6: Run the persistence and recovery tests**

Run: `py -3 -m unittest tests.test_channel_research -v`

Expected: PASS.

### Task 3: Add safe bridge commands, worker lifecycle, and profile isolation

**Files:**
- Modify: `scriptor/bridge.py:689-1031, 2302-2425, 8600-8840`
- Modify: `scriptor/channel_research.py`
- Modify: `tests/test_youtube_publisher.py`
- Modify: `tests/test_channel_research.py`

**Interfaces:**
- Adds bridge commands: `save-channel-research-config`, `import-channel-research-txt`, `start-channel-research`, `pause-channel-research`, `resume-channel-research`, `stop-channel-research`, `open-channel-research-profile`, `export-channel-research-results`, and `clear-channel-research-results`.
- `start-channel-research(payload)` consumes `{indices: list[int], mode: "fast" | "deep"}`; every selected index maps to one profile ID.
- Worker helper `run_channel_research(profile_id: str, *, mode: str) -> None` reads fresh settings at each source checkpoint and owns no token material.
- Snapshot projects `research: { channels: [...] }` with aggregate-safe fields only.

- [ ] **Step 1: Write failing bridge tests for unique profile ownership and snapshot redaction**

```python
def test_added_channels_receive_independent_research_agents_and_chrome_profiles(tmp_path, monkeypatch):
    first = add_channel({"name": "First", "channel": ""})
    second = add_channel({"name": "Second", "channel": ""})
    snapshot_data = snapshot()
    profiles = [item["profile_id"] for item in load_settings().analytics_channels]
    research = snapshot_data["research"]["channels"]
    assert len(set(profiles)) == 2
    assert {item["channelId"] for item in research} == set(profiles)
    assert "token" not in json.dumps(research).casefold()
    assert "cookie" not in json.dumps(research).casefold()
```

- [ ] **Step 2: Run bridge tests and verify failure because the research snapshot/commands are absent**

Run: `py -3 -m unittest tests.test_channel_research tests.test_youtube_publisher.PublicationJobTests.test_adding_channel_creates_visible_profile_row_and_operation_result -v`

Expected: FAIL with missing `research` key or command implementation.

- [ ] **Step 3: Project safe research state into `snapshot()` and provision it on channel creation**

```python
def _research_snapshot_channels(settings: Settings) -> list[dict]:
    rows = []
    for channel in settings.analytics_channels:
        profile_id = str(channel.get("profile_id", "")).strip()
        state = channel_research_state(settings, profile_id)
        status = dict(state["status"])
        rows.append({
            "channelId": profile_id,
            "name": str(channel.get("name", "Канал")),
            "profileReady": bool(profile_id),
            "status": {key: status.get(key) for key in ("state", "processed", "skipped", "message", "updatedAt")},
            "config": public_research_config(state["config"]),
            "tasks": public_tasks(state["tasks"]),
            "results": public_results(state["results"]),
        })
    return rows
```

Call `channel_research_state` from `add_channel` after the profile ID is assigned. Keep research state when a token is reset; remove only that channel's research state when the analytics row is removed.

- [ ] **Step 4: Write failing tests for pause, graceful stop, and channel isolation**

```python
def test_stop_marks_agent_stopping_and_does_not_dispatch_next_channel_task(monkeypatch):
    seed_research_state("profile-a", [
        {"id": "a-one", "url": "https://a.example/one", "status": "running"},
        {"id": "a-two", "url": "https://a.example/two", "status": "waiting"},
    ])
    seed_research_state("profile-b", [{"id": "b-one", "url": "https://b.example/one", "status": "waiting"}])
    result = stop_channel_research({"indices": [0]})
    rows = result["research"]["channels"]
    assert rows[0]["status"]["state"] == "stopping"
    assert rows[0]["tasks"][1]["status"] == "waiting"
    assert rows[1]["tasks"][0]["status"] == "waiting"
```

- [ ] **Step 5: Implement lifecycle controls with one lock per profile**

```python
_CHANNEL_RESEARCH_LOCKS: dict[str, threading.Lock] = {}

def start_channel_research(payload: dict) -> dict:
    indices = _validated_channel_indices(payload)
    for index in indices:
        profile_id = _channel_profile_id(load_settings(), index)
        _start_research_worker(profile_id, mode=str(payload.get("mode", "fast")))
    return snapshot()

def stop_channel_research(payload: dict) -> dict:
    settings = load_settings()
    for index in _validated_channel_indices(payload):
        state = channel_research_state(settings, _channel_profile_id(settings, index))
        state["status"].update({"state": "stopping", "message": "Завершаем начатые источники"})
    save_settings(settings)
    return snapshot()
```

At each task boundary the worker reloads settings. It exits before dispatching a new task for `paused` or `stopping`; for `stopping` it saves `idle` only after the active task has reached `completed`, `failed`, or `skipped`. Use `open_analytics_channel`/`_youtube_channel_profile_dir` to implement `open-channel-research-profile`; it launches the existing profile directory with a supplied public URL or the neutral new-tab page, never reads its cookies.

- [ ] **Step 6: Register every command in the bridge dispatcher and test command names**

```python
elif command == "start-channel-research":
    result = start_channel_research(payload if isinstance(payload, dict) else {})
elif command == "pause-channel-research":
    result = pause_channel_research(payload if isinstance(payload, dict) else {})
elif command == "stop-channel-research":
    result = stop_channel_research(payload if isinstance(payload, dict) else {})
```

Register all nine commands, not only the three shown. Validate unavailable indices, empty source queues, and unsupported mode with Russian operator-facing errors.

- [ ] **Step 7: Run bridge regression tests**

Run: `py -3 -m unittest tests.test_channel_research tests.test_youtube_publisher tests.test_youtube_oauth_handoff -v`

Expected: PASS; existing OAuth profile behavior remains unchanged.

### Task 4: Implement public-source discovery and compact/deep analysis handoff

**Files:**
- Modify: `scriptor/channel_research.py`
- Create: `scriptor/channel_research_browser.py`
- Modify: `scriptor/bridge.py`
- Modify: `tests/test_channel_research.py`

**Interfaces:**
- Produces `discover_public_sources(query: str, *, language: str, region: str, limit: int) -> list[dict[str, str]]` using public feed/search adapters.
- Produces `compact_analysis(source: dict[str, str]) -> dict[str, str]` from public title, description, published time, and allowed caption text.
- Produces `enqueue_discovered_sources(settings: Settings, profile_id: str, sources: list[dict[str, str]], origin: str) -> int`.
- Deep analysis consumes only a selected existing result URL and an explicit caption/transcript/audio reference supplied by the operator or public source adapter.
- `inspect_source_in_channel_profile(profile_dir: Path, url: str) -> BrowserSourceEvidence` launches a Playwright persistent context for the supplied NewsFlow-owned profile, opens only `url`, returns public title/text/thumbnail hints, and closes its page.

- [ ] **Step 1: Write failing deterministic discovery-adapter tests using local XML fixtures**

```python
def test_google_news_feed_parser_returns_recent_article_without_network(monkeypatch):
    xml = """<rss><channel><item><title>Headline</title><link>https://example.org/story</link><pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
    monkeypatch.setattr(channel_research, "fetch_text", lambda url, **_: xml)
    items = discover_public_sources("news", language="ru", region="BY", limit=100)
    assert items == [{"url": "https://example.org/story", "title": "Headline", "publisher": "", "publishedAt": "2026-09-01T10:00:00+00:00", "sourceType": "news"}]
```

- [ ] **Step 2: Run adapter tests and verify failure before adapters exist**

Run: `py -3 -m unittest tests.test_channel_research.ChannelResearchDiscoveryTests -v`

Expected: FAIL with missing `discover_public_sources`.

- [ ] **Step 3: Implement bounded adapters and rate/concurrency configuration**

```python
def discover_public_sources(query: str, *, language: str, region: str, limit: int) -> list[dict[str, str]]:
    capped_limit = max(1, min(int(limit), 250))
    feeds = [google_news_rss_url(query, language, region), youtube_channel_or_search_feed_url(query)]
    return dedupe_source_records(item for feed in feeds for item in parse_public_feed(fetch_text(feed)))[:capped_limit]
```

Use finite request timeouts, explicit User-Agent, retry only transient network statuses once, and a per-agent configurable concurrency default of four. Never request a URL that was not returned by the feed, imported by the operator, or selected in the UI.

- [ ] **Step 4: Write failing analysis tests for concise public records and explicit deep promotion**

```python
def test_compact_analysis_does_not_require_browser_session_or_cookie():
    result = compact_analysis({"title": "Budget vote", "description": "Parliament votes today", "url": "https://example.org"})
    assert result["topic"]
    assert result["summary"]
    assert "cookie" not in json.dumps(result).casefold()


def test_deep_analysis_rejects_unselected_source():
    with self.assertRaisesRegex(ValueError, "Выберите результат"):
        promote_to_deep_analysis([], "https://example.org/video")
```

- [ ] **Step 4a: Write a failing browser-adapter isolation test with a fake Playwright context**

```python
def test_browser_adapter_opens_only_the_queued_url_in_the_supplied_profile(monkeypatch, tmp_path):
    observed = []
    monkeypatch.setattr(channel_research_browser, "launch_context", lambda profile: FakeContext(observed, profile))
    evidence = inspect_source_in_channel_profile(tmp_path / "profile-a", "https://example.org/story")
    assert observed == [(tmp_path / "profile-a", "https://example.org/story")]
    assert evidence.title == "Story"
    assert not hasattr(evidence, "cookies")
```

- [ ] **Step 5: Implement compact analysis and deep-promotion validation**

```python
def promote_to_deep_analysis(results: list[dict[str, str]], url: str) -> dict[str, str]:
    selected = next((item for item in results if item.get("url") == normalize_source_url(url)), None)
    if selected is None:
        raise ValueError("Выберите результат для глубокого анализа")
    return {**selected, "analysisMode": "deep", "status": "waiting"}
```

Use a deterministic extractive fallback for title/description/caption snippets. If no permitted text is available, return `skipped` with `Нет доступного текста для анализа` rather than inventing a plot.

Implement `channel_research_browser.py` by following the existing persistent-context ownership pattern in `scriptor/voicer.py`: create a Playwright context for the exact profile directory, call `page.goto(url, wait_until="domcontentloaded")`, collect `document.title`, visible `main`/`article` text capped at 20,000 characters, and one public OpenGraph image URL, then close the page and context. Reject non-HTTP(S) URLs and never call cookie, storage-state, click, keyboard, media-playback, advertisement, account, or recommendation APIs.

- [ ] **Step 6: Run discovery/analysis tests**

Run: `py -3 -m unittest tests.test_channel_research -v`

Expected: PASS with no live network dependency in tests.

### Task 5: Add typed desktop snapshot data and the research workspace UI

**Files:**
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Create: `studio-ui-remotion-verify/src/ui/ChannelResearchDashboard.tsx`
- Create: `studio-ui-remotion-verify/src/ui/channel-research.css`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx:1-75, 240-290, 360-470, 750-800`

**Interfaces:**
- Adds `ResearchChannelSnapshot`, `ResearchTaskSnapshot`, and `ResearchResultSnapshot` in `desktop.d.ts`.
- `ChannelResearchDashboard` accepts `{ data: AppSnapshot; command: CommandFunction }` and renders only safe snapshot fields.
- `App.tsx` adds the `channel-research` page and imports the new stylesheet/component.

- [ ] **Step 1: Write failing TypeScript fixture assertions for the new snapshot shape**

```ts
const researchChannel: ResearchChannelSnapshot = {
  channelId: "profile-a",
  name: "Взгляд Сверху",
  profileReady: true,
  status: { state: "paused", processed: 102, skipped: 3, message: "Пауза", updatedAt: "2026-09-01T10:00:00+00:00" },
  config: { queries: ["новости"], languages: ["ru"], regions: ["BY"], manualUrls: [] },
  tasks: [],
  results: [],
};
```

Add the fixture to the existing UI type-check test location or a small `src/ui/channel-research.test.ts` that imports the interfaces.

- [ ] **Step 2: Run the type check and verify failure because the types/page are absent**

Run: `pnpm typecheck`

Working directory: `studio-ui-remotion-verify`

Expected: FAIL with missing research types or page route.

- [ ] **Step 3: Define redacted TypeScript types and default snapshot**

```ts
export interface ResearchChannelSnapshot {
  channelId: string;
  name: string;
  profileReady: boolean;
  status: { state: string; processed: number; skipped: number; message: string; updatedAt: string };
  config: { queries: string[]; languages: string[]; regions: string[]; manualUrls: string[] };
  tasks: ResearchTaskSnapshot[];
  results: ResearchResultSnapshot[];
}
```

Add `research: { channels: [] }` to the `emptySnapshot` in `App.tsx`. Do not add OAuth or browser-session fields to these types.

- [ ] **Step 4: Build `ChannelResearchDashboard` with scoped controls and confirmation**

```tsx
<Button kind="primary" onClick={() => void command("start-channel-research", { indices: selectedIndices, mode: "fast" })}>
  Старт выбранных
</Button>
<Button onClick={() => void command("pause-channel-research", { indices: selectedIndices })}>
  Пауза
</Button>
<Button kind="danger" onClick={() => void command("stop-channel-research", { indices: selectedIndices })}>
  Стоп и показать результаты
</Button>
```

Include channel checkboxes, `Старт всех`, `Продолжить`, public URL text area, `.txt` picker/import, result filter, `Глубокий анализ`, export format selector, and a native confirmation before `clear-channel-research-results`. Add `Открыть профиль канала` through `open-channel-research-profile`; show an explanatory note that Google may request sign-in again.

- [ ] **Step 5: Add responsive accessible styles and mount the page**

Add `channel-research` to `Page`, navigation metadata, grouped navigation, allowed pages, and conditional rendering. In CSS use existing panel/button/status tokens, visible keyboard focus, `aria-live="polite"` for status changes, and a single-column fallback below 900px.

- [ ] **Step 6: Run UI checks**

Run: `pnpm typecheck && pnpm test -- --run`

Working directory: `studio-ui-remotion-verify`

Expected: PASS.

### Task 6: Integrate exports, deletion boundaries, and end-to-end verification

**Files:**
- Modify: `scriptor/bridge.py`
- Modify: `scriptor/channel_research.py`
- Modify: `tests/test_channel_research.py`
- Modify: `studio-ui-remotion-verify/src/ui/ChannelResearchDashboard.tsx`

**Interfaces:**
- `export-channel-research-results(payload)` consumes `{index: number, format: "csv" | "json" | "markdown"}` and returns public `{path, format, count}`.
- `clear-channel-research-results(payload)` consumes `{index: number}` and preserves `config`, Chrome profile, OAuth token, and other channels.

- [ ] **Step 1: Write failing export/delete boundary tests**

```python
def test_delete_results_clears_only_selected_channel_results_and_preserves_oauth(monkeypatch):
    settings = load_settings()
    settings.youtube_oauth_tokens = {"profile-a": "secret-a", "profile-b": "secret-b"}
    settings.channel_research = {
        "profile-a": {"config": {}, "tasks": [], "results": [{"url": "https://a.example"}], "status": {}},
        "profile-b": {"config": {}, "tasks": [], "results": [{"url": "https://b.example"}], "status": {}},
    }
    save_settings(settings)
    clear_channel_research_results({"index": 0})
    restored = load_settings()
    assert restored.channel_research["profile-a"]["results"] == []
    assert restored.channel_research["profile-b"]["results"] == [{"url": "https://b.example"}]
    assert restored.youtube_oauth_tokens == {"profile-a": "secret-a", "profile-b": "secret-b"}
```

- [ ] **Step 2: Run export/delete tests and verify they fail before the handlers exist**

Run: `py -3 -m unittest tests.test_channel_research.ChannelResearchBridgeTests.test_delete_results_clears_only_selected_channel_results_and_preserves_oauth -v`

Expected: FAIL with missing clear/export command.

- [ ] **Step 3: Implement atomic export writing and selected-channel deletion**

```python
def clear_channel_research_results(payload: dict) -> dict:
    settings = load_settings()
    profile_id = _channel_profile_id(settings, int(payload["index"]))
    state = channel_research_state(settings, profile_id)
    state["results"] = []
    state["tasks"] = []
    state["status"] = {"state": "idle", "processed": 0, "skipped": 0, "message": "Результаты удалены", "updatedAt": _now_iso()}
    save_settings(settings)
    return snapshot()
```

Write exports under `app_data_root() / "ResearchExports" / safe_filename(profile_id)` using a temporary file then `Path.replace`. Never derive a path from a URL or user-provided filename.

- [ ] **Step 4: Run the complete backend suite**

Run: `py -3 -m unittest tests.test_channel_research tests.test_youtube_publisher tests.test_youtube_oauth_handoff tests.test_oauth_handoff_persistence -v`

Expected: PASS.

- [ ] **Step 5: Build and perform a manual two-channel smoke test**

Run: `pnpm package:preview`

Working directory: `studio-ui-remotion-verify`

Manual checks:

1. Create or select two connected channel rows and confirm their profile IDs and `Открыть профиль канала` targets differ.
2. Import a small `.txt` list into each channel and verify duplicate/invalid-line feedback is isolated.
3. Start both, pause the first, request graceful stop for the second, then confirm no next task begins for the second after its active task finishes.
4. Export the second channel to CSV, JSON, and Markdown; inspect each for results only and confirm neither includes `token`, `cookie`, `password`, or Chrome path.
5. Delete first-channel results and confirm its OAuth state, profile, configuration, and all second-channel results remain present.

- [ ] **Step 6: Record the non-Git handoff**

Because this checkout has no `.git`, list changed files, commands run, test results, package artifact path, and remaining manual verification in the final implementation handoff instead of creating a commit.

## Self-review

### Spec coverage

- Per-channel Chrome profile/agent ownership: Tasks 2 and 3.
- Public source search, `.txt` intake, 100+ fast scan, and deeper selected analysis: Tasks 1 and 4.
- Start selected/all, pause/resume, graceful stop, durable restart state: Tasks 2 and 3.
- Channel-scoped results, export, and deletion: Tasks 1, 5, and 6.
- Secret/cookie isolation and error handling: Tasks 1, 2, 3, 4, and 6.
- UI, accessibility, and two-channel verification: Tasks 5 and 6.

### Placeholder scan

The scan found no deferred-work markers or vague implementation instructions. Every task includes a failing test, an explicit command, implementation interfaces, and a passing verification command.

### Type consistency

`profile_id` is the Python persistence key and becomes `channelId` only at the redacted desktop snapshot boundary. All bridge commands accept channel indices at the UI boundary and resolve them to profile IDs before reading or writing state.
