---
name: newsflow-ai-evals
description: >-
  Систематические evals для AI-функций NewsFlow: Ideas, Scripts, Covers prompts, SEO/tags и provider routing по качеству, фактичности, latency, cost и robustness.
---

# NewsFlow AI Evals

Не оценивай prompt по одному красивому примеру.

## Dataset

Создай небольшой versioned benchmark из типичных, сложных, неоднозначных, длинных, неполных и failure-prone случаев. Production материалы не копируй без необходимости; используй обезличенные/синтетические кейсы.

## Criteria

Для функции выбери измеримые/рубрикаторные критерии: factual support, completeness, format compliance, repetition, style constraints, usefulness, safety, latency, token/cost budget и provider fallback behavior.

## Compare

A/B сравнивай на одном dataset и фиксированных условиях. Не меняй одновременно prompt, model, temperature/router и parser, если потом нельзя понять причину эффекта.

## Deterministic gates

Всё, что можно проверить программно (JSON/schema, length bounds, required sections, forbidden leakage), проверяй кодом. Субъективное качество оставляй rubric/human review.

## Release

Не продвигай новый prompt/provider policy, если выигрыш не воспроизводится или ухудшает важный сегмент без осознанного trade-off.

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
