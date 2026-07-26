# 0006. Degradation is non-fatal

**Status:** Accepted
**Date:** 2026-07-26

## Context

A Bowerbird result is assembled from several independent enrichment steps:
retrieval, link/DOI verification, thumbnail fetching, LLM-generated
rationale. Each depends on external services that will individually fail.
Failing the whole request because one step failed would make the tool flaky
in exactly the situations (flaky external services) it is meant to absorb.
Sibling project `document-lens` established this pattern.

## Decision

Every enrichment step is individually fallible. When a step fails, the
request still succeeds and returns results, with the affected fields
explicitly marked unavailable (not silently omitted). Component health is
surfaced in the UI so users can see *why* a field is missing.

## Consequences

- The result schema must represent "unavailable" distinctly from "absent" or
  "checked and negative" — e.g. a verification status of `unverified` is not
  the same as `dead link`.
- Users always get something; trust degrades gracefully instead of the tool
  appearing broken.
- Tests must cover partial-failure paths, not just happy paths.
- One hard exception: verification failure can never be papered over as
  success — an unverifiable resource must be visibly flagged, because
  verified-only results are the product's core promise.
