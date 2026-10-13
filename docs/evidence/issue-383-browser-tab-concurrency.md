# Issue #383: operator-owned browser tab concurrency

Base: `9cb1edc7ac19c5c303a0f5ebf6c2ee4ae4ac9135`.
Branch: `fix/chatgpt-tab-concurrency`.

## Root cause and implementation

The UI allowed typing 84, but its HTML maximum was 10. Bridge settings save,
runtime settings load, and the async semaphore independently clamped to 10.
The correction removes that ceiling at all four boundaries. A shared Python
validator preserves positive integer counts without an arbitrary upper cap;
the UI validates representable positive integers before save/launch and explains
simultaneous tabs versus total topics, resource usage, and unchanged ChatGPT limits.

Existing concurrency 1/10 and defaults are retained. No prompt, download,
ProductionItem routing, queue ownership, auth, or result ownership code changes.
The existing rolling semaphore still bounds active work to the chosen count.

## RED -> GREEN

Before implementation, the new scheduler regression admitted only 10 of 84
blocked fake transports; persistence returned 10 instead of 84/137. The corrected
UI test selector then reproduced `checkValidity() == false` for 84. Invalid-count
tests demonstrated silent coercion, missing UI errors, and non-domain exceptions.

After implementation:

- `python tests/run_isolated.py tests.test_browser_topic_scenarios tests.test_chatgpt_browser scriptor.test_command_contract -q`: **41/41 PASS**, production-write guard PASS, no skips.
- `pnpm test:ui src/ui/features/scenarios/browser-topic-scenarios.test.tsx --reporter=dot`: **8/8 PASS**.
- `pnpm test:ui --reporter=dot`: **398/398 PASS**, 55 files, no skips.
- `python -m ruff check scriptor/browser_topic_scenarios.py scriptor/bridge.py tests/test_browser_topic_scenarios.py`: PASS.
- `pnpm typecheck`, `pnpm build`, `pnpm verify:security`, `pnpm verify:secrets`: PASS.

The offline tests exercise 84 simultaneously admitted tasks, preservation of 137
(not a replacement cap at 84), safe settings round-trip, rejection without writes,
and a 3-slot pool refilling after an out-of-order success and failure. All 84
outcomes/calls remain ID-bound with no replay. Existing regressions cover queue
reorder, duplicate launch, per-topic failure, and preservation of ready/manual prose.
New Python regressions live in the module already executed by the independent CI
browser step; no workflow permission expansion or workflow modification is needed.

Read-only review found no critical/important issue. Its minor reload-test weakness
was corrected by changing the local input before applying the restored snapshot.

## Honest release boundary

- `pnpm verify:core-runtime`: **FAIL** as expected: actual changed `scriptor/bridge.py` blob does not match accepted Frozen r45.
- `python tests/run_isolated.py tests.test_core_runtime_guard -q`: **9 PASS / 1 FAIL**, solely `test_repository_lock_matches_current_source_and_package_revision` for that same stale blob. Production-write guard PASS.
- Frozen lock, package binding and guard tests are unchanged. No fake binding or guard bypass.
- This source PR is **draft / not merge-ready / not release-ready** until a genuine Frozen build/binding resolves the release guard. CI is not claimed green in advance.
- Frozen/TEST EXE builds, live ChatGPT generation, OAuth/provider calls and clean Windows Sandbox acceptance were not run. Browser transport is simulated; this is not a claim that 84 live ChatGPT generations succeed.
- Local Python/UI validation ran on Windows. No production/user settings, sessions, keys, Chrome queues, media or old immutable artifacts were modified by tests. Current running EXE is unchanged.

Live Chrome concurrency and provider acceptance remain constrained by operator
hardware/account/service limits. This change removes NewsFlow's hidden ceiling;
it does not bypass external rate limits or guarantee throughput.
