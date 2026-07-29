import type { Annotation } from '../types.js';
import type { Candidate } from '../retrieval/candidates.js';
import type { PipelineConfig } from '../config.js';
import { generateRationale } from './ollama.js';

/**
 * The annotation ladder (ADR-0011). Falling down a rung is per-resource and
 * non-fatal:
 *   1. LLM relational rationale
 *   2. extractive description from retrieval/page metadata
 *   3. nothing — metadata-only result
 */
export async function annotate(
  topic: string,
  candidate: Candidate,
  config: PipelineConfig,
  llmWanted: boolean,
  stance: 'supporting' | 'counterpoint' = 'supporting',
): Promise<Annotation> {
  if (llmWanted && config.ollamaUrl) {
    try {
      return {
        source: 'llm',
        text: await generateRationale(topic, candidate, config, stance),
      };
    } catch {
      // fall through to rung 2
    }
  }
  const extracted = candidate.description?.trim();
  if (extracted) {
    return { source: 'extracted', text: truncate(extracted, 400) };
  }
  return { source: 'none', text: null };
}

function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max - 1).trimEnd() + '…';
}
