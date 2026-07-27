# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
