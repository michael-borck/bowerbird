import type { Candidate } from '../retrieval/candidates.js';
import type { PipelineConfig } from '../config.js';

const GENERATE_TIMEOUT_MS = 30_000;
const DEFAULT_MODEL = 'llama3.1:8b';

/**
 * Generate a one-to-two sentence relational rationale (ADR-0011 rung 1).
 * Prompt is sized for 4B–8B models (spec §8): short, concrete, no format
 * tricks. The LLM only writes ABOUT a resource retrieval already found —
 * it can never introduce one.
 */
export async function generateRationale(
  topic: string,
  candidate: Candidate,
  config: PipelineConfig,
): Promise<string> {
  if (!config.ollamaUrl) throw new Error('no Ollama configured');
  const meta = [
    `Title: ${candidate.title}`,
    candidate.authors.length ? `By: ${candidate.authors.slice(0, 3).join(', ')}` : null,
    candidate.year ? `Year: ${candidate.year}` : null,
    `Type: ${candidate.format}`,
    candidate.description ? `Description: ${candidate.description.slice(0, 400)}` : null,
  ]
    .filter(Boolean)
    .join('\n');

  const prompt =
    `A lecturer is teaching: "${topic.slice(0, 300)}"\n\n` +
    `Candidate supporting resource:\n${meta}\n\n` +
    `In one or two sentences, say why this resource could support that teaching, ` +
    `what it adds, and (if apparent) what it does not cover. ` +
    `Be concrete and honest; do not invent details not present above. ` +
    `Reply with the sentences only.`;

  const res = await fetch(`${config.ollamaUrl.replace(/\/$/, '')}/api/generate`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(config.ollamaApiKey ? { authorization: `Bearer ${config.ollamaApiKey}` } : {}),
    },
    body: JSON.stringify({
      model: config.ollamaModel ?? DEFAULT_MODEL,
      prompt,
      stream: false,
      options: { num_predict: 120, temperature: 0.3 },
    }),
    signal: AbortSignal.timeout(GENERATE_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`Ollama HTTP ${res.status}`);
  const data = (await res.json()) as { response?: string };
  const text = data.response?.trim();
  if (!text) throw new Error('empty Ollama response');
  return text;
}
