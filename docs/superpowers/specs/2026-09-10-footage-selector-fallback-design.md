# Footage selector soft-constraint fallback

## Goal

When the local index contains a physically valid, readable and safe clip, a normal news scene receives a clip rather than failing because quality preferences have been exhausted.

## Root cause

`_select_montage_candidate` rejects `project_used_paths` and `project_used_families` before considering its `allow_historical` / `allow_reserved` fallback flags. Consequently its `SAFE_REUSE` pass cannot reuse a non-adjacent clip or family at all. The same candidate is counted once per fallback pass, so the prior `diversity=768` for a 256-candidate result was rejection events, not unique rejected candidates.

## Design

The selector keeps hard validation (physical path, duration, safe semantic guard) on every level. It treats threshold, history, family diversity and batch reservation as soft preferences. Candidate selection is deterministic and uses the existing bounded in-memory result pools.

The ladder is `STRICT_MATCH`, `RELAXED_MATCH`, `CATEGORY_CONTEXT_FALLBACK`, `SAFE_REUSE`, `RESERVED_REUSE`, `LAST_RESORT`. Reuse prefers a different clip and excludes the immediately previous clip whenever another hard-valid candidate exists. A final last-resort selection chooses a hard-valid candidate by category/semantic score, oldest local use, current-item use count, and normalized path.

Diagnostics record unique candidates by their first rejection reason and separate rejection events. Existing timeline clips and MP3 mappings are retained if planning needs a fallback; failure is reserved for an actually empty or hard-invalid local pool.

## Non-goals

Do not change fast mode, vector-index retrieval limits, the approximately six-second source-footage rule, final-tail-only trim, or video re-render policy.
