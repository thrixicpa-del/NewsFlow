# NewsFlow deterministic golden dataset

`tests.golden_dataset.materialize_golden_dataset()` creates the compact,
synthetic `newsflow-golden-v1` fixture under an explicit
`NEWSFLOW_TEST_ROOT`. It is deliberately generated rather than copied from a
user library: no production topic, script, face, cover, audio, footage,
channel, credential, or queue state belongs in this dataset.

The manifest provides fixed IDs and expected mappings for a single Topic →
Script → Voice → Cover → Timeline → Publication flow. The generated assets are
two 24×24 PNG images, a one-second MP3 tone, and a one-second 320×180 MP4
colour clip. They are small enough for every local or CI regression build and
are never written outside disposable test storage.

Run its contract through the required isolation wrapper:

```powershell
python tests/run_isolated.py tests.test_golden_dataset
```
