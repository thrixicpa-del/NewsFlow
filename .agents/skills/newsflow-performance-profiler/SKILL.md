---
name: newsflow-performance-profiler
description: >-
  Измеряемая оптимизация NewsFlow: React render cost, Python CPU/I/O/concurrency, SQLite, media decode/render, memory leaks и большие библиотеки футажей.
---

# NewsFlow Performance Profiler

Правило: сначала benchmark/profile, потом optimization, затем тот же benchmark.

## Frontend

Измеряй commit/render cost, количество rerenders, large-list behavior, media preview lifecycle, image decoding, subscriptions, search/filter latency и memory retention. Проверяй virtualization только там, где размер списка реально оправдывает её.

## Python/backend

Разделяй CPU-bound, I/O-bound и external-wait. Профилируй hot paths, filesystem scans, SQLite queries/indexes, serialization, hashing, thread/process pools, queue contention и subprocess startup.

## Media

Измеряй decode/encode throughput, disk read/write, proxy cache hit rate, concurrent renders, GPU utilization при доступности и fallback cost.

## Regression budget

Для важных путей фиксируй baseline, dataset, machine/environment, metric и допустимый threshold. Не сравнивай результаты разные машин как эквивалентные без нормализации.

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
