# 0012. Counterpoint mode via query inversion

**Status:** Accepted
**Date:** 2026-07-29

## Context

Counterpoint mode — deliberately surfacing material that disagrees with or
complicates the input's framing — is the spec's hardest-to-copy
differentiator (§3 point 3). It was deferred to v2 alongside interview
mode (ADR-0009). v1 is complete across all surfaces, so v2 work has begun.
The design question: how does a retrieval-grounded tool find *disagreeing*
material without generating claims about sources?

## Decision

Counterpoint is a second retrieval pass, not a generation feature:

1. **Query inversion.** The topic is turned into critical search queries —
   by the LLM when available ("queries that would find credible material
   disagreeing with this framing"), else a heuristic that appends critical
   terms (criticism, limitations evidence) to the topic's phrases. Both are
   rungs, per ADR-0011's pattern.
2. **Same pipeline.** Inverted queries run through the identical
   retrieve → verify → enrich path as supporting results — counterpoints
   are exactly as verified as everything else.
3. **Stance labelling.** Results carry `stance: 'supporting' | 'counterpoint'`;
   every surface renders counterpoints in a clearly labelled section, and
   the counterpoint rationale prompt asks how the resource *challenges*
   the framing rather than supports it.

Interview mode remains gated on observing colleagues' real usage
(ADR-0009's reasoning still holds — its questions should come from
watching where judgement actually needs prompting).

## Consequences

- The differentiator ships without weakening the verification guarantee:
  the LLM only writes queries and annotations, never sources.
- Counterpoint quality depends on the inversion queries; the LLM rung
  finds genuinely critical literature (e.g. effect-size meta-analyses),
  while the heuristic rung leans on "criticism" keyword matching —
  serviceable, clearly weaker, honestly reported via componentHealth.
- Counterpoint roughly doubles per-request LLM work; the queue job
  timeout was raised accordingly, and the counterpoint set is capped at
  about a third of maxResults.
