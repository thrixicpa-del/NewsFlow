# Editorial reading and coverage — D1–D4

This review is performed after reading all four complete visible responses.  A
coverage row says whether the fixed fixture step was delivered in the exact
post-adapter Writer input and how the response treated it.  It is an editorial
diagnostic, not a runtime veto and did not trigger a retry or rewrite.

## D1 — P1 with full current template

The opening begins with the event.  The third sentence is the required single
disclosure: “**Для вымышленной части этой истории это реконструкция, а не
подтверждённая хроника**”.  There is no premature whole-story ending.  The
prose is chronological and covers the 16 assigned steps.  It has a few
interpretive connectors (“Это и стало первым переломом”, “Это важно”), but they
follow concrete action and do not replace a fixture event.  At 2,516 characters
it misses the local length guidance; completion status and 632 output tokens do
not indicate truncation.

| Step | Delivered | Response paragraph / evidence | Assessment |
| --- | --- | --- | --- |
| E01.1–E01.2 | Yes | P1: “просел напор… звонки из двух кварталов” | Expanded |
| E01.3–E01.4 | Yes | P2: “сверил адреса… общий отрезок… отправили выездную бригаду… соседние линии оставили” | Expanded |
| E02.1–E02.2 | Yes | P3: “прошла от первого контрольного узла до второго… вода вышла на поверхность” | Expanded |
| E02.3–E02.4 | Yes | P3: “отметили границы… передали… проезд… закрыли” | Expanded |
| E03.1–E03.2 | Yes | P4: “передал смене точный перечень узлов… закрыла подачу” | Expanded |
| E03.3–E03.4 | Yes | P4: “выход воды прекратился… два квартала… участок… ремонтникам” | Expanded |
| E04.1–E04.2 | Yes | P5: “по одной доступной площадке… две машины с запасом воды” | Expanded |
| E04.3–E04.4 | Yes | P5–P6: “сообщили адреса… срок… не объявляли”; “обе точки… начали работать” | Expanded |

## D2 — P1 with short diagnostic template

D2 is more direct and has less commentary, but is substantially shorter at
1,783 characters.  Its third sentence gives a clear disclosure: “**Это
вымышленная учебная история о восстановлении водоснабжения**”.  The response
does not add sources, names, causes, loss amounts, or real-world attribution.

| Step | Delivered | Response paragraph / evidence | Assessment |
| --- | --- | --- | --- |
| E01.1–E01.2 | Yes | P1: “сигнал о падении давления… два обращения жителей” | Compressed but complete |
| E01.3–E01.4 | Yes | P1: “сверил адреса… один общий участок… направил… не отключая остальные” | Compressed but complete |
| E02.1–E02.2 | Yes | P2: “от первого… до второго… выход воды на поверхность” | Expanded |
| E02.3–E02.4 | Yes | P2: “обозначили границы… проезд закрыли” | Expanded |
| E03.1–E03.2 | Yes | P3: “перечень узлов… закрыли подачу именно к нему” | Expanded |
| E03.3–E03.4 | Yes | P3: “выход воды прекратился… отключение двух кварталов… участок ремонтникам” | Expanded |
| E04.1–E04.2 | Yes | P4: “по одной… площадке… две машины” | Expanded |
| E04.3–E04.4 | Yes | P4: “адреса… время… срок… не объявляли”; “точки открылись” | Expanded |

## D3 — P3 with full current template and fixed prefix

D3 does not repeat the opening disclosure, as required for FINAL.  It gives a
distinct terminal result rather than a question: “**оба квартала начинают
работать от восстановленной сети**”.  The response stays event-led; a few
general explanations of the tests are brief connectors, not separate analytic
paragraphs.  At 3,299 characters it remains below the local target but all
four P3 atoms and their results are present.

