# ADR-001: Stable Light foundations

- React + TypeScript + Vite remain the canonical renderer stack.
- Electron remains the desktop boundary; Python remains the core process.
- The project-local Markdown tree is the engineering vault until the user explicitly configures an existing external Obsidian vault.
- `Settings` at `%LOCALAPPDATA%\\NewsFlow` remains the canonical persistent root. A release must back it up and prove migration before launch.
- Universal V2 is the only canonical cover prompt builder.
- SEO, Tags and working YouTube publication are preserve-first modules.
- A legacy implementation never activates silently. A canonical error is surfaced with diagnostics/retry.
- No full rewrite and no bulk migration are permitted in Light; phases are small, independently tested changes.
