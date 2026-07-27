import { Queue, QueueEvents, Worker } from 'bullmq';
import {
  suggestResources,
  type PipelineConfig,
  type SuggestResult,
} from '@michaelborck/bowerbird-core';

/**
 * BullMQ queue so a single long generation cannot block the box (spec §9).
 * The constraint enforced is concurrency, not spend — inference is
 * self-hosted. Two deliberate properties:
 *
 * - Redis being down is non-fatal (ADR-0006): requests run inline and the
 *   queue component reports unavailable.
 * - BYO-key requests NEVER enter the queue: job payloads land in Redis,
 *   and user keys must not be written anywhere server-side (ADR-0004).
 *   BYOK traffic also uses the caller's own inference, so it does not
 *   contend for the box's Ollama — inline is the correct lane anyway.
 */

interface SuggestJob {
  input: string;
  maxResults: number;
}

const QUEUE_NAME = 'bowerbird-suggest';
const JOB_TIMEOUT_MS = 180_000;

export interface SuggestRunner {
  available: boolean;
  run(job: SuggestJob, config: PipelineConfig, byok: boolean): Promise<SuggestResult>;
}

export async function createRunner(
  redisUrl: string,
  defaults: PipelineConfig,
  concurrency: number,
): Promise<SuggestRunner> {
  const inline = (job: SuggestJob, config: PipelineConfig) =>
    suggestResources({ input: job.input, maxResults: job.maxResults }, config);

  let queue: Queue<SuggestJob> | null = null;
  let events: QueueEvents | null = null;
  try {
    const url = new URL(redisUrl);
    const connection = {
      host: url.hostname,
      port: Number(url.port || 6379),
      // Fail fast instead of retrying forever; inline mode covers us.
      retryStrategy: () => null,
      maxRetriesPerRequest: 1,
      enableOfflineQueue: false,
    };
    queue = new Queue<SuggestJob>(QUEUE_NAME, { connection });
    await queue.waitUntilReady();
    events = new QueueEvents(QUEUE_NAME, { connection });
    await events.waitUntilReady();
    new Worker<SuggestJob, SuggestResult>(
      QUEUE_NAME,
      async (job) => inline(job.data, defaults),
      { connection, concurrency },
    );
    console.log(`queue ready (concurrency ${concurrency})`);
  } catch (error) {
    console.warn(
      'queue unavailable, running inline:',
      error instanceof Error ? error.message : error,
    );
    queue = null;
  }

  return {
    available: queue !== null,
    async run(job, config, byok) {
      if (!queue || !events || byok) return inline(job, config);
      const queued = await queue.add('suggest', job, {
        removeOnComplete: true,
        removeOnFail: true,
      });
      return (await queued.waitUntilFinished(events, JOB_TIMEOUT_MS)) as SuggestResult;
    },
  };
}
