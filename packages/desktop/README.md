# bowerbird-desktop

Electron shell wrapping the web UI in `packages/web`
([ADR-0010](../../docs/adr/0010-electron-desktop-shell.md)). The main
process boots the same Express app the hosted server runs (via
`createApp` from `@michaelborck/bowerbird-server`) on a loopback-only
random port and points the window at it — one JSON contract, two homes.
Requests run inline (no queue on a personal machine); credentials come
per request from the UI's settings panel (browser storage, ADR-0004).
Nothing shell-specific may leak into `packages/web`.

The release pipeline (signing, notarisation, stapling) is copied from
`cite-sight` — see `electron-builder.yml` and `scripts/notarize.cjs` for the
workarounds and why they exist. Auto-update ships via electron-updater
against GitHub Releases.

```bash
npm run build -w @michaelborck/bowerbird-desktop   # tsc + bundle web dist
npm run start -w @michaelborck/bowerbird-desktop   # launch locally
```

First-run Ollama detection follows the `talk-buddy` flow: the settings
panel's "Detect local Ollama" probes localhost and offers the installed
models, with the hosted service as the equally prominent default.

Planned: batch input (a semester of topics), native full-page screenshot
capture via Electron's Chromium (`webContents.capturePage`).
