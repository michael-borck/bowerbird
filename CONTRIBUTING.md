# Contributing to Bowerbird

Thanks for your interest in contributing. Bowerbird is a small project with a
clear scope, so the most valuable contributions are focused ones.

## Getting started

```bash
git clone https://github.com/michael-borck/bowerbird.git
cd bowerbird
npm install
npm run build
npm test
```

Requires Node 20+. The repo is an npm workspaces monorepo — see the
[README](README.md#architecture) for the package layout.

## Before you write code

- **Check the [spec](docs/spec.md) and [ADRs](docs/adr/)** first. Several
  design decisions (TypeScript-only, no Python sidecar, BYOK keys never
  persisted server-side, non-fatal degradation) are deliberate and recorded.
  A PR that reverses an ADR without discussion will be closed with a pointer
  to the ADR.
- **Open an issue before a large PR.** Small fixes can go straight to a PR.
- Features listed as *out of scope for v1* in the spec (interview mode,
  counterpoint mode, mobile) need an issue discussion first.

## Ground rules

- **No generated references.** Everything Bowerbird returns must be
  retrieval-grounded and verified. This is the product's reason to exist.
- **Degradation is non-fatal.** If an enrichment step (verification,
  thumbnails, LLM) fails, return results with the affected field flagged as
  unavailable — never fail the whole request.
- **Never persist user API keys server-side.** Browser storage only, passed
  per request, held in memory for the life of the call.
- The core package must stay free of UI and transport assumptions.

## Pull requests

1. Fork and create a branch from `main`.
2. Keep the change focused; unrelated refactors belong in their own PR.
3. Add or update tests for behaviour changes.
4. Make sure `npm run build` and `npm test` pass.
5. Describe *why* as well as *what* in the PR description.

## Recording decisions

Significant architectural decisions are recorded as ADRs in
[`docs/adr/`](docs/adr/). If your change embodies a decision worth recording,
add an ADR in the same PR using the existing format.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
