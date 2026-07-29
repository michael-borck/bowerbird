import type { PipelineConfig } from '../config.js';
import { extractPhrases } from './query.js';

const QUERY_TIMEOUT_MS = 20_000;

/**
 * Counterpoint mode (spec §3 point 3): derive queries that find credible
 * material DISAGREEING with or complicating the topic's framing. The LLM
 * can invert a framing properly; the heuristic rung appends critical
 * search terms to the topic's phrases (ADR-0006: a floor, not a failure).
 */
export async function deriveCounterQueries(
  topic: string,
  config: PipelineConfig,
): Promise<string[]> {
  if (config.ollamaUrl) {
    try {
      const queries = await llmCounterQueries(topic, config);
      if (queries.length) return queries;
    } catch {
      // fall through to the heuristic
    }
  }
  return heuristicCounterQueries(topic);
}

export function heuristicCounterQueries(topic: string): string[] {
  const phrases = extractPhrases(topic, 2);
  const subjects = phrases.length ? phrases : [topic.slice(0, 60)];
  return subjects.flatMap((s) => [`${s} criticism`, `${s} limitations evidence`]).slice(0, 3);
}

async function llmCounterQueries(topic: string, config: PipelineConfig): Promise<string[]> {
  const res = await fetch(`${config.ollamaUrl!.replace(/\/$/, '')}/api/generate`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(config.ollamaApiKey ? { authorization: `Bearer ${config.ollamaApiKey}` } : {}),
    },
    body: JSON.stringify({
      model: config.ollamaModel ?? 'llama3.1:8b',
      prompt:
        `A lecturer is teaching: "${topic.slice(0, 1000)}"\n\n` +
        `Write 3 short search queries (3-7 words each) that would find ` +
        `credible material which DISAGREES with, criticises, or complicates ` +
        `this topic's usual framing. One query per line, queries only.`,
      stream: false,
      options: { num_predict: 60, temperature: 0.4 },
    }),
    signal: AbortSignal.timeout(QUERY_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`Ollama HTTP ${res.status}`);
  const data = (await res.json()) as { response?: string };
  return (data.response ?? '')
    .split('\n')
    .map((line) => line.replace(/^[\s\d.\-*"']+|["']$/g, '').trim())
    .filter((line) => line.length > 5 && line.length < 90)
    .slice(0, 3);
}
