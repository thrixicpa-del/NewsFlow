# Ideas Engine — external quality review package

Status: first working version; **not accepted yet**. This package is the stopping point for external editorial review.

## How this sample was made

- Real public YouTube search signals were fetched through the configured YouTube Data API.
- The configured ChatGPT route generated the `Topic → Angle → Title` candidates with the event bundle included in its prompt.
- The production selector accepted only candidates that could be tied to an event bundle; it rejected unsupported or weak candidates instead of filling the requested quota.
- The list below contains every accepted item from the chronological review batch across seven Directions: **20 accepted out of 30 generated candidates**. It is not a hand-picked “best of” list.
- Search-result titles are an evidence lead, not an independent verification of every claim. External review should pay particular attention to where a headline inherits framing from a source title.

## Regression and state checks performed before this review

- Python regression suite: **309 tests passed**.
- Ideas-specific tests: source grounding, legacy migration, persistence/reload, Directions → scenarios handoff, semantic duplicate handling, independent angles for one event, and unsourced-title rejection.
- TypeScript typecheck passed.
- Ideas UI contract passed: **26 controls** found.
- The packaged `core-bin` is intentionally not treated as current for this review: it predates the source changes and was not rebuilt, because the agreed stopping point is this editorial review.

## OLD RESULT

The previous title-only queue did not retain the event, Topic, Angle, source context, or script contract. A representative chronological fragment from the existing queue:

1. `Удар по военным заводам Украины: что осталось после прилёта`
2. `РФ бьёт по оборонке Украины: почему это стало новым давлением`
3. `Военные заводы Украины под ударом: какой риск теперь скрывают власти`
4. `Что повредил удар РФ по заводам Украины и как это скажется дальше`
5. `Украинская оборонка в огне: удар по заводам может изменить фронт`

The old form could not distinguish an original angle from a rewording, nor could the script generator see what claim required support.

## NEW RESULT

Each accepted row below is a structured Production Item. `Nearest duplicate` means an accepted item in the same live batch; where none appears, no accepted near-duplicate survived the gate.

### Item 01

Direction: Украина — удар РФ по военным заводам  
Topic: Атака на военные объекты Украины  
Angle: конфликт интересов и ответный удар  
Title: Ответный удар или новая эскалация: что бьют по Украине сейчас  
Character count: 61  
Hook family: event  
Click score: 83  
Novelty score: 100  
Scriptability score: 80  
Supporting event/context: «ВС РФ нанесли массированный удар по объектам на территории Украины».  
Script requirements:

- объяснить атаку на военные объекты Украины;
- назвать участников: ЕС;
- раскрыть подтверждённый контекст и угол «конфликт интересов и ответный удар».

Nearest duplicate: none accepted in this batch.  
Similarity: n/a.

### Item 02

Direction: Украина — удар РФ по военным заводам  
Topic: Массированный удар по территории Украины  
Angle: объяснение масштаба атаки и её смысла  
Title: Массированный удар по Украине: зачем били именно по заводам  
Character count: 59  
Hook family: event  
Click score: 87  
Novelty score: 100  
Scriptability score: 85  
Supporting event/context: «ВС РФ нанесли массированный удар по объектам на территории Украины».  
Script requirements:

- объяснить масштаб атаки;
- назвать участников: ЕС;
- отделить подтверждённый контекст от трактовки «зачем».

Nearest duplicate: Item 01, but angle differs.  
Similarity: below duplicate threshold.

### Item 03

Direction: Трамп-Зеленский — давление и переговоры  
Topic: Встреча Зеленского, Путина и Трампа: возможный формат и напряжение  
Angle: вопрос и поворот  
Title: Зеленский, Путин и Трамп: кто на самом деле не готов к встрече  
Character count: 62  
Hook family: event  
Click score: 87  
Novelty score: 100  
Scriptability score: 85  
Supporting event/context: «Трамп и Зеленский — условие для мира»; «Встреча Зеленского, Путина и Трампа. Кто испугался?».  
Script requirements:

- назвать Трампа и Зеленского;
- показать, что известно о формате встречи;
- не выдавать вопросительный хук за установленный факт.

Nearest duplicate: Item 04.  
Similarity: below duplicate threshold.

### Item 04

Direction: Трамп-Зеленский — давление и переговоры  
Topic: Трамп, Зеленский и возможная встреча с Путиным  
Angle: решение и скрытый риск  
Title: Трамп толкает к переговорам: Зеленский рискует оказаться в ловушке формата  
Character count: 74  
Hook family: event  
Click score: 83  
Novelty score: 100  
Scriptability score: 80  
Supporting event/context: «Трамп и Зеленский — условие для мира».  
Script requirements:

