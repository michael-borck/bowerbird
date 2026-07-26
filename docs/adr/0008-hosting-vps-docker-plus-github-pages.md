# 0008. Hosting: VPS Docker for the app, GitHub Pages for the landing page

**Status:** Accepted
**Date:** 2026-07-26

## Context

The hosted web UI is the primary interface for colleagues and students, and
inference is self-hosted Ollama (ADR-0003), which needs a machine, not a
serverless platform. A public marketing/landing page is also needed, but it
is static and should not depend on the app server being up. The same Docker
image should serve both the hosted instance and the self-host option, so the
self-host story is "run exactly what production runs".

## Decision

- **App:** one Docker image (server + built web UI) run on a VPS at
  `bowerbird.eduserver.au`, orchestrated with `docker-compose.yml`
  (app + Redis for BullMQ, optional Ollama service). Images are published to
  GHCR (and optionally Docker Hub) by the release workflow.
- **Landing page:** static site in `site/`, deployed to GitHub Pages by a
  workflow on every push to `main`. The landing page's "Try it" button links
  to the VPS instance; download buttons link to GitHub Releases; the
  self-host section shows the `docker run` / `docker compose` commands.

## Consequences

- Free-tier hosting cost is the VPS, which is already sunk; scale-up is a
  bigger VPS, not a re-architecture.
- Landing page stays up even when the app is down — outages don't take down
  the front door or the download links.
- Self-hosters run the identical image, so hosted-vs-self-host bug reports
  are comparable.
- The VPS needs conventional ops (TLS, updates, backups) — accepted; it
  already hosts sibling projects.
