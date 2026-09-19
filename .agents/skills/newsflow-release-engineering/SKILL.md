---
name: newsflow-release-engineering
description: >-
  Release engineering NewsFlow: immutable TEST/RC/STABLE artifacts, manifests/hashes, CI evidence, packaged smoke, clean Windows, rollback и fail-closed release gate.
---

# NewsFlow Release Engineering

Используй на milestone/PR/RC/Stable, а не после каждого мелкого bugfix.

## Candidate identity

Кандидат привязан к exact commit SHA, version/channel/RC number и immutable output path. После изменения package inputs кандидат считается новым.

## Gate

Release-ready означает, что все mandatory checks реально выполнены: source tests, security, runtime/core parity, packaging, independent manifest/hash verification, packaged smoke и production integrity. Required SKIP/BLOCKED не превращай в PASS.

## Artifact verification

Проверяй deliverable, а не только build directory: bundled core/native binaries, manifest, hashes, version, channel metadata и launch behavior.

## Clean environment

Перед Stable нужен controlled clean Windows/Sandbox/runner check: install/portable launch, first-run paths, permissions, bundled dependencies и отсутствие скрытой зависимости от dev machine.

## Rollback

Сохраняй previous stable identity, migration compatibility и понятный recovery path. Release notes должны отделять code changes, known limitations и operational requirements.

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
