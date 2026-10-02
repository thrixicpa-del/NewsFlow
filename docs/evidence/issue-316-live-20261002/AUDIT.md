# Issue #316 — real STANDARD/TABLOID baseline

Run: `issue316-cover-live-20261002`, 2 October 2026 (Europe/Minsk).
Runtime source: `a2982ba58efb4cd0bc9d7ad795b7067cf40ecaed`.
Configured model: `gpt-5.4-mini`; all 17 actual responses report
`gpt-5.4-mini-2026-03-17`. Route: OpenAI `POST /v1/responses`.
This is an actual paid test authorized by the user, not mocked generation.

## Protocol and evidence

Four fixed synthetic topics, STANDARD then TABLOID, through the real
`generate_cover_texts` → headline/subheadline handlers, validation, selection and
disposable persistence. No fixture was rewritten after observing a response.
Headline variations and structure IDs match between modes for each topic.
Subheadline requests use the headline selected by that mode, as in the normal app.
The same disposable profile retains recent-pattern memory across cases; this is
a bounded baseline, not a repeated/statistically controlled benchmark.

`ledger.json` contains the **actual post-adapter payload** and only visible
response text, IDs, model, status and usage; Authorization and hidden reasoning
are excluded. `results.json` contains all eight persisted cover rows and their
full candidate/selection evidence. `dataset.json` gives the exact synthetic
input. These inputs are diagnostic fixtures, not independently verified news.
No account settings or real credential records are part of this package.

There were 16 initial text-stage requests and one normal semantic subheadline
repair for the protest/TABLOID pair: **17 paid HTTP attempts**, no transport/SDK
retry or additional full-run selection. Input tokens: **19,919**; output tokens:
**1,143**. All responses: `completed`, `incomplete_details=null`. Output limits,
temperature and tools were omitted by the adapter; provider defaults are UNKNOWN.
The client-side 24-request cap was not reached. No new paid requests were made
after the production guard warning.

## Complete selected copy

| Topic | Mode | Headline | Subheadline |
| --- | --- | --- | --- |
| Tariffs | STANDARD | Трамп поднял пошлины | Китай ввёл ответные сборы |
| Tariffs | TABLOID | Ответ Пекина Трампу | Дороже станет весь импорт |
| Tomato prices | STANDARD | Цены не падают | Покупатели жалуются в магазинах |
| Tomato prices | TABLOID | Помидоры всё ещё дорогие | Покупатели недовольны ценой |
| Protest/arrest | STANDARD | Красная площадь: арест | Дело после антивоенной акции |
| Protest/arrest | TABLOID | Москва: протест под арестом | Мужчина вышел с плакатом |
| Software update | STANDARD | Пользователи без документов | Инженеры продолжают восстановление |
| Software update | TABLOID | Часть документов недоступна | Альфа вернула старую версию |

## Editorial findings — QUALITY=FAIL

All rows have READY and all selected local evaluations assert naturalness and
factual passes. Reading the actual copy does **not** support blanket acceptance.

1. Tariffs/TABLOID: **«Дороже станет весь импорт»** widens a fixture about specific
   Chinese/American goods and higher duties into a claim about **all** imports.
   This was visible candidate #3 in HTTP request #4 and was promoted over
   **«Импортёры платят больше»**, a narrower supported candidate in the same answer.
   The persisted selected candidate has `factual_pass=true`, `emotion_score=1`
   and `literalness_score=0`. Lexical overlap is not factual entailment.
2. Prices/STANDARD: **«Покупатели жалуются в магазинах»** adds an unsupported place
   where the complaints occurred; the fixture states complaints and says stores
   have not reduced prices, not that complaints happened there. This candidate
   was visible in HTTP #6 and persisted unchanged. Provider invention and local
   acceptance both contributed.
3. Protest/TABLOID: **«Москва: протест под арестом»** attributes a person's arrest
   to the abstract protest. It is awkward rather than plain literal copy.
   HTTP #11 contains this candidate, while the fixture says a man was arrested.
   Persisted evaluation gives naturalness=true, hook=2 and emotion=2. Thus this
   is not text corruption between provider response and storage.
