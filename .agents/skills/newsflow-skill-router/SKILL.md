---
name: newsflow-skill-router
description: >-
  Select the smallest useful combination of NewsFlow deep skills for a software task.
  Use when multiple domains overlap or when deciding which specialist skill should drive the work.
---

# NewsFlow Skill Router

Не загружай все skills одновременно. Выбирай 1 основной + максимум 1–3 дополняющих по реальному failure path.

| Запрос | Основной | Дополнительные |
| --- | --- | --- |
| Кнопка/форма/React state | react-desktop | runtime-qa, electron-windows-deep |
| IPC/process/path/packaging | electron-windows-deep | runtime-qa, security-threat-model |
| Монтаж/audio/video/footage | media-engineering | runtime-qa, performance-profiler |
| Медленно/RAM/CPU | performance-profiler | react-desktop или media-engineering |
| Системная архитектурная проблема | architecture-evolution | brainstorm-critical, runtime-qa |
| Security finding | security-threat-model | electron-windows-deep, data-migrations-recovery |
| Непонятный runtime failure | observability-debug | runtime-qa, domain skill |
| Prompt/model/provider quality | ai-evals | brainstorm-critical, product-discovery |
| Migration/corruption/restore | data-migrations-recovery | security-threat-model, release-engineering |
| Новая функция/workflow | product-discovery | brainstorm-critical, architecture-evolution |
| RC/Stable | release-engineering | runtime-qa, security, migrations |

## Правило маршрутизации

Сначала классифицируй observable outcome и первую подозрительную границу. Если после доказательств граница меняется — переключи skill. Не используй architecture/brainstorm для мелкого воспроизводимого бага без причины.
