# 0007. Defer the desktop shell choice (Electron vs Tauri)

**Status:** Superseded by [0010](0010-electron-desktop-shell.md)
**Date:** 2026-07-26

## Context

Both candidate shells are proven in-house: `cite-sight` ships with Electron;
`document-lens` and `career-compass` ship with Tauri. The desktop app wraps
the same web UI either way, and the contract between the web UI and the
server (JSON over HTTP) does not couple to the shell. There is not yet
evidence that colleagues want a desktop icon rather than a URL.

## Decision

Build core, CLI, server and the hosted web UI first. Choose the shell only
once there is demand evidence. Nothing in `packages/web` may assume a
specific shell; anything shell-specific stays in `packages/desktop`.

## Consequences

- No effort is spent packaging, signing and notarising an app nobody has
  asked for yet.
- The release workflow contains a desktop job that is disabled until the
  shell is chosen; signing secrets are added when it is enabled.
- Playwright screenshots (a desktop-tier feature) bundle their own Chromium
  and work under either shell, so this deferral blocks nothing.
- `packages/desktop` exists in the tree as a placeholder to keep the
  contract boundary visible.
