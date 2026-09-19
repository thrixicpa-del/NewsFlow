---
name: newsflow-observability-debug
description: >-
  Диагностика NewsFlow через структурированные логи, correlation IDs, operation/job tracing, redaction, error taxonomy и доказуемое локализованное наблюдение.
---

# NewsFlow Observability + Debug

Цель — быстро ответить: «что произошло с конкретной операцией и где она сломалась?» без утечки секретов.

## Correlation

Каждая значимая операция должна иметь correlation/operation/job ID, проходящий через UI request, IPC, bridge, service/worker и provider/render logs, если архитектура это поддерживает.

## Structured events

Логируй event name, timestamp, operation id, stage, duration, result class и безопасный контекст. Не логируй tokens, full prompts с секретами, OAuth payloads или лишние абсолютные пути.

## Error taxonomy

Разделяй validation, user cancellation, provider quota/auth/timeout, filesystem, subprocess, media decode/render, invariant/bug и unknown. UI-сообщение пользователю и diagnostic detail могут различаться.

## Debug loop

Собери timeline → найди первый divergence от expected → воспроизведи минимально → добавь instrumentation только если текущих доказательств недостаточно → удаляй шум после диагностики или делай его debug-level.

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
