---
name: newsflow-media-engineering
description: >-
  Глубокая media-инженерия NewsFlow: FFmpeg/FFprobe, Remotion, audio/video timing, proxies, codecs, footage pipeline, render correctness и техническое качество output.
---

# NewsFlow Media Engineering Deep

Используй для Voice, Footage, Montage, Remotion и любого дефекта итогового медиа.

## Audio

Проверяй duration, sample rate, channels, codec, silence/clipping при необходимости, mapping, start/end timestamps и сохранность всей речи. Metadata duration сама по себе не доказывает, что конец текста не потерян.

## Video

Проверяй fps/CFR-VFR, resolution, pixel format, aspect ratio, timestamps, keyframes при релевантности, stream mapping, concat/filtergraph и hardware/software encoder fallback.

## Timeline

Сопоставляй semantic duration сцен, voice duration и render duration. Не исправляй audio truncation простым растягиванием последнего кадра, если причина находится выше по pipeline.

## Footage & proxies

Оригиналы read-only. Проверяй deterministic proxy key, invalidation при изменении исходника, deduplication, missing/offline file handling, incremental indexing и cleanup только test-owned artifacts.

## Remotion

Проверяй composition props, frame math, fps conversion, asset availability, async render lifecycle и reproducibility. Не переносись в cloud rendering без отдельного решения.

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
