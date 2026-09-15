# Research agents per YouTube channel

## Goal

Add an `Исследование каналов` workspace for finding and analysing public
news sources. Each NewsFlow YouTube channel receives an isolated local Chrome
profile, a dedicated research agent, its own queue, and its own results. The
workspace helps an operator discover topics and analyse selected video
material; it is not a mechanism for fabricated engagement, cookie warming, or
evasion of platform controls.

## Scope and non-goals

In scope:

- Search public YouTube and web-news sources using operator-selected queries,
  languages, and regions.
- Import a UTF-8 `.txt` file where every non-empty line is a channel, video,
  or web URL.
- Produce a fast, high-volume source scan and an optional deeper content
  analysis for selected material.
- Keep one persistent queue and result store per connected NewsFlow channel.
- Export a channel's result set as CSV, JSON, and Markdown; allow that result
  set to be deleted.

Out of scope:

- Automated viewing, clicking, or browsing intended to increase YouTube trust,
  views, advertising activity, or cookie history.
- Credentials, passwords, cookies, or refresh tokens in UI payloads, reports,
  exports, or logs.
- Publishing, commenting, liking, subscribing, or any other action on an
  external service.

## Channel, Chrome profile, and agent relationship

Every analytics-channel record already has a stable local profile ID. The
research subsystem extends that relationship without sharing state between
channels:

```text
NewsFlow channel row
  -> one dedicated Chrome profile directory
  -> one dedicated research-agent queue
  -> one channel-scoped result store and export set
```

Creating a new channel row provisions a new empty Chrome profile and an empty
research-agent state. The operator performs any Google sign-in and YouTube
OAuth consent manually in that profile. Once connected, the same profile may
open operator-selected public research pages through a persistent Playwright
context. The browser adapter visits only a queued public source, captures
public page text and key visual signals for the corresponding analysis task,
then closes its tab. It must never copy browser data from another channel or
from the everyday Chrome profile.

For several channels managed by one Google account, the operator adds a row
for each channel and completes OAuth one at a time. Before each new OAuth
connection the operator selects that channel as the default channel in
YouTube. Existing successfully connected rows are not reconnected after the
default-channel switch, so their stored tokens and profiles remain independent.

## Source intake and research modes

### Inputs

Each channel can have:

- saved search phrases;
- selectable language and region filters;
- a list of manually entered URLs;
- a `.txt` import with one URL per line;
- optional selected items promoted from a fast scan to deep analysis.

Invalid, duplicate, unsupported, and inaccessible URLs are retained in the
run log with a reason; the remaining input continues processing.

### Fast scan

Fast scan is the default continuous mode. It discovers public sources using
approved public search/feed mechanisms, processes more than 100 sources per
run where available, and stores a compact result per source:

- source title, URL, publisher/channel, published time, and source type;
- detected language and matching search phrase;
- concise topic and factual summary;
- hook, angle, and a non-copying scenario idea;
- result status and any safe error message.

The fast scan favours metadata and available captions over expensive media
processing. It is bounded by a configurable concurrency and source rate so
that one agent does not overload the local machine or an external site.

For a source promoted to browser analysis, the channel agent opens that exact
source in the selected channel's own Chrome profile. It does not follow random
recommendations, play media for an engagement signal, click advertisements, or
perform an external-account action.

### Deep analysis

The operator can promote selected video sources to deep analysis. The agent
uses permitted captions, operator-provided transcript/audio, and key visual
signals to create a structured content brief: premise, story sequence, key
facts, format, hooks, and original topic opportunities. It does not create an
automated YouTube-viewing workflow or use viewing as a trust signal.

## Queue and controls

Each agent has independently persisted task states: `waiting`, `running`,
`paused`, `stopping`, `completed`, `failed`, and `skipped`.

- `Старт выбранных` starts only selected channel agents.
- `Старт всех` starts every configured channel agent with pending work.
- `Пауза` prevents dispatch of the next atomic source operation; a task already
  inside an atomic fetch or analysis step is allowed to reach a safe checkpoint.
- `Продолжить` resumes dispatch for the selected channel agents.
- `Стоп и показать результаты` changes the agent to `stopping`: no new work is
  dispatched, already-started atomic operations finish, results are flushed,
  then the UI opens the saved results.
- `Удалить результаты` deletes only the selected channel's result records and
  exports after an explicit confirmation. It does not delete the channel,
  browser profile, source configuration, OAuth token, or another channel's
  work.

Queue state is saved after each source reaches a terminal checkpoint. An app
restart therefore resumes only work that was not completed, skipped, or
cancelled by graceful stop.

## UI

The new navigation item is `Исследование каналов`. Its layout has:

1. A left channel selector with an agent status badge and last-run summary.
2. A source-configuration panel for queries, language/region, manual URL, and
   `.txt` import.
3. A compact control bar with Start selected, Start all, Pause/Continue, and
   Stop and show results.
4. A queue table that reports current phase, processed count, skipped count,
   and a non-secret diagnostic message.
5. A result list with filters, promotion to deep analysis, Export, and Delete
   results.

`Открыть профиль канала` opens only the selected channel's dedicated Chrome
profile. The operator may need to sign in again if Google has expired its
session; the product makes no promise that third-party sessions persist.

## Data boundaries and error behaviour

- Stored task and result data contains only URLs, public metadata, summaries,
  local timestamps, and status information.
- OAuth credentials stay in the existing encrypted per-channel token mapping;
  research commands never return them to the UI.
- Search/feed unavailability creates a retryable task error without stopping
  other channels or other sources.
- A closed browser, expired Google session, or blocked public page is logged
  against the relevant source. The agent continues the queue where possible.
- A malformed `.txt` import reports line-level errors and imports valid lines.

## Verification

- Unit tests prove new channel provisioning gives unique profile and agent IDs.
- Unit tests cover import parsing, duplicate removal, queue isolation,
  pause/resume, graceful stop, restart persistence, and channel-scoped delete.
- Tests verify no token, cookie, password, or secret appears in a research
  snapshot, error, export, or log.
- UI tests cover start-selected versus start-all, disabled/visible control
  states, progress display, result export, and delete confirmation.
- A manual smoke test connects two channels, confirms their Chrome-profile
  paths are distinct, starts an imported research queue for each, pauses one,
  gracefully stops the other, and verifies the two result sets stay separate.
