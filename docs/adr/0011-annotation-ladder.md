# 0011. Annotation ladder: LLM rationale degrades to extractive description

**Status:** Accepted
**Date:** 2026-07-27

## Context

The LLM's role in Bowerbird is narrow (ADR-0003): it annotates resources
that retrieval and verification have already produced — a rationale per
suggestion, tags, discussion prompts. It never finds or cites sources.
That raises the question of whether the app can run without an LLM at all.

Most of what Bowerbird attaches to a resource is already non-LLM:
verification status, source-type label, commercially-interested flag,
licensing, accessibility notes, thumbnails. And the verification layer
already fetches material that describes each resource — og:description and
meta description (fetched alongside og:image), Crossref abstracts (returned
with DOI lookups), podcast episode summaries (in the RSS being parsed),
video descriptions (via oEmbed).

The distinction that matters is *descriptive* versus *relational*
annotation. Heuristics can say what a resource **is**; only the LLM can say
what it **does for this teaching context** — why this one, what it adds,
what it does not cover, relative to the lecturer's input. That relational
rationale is the pedagogical-framing differentiator (spec §3), and
discussion prompts and counterpoint mode are similarly out of heuristic
reach.

## Decision

Annotation is a three-rung ladder, applied per resource:

1. **LLM available** → relational rationale, tags, discussion prompts.
2. **No LLM** (quota exhausted, Ollama down, or a deliberately LLM-free
   deployment) → extractive description taken from og:description, abstract,
   RSS summary or video description, clearly labelled as a description.
3. **Nothing extractable** → title, source type and verification status only.

Falling down the ladder is per-resource and non-fatal (ADR-0006). The core
exposes which rung each annotation came from, and every UI must render the
distinction — "description (extracted)" is never presented as
"rationale (generated)". Degraded results must not masquerade as the full
product.

## Consequences

- A genuinely useful zero-LLM mode falls out for free: the CLI works with
  no Ollama installed, and the hosted tier keeps returning annotated
  results when the inference queue is saturated.
- The extractive sources cost nothing extra — they ride along with fetches
  the verification and thumbnail layers already make, so rung 2 adds no
  new requests.
- The annotation schema needs a provenance field (e.g.
  `annotation.source: 'llm' | 'extracted' | 'none'`) rather than a bare
  string, and tests must cover each rung.
- The differentiator remains the default experience; heuristics are a
  floor, not a substitute. Any future pressure to make rung 2 the default
  (e.g. to cut inference cost) should be weighed against spec §3 — the
  relational rationale is the wedge.
