---
name: newsflow-electron-windows-deep
description: >-
  Глубокая экспертиза Electron + Windows для NewsFlow: main/preload/IPC, process lifecycle, paths, packaging, userData, child processes, frozen core, installer/portable и native edge cases.
---

# NewsFlow Electron + Windows Deep

Используй для проблем, зависящих от Electron, Windows, упаковки или дочерних процессов.

## Security boundary

Подтверди `contextIsolation`, `nodeIntegration`, preload API, IPC allow-list, navigation/window-open policy и отсутствие прямого renderer-доступа к Node/FS. Не расширяй preload API «для удобства» без необходимости.

## Process lifecycle

Для Python, FFmpeg, Vite и других child processes проверяй spawn mode, quoting, cwd, env, stdout/stderr draining, timeout, cancellation, Windows process tree termination, orphan/zombie processes и graceful shutdown.

## Windows paths

Тестируй пробелы, Unicode, длинные пути, drive letters, UNC при релевантности, TEMP/LOCALAPPDATA/userData, read-only/locked files и отсутствие hard-coded machine paths.

## DEV vs packaged

Всегда фиксируй, какой runtime запускается: source Python, frozen core, portable build или installed app. Проверяй stale core, bundled resources, native binaries и manifest/hash parity.

## Packaging acceptance

Package success ≠ app success. Нужны independent artifact verification, launch, minimal navigation, isolated userData, child process startup, bundled core/FFmpeg availability и clean shutdown.

## Общие границы NewsFlow

- Skill — это методика, а не разрешение на внешние или опасные действия. Следуй текущей задаче пользователя, подтверждённым правилам репозитория и доступным инструментам.
- Перед изменением кода подтверждай репозиторий, ветку, SHA, рабочее дерево, версии и фактический runtime. Не считай старый чат текущим состоянием.
- Не трогай оригинальную production-медиатеку, реальные ключи, OAuth, рабочие очереди и пользовательские данные в автоматических тестах. Используй синтетические фикстуры или отдельно согласованные копии.
- Не делай merge в `main`, force-push, публикацию, пллатный provider-call, массовое обновление зависимостей или расширение прав без явного разрешения.
- Быстрый цикл по умолчанию: source/DEV → targeted tests → relevant regression → integration/E2E при необ�iодимости → commit. Полный EXE/TEST RC — на контрольной точке или при packaging-specific дефекте.
- Факт отделяй от гипотезы. Не называй тест выполненным, пока он не был реально запущен; SKIP не равен PASS.
- Не маскируй сбой отключением теста, `continue-on-error`, удалением проверки или возвратом фиктивного success.
- Исправляй первопричину минимальным изменением; широкую перестройку выноси в отдельное решение.
- Для каждого результата фиксируй: expected/actual, root cause evidence, изменённые файлы, SHA, команды, PASS/FAIL/SKIP/BLOCKED и оставшиеся риски.
