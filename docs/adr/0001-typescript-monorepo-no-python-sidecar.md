# 0001. TypeScript monorepo, no Python sidecar

**Status:** Accepted
**Date:** 2026-07-26

## Context

Bowerbird spans five surfaces: a library, a CLI, a server, a web UI and a
desktop shell. A sibling project (`document-lens`) uses an embedded Python
FastAPI sidecar for ML workloads, and that pattern was a candidate here. The
workload, however, is HTTP fetching, HTML parsing and LLM API calls — nothing
that needs Python's ML stack. A direct dependency,
`@michaelborck/cite-sight-core`, is already published on npm.

## Decision

One language: TypeScript, in an npm-workspaces monorepo mirroring the
`cite-sight` layout (`packages/core`, `cli`, `server`, `web`, `desktop`).
No Python sidecar. The core is a library with no UI assumptions; the server
exposes it over JSON; web and desktop are both clients of that same contract.

## Consequences

- One toolchain across CLI, server, web, desktop and (later) mobile; shared
  types end-to-end.
- `cite-sight-core` can be consumed directly rather than over a bridge.
- The Python sidecar's complexity (process management, packaging two
  runtimes) is avoided entirely.
- If a genuinely Python-only capability is ever needed, it would have to be
  an external service — accepted, as none is on the roadmap.
