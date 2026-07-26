# bowerbird-desktop

Placeholder. The desktop shell (Electron vs Tauri) is deliberately deferred
until there is evidence colleagues want a desktop icon rather than a URL —
see [ADR-0007](../../docs/adr/0007-defer-desktop-shell-choice.md).

When the shell is chosen it wraps the same web UI in `packages/web`, talking
to the same JSON contract. Nothing shell-specific may leak into
`packages/web`. First-run Ollama detection follows the `talk-buddy` flow,
with "use the hosted service instead" equally prominent.
