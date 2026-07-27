import type { ComponentState, Resource, SuggestRequest, SuggestResult } from './types.js';
import type { PipelineConfig } from './config.js';
import type { Candidate } from './retrieval/candidates.js';
import { retrievePapers } from './retrieval/papers.js';
import { retrievePodcasts } from './retrieval/podcasts.js';
import { retrieveBooks } from './retrieval/books.js';
import { retrieveVideos } from './retrieval/videos.js';
import { retrieveWeb } from './retrieval/web.js';
import { verifyCandidate } from './verify/verify.js';
import { classifySource } from './enrich/sourceType.js';
import { fetchPageMeta } from './enrich/page.js';
import { annotate } from './annotate/ladder.js';
import { diversify } from './rank/diversity.js';
import { deriveQuery } from './retrieval/query.js';

const DEFAULT_MAX_RESULTS = 10;
const ANNOTATE_CONCURRENCY = 3;

/**
 * List mode (spec §4): input goes in, a verified and annotated resource
 * list comes out. Every enrichment step is individually fallible and
 * non-fatal (ADR-0006); the LLM only annotates what retrieval found
 * (ADR-0011).
 */
export async function suggestResources(
  request: SuggestRequest,
  config: PipelineConfig = {},
): Promise<SuggestResult> {
  const input = request.input.trim();
  if (!input) return { resources: [], componentHealth: {} };
  const maxResults = request.maxResults ?? DEFAULT_MAX_RESULTS;
  const health: Record<string, ComponentState> = {};

  // A pasted document is not a search query; derive one (LLM preferred,
  // term-frequency fallback). Short inputs pass through unchanged.
  const topic = await deriveQuery(input, config);

  // --- Retrieve, one component per source type -------------------------
  const sources: Array<[string, Promise<Candidate[]> | null]> = [
    ['papers', retrievePapers(topic, config.mailto)],
    ['podcasts', retrievePodcasts(topic)],
    ['books', retrieveBooks(topic)],
    ['videos', config.youtubeApiKey ? retrieveVideos(topic, config.youtubeApiKey) : null],
    ['web', config.searxngUrl ? retrieveWeb(topic, config.searxngUrl) : null],
  ];
  const settled = await Promise.allSettled(
    sources.map(([, p]) => p ?? Promise.reject(new Error('not configured'))),
  );
  const candidates: Candidate[] = [];
  settled.forEach((outcome, i) => {
    const name = sources[i][0];
    if (outcome.status === 'fulfilled') {
      health[name] = 'ok';
      candidates.push(...outcome.value);
    } else {
      health[name] = 'unavailable';
    }
  });

  // --- Verify web candidates before selection so dead links don't crowd
  // out live ones; database-attested candidates are already existence-checked.
  const verified = new Map<Candidate, Resource['verification']>();
  await Promise.all(
    candidates.map(async (c) => {
      verified.set(c, await verifyCandidate(c));
    }),
  );
  const usable = candidates.filter((c) => verified.get(c) !== 'dead');

  // --- Select a diverse set, then enrich + annotate only the selected ---
  const preliminary = usable.map((c) => toResource(c, verified.get(c) ?? 'unverified'));
  const selectedResources = diversify(preliminary, maxResults);
  const selected = selectedResources.map(
    (r) => usable[preliminary.indexOf(r)],
  );

  let thumbnailFailures = 0;
  let llmSuccesses = 0;
  let llmAttempts = 0;

  await mapLimit(selected, ANNOTATE_CONCURRENCY, async (candidate, i) => {
    const resource = selectedResources[i];

    // Page metadata: one fetch covers og:image (ADR-0005 layer 2) and the
    // extractive description (ADR-0011 rung 2). Only for candidates that
    // still lack either, and never for DOI links (publisher bot-walls).
    if ((!candidate.thumbnailUrl || !candidate.description) && !candidate.doi) {
      try {
        const meta = await fetchPageMeta(candidate.url);
        candidate.thumbnailUrl ??= meta.ogImage;
        candidate.description ??= meta.description;
        resource.thumbnailUrl = candidate.thumbnailUrl ?? null;
      } catch {
        thumbnailFailures += 1;
      }
    }

    if (config.ollamaUrl) llmAttempts += 1;
    resource.annotation = await annotate(topic, candidate, config, true);
    if (resource.annotation.source === 'llm') llmSuccesses += 1;
  });

  health.thumbnails =
    thumbnailFailures === 0 ? 'ok' : thumbnailFailures < selected.length ? 'degraded' : 'unavailable';
  health.llm = !config.ollamaUrl
    ? 'unavailable'
    : llmSuccesses === llmAttempts
      ? 'ok'
      : llmSuccesses > 0
        ? 'degraded'
        : 'unavailable';

  return { resources: selectedResources, componentHealth: health };
}

function toResource(candidate: Candidate, verification: Resource['verification']): Resource {
  const { sourceType, commerciallyInterested } = classifySource(candidate);
  return {
    title: candidate.title,
    url: candidate.url,
    format: candidate.format,
    sourceType,
    authors: candidate.authors,
    year: candidate.year,
    verification,
    commerciallyInterested,
    licensing: 'unknown',
    annotation: { source: 'none', text: null },
    thumbnailUrl: candidate.thumbnailUrl ?? null,
    accessibilityNotes: [],
  };
}

async function mapLimit<T>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<void>,
): Promise<void> {
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const i = next++;
      await fn(items[i], i);
    }
  });
  await Promise.all(workers);
}
