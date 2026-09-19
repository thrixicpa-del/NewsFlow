---
name: newsflow-security-threat-model
description: >-
  Контекстный threat modeling и security review NewsFlow: Electron boundary, secrets/OAuth, filesystem, subprocess, providers, untrusted media/JSON и защита production данных.
---

# NewsFlow Security Threat Model

Сначала перечисли assets, trust boundaries и attacker-controlled inputs.

## Assets

Production media/state, API keys, OAuth tokens, Chrome sessions, prompts/templates, output packages и release integrity.

## Boundaries

Renderer ↔ preload/IPC ↔ Electron main ↔ Python/frozen core ↔ filesystem/subprocess ↔ providers/network.

## Проверки

Ищи path traversal, unsafe shell construction, command injection, arbitrary file overwrite/delete, symlink/reparse risks при релевантности, secret leakage in logs/errors, insecure navigation, overly broad IPC, token persistence, OAuth state/redirect validation, untrusted JSON/schema abuse и poisoned filenames/media metadata.

## Security fix discipline

Не «санитизируй всё строкой regex». Валидируй тип/структуру/allow-list и используй safe APIs. После исправления добавляй regression test и проверяй, что функциональность сохранилась.

## Reporting

Severity отделяй от exploitability. Не объявляй vulnerability без воспроизводимой цепочки или достаточного code evidence; configuration blocker отмечай отдельно от code flaw.

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
