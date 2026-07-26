# 0010. Electron for the desktop shell

**Status:** Accepted (supersedes the deferral in [0007](0007-defer-desktop-shell-choice.md))
**Date:** 2026-07-26

## Context

ADR-0007 deferred the Electron-vs-Tauri choice until it mattered. It now
does: the signing and notarisation secrets are provisioned, and the desktop
tier (batch input, full screenshots, local Ollama) is next on the roadmap.
Both shells remain proven in-house — `cite-sight` ships Electron;
`document-lens` and `career-compass` ship Tauri.

Two facts tipped the decision:

1. **cite-sight's Electron release pipeline is battle-tested and directly
   copyable**: the persistent-keychain workaround for codesign, the
   `afterSign` notarize hook (electron-builder's own notarize wrapper being
   unreliable), and the DMG sign → notarise → staple flow. Bowerbird already
   mirrors cite-sight's monorepo, workflow shape and verification core, so
   this keeps the two repos structurally twinned.
2. **The screenshot tier wants a Chromium.** Full-page thumbnails
   (ADR-0005, layer 3) need a real browser engine. Electron bundles
   Chromium, so the desktop app can capture pages natively
   (`webContents.capturePage`) with no extra download. Tauri uses the system
   WebView, so it would need Playwright's bundled Chromium alongside —
   a second engine and a multi-hundred-MB dependency. (Playwright itself is
   a TypeScript-native Node library, so it fits the stack either way — but
   not needing it in the desktop build is simpler still.)

## Decision

The desktop shell is **Electron**, in `packages/desktop`, wrapping the same
web UI (`packages/web`) per the contract in ADR-0001. Packaging uses
electron-builder with cite-sight's release pipeline copied as-is: CI signs
with the Developer ID certificate, notarises the `.app` via the `afterSign`
hook, then signs, notarises and staples the DMGs in a workflow step.
Auto-update ships via electron-updater against GitHub Releases.

## Consequences

- The disabled desktop job in `release.yml` is enabled; a `v*` tag now
  produces signed and notarised macOS builds plus Windows and Linux
  installers.
- Installer size is Electron-class (~100 MB) versus Tauri's ~10 MB —
  accepted; the desktop tier targets power users on capable machines.
- Server-side screenshots (self-host tier) still use Playwright, since the
  server has no Electron. The core exposes a screenshot interface; desktop
  and server provide different engines behind it.
- The `talk-buddy` first-run Ollama detection flow ports into Electron
  main-process code when that feature lands.
