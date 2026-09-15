# Voice Engine

## Active Light path

`VoiceQueue` invokes `generate-voice` or `generate-voice-range` in `scriptor/bridge.py`. The canonical worker path is:

`VoiceQueue → Electron IPC → bridge.generate_voice[_range] → persisted TTS snapshot → selected provider → staged audio → FFmpeg duration validation → canonical MP3 → durable READY status`.

Each snapshot is keyed by `production_item_id`. WProject stores `remote_task.provider`, `remote_task.task_id` and the credential label before it starts polling. A resumed run polls that same remote task; it must not create a second paid request. Retry is allowed only before WProject returns a task ID.

## Artifact/status rule — 2026-09-11

- Provider bytes now land in `voicer_output_folder/.newsflow-voice-staging` first. A failed or unreadable response cannot overwrite an existing READY narration.
- `validate_voiceover_artifact()` requires a real file and a positive duration from the configured FFmpeg binary before promotion.
- Promotion is an atomic same-volume replacement into the canonical voice-output folder. Only then may `voice_scenario_outputs`, job `state=ready`, status `Готово`, and artifact metadata be persisted.
- A successful job records `artifact.path`, `artifact.duration_seconds`, `artifact.validated_at`; the projected status also carries `artifactPath` and `durationSeconds`.
- Manual single, file-list/ZIP, and folder imports validate the source and managed destination before attachment. Ambiguous/fuzzy mappings remain review-only; no automatic attachment occurs.

The existing VoiceQueue UI already projects backend `voiceStatus`, progress, update time and `voiceError`; it does not infer READY from button acknowledgement. The path is visible only after backend validation.

## Regression evidence

- `test_manual_import_rejects_unreadable_audio_without_attaching_it`
- `test_generated_voice_marks_invalid_audio_as_error_not_ready`
- `test_voice_status_is_saved_per_completed_task`
- `test_wproject_retries_long_russian_text_before_task_id_without_duplicate`
- `test_wproject_one_failed_task_does_not_cancel_its_neighbor`
- Existing matching, resume and range tests in `tests.test_voicer` and `tests.test_tts_ranges`.

Focused result: 47 tests passed on 2026-09-11. No live WProject request, provider job, browser voice task, production queue, or canonical user-data write was performed. The WProject endpoint contract is covered by local adapter tests; live external behavior remains **NOT VERIFIED** until a controlled authorized run.

## Production-recovery verification — 2026-09-14

- The live WProject OpenAPI requires `Idempotency-Key` for `POST /v1/tts`. The source previously did not send it; the first adapter edit exposed a second defect where `_request()` did not accept custom headers. The current client persists one provider idempotency key before the first submit, reuses it on submit retry, and now forwards the header to `urllib`.
- `VoiceQueue` has separate current actions: **Озвучить выбранные** retains `generate-voice`, while **Озвучить все в очереди** invokes `generate-voice-queue`. The queue action submits only `DONE` scripts and writes an explicit “Пропущено: сценарий не готов” reason for non-ready rows.
- Controlled live E2E used the existing WProject profile/key only to create a short disposable task under `D:\NewsFlow Studio\BuildValidation\wproject-e2e-20260914`. It produced `001 — Проверка WProject.mp3`, 116,289 bytes, duration 7.58 s, and durable isolated status `Готово`. No production settings, queue records, or output folders were used.
- Regression evidence: `test_wproject_http_request_keeps_the_idempotency_header`, `test_wproject_task_submission_sends_the_required_idempotency_key`, retry-key tests in `test_tts_ranges.py`, and `test_voice_queue_command_selects_only_ready_scenarios_and_keeps_skip_reasons`. Focused suite: 51 passing backend tests; Voice UI suite: 36 passing tests; TypeScript check passed.
