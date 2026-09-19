---
name: newsflow-data-migrations-recovery
description: >-
  Безопасная эволюция данных NewsFlow: schema/config migrations, corruption handling, backup/restore, rollback, compatibility, idempotency и recovery drills.
---

# NewsFlow Data Migrations + Recovery

Используй при изменениях persisted JSON/SQLite/config/cache/job schema или восстановлении после повреждения.

## Migration properties

Миграция должна быть versioned, deterministic, testable, bounded, idempotent где возможно и не зависеть от production side effects. Старый формат → migrate → current runtime → restart должен сохранять смысловые данные.

## Corruption

Не интерпретируй corrupted state как пустой default с последующей записью. Сохрани evidence, fail visibly или используй явный recovery path по текущему контракту.

## Backup/restore

Backup не равен restore proof. Проверяй creation, integrity/hash/manifest при наличии, восстановление на копии, schema compatibility и post-restore launch.

## Rollback

Перед migration планируй forward fix/rollback constraints. Если downgrade небезопасен, это должно быть явно зафиксировано до релиза.

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
