# 0009. List mode first; interview mode deferred to v2

**Status:** Accepted
**Date:** 2026-07-26

## Context

Two interaction modes are envisioned. **List mode**: input goes in, a
verified and annotated resource list comes out — fast, no dialogue.
**Interview mode**: the tool asks first (reinforce or challenge the reading?
what do students already have? pre- or post-class?) and then suggests.
Interview mode is the more distinctive feature, which makes it tempting to
build first.

## Decision

Ship list mode as v1. Defer interview mode to v2 — for design reasons, not
cost reasons: the interview's questions will be far better chosen after
watching colleagues use list mode and seeing where their judgement actually
needs prompting. Counterpoint mode (deliberately surfacing disagreeing
material) is deferred alongside it.

## Consequences

- v1 is shippable and simple to explain: content in, verified list out.
- The rationale-per-suggestion field already carries the pedagogical framing
  in v1, so the differentiator is present from day one.
- Observing real usage becomes a prerequisite for v2 design — which
  interacts with open decision #4 in the spec (whether to log usage at all).
