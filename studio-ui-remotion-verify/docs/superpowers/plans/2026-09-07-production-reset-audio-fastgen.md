# Production Reset, Audio Import, and FastGen Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make scripts exportable as individually named files, support user narration import, continue FastGen at `HH:01`, and safely reset production data while retaining channel access and settings.

**Architecture:** Python bridge commands own files, state, queue recovery, and path safety. React exposes those commands with clear enabled actions, review states, and confirmation UI. New persisted settings store only selected FastGen key labels and no secrets.

**Tech Stack:** Python 3, Electron IPC bridge, React/TypeScript, `unittest`, ZIP archives.

**Spec:** `docs/superpowers/specs/2026-09-07-production-reset-audio-fastgen-design.md`

## Global Constraints

- Delete only resolved paths inside configured NewsFlow production roots.
- Never delete channels, OAuth tokens, Chrome profiles, API keys, or global settings.
- Accept MP3, WAV, M4A, AAC, OGG, and FLAC as standalone files or ZIP members.
- Resume rate-limited FastGen queue items at the next `HH:01` local time.

---

### Task 1: Script ZIP export

**Files:**
- Modify: `../scriptor/bridge.py`
- Test: `../tests/test_core.py`
- Modify: `src/ui/App.tsx`

**Interfaces:**
- Produces `export_scripts_separate_txt(payload: dict) -> dict`.
- React invokes `command("export-scripts-separate-txt", {indices})`.

- [ ] **Step 1: Write the failing test**

```python
def test_export_scripts_separate_txt_uses_titles_for_zip_members(self):
    result = bridge.export_scripts_separate_txt({"indices": [0, 1]})
    with zipfile.ZipFile(result["exportedPath"]) as archive:
        self.assertEqual(archive.namelist(), ["Первая тема.txt", "Вторая тема.txt"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m unittest tests.test_core.CoreTests.test_export_scripts_separate_txt_uses_titles_for_zip_members`

- [ ] **Step 3: Write minimal implementation**

```python
def export_scripts_separate_txt(payload: dict) -> dict:
    # collect DONE scenario jobs, make a UTF-8 ZIP in output/Выгрузки этапов,
    # and suffix duplicate safe file names before writing each scenario result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m unittest tests.test_core.CoreTests.test_export_scripts_separate_txt_uses_titles_for_zip_members`

- [ ] **Step 5: Add the visible button**

```tsx
<Button onClick={() => void command("export-scripts-separate-txt", { indices: selected })}>
  Скачать все отдельными TXT
</Button>
```

### Task 2: User audio import and results controls

**Files:**
- Modify: `../scriptor/bridge.py`
- Test: `../tests/test_voicer.py`
- Modify: `src/ui/App.tsx`
- Modify: `src/desktop.d.ts`

**Interfaces:**
- Produces `import_voiceover_files(payload: dict) -> dict`, `open_voiceover_results(payload: dict) -> dict`.
- React invokes `command("import-voiceover-files", {paths})` and `command("open-voiceover-results", {})`.

- [ ] **Step 1: Write failing tests**

```python
def test_import_voiceover_files_matches_numbered_filename_to_title(self):
    result = bridge.import_voiceover_files({"paths": [str(audio_path)]})
    self.assertEqual(result["operationResult"]["matched"], 1)

def test_import_voiceover_files_marks_ambiguous_title_for_review(self):
    result = bridge.import_voiceover_files({"paths": [str(audio_path)]})
    self.assertEqual(result["operationResult"]["review"], 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m unittest tests.test_voicer`

- [ ] **Step 3: Implement import, matching, and safe extraction**

```python
SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
# normalise names; copy standalone files; validate ZIP member paths and suffixes;
# attach only unique matches; persist unmatched/ambiguous review rows.
```

- [ ] **Step 4: Implement UI actions**

```tsx
<Button onClick={chooseAudioFiles}>Добавить свою озвучку</Button>
<Button onClick={() => void command("open-voiceover-results", {})}>Показать результаты MP3</Button>
<Button onClick={() => void command("remove-voiceovers", { indices: selected })}>Удалить MP3</Button>
```

- [ ] **Step 5: Run tests**

Run: `py -3 -m unittest tests.test_voicer`

### Task 3: Selected FastGen keys and hourly resume

**Files:**
- Modify: `../scriptor/config.py`
- Modify: `../scriptor/cover_rate_limit.py`
- Modify: `../scriptor/bridge.py`
- Test: `../tests/test_covers.py`
- Modify: `src/ui/App.tsx`
- Modify: `src/desktop.d.ts`

**Interfaces:**
- Produces `next_fastgen_resume_at(now: datetime) -> datetime` and selected-key filtering in `FastGenPool` construction.
- React saves `fastgenKeyLabels` through `save-cover-settings`.

- [ ] **Step 1: Write failing tests**

```python
def test_next_fastgen_resume_is_one_minute_after_next_hour(self):
    self.assertEqual(next_fastgen_resume_at(at_1259), at_1301)

def test_cover_generation_uses_only_selected_active_keys(self):
    self.assertEqual(pool.labels, ["Key B"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m unittest tests.test_covers`

- [ ] **Step 3: Implement persisted selection and resumption**

```python
# Store selected active key labels in Settings.
# Build FastGenPool from selected labels.
# On rate limit set rate_limit_wait_until to next HH:01.
# Resume only waiting items after usage refresh confirms an available selected key.
```

- [ ] **Step 4: Add key checkboxes and queue status**

```tsx
<label><input type="checkbox" checked={selectedKeys.includes(key.label)} />{key.label}</label>
<span>Следующая попытка: {cover.rate_limit_wait_until}</span>
```

- [ ] **Step 5: Run tests**

Run: `py -3 -m unittest tests.test_covers`

### Task 4: Safe production reset

**Files:**
- Modify: `../scriptor/bridge.py`
- Test: `../tests/test_core.py`
- Modify: `src/ui/App.tsx`

**Interfaces:**
- Produces `clear_all_production_data(payload: dict) -> dict`.
- React invokes `command("clear-all-production-data", {confirmed: true})` after confirmation.

- [ ] **Step 1: Write failing tests**

```python
def test_clear_all_production_data_removes_managed_artifacts_only(self):
    result = bridge.clear_all_production_data({"confirmed": True})
    self.assertEqual(result["operationResult"]["kind"], "production-reset")
    self.assertTrue(channel_settings_are_unchanged())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m unittest tests.test_core.CoreTests.test_clear_all_production_data_removes_managed_artifacts_only`

- [ ] **Step 3: Implement the restricted reset**

```python
# Resolve and delete only content/output, voice, cover, footage/cut, montage,
# final render, and package roots. Clear topics, sessions and production queues.
# Preserve analytics_channels, OAuth fields, browser paths, keys and preferences.
```

- [ ] **Step 4: Add management-centre confirmation action**

```tsx
if (window.confirm("Удалить все темы, сценарии, аудио, обложки и ролики? Каналы и ключи останутся.")) {
  await command("clear-all-production-data", { confirmed: true });
}
```

- [ ] **Step 5: Run tests**

Run: `py -3 -m unittest tests.test_core`

### Task 5: Integration verification

**Files:**
- Modify: `src/desktop.d.ts`
- Modify: `src/ui/App.tsx`

- [ ] **Step 1: Run focused Python tests**

Run: `py -3 -m unittest tests.test_core tests.test_voicer tests.test_covers`

- [ ] **Step 2: Build the desktop UI**

Run: `pnpm build:web`

- [ ] **Step 3: Run the full Python suite**

Run: `py -3 -m unittest discover -s ../tests -q`
