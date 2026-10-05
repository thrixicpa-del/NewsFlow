# ChatGPT browser topic scenarios — design

## Context

Issue #337 adds a direct, operator-authenticated ChatGPT browser route. It is
not a replacement for the existing API Scenario Planner/Writer pipeline. The
route starts from selected NewsFlow topics and asks the browser chat to create
a new scenario for each topic.

## Decision

Introduce a bounded browser-topic-scenario adapter behind a new bridge command
and a dedicated desktop screen. The adapter owns web interaction only. The
existing session remains the durable owner of `ProductionItem` identity and
of the completed scenario result.

Each browser task contains an immutable `production_item_id`, title, URL and
effective prompt contract captured at dispatch. Completion is matched only by
that identity, never by visible row index, title position, completion order or
tab index.

## User-visible contract

- Input is a queue of topics, not existing scenario prose.
- The active prompt source is either an attached requirements file or editable
  requirements text; the two sources are never silently combined.
- The operator prompt never needs to contain a title or character counts.
  NewsFlow appends exact `Тема сценария` and the configured `min–max` range at
  dispatch time.
- A global prompt and optional per-ProductionItem override are supported.
- A global ChatGPT project URL and optional per-ProductionItem URL assignment
  are supported. Conflicting URL assignments are an error before dispatch.
- One NewsFlow-managed Chrome profile is used. Its configured concurrency
  controls the number of tabs/tasks. A completed tab frees a slot for the next
  pending topic.
- Browser authentication is manual. No password, OTP, cookies or API secret is
  read, copied or exposed by NewsFlow.
- The returned text is saved as the new browser-generated scenario for the
  same ProductionItem and exported through the existing safe TXT exporter.

## Boundaries and non-goals

- No OpenAI API, Planner, Writer, Covers, publication or OAuth flow is used.
- No semantic/topic/quality gate rejects a title. Only truthful technical
  errors can stop an individual task.
- No hidden retry, regeneration or automatic overwrite of a prior completed
  result is allowed.
- The browser adapter must be testable through an injected transport. Unit
  tests use an offline fake transport; live ChatGPT acceptance happens only
  after local verification and an operator-authenticated profile.

## Failure handling

Input validation occurs before dispatch. Browser/auth/network/empty-response
errors are persisted on the same durable task with a human-readable reason;
the task remains recoverable and no other topic is redirected. A response
outside the requested range is persisted without rewrite and marked
`NEEDS_REVIEW` with actual length.

## Verification

RED-first tests cover prompt assembly, per-ID settings and URL resolution,
concurrency/slot release, durable ID matching after reorder, no API
Planner/Writer calls, successful result persistence/TXT export, and all
technical error paths. Desktop tests cover editing/saving the controls and
command payload identity.
