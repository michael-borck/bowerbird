# @michaelborck/bowerbird-core

Shared logic for Bowerbird: retrieval, verification, ranking and rationale.

- No UI or transport assumptions — the CLI, server, web and desktop surfaces
  all consume this package ([ADR-0001](../../docs/adr/0001-typescript-monorepo-no-python-sidecar.md)).
- Verification extends [`@michaelborck/cite-sight-core`](https://www.npmjs.com/package/@michaelborck/cite-sight-core)
  ([ADR-0002](../../docs/adr/0002-extend-cite-sight-core-for-verification.md)).
- Every enrichment step degrades non-fatally
  ([ADR-0006](../../docs/adr/0006-non-fatal-degradation.md)).
