# 0005. Layered thumbnails, cheapest first

**Status:** Accepted
**Date:** 2026-07-26

## Context

Thumbnails exist for triage, not evidence: a lecturer scanning fifteen
results needs to spot the cookie wall, the login gate, the parked domain and
the SEO farm at a glance. Rendering arbitrary user-supplied URLs in a
server-side browser is both a cost problem and an SSRF surface, so "full
screenshot for everything" is the wrong default.

## Decision

Three layers, cheapest first:

1. **oEmbed thumbnail** for YouTube, Vimeo and podcasts — already provided by
   `cite-sight-core`, effectively free.
2. **og:image** for everything else — one HTTP fetch, no browser.
3. **Full screenshot** (Playwright, bundled Chromium) only as a fallback when
   og:image is absent or on explicit request — and only on the self-host and
   desktop tiers, never the hosted free tier.

## Consequences

- The hosted tier never runs a browser against user-supplied URLs, capping
  both cost and SSRF exposure.
- Most results still get a useful visual (oEmbed and og:image cover the
  large majority of articles, papers and videos).
- Playwright's bundled Chromium works under either candidate desktop shell,
  so this decision does not constrain [ADR-0007](0007-defer-desktop-shell-choice.md).
- Screenshots become a visible tier benefit for self-host/desktop.
