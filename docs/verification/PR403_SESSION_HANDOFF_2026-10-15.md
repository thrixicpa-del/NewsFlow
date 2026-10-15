# Goal

Continue draft PR403 on `codex/footage-semantic-person-fallback-v3`: correct real footage, preserve topical fallback, speed, history/rotation and broad diversity between videos. The owner requested completing the current source-fix block and stopping for shutdown; resume only when requested.

# Current status

The source block and its verification are recorded in [the current report](PR403_REAL_QUALITY_2026-10-15.md). Full task acceptance remains incomplete. `main`, merge, issue closure, Frozen/EXE, lock files and production data remain outside this pass.

# Completed

Both unchanged 300-second narrations rendered completely at source `11fe1e8`; independent review found no known wrong actions in those two outputs, with six uncertain scenes. The six short controls exposed one remaining wrong action, rally narration over seedlings. The current block addresses that visual negative, cross-segment VoiceMap context and repeated invalid-window work. Correctness is assessed separately from successful rendering.

# Validation

The report preserves RED/GREEN, independent review, native regression, real-output results and historical failures. The first cross-segment implementation failed four existing regressions and was not accepted. Tests and limits were not weakened. Final UI/output, whole-library diversity and A/B checks are postponed at the owner's explicit stop request.

# Next steps

1. Inspect current HEAD/status and the final block outcome in the report. Preserve unrelated changes.
2. Repeat both original 300-second narrations and six controls through the active source UI on the final source. Check timelines, every scene, source intervals, actual MP4 frames/PTS, full decode and speech correspondence. Keep word alignment approximate.
3. Run bounded actual selection against the full authorized test-index snapshot before freezing final performance. Measure beginnings, triples, halves, source families and intersections between videos. Separate normal/fast, history and concurrency effects; a 256-file sample is insufficient evidence of whole-library diversity.
4. Run a new frozen sequential A/B and identical fixed-timeline render comparison with the same runtime/settings/history. Preserve the interrupted `11fe1e8` benchmark and all slow/failed cases.
5. Run the prepared matched normal-mode comparison and unchanged sealed secondary holdout, then update the same draft PR and verify CI on the resulting HEAD.

# Risks/blockers

Known control mismatch requires a real UI/output repeat; the corrected source alone does not clear semantic FAIL. Person identity/event attribution and exact word timing remain unverified. Repetition is substantial on the limited test pool. Docker's engine pipe is unavailable. Historical production-integrity FAIL remains unresolved by writer. Frozen binding is stale and rebuilding/changing its lock is forbidden. Windows source build, local source UI and independent Windows E2E remain separate gates. No merge/release readiness is claimed.

# Files/context

- [Detailed report](PR403_REAL_QUALITY_2026-10-15.md)
- [Implementation plan](../superpowers/plans/2026-10-15-footage-real-quality.md)
- [Historical follow-up](PR403_FOLLOWUP_V2_2026-10-15.md)
- Private resume notes and exact test commands are retained locally in ignored `test-data/footage-v3/quality-pass/RESUME_2026-10-15.md`; no private media, speech, scripts, faces or full original paths are published.
