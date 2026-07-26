# 0003. Self-hosted Ollama behind a bearer key, with BYOK

**Status:** Accepted
**Date:** 2026-07-26

## Context

The LLM tasks are short and structured: a sentence of rationale per resource,
tags, a few discussion prompts. A 4B–8B model is sufficient. Paying per-token
to a commercial API for this workload adds cost and a data-governance
question (teaching content leaving the institution) without adding quality.
Sibling project `document-lens` already established a Settings → AI provider
pattern with self-hosted Ollama plus bring-your-own-key.

## Decision

The hosted service uses self-hosted Ollama behind a bearer key as the default
provider. Users may configure their own API key (BYOK) under Settings → AI
provider. The desktop app reuses the optional Ollama detection and install
flow from `talk-buddy`, with the "use the hosted service instead" path
equally prominent — a multi-gigabyte model download is a poor first run on
campus wifi.

## Consequences

- The free tier's constraint is inference concurrency, not a per-token bill;
  quota enforcement is a queue-concurrency problem (BullMQ).
- Small-model choice keeps the quality gap between hosted and local/desktop
  inference small.
- Prompt design must target small models: short, structured outputs.
- BYOK handling has a hard security requirement, recorded separately in
  [ADR-0004](0004-byok-keys-never-persisted-server-side.md).