- назвать Трампа и Зеленского;
- объяснить, какие условия подтверждены;
- маркировать «ловушку формата» как анализ, а не факт.

Nearest duplicate: Item 03.  
Similarity: below duplicate threshold.

### Item 05

Direction: Трамп-Зеленский — давление и переговоры  
Topic: Трамп и Зеленский: давление вокруг мирных переговоров  
Angle: контекст, конфликт интересов и проверка сценария  
Title: Переговоры Трампа и Зеленского: мирный план есть, но цена для Киева туманна  
Character count: 75  
Hook family: event  
Click score: 83  
Novelty score: 100  
Scriptability score: 80  
Supporting event/context: «Трамп и Зеленский — условие для мира».  
Script requirements:

- объяснить переговорный контекст;
- назвать Трампа и Зеленского;
- не утверждать наличие конкретного плана без отдельного подтверждения.

Nearest duplicate: Item 03.  
Similarity: below duplicate threshold.

### Item 06

Direction: Россия — депортации и диаспоры  
Topic: Выдворение главы азербайджанской диаспоры Москвы  
Angle: событие с конфликтом интересов и последствием для общины  
Title: Главу азербайджанской диаспоры Москвы депортировали: что это значит для общины  
Character count: 78  
Hook family: event  
Click score: 95  
Novelty score: 100  
Scriptability score: 90  
Supporting event/context: «У главы московской диаспоры азербайджанцев отобрали российский паспорт»; «Главу азербайджанской диаспоры Подмосковья депортировали из России».  
Script requirements:

- отделить решение о паспорте от сообщения о депортации;
- раскрыть статус и последствия для общины;
- не делать юридических выводов без документа или комментария юриста.

Nearest duplicate: Item 08.  
Similarity: below duplicate threshold.

### Item 07

Direction: Россия — депортации и диаспоры  
Topic: Проверка законности депортации и обжалования решений  
Angle: объяснение через юридический риск и вопрос  
Title: Депортация мигрантов из России: что можно обжаловать и где скрыт риск  
Character count: 69  
Hook family: event  
Click score: 87  
Novelty score: 100  
Scriptability score: 85  
Supporting event/context: «Массовая депортация мигрантов в аэропорту Домодедово»; материал о сроках обжалования выдворения.  
Script requirements:

- не давать персональную юридическую консультацию;
- разделить общий порядок обжалования и конкретный случай;
- показать проверяемые источники права.

Nearest duplicate: none accepted in this batch.  
Similarity: n/a.

### Item 08

Direction: Россия — депортации и диаспоры  
Topic: Российский паспорт у главы московской диаспоры азербайджанцев  
Angle: скрытый риск и поворот вокруг статуса и последствий  
Title: У главы московской диаспоры азербайджанцев отобрали паспорт: что дальше  
Character count: 71  
Hook family: event  
Click score: 95  
Novelty score: 100  
Scriptability score: 90  
Supporting event/context: «У главы московской диаспоры азербайджанцев отобрали российский паспорт».  
Script requirements:

- объяснить, что именно подтверждено источником;
- не подменять отзыв паспорта депортацией;
- раскрыть последствия только при наличии подтверждённых данных.

Nearest duplicate: Item 06.  
Similarity: below duplicate threshold.

### Item 09

Direction: Иран — Ормузский пролив  
Topic: Иран и Ормузский пролив: возможное расширение контроля и реакция США  
Angle: конфликт интересов и международный риск  
Title: Иран может усилить контроль не только над Ормузским проливом — что это значит?  
Character count: 78  
Hook family: question  
Click score: 73  
Novelty score: 100  
Scriptability score: 80  
Supporting event/context: «Иран будет контролировать не только Ормузский пролив».  
Script requirements:

- назвать Иран и Трампа только в пределах источника;
- объяснить, что означает формулировка о контроле;
- не превращать прогноз в факт.

Nearest duplicate: Item 10.  
Similarity: below duplicate threshold.

### Item 10

Direction: Иран — Ормузский пролив  
Topic: Иран и Ормузский пролив: спор о пределах влияния Тегерана  
Angle: скрытый риск для морских маршрутов и торговли  
Title: Ормузский пролив под давлением: зачем Ирану расширять контроль  
Character count: 62  
Hook family: event  
Click score: 83  
Novelty score: 100  
Scriptability score: 80  
Supporting event/context: «Иран будет контролировать не только Ормузский пролив».  
Script requirements:

- описать подтверждённое заявление;
- отделить торговые последствия от допущений;
- раскрыть угол «риск для маршрутов».

Nearest duplicate: Item 09.  
Similarity: below duplicate threshold.

### Item 11