4. Technology/TABLOID: **«Часть документов недоступна»** plus
   **«Альфа вернула старую версию»** is factual/plain, but reads like a status
   summary, not a materially sharper hook than STANDARD. This is an editorial
   weakness, not grounds to invent deleted/lost documents or other new harm.
5. Prices/TABLOID is also plain but not clearly stronger than STANDARD. Different
   strings alone do not establish stronger clickability. Actual CTR is UNKNOWN;
   there was no publication or audience experiment.

The raw model also offered weak phrases such as **«Помидоры не падают»**,
**«Цены стоят мёртво»**, **«Покупатели уже злые»** and
**«Документы снова под ударом»**. They were not selected in the corresponding
rows, but show that the prompt does not guarantee natural literal candidates.
There is no claim that this model can never satisfy the task; this particular
model+contract+selection baseline failed the requested editorial acceptance.

## Reproducible cause versus limits

`_cover_word_editorial_evaluation` in `scriptor/bridge.py` estimates grounding,
naturalness, specificity and emotion largely through word stems/markers.
`_cover_word_editorial_selection_score` promotes emotion/hook before specificity
and literalness in TABLOID. An awkward phrase with more arrest/protest markers
can outrank a literal supported phrase. The real recorded rows demonstrate this
limitation; merely adding more style words or passing existing mock tests is
not proof of correction. The style flag reached the actual prompt and the model:
lost UI tabloidMode is not the demonstrated cause here.

No business-source fix has yet been accepted by this baseline evidence commit.
TXT triple import and its productionItemId regressions remain implementation
work under #316. This report must not be presented as completion of that feature
or proof of improved live quality after a fix.

## Isolation warning and safe replay

The live test began by asserting that `config_path()` is inside the official
runner's disposable TEST_ROOT. Production credentials were read explicitly and
read-only; only an in-memory credential and configured model were reused. All
fixture state and cover-library writes used disposable storage. No FastGen,
OAuth, YouTube or image-generation calls were issued by this harness.

Nevertheless, `tests/run_isolated.py` returned
**PRODUCTION_WRITE_GUARD=FAIL changed=settings.json** after the live test.
There was a running NewsFlow Studio application. A read-only follow-up found no
`Live acceptance` credential label or synthetic fixture IDs in production, and
the contemporary LKG/primary difference included `seo_queue`, unrelated to this
harness. Concurrent app activity is a plausible explanation, **not conclusive
attribution of the historical write**. No user settings were restored, replaced
or overwritten in response to this warning. Overall live isolation acceptance
must remain FAIL/attribution UNKNOWN rather than being relabeled PASS.

`replay_safe.py` replays the 17 captured visible responses with a synthetic
credential and network replaced. It asserted **all 17 request payloads exactly
match** the original ledger and reproduced all eight persisted outputs.
Replay: **1 PASS, production-write guard PASS, real paid calls=0**.
The inherited harness prints REAL_HTTP_ATTEMPTS=17 while replaying mocked
requests; in this offline context that counts intercepted requests only. It is
not 17 additional paid calls and not a new model-quality test.

## File integrity

Original byte hashes (SHA-256):

Git treats the JSON files as text and normalizes CRLF to LF in its text view.
The accompanying `issue-316-live-20261002-original-bytes.zip` preserves the
original file bytes; use that archive when checking the hashes below. No
scenario/model text was edited during this line-ending normalization.

- `dataset.json`: `690bcf8480024fe1182c86a6d578b4d3c41e5f245095678f3cc8c410574ae5ba`
- `manifest.json`: `a06dfcb49ce39539872e495f4c90b059c1b636fd8764047e32cbca7650779c5f`
- `ledger.json`: `0df47db722c583fdbb5cec8df682e37cad2bd92615b11ec21dec8654c1ac98dc`
- `results.json`: `e611c7eb30943bf09550d0ef0dea23af73ec428dd79612bc525e6a125660344d`
- `run_live.py`: `a9ad28dac888413ff21b8736e009525626029c29705a298d6bdd589d2e9b2d2b`

No merge, Core rebuild, Core lock/hash change or EXE packaging.
