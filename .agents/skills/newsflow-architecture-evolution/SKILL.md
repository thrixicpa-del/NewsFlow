---
name: newsflow-architecture-evolution
description: >-
  Архитектурный анализ и безопасная эволюция NewsFlow: boundaries, domain/services/adapters, legacy paths, state ownership, extensibility и подготовка к niche profiles без big-bang rewrite.
---

# NewsFlow Architecture Evolution

Используй, когда локальный баг указывает на системную причину или пользователь просит масштабируемую архитектуру.

## Сначала карта, потом рефакторинг

Определи реальные runtime boundaries и dependency directions. Найди god objects, duplicated contracts, legacy/current parallel paths, provider-specific logic внутри domain, скрытое global state, storage leakage в UI и циклические зависимости.

## Эволюция

Предпочитай seams/adapters и strangler-style переход вместо big-bang rewrite. Сначала стабилизируй контракт тестом, затем перемести одну ответственность, сохрани observable behavior, после чего удали legacy только при доказанной неиспользуемости.

## Extensibility

Для будущих ниш отделяй неизменное ядро workflow от profile/config/prompt/provider policy. Не создавай абстракцию до второго реального use case, если цена сложности превышает пользу.

## Architecture decision

Для значимого решения фиксируй context, options, constraints, decision, consequences, rollback/migration и verification. Архитектурная «красота» без measurable effect не является достаточной причиной.

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
