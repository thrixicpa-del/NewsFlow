# Runtime topology

```mermaid
flowchart LR
  UI[React renderer] --> CMD[typed command contract]
  CMD --> PL[Electron preload]
  PL --> IPC[Electron IPC]
  IPC --> BR[scriptor.bridge]
  BR --> SVC[domain service]
  SVC --> WK[worker / provider]
  WK --> PS[(canonical persistence)]
  PS --> ST[validated status/result]
  ST --> UI
```

Current production transport is generic `window.newsflowDesktop.command(command, payload)` → `newsflow:command` → `scriptor.bridge.main()`. The Light contract phase will make critical command names, request payloads and response/status shapes statically testable without replacing Electron or Python.

The renderer’s initial state uses `snapshot()`. Its current implementation performs recovery and writes; [[05 - Persistence/Settings Persistence]] is the prerequisite for separating safe read projection from explicit reconciliation.
