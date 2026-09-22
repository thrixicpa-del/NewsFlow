# MONTAGE-004 VoiceMap Alignment Design

**Issue:** [#49](https://github.com/borovojarkadij-png/NewsFlow/issues/49)

**Baseline:** `f4d8ac597d37f8bd21c5b255b598578c0e1d1817`

**Status:** Approved for implementation

## Outcome

NewsFlow inserts one durable, versioned `VoiceMap` contract between a finished
scenario/MP3 pair and Montage. The scenario remains the text authority, the
audio remains the timing authority, and the ProductionItem ID remains the
identity authority. Montage consumes the same contract in both modes:

- `aligned`: real timed audio observations were reliably reconciled to the
  canonical final scenario;
- `approximate`: the existing local planner produced an explicitly labelled
  fallback because an alignment engine/model was unavailable or unreliable.

An approximate VoiceMap keeps Montage usable. It must never be reported as
exact alignment.

## Storage and identity

VoiceMaps live below the NewsFlow application-data root in `voice-maps/` and
are named from a filesystem-safe SHA-256 digest of the ProductionItem ID. The
artifact contains the original ProductionItem ID; title and scenario index are
metadata only. This avoids collisions and prevents a new ProductionItem with
the same title from inheriting an old map.

Schema version 1 has this minimum shape:

```json
{
  "schemaVersion": 1,
  "productionItemId": "production:example",
  "scenarioIndex": 0,
  "title": "Example",
  "audioPath": "D:/isolated/voice.mp3",
  "audioDuration": 12.34,
  "scriptSha256": "...",
  "audioSha256": "...",
  "timingMode": "aligned",
  "alignmentEngine": "ffmpeg-whisper-canonical-v1",
  "alignmentConfidence": 0.94,
  "createdAt": "2026-09-20T12:00:00+00:00",
  "segments": [
    {
      "id": 1,
      "start": 0.0,
      "end": 4.82,
      "duration": 4.82,
      "text": "Canonical scenario phrase.",
      "visualQuery": "observable news footage",
      "scriptCharStart": 0,
      "scriptCharEnd": 26,
      "confidence": 0.95
    }
  ],
  "alignment": {
    "words": [
      {"text": "Canonical", "start": 0.12, "end": 0.48}
    ]
  }
}
```

`alignment.words` is optional and is omitted when the engine does not provide
word evidence. Approximate maps use `timingMode: "approximate"`,
`alignmentEngine: "newsflow-fallback"`, and never invent word evidence.

## Validation and atomic publication

Every read validates the schema, identity, hashes, timing mode, positive and
monotonic segment boundaries, canonical text coverage, and the final endpoint
against the probed audio duration. Unsupported schema versions are stale and
require rebuilding. Corrupt JSON is a recoverable error and is never treated
as an empty valid map.

Publication order is fixed:

1. align and build candidate JSON in memory;
2. reload current settings/session;
3. verify the ProductionItem still exists and is not tombstoned;
4. recompute and compare script and audio hashes;
5. validate the complete candidate contract;
6. write a sibling temporary file, flush it, and atomically replace the target.

Delete/reset writes the existing SESSION-001 tombstone fence first, then
physically removes the artifact. A stale worker repeats all authority checks
immediately before replace, so it cannot resurrect a deleted VoiceMap.

## Alignment engines

`AlignmentEngine` returns timed observations plus provenance. Tests inject a
deterministic engine with explicit synthetic observations; production never
selects that engine.

The optional production adapter uses the local FFmpeg `whisper` filter only
when both capabilities are explicit:

- the selected FFmpeg reports the `whisper` filter;
- `NEWSFLOW_WHISPER_MODEL` or the project-owned model-cache location points to
  an existing model file.

NewsFlow does not download or bundle a model. The adapter writes Whisper JSON
to disposable storage, parses only real timed observations, and reconciles the
normalised observation tokens against canonical scenario tokens. Canonical
text is copied from NewsFlow, not from ASR. Low coverage, non-monotonic timing,
or materially divergent text rejects the aligned candidate; the caller writes
an approximate map with an explicit reason instead.

The production adapter may use CPU or the FFmpeg build's configured GPU path.
The first run has no hidden network work. Offline use succeeds when the model
is already cached and falls back honestly when it is not. Packaged acceptance
must separately prove that the bundled FFmpeg has the filter; this feature does
not silently add a large packaged dependency.

## Segment construction

Aligned observations are projected onto the canonical token stream. Segment
boundaries prefer, in order, sentence punctuation, clause punctuation, an
observed pause, and then a word boundary. The target range is approximately
3–6 seconds. A modest overrun is allowed to preserve a natural boundary, but
unexplained 12–20 second segments are invalid. No boundary may split a word.

Short adjacent canonical phrases may be grouped. Long sentences are split at
clause/pause/word boundaries. Segment text ranges must cover the complete
canonical scenario once and in order. The last segment reaches the complete
audio duration within the existing media tolerance.

Each segment derives its visual query through the current deterministic news
query logic. The VoiceMap only defines timing and semantic units; MONTAGE-003
continues to own the query ladder, semantic contradiction guards, screen-text
guard, family diversity, source-start rotation, external fallback, and safe
reuse.

## Runtime integration

After generated or imported audio is validated and promoted, Voice asks the
VoiceMap service to ensure a current map. Cache hits avoid alignment work.
Manual Voice does not start Montage. The auto-pipeline continues only after a
map (aligned or approximate) is available.

Snapshot exposes one operator-facing state per Voice item:

- `Ожидает MP3`
- `Анализ аудио`
- `Тайминг готов`
- `Приблизительный тайминг`
- `Тайминг устарел`
- `Ошибка тайминга`

A `rebuild-voice-map` command crosses the existing renderer command contract,
Electron allow-list, Python bridge dispatch, and frozen-core route. It rebuilds
the selected artifact only; it does not render a Montage.

`prepare_montage()` ensures/loads the VoiceMap and converts its segments into
the existing scene retrieval path. `TimelineClip` stores `voice_segment_id`
and narration start/end. `TimelineProject` stores VoiceMap provenance:
alignment mode, artifact path/schema, hashes, engine, and confidence. Saving a
project therefore makes the relationship auditable in `.newsflow`.

## Failure behaviour

- Missing engine/model: explicit unavailable reason, durable approximate map,
  Montage continues.
- ASR/canonical mismatch: no aligned map is published; approximate map records
  the reconciliation failure.
- Corrupt/partial JSON: recoverable rebuild/error; Montage never crashes.
- Script/audio change: current map becomes stale and is rebuilt before use.
- Alignment failure never modifies or removes the script or MP3.
- Interrupted write cannot leave valid-looking JSON at the final path.

## Verification

Tests use only disposable `NEWSFLOW_TEST_ROOT` storage and synthetic/local
media. RED-first coverage includes segment boundaries and coverage, hashes and
identity, schema changes, corruption/interruption, unavailable engines,
delete/reset ordering, stale-worker rejection, cache reuse, snapshot/IPC/UI,
Montage provenance, and all MONTAGE-003 regressions.

The real isolated acceptance retains the synthetic/local MP3, canonical
scenario, generated VoiceMap, `.newsflow`, final MP4, FFprobe JSON, hashes,
timing metrics, and manifest. It does not mutate production settings, sessions,
media, OAuth, credentials, or providers. Long-form three-video quality review
is explicitly deferred to a separate issue.
