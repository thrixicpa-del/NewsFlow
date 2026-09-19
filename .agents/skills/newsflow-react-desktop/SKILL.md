---
name: newsflow-react-desktop
description: >-
  Глубокая диагностика и исправление React/TypeScript desktop UI NewsFlow: состояние, async races, формы, большие списки, composition, accessibility, performance и визуальная целостность.
---

# NewsFlow React Desktop Deep

Используй для React/TypeScript интерфейса Electron-приложения, а не React Native и не Next.js по умолчанию.

## Correctness

- Проследи событие: component → handler → state owner → IPC/service → response → UI state.
- Проверяй stale closures, racing requests, out-of-order responses, double submit, cancellation/unmount, optimistic update rollback.
- Состояние должно иметь одного понятного владельца. Derived state вычисляй, а не синхронизируй эффектами без необходимости.
- Таблицы/списки должны действовать по стабильному ID, а не по индексу строки после сортировки/фильтра.
- Для форм различай draft, persisted value и backend authoritative value.

## Desktop UX

Проверяй loading, empty, partial-success, error, retry, disabled reason, cancellation, restore-after-restart. Для плотной workstation UI оценивай читаемость, клавиатуру, focus management, modal focus return, long Russian text, paths, zoom/DPI и узкие окна.

## Performance

Сначала измеряй. Проверяй большие списки, expensive selectors, media previews, unnecessary rerenders, event subscriptions, object URL/video lifecycle и память. Не добавляй memoization/virtualization без подтверждённой пользы.

## Verification

Vitest/RTL проверяет компонентный контракт; contract/integration — передачу команд; Playwright/Electron — реальное пользовательское действие. Наличие handler не доказывает результат функции.

## Общие границы NewsFlow

- Skill — это методика, а не разрешение на внешние или опасные действия. Следуй текущей задаче пользователя, подтверждённым правилам репозитория и доступным инструментам.
- Перед изменением кода подтверждай репозиторий, ветку, SHA, рабочее дерево, версии и фактический runtime. Не считай старый чат текущим состоянием.
- Не трогай оригинальную production-медиатеку, реальные ключи, OAuth, рабочие очереди и пользовательские данные в автоматических тестах. Используй синтетические фикстуры или отдельно согласованные копии.
- Не делай merge в `main`, force-push, публикацию, платный provider-call, массовое обновление зависимостей или расширение прав без явного разрешения.
- Быстрый цикл по умолчанию: source/DEV → targeted tests → relevant regression → integration/E2E при необ�iодимости → commit. Полный EXE/TEST RC — на контрольной точке или при packaging-specific дефекте.
- Факт отделяй от гипотезы. Не называй тест выполненным, пока он не был реально запущен; SKIP не равен PASS.
- Не маскируй сбой отключением теста, `continue-on-error`, удалением проверки или возвратом фиктивного success.
- Исправляй первопричину минимальным изменением; широкую перестройку выноси в отдельное решение.
- Для каждого результата фиксируй: expected/actual, root cause evidence, изменённые файлы, SHA, команды, PASS/FAIL/SKIP/BLOCKED и оставшиеся риски.
