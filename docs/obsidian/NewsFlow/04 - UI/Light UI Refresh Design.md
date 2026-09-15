# Light UI Refresh Design

**Status:** approved for implementation on 2026-09-12.

## Goal

Make the current NewsFlow Light renderer visibly modern while preserving every verified runtime path. This is a forward-only React UI migration, not NewsFlow V3 and not a backend rewrite.

## Non-negotiable runtime boundary

`window.newsflowDesktop` calls, `NewsFlowCommand` names, command payloads, Electron IPC, Python bridge/service/worker paths, storage schemas and user-data roots remain unchanged. A migrated control calls the same handler and the same `command(name, payload)` as its legacy counterpart.

## Current active renderer

`src/main.tsx` mounts `src/ui/App.tsx`. Electron loads `dist/index.html`. `App.tsx` remains the route/state owner during this work; only visual shell and screen-local presentational parts move out. The current route IDs and navigation ordering remain stable.

## Target architecture

```text
App.tsx (state, refresh, command contract, route selection)
  -> AppShell (layout only)
      -> Sidebar + PageHeader + TaskCenter + notice host
      -> active feature view
          -> shared UI kit
          -> existing handler / command callback
              -> unchanged Electron and Python runtime
```

## Visual language

Publication V2 is the reference: dark desktop surface, compact typography, clear primary action, restrained blue primary color, semantic success/warning/danger states, high-density tables with readable hierarchy. New shared components use `nf-*` namespaced classes and Tailwind utilities where they add clarity. Legacy global classes remain only for screens that have not yet migrated.

## Migration rules

1. A screen first receives a component-level test that proves its existing callback/command request survives the visual migration.
2. The focused UI test, affected command-contract test, and an isolated runtime regression run before the next screen.
3. New screen CSS is namespaced. Its old CSS is removed only after source search shows no remaining consumer and the visual check passes.
4. `App.tsx` may delegate rendering but keeps its state variables, handlers and route selection until the final cleanup phase.
5. No provider, API, media, storage or queue action is launched against production data.

## Completion definition

The shell and priority screens visibly use the unified kit; no active screen relies on the legacy `Button`, `Empty`, `Stat`, generic legacy toolbar or old page-header implementation. Current command contracts and Python isolated regressions remain green. No EXE is built in this phase.
