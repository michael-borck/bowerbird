import type { SuggestRequest, SuggestResult } from './types.js';
import type { PipelineConfig } from './config.js';
import { suggestResources } from './pipeline.js';
import { toMarkdown } from './export/markdown.js';

export interface BatchEntry {
  topic: string;
  result: SuggestResult;
}

const BATCH_CONCURRENCY = 2;
const MAX_TOPICS = 50;

/**
 * Batch input (spec §9): a semester of topics at once. A self-host and
 * desktop tier feature — the hosted free tier takes one topic per request.
 * One failed topic never sinks the batch (ADR-0006): it reports an empty
 * result with the failure flagged in componentHealth.
 */
export async function suggestBatch(
  topics: string[],
  config: PipelineConfig = {},
  options: Omit<SuggestRequest, 'input'> = {},
): Promise<BatchEntry[]> {
  const cleaned = topics.map((t) => t.trim()).filter(Boolean).slice(0, MAX_TOPICS);
  const entries: BatchEntry[] = new Array(cleaned.length);
  let next = 0;
  const workers = Array.from(
    { length: Math.min(BATCH_CONCURRENCY, cleaned.length) },
    async () => {
      while (next < cleaned.length) {
        const i = next++;
        try {
          entries[i] = {
            topic: cleaned[i],
            result: await suggestResources({ ...options, input: cleaned[i] }, config),
          };
        } catch (error) {
          entries[i] = {
            topic: cleaned[i],
            result: {
              resources: [],
              componentHealth: {
                batch: 'unavailable',
              },
            },
          };
          void error;
        }
      }
    },
  );
  await Promise.all(workers);
  return entries;
}

/** One markdown document, a section per topic. */
export function toBatchMarkdown(entries: BatchEntry[]): string {
  return entries.map((e) => toMarkdown(e.topic, e.result)).join('\n\n---\n\n');
}
