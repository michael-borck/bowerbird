# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-07-29

### Added

- Counterpoint mode (ADR-0012): a second retrieval pass through inverted
  queries surfaces verified material that disagrees with or complicates
  the framing, stance-labelled and rendered in its own section across
  web UI, markdown, and CLI (`--counterpoint`).
- Batch input (spec §9 tier feature): `/api/batch` and `bowerbird batch
  topics.txt` — many topics per run, one markdown document out. On by
  default for self-host/desktop; the hosted instance disables it with
  BOWERBIRD_ALLOW_BATCH=0.
- Link-rot re-run mode: `bowerbird recheck saved.json` re-verifies a
  previously saved list (DOIs against the databases, URLs re-probed) and
  reports status changes first.
- Full-page screenshot thumbnails on desktop (ADR-0005 layer 3) via
  Electron's own Chromium, as fallback when oEmbed/og:image yield nothing.

### Changed

- Queue job timeout raised to 6 minutes — counterpoint doubles LLM work
  and self-hosted inference on modest hardware is slow.

## [0.4.0] - 2026-07-27

### Added

- The desktop app is now functional: the Electron main process embeds the
  same Express app the hosted server runs (`createApp` from the server
  package) on a loopback-only random port — one JSON contract, two homes.
- Settings panel in the web UI (shared by desktop): AI provider URL, key
  and model, plus a YouTube API key for video search. Stored in browser
  storage only, sent per request, never persisted server-side (ADR-0004).
- Local Ollama detection (`/api/detect-ollama`) with model listing —
  the talk-buddy first-run pattern.
- Per-request YouTube key joins the BYO contract; any BYO credential
  routes around the queue so it never lands in Redis.

### Changed

- Server refactored into an embeddable `createApp` plus a thin hosted
  entry point (env config, BullMQ runner, listen).

## [0.3.0] - 2026-07-27

### Added

- Licensing status on results (spec §3 institutional plumbing): CC /
  open-access / library-subscription for papers via OpenAlex, ebook access
  for books via Open Library, Creative Commons flag for YouTube videos.
- Accessibility notes: captions flag on videos from the YouTube API.
- Venue (journal / publisher / channel) on results.
- Citation export: APA 7 and Harvard, from held metadata only — missing
  fields are omitted, never invented.
- LMS-ready HTML export: single self-contained fragment, inline styles
  only (LMS editors strip style blocks), with annotation provenance.
- SearXNG service in the compose stack behind a `websearch` profile, with
  the settings file that enables its JSON API (`deploy/searxng/`).
- PWA: web manifest, feather icon, and a network-first service worker
  that never caches API responses.

### Fixed

- Duplicate results from one retrieval source (URL-level dedupe across
  all sources).
- Internal workspace dependencies use `*` so npm never substitutes a
  published registry copy for the local workspace.

## [0.2.1] - 2026-07-27

### Added

- BullMQ queue on the server: suggest requests run through Redis-backed
  workers (SUGGEST_CONCURRENCY, default 2) so one long generation cannot
  block the box; inline fallback when Redis is down. BYO-key requests
  bypass the queue so user keys never touch Redis (ADR-0004).
- Document upload in the web UI via `/api/extract` (PDF, DOCX, TXT, MD).
- Query derivation for document input: LLM keyword extraction with a
  phrase-frequency heuristic fallback that filters course-material
  boilerplate.

### Changed

- Paper retrieval now uses OpenAlex phrase-quoted title/abstract search
  with reconstructed abstracts, replacing plain relevance search that
  surfaced mega-cited off-topic works; Crossref remains the fallback.
- Open Library book search uses the same phrase-quoted strategy.

## [0.2.0] - 2026-07-27

### Added

- Working v1 list-mode pipeline: retrieval (papers via OpenAlex/Crossref
  through cite-sight-core, podcasts via iTunes, books via Open Library;
  videos and general web behind optional YOUTUBE_API_KEY / SEARXNG_URL),
  verification, source-type labelling with commercially-interested flag,
  og:image thumbnails, diversity-balanced ranking, markdown export.
- Annotation ladder (ADR-0011): Ollama-generated relational rationale,
  degrading per-resource to extracted description, then metadata-only,
  with provenance surfaced in every UI.
- CLI: `bowerbird suggest <topic>` and `--file` document input (PDF, DOCX,
  TXT, MD via cite-sight-core extractors), markdown or `--json` output.
- Server: `/api/suggest` with per-request BYO provider override
  (ADR-0004: held in memory for the life of the call only).
- Web UI: search, result cards with verification/source badges and
  annotation provenance, component health footer, markdown download.

## [0.1.1] - 2026-07-27

### Added

- Initial project scaffold: monorepo structure, docs, ADRs, CI/release
  workflows, Docker packaging, landing page, Electron desktop shell
  (ADR-0010), signed and notarised release pipeline.
