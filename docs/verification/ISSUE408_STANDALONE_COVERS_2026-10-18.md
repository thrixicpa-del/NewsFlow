# Issue 408 — самостоятельные темы и промпты в Обложках

[Issue #408](https://github.com/thrixicpa-del/NewsFlow/issues/408). Отдельная ветка `codex/covers-standalone-topics` от `43dd0709d7341eb79b308303031b5f3a47fd3ebc`; main и PR #403/#405/#407 не изменялись.

## Поведение

«Добавить темы и промпты» открывает форму в основном окне: пары можно вставить вручную или загрузить из TXT. Формат: строка темы, строка промпта, затем следующие пары. Предварительные идеи, сценарии и озвучка не нужны. Отдельная кнопка запускает генерацию; добавление пар само по себе не вызывает провайдера.

Новая тема получает UUID ProductionItem, строку обложки с тем же ID и ручным промптом. Существующая однозначная строка обложки сохраняет ID. Все пары валидируются до изменения: неоднозначные темы, разные промпты для одной темы, недостающие строки и отсутствующие ID существующих строк отклоняются без частичного импорта. Прежний строгий TXT-импорт сохранён; создание новых тем включается явным `createMissingTopics: true` в том же IPC-контракте.

Самостоятельная строка явно помечена `origin=covers`, `manual=true`; её текущее владение вычисляется из settings.cover_queue до гидратации библиотеки. Поэтому удаление другой идеи и сохранение старого списка идей не прячут самостоятельные обложки. Library-only и legacy записи не предоставляют разрешения; global/queue tombstones исключаются. Reset фиксирует ID самостоятельных обложек, очищает очередь и не позволяет позднему worker вернуть старую строку. Повторное добавление после reset даёт новый ID.

## Доказательства

- Backend RED: три исходных теста завершились UNKNOWN_TOPIC для новых тем. GREEN: создание без сценариев, разные ниши/ID, перезагрузка, существующая тема, атомарность неоднозначного пакета, reset/re-add.
- UI RED: три теста не находили новую кнопку. GREEN: ввод при пустой очереди, блокировка двойного нажатия, сохранение ввода при ошибке, TXT в редактор без запуска генерации.
- Независимый review выявил потерю владения через idea_production_items после удаления другой идеи и непустого stale save. Оба случая воспроизведены RED; владение перенесено на текущую явно помеченную строку Covers. Новые регрессии GREEN; повторный независимый review без существенных замечаний, 6 backend-тестов OK (outer guard FAIL).
- Связанные backend suites: **377 тестов OK**,64.075s. Команда: `python tests/run_isolated.py tests.test_cover_standalone_topics tests.test_cover_prompt_pairs_import tests.test_cover_manual_prompt_readiness tests.test_cover_manual_no_paid_aux tests.test_cover_result_identity tests.test_cover_queue_tombstones tests.test_cover_text_triples_import tests.test_cover_scene_briefs tests.test_cover_quality_selection tests.test_covers -q`.
- UI/IPC: **65 тестов PASS**,3 файла: covers-view, covers-polling, electron/core-transport. Typecheck, source web/Electron builds, Ruff и diff check PASS.
- Реальный DEV Electron → React controls → preload/IPC → Python → disposable storage: пустые Covers/scenarios → две пары → reset через контрольную фразу → те же пары с новыми ID → полный перезапуск → обе темы/промпты с теми же новыми ID. PASS7.497s. Команда: `python tests/run_isolated.py tests.test_cover_standalone_ui -v`. Первый harness не раскрыл группу навигации; исправлен реальный маршрут через «ОБЛОЖКИ И ГЕНЕРАЦИИ» → «Обложки YouTube».
- Внешний вид формы проверен по screenshot настоящего изолированного Electron: поля и обе кнопки доступны, текст/пары не обрезаны. Необязательный захват включается через `NEWSFLOW_CAPTURE_UI_SCREENSHOTS=1`; скрытое окно первоначально возвращало UnknownVizError, поэтому только при захвате собственное тестовое окно показывается без активации и затем скрывается. Прогон с захватом PASS8.147s (outer guard FAIL). Функциональные assertions обязательны независимо от захвата; его ошибки не подавляются.
- Генерация проверена через настоящий generate_covers с offline fake image adapter, без сети/платных text AI: тестовая PNG остаётся привязанной к ID своей темы после сохранения/загрузки, другая тема сценария не подменяет результат. Это контроль интеграции, не визуальная приёмка реального AI-провайдера.
- Первоначальный тест расположения PNG обнаружил штатное перенаправление TEMP-пути в общий disposable NEWSFLOW_TEST_ROOT/Media; рабочие папки не использовались. Фикстура получила собственные TEMP/TMP как в production-reset tests; сохранена строгая проверка нахождения результата внутри её тестового корня.
- Windows CI дополнен обязательным runtime закреплённого Electron и реальным UI/restart; Linux CI дополнен backend Covers suites. Удалённые результаты и точный HEAD фиксируются в draft PR.

## Ограничения

Рабочий NewsFlow остаётся открыт по выбору пользователя. Canonical локальные команды неоднократно дали `PRODUCTION_WRITE_GUARD=FAIL changed=settings.json`, несмотря на успешные assertions. Локальная неизменность рабочего профиля BLOCKED; guard не отключался/не перенаправлялся. История FAIL сохранена в игнорируемых `.superpowers/covers-standalone/` логах. Все действия очистки/добавления/генерации в тестах использовали disposable-профили и пути; рабочее приложение не останавливалось.

Security/integrity:26 тестов,25 PASS/1 FAIL — Frozen Core lock не соответствует изменённому bridge source. Lock не обновлялся без Frozen build. Docker NOT RUN: engine pipe недоступен. EXE/Frozen, packaged/clean Windows RELEASE и реальный платный provider acceptance NOT RUN по границам задачи. MP4 N/A: изменения не затрагивают монтаж/медиа-рендер видео. Не объявляется release-ready; merge и закрытие issue не выполняются.
