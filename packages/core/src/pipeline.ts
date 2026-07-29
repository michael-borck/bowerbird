import type {
  ComponentState,
  Resource,
  Stance,
  SuggestRequest,
  SuggestResult,
} from './types.js';
import type { PipelineConfig } from './config.js';
import type { Candidate } from './retrieval/candidates.js';
import { retrievePapers } from './retrieval/papers.js';
import { retrievePodcasts } from './retrieval/podcasts.js';
import { retrieveBooks } from './retrieval/books.js';
import { retrieveVideos } from './retrieval/videos.js';
import { retrieveWeb } from './retrieval/web.js';
import { deriveCounterQueries } from './retrieval/counterpoint.js';
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
 * (ADR-0011). Counterpoint mode adds a second retrieval pass that
 * deliberately hunts disagreeing material (spec §3 point 3).
 */
export async function suggestResources(
  request: SuggestRequest,
  config: PipelineConfig = {},
): Promise<SuggestResult> {
  const input = request.input.trim();
  if (!input) return { resources: [], componentHealth: {} };
  const maxResults = request.maxResults ?? DEFAULT_MAX_RESULTS;
  const health: Record<string, ComponentState> = {};
  const seenUrls = new Set<string>();
  const stats = { thumbnailFailures: 0, llmAttempts: 0, llmSuccesses: 0, enriched: 0 };

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
      candidates.push(...dedupeAgainst(seenUrls, outcome.value));
    } else {
      health[name] = 'unavailable';
    }
  });

  const selected = await selectUsable(candidates, maxResults, 'supporting');
  await enrichAll(selected, topic, config, stats);
  const resources = selected.map(({ resource }) => resource);

  // --- Counterpoint pass (spec §3 point 3) -----------------------------
  if (request.counterpoint) {
    try {
      const queries = await deriveCounterQueries(topic, config);
      const counterSettled = await Promise.allSettled(
        queries.flatMap((q) => [
          retrievePapers(q, config.mailto),
          ...(config.searxngUrl ? [retrieveWeb(q, config.searxngUrl)] : []),
        ]),
      );
      const counterCandidates = dedupeAgainst(
        seenUrls,
        counterSettled.flatMap((o) => (o.status === 'fulfilled' ? o.value : [])),
      );
      const counterCount = Math.max(2, Math.floor(maxResults / 3));
      const counterSelected = await selectUsable(
        counterCandidates,
        counterCount,
        'counterpoint',
      );
      await enrichAll(counterSelected, topic, config, stats);
      resources.push(...counterSelected.map(({ resource }) => resource));
      health.counterpoint = counterSelected.length > 0 ? 'ok' : 'degraded';
    } catch {
      health.counterpoint = 'unavailable';
    }
  }

  health.thumbnails =
    stats.thumbnailFailures === 0
      ? 'ok'
      : stats.thumbnailFailures < stats.enriched
        ? 'degraded'
        : 'unavailable';
  health.llm = !config.ollamaUrl
    ? 'unavailable'
    : stats.llmSuccesses === stats.llmAttempts
      ? 'ok'
      : stats.llmSuccesses > 0
        ? 'degraded'
        : 'unavailable';

  return { resources, componentHealth: health };

  /** Verify, drop dead links, pick a diverse set, pair candidate+resource. */
  async function selectUsable(
    pool: Candidate[],
    count: number,
    stance: Stance,
  ): Promise<Array<{ candidate: Candidate; resource: Resource }>> {
    const verified = new Map<Candidate, Resource['verification']>();
    await Promise.all(
      pool.map(async (c) => {
        verified.set(c, await verifyCandidate(c));
      }),
    );
    const usable = pool.filter((c) => verified.get(c) !== 'dead');
    const preliminary = usable.map((c) =>
      toResource(c, verified.get(c) ?? 'unverified', stance),
    );
    const chosen = diversify(preliminary, count);
    return chosen.map((resource) => ({
      candidate: usable[preliminary.indexOf(resource)],
      resource,
    }));
  }

  /** Page-meta + screenshot thumbnails (ADR-0005) and annotation (ADR-0011). */
  async function enrichAll(
    pairs: Array<{ candidate: Candidate; resource: Resource }>,
    annotateTopic: string,
    cfg: PipelineConfig,
    s: typeof stats,
  ): Promise<void> {
    s.enriched += pairs.length;
    await mapLimit(pairs, ANNOTATE_CONCURRENCY, async ({ candidate, resource }) => {
      if ((!candidate.thumbnailUrl || !candidate.description) && !candidate.doi) {
        try {
          const meta = await fetchPageMeta(candidate.url);
          candidate.thumbnailUrl ??= meta.ogImage;
          candidate.description ??= meta.description;
          resource.thumbnailUrl = candidate.thumbnailUrl ?? null;
        } catch {
          s.thumbnailFailures += 1;
        }
      }
      // Layer 3 (ADR-0005): full screenshot, only where a tier injected a
      // capture engine and cheaper layers produced nothing.
      if (!resource.thumbnailUrl && cfg.screenshot) {
        try {
          resource.thumbnailUrl = (await cfg.screenshot(candidate.url)) ?? null;
        } catch {
          // screenshots are a bonus, never a failure
        }
      }
      if (cfg.ollamaUrl) s.llmAttempts += 1;
      resource.annotation = await annotate(
        annotateTopic,
        candidate,
        cfg,
        true,
        resource.stance,
      );
      if (resource.annotation.source === 'llm') s.llmSuccesses += 1;
    });
  }
}

function dedupeAgainst(seen: Set<string>, incoming: Candidate[]): Candidate[] {
  const out: Candidate[] = [];
  for (const candidate of incoming) {
    const key = candidate.url.replace(/\/$/, '').toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(candidate);
  }
  return out;
}

function toResource(
  candidate: Candidate,
  verification: Resource['verification'],
  stance: Stance,
): Resource {
  const { sourceType, commerciallyInterested } = classifySource(candidate);
  return {
    stance,
    title: candidate.title,
    url: candidate.url,
    format: candidate.format,
    sourceType,
    authors: candidate.authors,
    year: candidate.year,
    venue: candidate.venue ?? null,
    verification,
    commerciallyInterested,
    licensing: candidate.licensing ?? 'unknown',
    annotation: { source: 'none', text: null },
    thumbnailUrl: candidate.thumbnailUrl ?? null,
    accessibilityNotes: candidate.accessibilityNotes ?? [],
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