| Step | Delivered | Response paragraph / evidence | Assessment |
| --- | --- | --- | --- |
| E09.1–E09.2 | Yes | P1: “дают пробную подачу… идёт вдоль новых соединений” | Expanded |
| E09.3–E09.4 | Yes | P2: “показания… не скачут… бригадир… без обнаруженной утечки” | Expanded |
| E10.1–E10.2 | Yes | P3: “завершают промывку… отбирают пробы” | Expanded |
| E10.3–E10.4 | Yes | P4: “соответствуют… смена даёт разрешение… точки… продолжают” | Expanded |
| E11.1–E11.2 | Yes | P5: “сначала… первый, затем… второй… из одного дома… обращение” | Expanded |
| E11.3–E11.4 | Yes | P6: “домовой узел… закрыт… узел открывают… повторного повреждения… нет” | Expanded |
| E12.1–E12.2 | Yes | P7: “подтверждения… обоих кварталов… водоканал фиксирует… передаёт” | Expanded |
| E12.3–E12.4 | Yes | P7: “закрывает временную выдачу… машины покидают… контроль… на ночь” | Expanded |

## D4 — P3 with short diagnostic template and fixed prefix

D4 covers the same terminal chain, but its first paragraph contains an
unnecessary and grammatically awkward warning: “**Вымышленная история здесь
показывает только учебной случай**”.  FINAL was expressly told not to repeat a
warning, so this is a Writer instruction-following failure.  It neither changes
the fixture nor creates an extra provider call.  The terminal result itself is
still concrete: the utility closes temporary points after both quarters,
including the last house, are restored.

| Step | Delivered | Response paragraph / evidence | Assessment |
| --- | --- | --- | --- |
| E09.1–E09.2 | Yes | P1: “подали пробную воду… прошла весь стык” | Expanded |
| E09.3–E09.4 | Yes | P1: “давление не прыгало… признаков… нет” | Expanded |
| E10.1–E10.2 | Yes | P2: “завершили промывку… отобрали пробы” | Expanded |
| E10.3–E10.4 | Yes | P2: “пробы соответствуют… смена… разрешение… точки… продолжали” | Expanded |
| E11.1–E11.2 | Yes | P3: “сначала… первый… затем… второй… отдельное обращение” | Expanded |
| E11.3–E11.4 | Yes | P3: “домовой узел… остался закрыт… открыли… повреждения магистрали… нет” | Expanded |
| E12.1–E12.2 | Yes | P4: “подтверждения… обоих кварталов… итоговый статус” | Expanded |
| E12.3–E12.4 | Yes | P4: “завершили отпуск воды… оба квартала… восстановленную сеть… контроль… на ночь” | Expanded |

## Comparison and conclusion

| Question | Evidence-backed answer | Limit |
| --- | --- | --- |
| Did the Writer receive full current material? | Yes. Every assigned fixture step appears in the post-adapter payload and is traceable to prose above. | It says nothing about the quality of a Planner-generated map. |
| Can the current Writer disclose and narrate concrete material with the full template? | Yes in D1 and D3. D1 has the required disclosure; D3 carries all terminal events without repeating it. | One response per condition is screening evidence, not a reliability rate. |
| Is the short template uniformly better? | No. D2 is more concise, but D4 repeats a forbidden final warning and is less natural. | The templates differ in multiple content/style instructions, not only length. |
| Is a transport limit the cause of short output? | No evidence of that: all are completed, `incomplete_details=null`, and output tokens are far below 5,120. | This does not prove a model will comply with length in every future response. |
| Is there a confirmed runtime defect to fix now? | No. The controlled Writer boundary transmits and uses strong concrete material. | Existing A3 still shows the Planner can create a weak event map; D1–D4 do not identify a deterministic source defect that can be safely changed without a new Planner experiment. |

Therefore no Scenario business logic was changed after D1–D4 and **R1 was not
spent**.  Running a full political pipeline on the same runtime would be a
second chance, not validation of a demonstrated repair; the fixed task protocol
explicitly forbids that use of the remaining budget.  `Writer regeneration=0`.
