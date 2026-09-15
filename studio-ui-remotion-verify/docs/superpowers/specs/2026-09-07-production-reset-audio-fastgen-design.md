# Production reset, audio import, and FastGen continuation design

## Goal

Make batch production recoverable and understandable: export every finished script as an individually named text file, import finished narration files safely, choose FastGen keys deliberately, resume thumbnail work after the provider's hourly reset, and clear one completed production batch without disturbing channel access or application settings.

## Scope

This design covers the React/Electron screen in `src/ui/App.tsx`, the local Python command bridge, and persisted NewsFlow settings. It does not alter YouTube channels, OAuth credentials, Chrome profiles, or API-key storage.

## Script export

The finished-scripts screen gains a distinct `Скачать все отдельными TXT` action. It produces one ZIP archive. Every ready script becomes one UTF-8 `.txt` file named from its scenario title; characters invalid in Windows file names are replaced with `_`, and duplicate safe names gain a numeric suffix. The existing general `Скачать все` action keeps its current behaviour.

## Imported narration

The narration screen enables `Добавить свою озвучку`, `Удалить MP3`, and opening the ready-results folder.

Accepted standalone and ZIP-contained formats are MP3, WAV, M4A, AAC, OGG, and FLAC. ZIP members are extracted into the configured narration folder only after path traversal and extension validation. File-to-scenario matching compares a normalised filename stem with a normalised scenario title: it ignores the extension, an optional leading sequence number, whitespace, punctuation, and case. A unique match is attached automatically. No match and ambiguous match are recorded as review states rather than assigned to an arbitrary scenario; the UI provides a manual scenario selector for those files.

## FastGen key selection and hourly continuation

The cover settings store an explicit selected FastGen-key set. The editor may select exactly one active key, any selected set of active keys, or all active keys. The pool receives only that selected set and rotates across keys when work is generated.

When FastGen reports exhaustion or rate limiting, unfinished cover items retain their progress and enter `Ожидает лимит FastGen`. The queue stores the next resume moment at the next local clock `HH:01`. At that time it refreshes FastGen usage and resumes remaining items with available selected keys. The UI displays the scheduled resume time and does not lose or recreate a completed image.

## Production reset

The management centre gains `Удалить всё производство`. It displays counts and requires an explicit confirmation. On confirmation it removes only production artefacts and their working folders: topics, ready scripts, SEO packages, tags, imported/generated narration, cover assets, footage/cut assets, render inputs, final MP4 files, and completed package folders. It also clears their persisted queue records.

The command uses only configured NewsFlow production/output paths, resolves each target before deletion, and refuses a path outside an allowed production root. Channels, OAuth tokens, Chromium profiles, API keys, global settings, and the saved audio-output path are retained. The UI reports what was removed and which configured folders were already absent.

## Error handling

Invalid or empty archives do not change existing audio rows. An unsupported item is skipped and reported by filename. A missing results folder is created before opening. If a FastGen response has no reset timestamp, the known hourly reset contract is used and the next attempt is still scheduled for `HH:01`.

## Verification

Automated tests cover safe individual script names, ZIP and standalone audio acceptance, unique/ambiguous/non-matching filename behaviour, selected-key filtering, next-hour-plus-one-minute scheduling, and production reset exclusion rules. UI builds and the existing Python test suite run after the changes.
