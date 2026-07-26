# Architecture overview

For the full product rationale see the [spec](spec.md); for individual
decisions see the [ADRs](adr/). This page is the five-minute orientation.

## Shape

```
                       ┌─────────────────────────────┐
                       │  @michaelborck/bowerbird-core │
                       │  retrieval · verification    │
                       │  ranking · rationale         │
                       └──────┬──────────────┬───────┘
                              │              │
                    ┌─────────┴───┐    ┌─────┴──────────────┐
                    │  CLI        │    │  Server (Express)  │
                    │  Commander  │    │  + BullMQ queue    │
                    └─────────────┘    └─────┬──────────────┘
                                             │ JSON contract
                              ┌──────────────┼──────────────┐
                        ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
                        │  Web UI   │  │  Desktop  │  │  PWA      │
                        │  React    │  │  (shell)  │  │  (v1.1)   │
                        └───────────┘  └───────────┘  └───────────┘
```

- **core** is a pure library: no UI, no transport assumptions. Everything
  interesting (retrieval, verification via `cite-sight-core`, ranking,
  rationale generation) lives here so every surface benefits.
- **server** exposes core over JSON and owns the queue. Long generations go
  through BullMQ (Redis) so one job cannot block the box; the free tier's
  quota is enforced as queue concurrency.
- **web** is a React + Vite app, later also the PWA. It talks only to the
  JSON contract.
- **cli** wraps core directly (no server needed) for scripting and batch.
- **desktop** wraps the web UI; shell choice deferred
  ([ADR-0007](adr/0007-defer-desktop-shell-choice.md)).

## The request pipeline

For a topic or uploaded document:

1. **Extract** — pull topic signals from the input (PDF, DOCX, TXT, MD).
2. **Retrieve** — candidate resources across types: papers, videos, podcasts,
   books, web pages, reports.
3. **Verify** — every candidate checked for existence
   ([ADR-0002](adr/0002-extend-cite-sight-core-for-verification.md)):
   DOI resolution, HTTP checks distinguishing paywalled from dead, oEmbed,
   Open Library. Unverifiable candidates are flagged, never silently passed.
4. **Enrich** — source-type label, commercially-interested flag, licensing
   status, accessibility notes, thumbnail
   ([ADR-0005](adr/0005-layered-thumbnails-cheapest-first.md)).
5. **Rationalise** — a short LLM-generated rationale per resource
   ([ADR-0003](adr/0003-self-hosted-ollama-with-byok.md)): why this one,
   what it adds, what it does not cover.
6. **Balance** — diversify the return set across format and voice.

Every step from 3 onward is individually fallible and non-fatal
([ADR-0006](adr/0006-non-fatal-degradation.md)).

## Deployment

See [ADR-0008](adr/0008-hosting-vps-docker-plus-github-pages.md). One Docker
image serves both the hosted instance and self-hosters; the landing page is
static on GitHub Pages; releases are cut from `v*` tags by the release
workflow (npm, GHCR/Docker Hub, desktop installers when enabled).