Direction: Иран — Ормузский пролив  
Topic: Иран и Ормузский пролив: заявление, вызвавшее новый спор с Вашингтоном  
Angle: поворот в отношениях с США и фигура Трампа  
Title: Трамп в центре спора: Иран и Ормузский пролив снова в фокусе  
Character count: 60  
Hook family: event  
Click score: 91  
Novelty score: 100  
Scriptability score: 90  
Supporting event/context: «Иран будет контролировать не только Ормузский пролив».  
Script requirements:

- не приписывать Трампу действие без источника;
- показать, чем вызван спор;
- раскрыть международный контекст.

Nearest duplicate: Item 09.  
Similarity: below duplicate threshold.

### Item 12

Direction: Иран — Ормузский пролив  
Topic: Иран и Ормузский пролив: спор вокруг формулировки о контроле  
Angle: вопрос о масштабе и границах влияния  
Title: Не только пролив: Иран заявил о контроле шире — как это понимать  
Character count: 64  
Hook family: event  
Click score: 87  
Novelty score: 100  
Scriptability score: 85  
Supporting event/context: «Иран будет контролировать не только Ормузский пролив».  
Script requirements:

- процитировать или пересказать исходную формулировку точно;
- объяснить диапазон возможных трактовок;
- не делать выводов о реальной юрисдикции.

Nearest duplicate: Item 10.  
Similarity: below duplicate threshold.

### Item 13

Direction: Европа — энергетический кризис  
Topic: Топливное давление на европейцев  
Angle: последствие  
Title: Топливный кризис в Европе: как он меняет повседневную жизнь людей  
Character count: 65  
Hook family: event  
Click score: 87  
Novelty score: 100  
Scriptability score: 85  
Supporting event/context: «Европа между молотом и наковальней: разрыв с США и новый топливный кризис».  
Script requirements:

- не обобщать ситуацию на всю Европу по одному материалу;
- показать конкретные подтверждённые последствия;
- раскрыть угол «повседневная жизнь» через проверяемые примеры.

Nearest duplicate: Item 14.  
Similarity: below duplicate threshold.

### Item 14

Direction: Европа — энергетический кризис  
Topic: Ответ ЕС на энергетический кризис  
Angle: решение  
Title: В ЕС ищут ответ на энергетический кризис: какие меры обсуждают сейчас  
Character count: 69  
Hook family: event  
Click score: 83  
Novelty score: 100  
Scriptability score: 80  
Supporting event/context: «Энергетический кризис в Европе. Последствия для Украины».  
Script requirements:

- перечислить только реально обсуждаемые меры;
- назвать ЕС;
- отличить обсуждение от принятого решения.

Nearest duplicate: Item 15.  
Similarity: below duplicate threshold.

### Item 15

Direction: Европа — энергетический кризис  
Topic: Риски углубления энергетического кризиса в Европе  
Angle: скрытый риск  
Title: Энергетический кризис в Европе: какой риск может ударить следом  
Character count: 63  
Hook family: event  
Click score: 87  
Novelty score: 100  
Scriptability score: 85  
Supporting event/context: «Энергетический кризис в Европе. Последствия для Украины».  
Script requirements:

- показать, на чём основан риск;
- назвать ЕС в источниковом контексте;
- не представить прогноз как подтверждённое последствие.

Nearest duplicate: Item 14.  
Similarity: below duplicate threshold.

### Item 16

Direction: НАТО — реакция на эскалацию  
Topic: Реакция НАТО на новую эскалацию вокруг России  
Angle: объяснение: к чему ведут угрозы и сигналы с обеих сторон  
Title: НАТО и Россия: сдерживание или путь к новой эскалации?  
Character count: 54  
Hook family: question  
Click score: 73  
Novelty score: 100  
Scriptability score: 80  
Supporting event/context: «Сдерживание или эскалация. О чём на самом деле говорят угрозы НАТО в адрес России?».  
Script requirements:

- назвать НАТО, Россию и ЕС в пределах источника;
- сравнить сигналы сторон;
- не отвечать на вопрос в заголовке неподтверждённым прогнозом.

Nearest duplicate: Item 17.  
Similarity: below duplicate threshold.

### Item 17

Direction: НАТО — реакция на эскалацию  
Topic: Ответ НАТО на инциденты и усиление военного присутствия в Европе  
Angle: последствие: что меняется после дронов в Польше и истребителей в Эстонии  
Title: Дроны в Польше, истребители в Эстонии: как НАТО реагирует на рост напряжения  
Character count: 76  
Hook family: event  
Click score: 95  
Novelty score: 100  
Scriptability score: 90  
Supporting event/context: «Дроны в Польше, истребители в Эстонии, договор Путина: к чему ведёт эскалация между Россией и НАТО».  
Script requirements:

