# NewsFlow Repository Instructions

## Roles

- ChatGPT is the default architecture/code author for this project.
- Codex is the local execution and verification agent by default.
- Codex must not independently invent or implement source fixes unless the current GitHub task explicitly authorizes a concrete change or an exact ChatGPT-authored patch.
- On a verification RED, collect exact evidence, report it, and stop. Do not turn verification into an unreviewed implementation pass.
- The latest explicit GitHub task correction supersedes older task text when they conflict.

## Repository skills

NewsFlow project skills live under `.agents/skills`.

Start by using `newsflow-skill-router` and select the smallest useful combination:
- one primary NewsFlow skill;
- normally no more than 1–3 supporting NewsFlow skills.

Typical routing:
- Montage / audio / video / footage: `newsflow-media-engineering` + `newsflow-runtime-qa` + `newsflow-performance-profiler`.
- React desktop UI: `newsflow-react-desktop`.
- Electron / Windows / IPC / packaging: `newsflow-electron-windows-deep`.
- Architecture: `newsflow-architecture-evolution`.
- Security: `newsflow-security-threat-model`.
- Logs / tracing / runtime diagnosis: `newsflow-observability-debug`.
- Persisted schema / recovery: `newsflow-data-migrations-recovery`.
- AI prompts/providers/evals: `newsflow-ai-evals`.
- Product discovery: `newsflow-product-discovery`.
- RC / Stable: `newsflow-release-engineering`.
- Ideation / critical alternatives: `newsflow-brainstorm-critical`.

General workflow skills such as bug investigation, code review, feature testing, comprehensive QA and pre-release review complement these domain skills rather than replacing them.

## Non-negotiable safety

- Never mutate production settings, sessions, indexes, originals or source footage in automated tests.
- Original media is read-only.
- A human-review task may read production sources only when explicitly authorized and must perform all transforms/writes on isolated copies.
- Never run real paid provider, OAuth, publication or public YouTube actions unless the current task explicitly authorizes them.
- Never expose API keys, tokens, cookies or secrets in logs, artifacts, issue comments or test output.
- Never work directly on `main`.
- One task = one branch = one worktree.
- No force-push, merge, issue closure, destructive migration or broad dependency update unless explicitly authorized.

## Engineering workflow

Before work:
1. Confirm repository, branch, expected HEAD, clean/dirty state and latest issue comments.
2. Read the relevant project skill(s) and current acceptance contract.
3. Treat old chat/status reports as navigation evidence, not current repository truth.

Default implementation/verification ladder:
`REPRO/RED → focused regression → minimal root-cause fix → targeted tests → relevant regression → contract/integration → Electron/Playwright when needed → real media smoke when needed → production/security guards → independent CI → manual acceptance`.

Rules:
- Run cheap/source checks before expensive E2E/render/package checks.
- Do not package EXE after every bugfix. Packaged TEST/RC is for functional checkpoints, packaging-specific defects or release gates.
- SKIP/BLOCKED is not PASS.
- Do not mask failures with disabled tests, `continue-on-error`, deleted assertions or fake success.
- Preserve the first failure/flaky evidence even if a rerun passes.
- Fix root cause with the smallest correct change; move broad refactors to a separate decision/task.
- Keep original media hashes unchanged in media tests and retain manifests/evidence for generated derivatives.
- For each result record exact SHA, commands, PASS/FAIL/SKIP/BLOCKED counts, changed files, artifact paths and remaining risks.

## Montage-specific defaults

For Montage work:
- semantic relevance and safety beat diversity;
- diversity is a bounded preference, never permission to select contradictory footage;
- exact narration/MP3 pairing and voice duration are authoritative;
- source footage is never modified;
- `source_start`, source family and fallback diagnostics must survive persistence/render;
- selection must remain bounded for large libraries: no per-scene full filesystem scan, full-corpus decode or ffprobe storm;
- validate rendered MP4 with FFmpeg/FFprobe evidence, not only file existence;
- final functional acceptance includes real Electron action flow and human review of representative rendered videos.
