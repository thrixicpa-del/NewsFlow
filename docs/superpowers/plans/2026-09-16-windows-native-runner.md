# Windows Native Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision a dedicated, non-production Windows runner for packaged NewsFlow smoke tests only after explicit repository-owner approval.

**Architecture:** GitHub-hosted Windows continues source build coverage. A dedicated runner is isolated by account and storage root, receives immutable artifacts, and has no production NewsFlow data or credentials.

**Tech Stack:** GitHub Actions runner, Windows VM/PC, Node 24.19.x, Python 3.12, pnpm 11.19.x, current NewsFlow packaged smoke harness.

**Spec:** `docs/obsidian/NewsFlow/01 - Architecture/Windows Native Runner.md`

## Global Constraints

- Never register the user workstation automatically.
- Never mount production `%LOCALAPPDATA%\\NewsFlow`, credentials, OAuth, footage or face libraries.
- Packaged tests use only an isolated TEST/RC user-data root.

### Task 1: Dedicated machine provisioning

**Files:**
- Reference: `docs/obsidian/NewsFlow/01 - Architecture/Windows Native Runner.md`

- [ ] Create a dedicated VM or PC and a non-administrator service account.
- [ ] Install the pinned Git, Node, Python and pnpm toolchain.
- [ ] Confirm the account cannot read the production user profile.

### Task 2: Repository-scoped registration

**Files:**
- Modify: `.github/workflows/windows-native.yml`

- [ ] Obtain a GitHub runner registration token through the repository UI after owner approval.
- [ ] Register with the `newsflow-native-windows` label and repository scope only.
- [ ] Add a label-gated packaged-smoke job that sets `NEWSFLOW_TEST_ROOT` before launch.

### Task 3: Validation and rollback

**Files:**
- Modify: `.github/workflows/windows-native.yml`

- [ ] Run a disposable packaged smoke and upload only redacted artifacts.
- [ ] Confirm production hashes are absent from the runner and remove the runner through GitHub if isolation fails.
