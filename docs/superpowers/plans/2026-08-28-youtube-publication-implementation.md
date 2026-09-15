# План реализации: центр публикации YouTube

> Спецификация: `docs/superpowers/specs/2026-08-28-youtube-publication-design.md`

## Этап 1 — доменная модель и локальная очередь

**Файлы**

- Create: `scriptor/youtube_publisher.py`
- Modify: `scriptor/config.py`
- Modify: `scriptor/bridge.py`
- Create: `tests/test_youtube_publisher.py`

1. Написать падающие тесты для `PublicationJob`: создание из готового пакета с названием сценария, SEO-фразами, тегами и обложкой; валидация статусов, приватность по умолчанию и планирование. Название сценария длиннее 100 символов должно блокировать upload и сформировать запрос на перефразирование.
2. Добавить чистые dataclass/функции без сетевых вызовов: `PublicationJob`, `ChannelProfile`, `PublicationPreset`, `MetricSnapshot`, `WarmupRun`, `ActivityLogEntry`.
3. Добавить в `Settings` версионируемые поля публикации; мигрировать существующие `analytics_channels` в новые профили, не удаляя исходные данные.
4. Реализовать команды bridge: собрать готовые пакеты, добавить/удалить задачу, массово назначить канал/видимость/время, сохранить пресет, журнал.
5. Реализовать чистый планировщик «сетки»: период в минутах, режимы равномерного разнесения/совпадений/синхронного выхода, стабильные смещения, ручные блокировки и массовый сдвиг, предпросмотр и расчёт нужной суточной квоты.
6. Прогнать `pytest tests/test_youtube_publisher.py` и весь набор тестов.

## Этап 2 — экран публикации и интеграция результатов

**Файлы**

- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Create: `studio-ui-remotion-verify/src/ui/publication.css`
- Modify: `studio-ui-remotion-verify/src/ui/analytics.css`
- Create/modify: UI unit tests if current harness supports them

1. Расширить `NewsFlowSnapshot` отдельным `publication` DTO.
2. Добавить пункт «Публикация YouTube» первым в группе «ПУБЛИКАЦИЯ».
3. Создать обзор с «линией эфира», числом готовых MP4 и ближайшими задачами.
4. Создать очередь с выделением нескольких задач, массовыми действиями, временем/видимостью, пресетами и подробной временной линией статусов.
5. Реализовать пустые состояния и сообщения, различающие отсутствие готовых MP4, отсутствие подключённого канала и ошибку задачи.
6. Проверить `pnpm run typecheck`/`pnpm build` и вручную открыть экран в desktop-приложении.

## Этап 3 — каналы, OAuth и Studio

**Файлы**

- Modify: `scriptor/youtube_publisher.py`
- Modify: `scriptor/bridge.py`
- Modify: `scriptor/config.py`
- Modify: `studio-ui-remotion-verify/electron/main.ts`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `requirements.txt`
- Modify: `tests/test_youtube_publisher.py`

1. Добавить тесты интерфейса OAuth-клиента на поддельном браузере/HTTP-клиенте: запрос scope, обработка callback, отказ, истечение токена, безопасное удаление.
2. Добавить официальный Google OAuth desktop flow с системным браузером и localhost callback; токены сохранять защищённо, раздельно по profile ID.
3. Реализовать запрос `channels.list(mine=true)` для фиксации channel ID, имени и URL Studio.
4. Добавить команды «подключить», «проверить/обновить», «переподключить», «отключить», «открыть Studio».
5. В UI показать статус доступов публикации, базовой и денежной аналитики с понятным объяснением.
6. API-клиент и UI проверить на фикстурах; реальный OAuth проверить только после получения JSON пользователя.

## Этап 4 — загрузка, планирование и обработка

**Файлы**

- Modify: `scriptor/youtube_publisher.py`
- Modify: `scriptor/bridge.py`
- Modify: `studio-ui-remotion-verify/electron/main.ts`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `tests/test_youtube_publisher.py`

1. Написать тесты переходов `ready → uploading → processing → awaiting-publication/published` и ошибок возобновляемой загрузки.
2. Добавить резюмируемую загрузку `videos.insert`, metadata и обложку `thumbnails.set`.
3. Добавить worker очереди, который проверяет расписание, лимиты пресета и состояние обработки ролика.
4. Начать worker из Electron так же, как существующую очередь монтажа: интерфейс не ждёт загрузку.
5. Отдельно обработать недоступность OAuth, отсутствие MP4, квоту, обработку YouTube и приватный режим по умолчанию.
6. Проверить тестовый upload только в private-режиме после предоставления OAuth.

## Этап 5 — аналитика и сигналы роста

**Файлы**

- Modify: `scriptor/youtube_publisher.py`
- Modify: `scriptor/bridge.py`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/publication.css`
- Modify: `tests/test_youtube_publisher.py`

1. Написать тесты подсчёта просмотров в час, окна 48 часов, отсутствующих точек и расчёта сигнала роста.
2. Сохранять компактные локальные снимки общественных счётчиков, с ограничением срока хранения.
3. Добавить запросы Analytics API для роликов/каналов, отдельный денежный scope и задания YouTube Reporting API для ежедневной загрузки CSV-истории.
4. Создать экран аналитики с фильтрами «все каналы / один канал / группа», периодами 1 час, 24 часа, 48 часов, 7, 28 и 30 дней; строить отдельные и суммарные графики просмотров, просмотров в час, подписчиков, публикаций и дохода.
5. Для канала создать развёрнутый отчёт с цветными метриками и фильтруемыми таблицами по роликам, источникам трафика, странам, устройствам/ОС, местам просмотра, аудитории и финансовым данным; подписывать источник и фактическую дату обновления каждой секции.
6. На суммарном доходе явно отмечать покрытие: «все каналы с финансовым доступом» или число каналов, по которым доход недоступен.
7. Явно отделить «нет доступа к доходу» от вывода о монетизации.

## Этап 6 — «Прогрев» и журнал

**Файлы**

- Modify: `scriptor/youtube_publisher.py`
- Modify: `scriptor/bridge.py`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/publication.css`
- Modify: `tests/test_youtube_publisher.py`

1. Написать тесты выбора каналов, создания отчёта, сохранения журнала и отсутствия неявных публичных действий.
2. Добавить задания анализа последних роликов и метрик выбранных каналов, без автоматических likes/comments.
3. Добавить UI «все/выбранные каналы», запуск/остановку, отчёт и черновики для ручного подтверждения.
4. Связать все события публикации, OAuth, аналитики и прогрева с единым журналом.

## Этап 7 — сборка и проверка как пользователь

1. Запустить все Python тесты и UI build/typecheck.
2. Собрать desktop-приложение.
3. Открыть собранное приложение; проверить очередь, пресеты, удаление, массовые действия, Studio, статусы, графики с фикстурами и пустые состояния.
4. После получения OAuth JSON и тестового канала — выполнить реальное подключение и приватный тестовый upload, затем вручную проверить Studio.
