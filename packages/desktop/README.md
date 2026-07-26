# bowerbird-desktop

Electron shell wrapping the web UI in `packages/web`
([ADR-0010](../../docs/adr/0010-electron-desktop-shell.md)). Nothing
shell-specific may leak into `packages/web`; both talk to the same JSON
contract.

The release pipeline (signing, notarisation, stapling) is copied from
`cite-sight` — see `electron-builder.yml` and `scripts/notarize.cjs` for the
workarounds and why they exist. Auto-update ships via electron-updater
against GitHub Releases.

```bash
npm run build -w @michaelborck/bowerbird-desktop   # tsc + bundle web dist
npm run start -w @michaelborck/bowerbird-desktop   # launch locally
```

Planned: first-run Ollama detection following the `talk-buddy` flow, with
"use the hosted service instead" equally prominent; native full-page
screenshot capture via Electron's Chromium (`webContents.capturePage`).
