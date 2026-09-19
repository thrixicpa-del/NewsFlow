---
name: newsflow-runtime-qa
description: >-
  Сквозная QA-методика NewsFlow от UI через Electron/Python/queues/storage/providers до сохранённого и пользовательски видимого результата, включая media validation.
---

# NewsFlow Runtime QA Deep

Проверяй не «вызов прошёл», а обещанный пользователю результат.

## Сквозная трасса

`UI → handler → preload/IPC → Electron main → Python bridge/frozen core → service/worker → storage/provider → result → UI`.

Для каждого шага проверяй вход, выход, идентификатор объекта, ошибку, таймаут, отмену, retry/idempotency и persistence.

## State & queues

Проверяй duplicate click, process restart, interrupted job, stale status, partial output, missing file, retry после timeout, повторный запуск после success и конкурентное изменение одного объекта.

## Media outcome

FFprobe/FFmpeg подтверждают duration/streams/codec/resolution, но не semantic quality. Для voice/montage отдельно проверяй наличие начала/середины/конца речи, отсутствие обрезки, sync и доступность финального output.

## Evidence ladder

Unit → contract → integration → source Electron E2E → packaged smoke → controlled real-provider acceptance. Используй только нужный уровень; более высокий не заменяет точечный regression test.

## Общие границы NewsFlow

- Skill — это методика, а не разрешение на внешние или опасные действия. Следуй текущей задаче пользователя, подтверждённым правилам репозитория и доступным инструментам.
- Перед изменением кода подтверждай репозиторий, ветку, SHA, рабочее дерево, версии и фактический runtime. Не считай старый чат текущим состоянием.
- Не трогай оригинальную production-медиатеку, реальные ключи, OAuth, рабочие очереди и пользовательские данные в автоматических тестах. Используй синтетические фикстуры или отдельно согласованные копии.
- Не делай merge в `main`, force-push, публикацию, платный provider-call, массовое обновление зависимостей или расширение прав без явного разрешения.
- Быстрый цикл по умолчанию: source/DEV → targeted tests → relevant regression → integration/E2E при необходимости → commit. Полный EXE/TEST RC — на контрольной точке или при packaging-specific дефекте.
- Факт отделяй от гипотезы. Не называй тест выполненным, пока он не был реально запущен; SKIP не равен PASS.
- Не маскируй сбой отключением теста, `continue-on-error`, удалением проверки или возвратом фиктивного success.
- Исправляй первопричину минимальным изменением; широкую перестройку выноси в отдельное решение.
- Для каждого результата фиксируй: expected/actual, root cause evidence, изменённые файлы, SHA, команды, PASS/FAIL/SKIP/BLOCKED и оставшиеся риски.
