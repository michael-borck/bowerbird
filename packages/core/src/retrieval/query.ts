import type { PipelineConfig } from '../config.js';

const SHORT_INPUT_CHARS = 150;
const QUERY_TIMEOUT_MS = 20_000;

const STOPWORDS = new Set(
  (
    'a an and are as at be but by for from has have if in into is it its of on or ' +
    'that the their there these this to was were will with we you your not can ' +
    'which what when where who how than then also may might must should would could ' +
    'about after all any because been before being between both do does did each ' +
    'few he her him his i me more most much my no nor only other our out over own ' +
    'same she so some such them they those through under until up very while'
  ).split(' '),
);

/**
 * Turn the request input into a search query. A short input IS the query;
 * a pasted document or worksheet is not — querying APIs with 40 KB of text
 * matches everything and nothing. Prefer an LLM keyword extraction (it can
 * infer the topic), fall back to term frequency (ADR-0006: heuristic rung,
 * never a failure).
 */
export async function deriveQuery(input: string, config: PipelineConfig): Promise<string> {
  const trimmed = input.trim().replace(/\s+/g, ' ');
  if (trimmed.length <= SHORT_INPUT_CHARS) return trimmed;
  if (config.ollamaUrl) {
    try {
      return await llmKeywords(trimmed, config);
    } catch {
      // fall through to the heuristic
    }
  }
  return heuristicKeywords(trimmed);
}

async function llmKeywords(text: string, config: PipelineConfig): Promise<string> {
  const res = await fetch(`${config.ollamaUrl!.replace(/\/$/, '')}/api/generate`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(config.ollamaApiKey ? { authorization: `Bearer ${config.ollamaApiKey}` } : {}),
    },
    body: JSON.stringify({
      model: config.ollamaModel ?? 'llama3.1:8b',
      prompt:
        `This is teaching material:\n\n${text.slice(0, 3000)}\n\n` +
        `Reply with a 3-8 word search query capturing its main topic, ` +
        `suitable for an academic search engine. Reply with the query only.`,
      stream: false,
      options: { num_predict: 30, temperature: 0.1 },
    }),
    signal: AbortSignal.timeout(QUERY_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`Ollama HTTP ${res.status}`);
  const data = (await res.json()) as { response?: string };
  const query = data.response?.trim().replace(/^["']|["']$/g, '').split('\n')[0];
  if (!query || query.length > 120) throw new Error('unusable query from LLM');
  return query;
}

/**
 * Split a short topic into multi-word content phrases at stopword and
 * punctuation boundaries: "spaced repetition and retrieval practice in
 * learning" → ["spaced repetition", "retrieval practice"]. Phrase-quoted
 * search is what keeps mega-cited generic-term papers out of the results.
 * Chunks longer than 3 words are split into bigrams so an LLM-derived
 * keyword run doesn't become one impossible phrase.
 */
export function extractPhrases(text: string, maxPhrases = 4): string[] {
  const chunks: string[][] = [];
  let current: string[] = [];
  for (const raw of text.toLowerCase().split(/[^a-z0-9'-]+/)) {
    if (!raw || STOPWORDS.has(raw)) {
      if (current.length) chunks.push(current);
      current = [];
    } else {
      current.push(raw);
    }
  }
  if (current.length) chunks.push(current);

  const phrases: string[] = [];
  for (const chunk of chunks) {
    if (chunk.length < 2) continue;
    if (chunk.length <= 3) {
      phrases.push(chunk.join(' '));
    } else {
      for (let i = 0; i + 1 < chunk.length; i += 2) {
        phrases.push(chunk.slice(i, i + 2).join(' '));
      }
    }
  }
  return [...new Set(phrases)].slice(0, maxPhrases);
}

/**
 * Course-material boilerplate: high-frequency in worksheets and slides,
 * zero topical signal. Excluded from derived queries only — a short typed
 * topic like "exam preparation" is never filtered.
 */
const TEACHING_BOILERPLATE = new Set(
  (
    'week worksheet lecture lectures students student quiz exercises exercise ' +
    'exam exams unit assignment assignments semester chapter module topic topics ' +
    'course class homework reading readings page pages slide slides tutorial ' +
    'session attempt cover covers includes learning'
  ).split(' '),
);

/**
 * Topic phrases from a document, scored by member-word frequency, joined
 * with commas so downstream phrase extraction preserves the boundaries.
 * Falls back to top single words when the text yields no phrases.
 */
export function heuristicKeywords(text: string, maxPhrases = 3): string {
  const skip = (w: string) => STOPWORDS.has(w) || TEACHING_BOILERPLATE.has(w) || /\d/.test(w);

  const freq = new Map<string, number>();
  const chunks: string[][] = [];
  let current: string[] = [];
  for (const raw of text.toLowerCase().split(/[^a-z0-9'-]+/)) {
    if (!raw || skip(raw)) {
      if (current.length) chunks.push(current);
      current = [];
      continue;
    }
    freq.set(raw, (freq.get(raw) ?? 0) + 1);
    current.push(raw);
  }
  if (current.length) chunks.push(current);

  const phrases = new Map<string, number>();
  for (const chunk of chunks) {
    if (chunk.length < 2) continue;
    const parts: string[][] =
      chunk.length <= 3
        ? [chunk]
        : Array.from({ length: Math.floor(chunk.length / 2) }, (_, i) =>
            chunk.slice(i * 2, i * 2 + 2),
          );
    for (const part of parts) {
      const key = part.join(' ');
      const score = part.reduce((sum, w) => sum + (freq.get(w) ?? 0), 0);
      phrases.set(key, Math.max(phrases.get(key) ?? 0, score));
    }
  }
  if (phrases.size) {
    return [...phrases.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, maxPhrases)
      .map(([p]) => p)
      .join(', ');
  }
  return [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([w]) => w)
    .join(' ');
}
