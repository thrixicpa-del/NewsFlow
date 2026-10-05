# GPU timeline renderer and cooperative montage pause

## Goal

Add a selectable `gpu-timeline` montage renderer for long NewsFlow videos.  It
keeps the existing scene plan and selected footage unchanged, renders a
1080p/30fps CFR output with the installed NVIDIA encoder, and uses the
operator's existing render-worker setting.  The current FFmpeg, Remotion and
DaVinci choices remain available.  New projects use GPU timeline only when
the runtime can prove the required NVIDIA encoder is available; existing
projects retain their persisted choice.

Fix the queue Pause control at the same time.  A persisted pause request must
be observed by an already-running queue at a safe checkpoint, without killing
the current FFmpeg invocation or losing a project.

## Non-goals

This does not change story planning, footage discovery or selection, scene
durations, voice mapping, Covers, publication, provider calls, or production
settings.  It does not silently fall back from GPU timeline to CPU FFmpeg.

## Renderer contract

`gpu-timeline` is a new explicit renderer value in the UI/IPC/Core contract.
Its preflight requires an NVIDIA H.264 encoder.  A missing encoder or GPU
render failure is reported as a GPU-timeline error; the operator can explicitly
select the existing FFmpeg renderer and rerun.

The renderer normalizes each selected source segment into the established
1920x1080, 30fps, yuv420p timeline contract while producing substantially
fewer intermediates than the current per-clip proxy path.  Work is assembled
in bounded timeline chunks, then concatenated without re-encoding.  Chunks
avoid Windows command-line limits while retaining one consistent render
contract.  Each chunk uses the same source trims, crop rules and clip order as
the existing renderer.  Output validation continues to check duration and
stream properties.

The existing `renderWorkers` value remains the sole user-controlled queue
parallelism setting.  GPU renderer availability is exposed as capability
information, not as a new hidden concurrency limit.

## Pause contract

`save-montage-settings({queuePaused})` persists the requested state.  Queue
workers refresh only that pause signal from durable settings at safe
checkpoints: before a new project, between planning/download/render stages,
and between bounded render chunks.  Active atomic FFmpeg work is allowed to
finish; no new unit starts until Continue is pressed.  Task status shows
`Пауза`, and resume returns it to `В очереди` without changing the project or
its selected footage.

## Compatibility and migration

Old settings accept `ffmpeg` and `remotion` unchanged.  A missing renderer
uses GPU timeline only for a new settings profile with GPU capability;
otherwise it retains the existing FFmpeg default.  DaVinci export remains an
independent optional handoff.  Persisted existing project metadata is not
rewritten merely by viewing settings.

## Verification

Red regressions precede code for: pause after an external settings save;
GPU capability/preflight; no silent fallback; 1080p/30fps output and duration;
bounded chunk assembly; preservation of source order/trims; renderer
round-trip in React/IPC/Core; manual renderer selection; and existing FFmpeg,
Remotion and DaVinci behavior.  Media tests use disposable synthetic clips and
never access the user's footage or settings.