- проверить каждый инцидент отдельно;
- назвать Путина, НАТО и ЕС только если они подтверждены источниками;
- раскрыть реакцию, а не склеивать события в одну причинную цепь.

Nearest duplicate: Item 16.  
Similarity: below duplicate threshold.

### Item 18

Direction: Трамп-Путин — контакты и угрозы  
Topic: Контакты Трампа и Путина на фоне обсуждения прекращения огня  
Angle: ключевой вопрос: возможен ли сдвиг к перемирию или это лишь жёсткий торг  
Title: Трамп и Путин в одной комнате: переговоры о прекращении огня в фокусе  
Character count: 69  
Hook family: event  
Click score: 91  
Novelty score: 100  
Scriptability score: 90  
Supporting event/context: «Вы согласитесь на прекращение огня? Путин и Трамп в комнате для прессы».  
Script requirements:

- назвать Трампа, Путина и ЕС в пределах источника;
- отделить вопрос журналиста от позиции сторон;
- не заявлять о достигнутом перемирии.

Nearest duplicate: none accepted in this batch.  
Similarity: n/a.

### Item 19

Direction: Трамп-Путин — контакты и угрозы  
Topic: Публичные реплики и давление вокруг Трампа  
Angle: неожиданный эмоциональный эпизод как контраст к большой политике  
Title: Сын Илона Маска велел Трампу замолчать — неловкий момент в кадре  
Character count: 64  
Hook family: statement  
Click score: 73  
Novelty score: 100  
Scriptability score: 80  
Supporting event/context: «Четырёхлетний сын Илона Маска попросил Трампа закрыть рот».  
Script requirements:

- не связывать эпизод с переговорами Трампа и Путина без доказательств;
- дать возраст и формулировку только при подтверждении;
- объяснить, почему это отдельный ролик, а не политический вывод.

Nearest duplicate: none accepted in this batch.  
Similarity: n/a.

### Item 20

Direction: Трамп-Путин — контакты и угрозы  
Topic: Экономические сигналы после контактов и переговоров вокруг Путина  
Angle: что рынки читают в политических встречах и почему это важно проверить  
Title: Акции Газпрома растут: что говорят итоги встречи Путина и Помпео  
Character count: 64  
Hook family: event  
Click score: 95  
Novelty score: 100  
Scriptability score: 90  
Supporting event/context: «Взлёт акций Газпрома, итоги встречи Путина и Помпео, отчёт ОПЕК».  
Script requirements:

- проверить дату, участников и сам факт встречи;
- отделить рыночную корреляцию от причинности;
- не выносить финансовый прогноз без источника.

Nearest duplicate: none accepted in this batch.  
Similarity: n/a.

## REJECTED EXAMPLES

These are actual live-batch candidates, retained rather than silently replaced:

| Direction | Candidate | Rejection reason |
| --- | --- | --- |
| Украина — удар РФ по военным заводам | «Военные заводы Украины под ударом: чем это грозит фронту» | factual support insufficient |
| Украина — удар РФ по военным заводам | «Поражены военные заводы: Украина может столкнуться с дефицитом» | factual support insufficient |
| Трамп-Зеленский — давление и переговоры | «Трамп давит на Зеленского: мирная сделка может выйти боком Украине» | factual support insufficient |
| Трамп-Зеленский — давление и переговоры | «Трамп меняет тон: что это значит для Зеленского и переговоров о мире» | factual support insufficient |
| Армения-Азербайджан — мирный процесс и Карабах | «Карабах и переговоры: почему тема по-прежнему вызывает напряжение» | low scriptability |
| Европа — энергетический кризис | «Европа ищет газовый баланс: хватит ли запасов без новых потрясений» | low scriptability |
| Европа — энергетический кризис | «Европа спорит о новых поставках энергии: где проходит красная линия» | low scriptability |
| НАТО — реакция на эскалацию | «О чём предупреждает НАТО: скрытый риск в ответе на эскалацию» | factual support insufficient |

The deterministic regression suite also exercises `duplicate`, `vague`, `> 100 characters`, and `question limit` gates. No accepted duplicate was present in this live sample; that is a result of the duplicate gate, not a manual omission.

## Questions for the external editor

1. Are the accepted angles genuinely independent enough to justify separate scripts, especially Items 03–05 and 09–12?
2. Are click scores too generous for the weakest accepted hooks (notably Items 09, 16, and 19)?
3. Does the source-title evidence threshold need stronger source-quality weighting before production use?
4. Which accepted titles cross from useful uncertainty into suggestive or misleading framing?
5. Should specific entities, geography, and event families be extracted more accurately before scoring the portfolio?

---

No further FlowNews work should be considered accepted until this file has received external editorial review and the user confirms the next iteration.
