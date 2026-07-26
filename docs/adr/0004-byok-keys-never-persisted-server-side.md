# 0004. BYOK keys are never persisted server-side

**Status:** Accepted
**Date:** 2026-07-26

## Context

Colleagues and students can bring their own LLM API key. Storing those keys
on a university-adjacent server would make the operator a custodian of other
people's billable credentials — a liability, an attack target, and a
governance problem. This risk exists from the first BYOK request, so it
cannot be an optimisation to revisit later.

## Decision

BYO API keys are stored in browser storage only, sent per request, held in
server memory for the life of the call, and never written to disk, database,
logs or crash reports. There is no server-side "save my key" feature, and
none will be added.

## Consequences

- The server keeps no credential store to secure, rotate or breach-notify.
- Users re-enter or sync their key per browser; slightly more friction,
  accepted deliberately.
- Request logging and error handling must be written (and reviewed) to
  exclude the key material; a violation of this ADR is treated as a security
  vulnerability, not a bug.
