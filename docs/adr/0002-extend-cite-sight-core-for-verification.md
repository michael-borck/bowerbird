# 0002. Extend cite-sight-core for verification

**Status:** Accepted
**Date:** 2026-07-26

## Context

Verification is Bowerbird's primary differentiator: every link resolved,
every DOI validated, no generated references. `@michaelborck/cite-sight-core`
already implements DOI resolution (Crossref, with Semantic Scholar and
OpenAlex fallbacks), URL HTTP checks that distinguish blocked/paywalled from
dead, YouTube/Vimeo oEmbed, Open Library lookups and confidence scoring.
Duplicating this would fork the logic and split maintenance effort.

## Decision

Extend `cite-sight-core` rather than reimplementing verification in this
repo. New capabilities that are general-purpose (podcast RSS metadata,
generic-page canonical URL and publication date extraction, Wayback archive
fallback) are contributed upstream to `cite-sight-core`. Capabilities that
are Bowerbird-specific (source-type labelling, the commercially-interested
flag on consultant material, currency flags) live in `packages/core` here.

## Consequences

- Both tools improve at once; verification bug fixes land in one place.
- Bowerbird takes a versioned dependency on `cite-sight-core` and must track
  its releases.
- The boundary rule — general-purpose upstream, pedagogical labelling here —
  must be applied at review time to avoid drift.
