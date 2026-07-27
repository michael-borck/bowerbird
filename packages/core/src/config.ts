/**
 * Pipeline configuration. Everything is optional: missing capability means
 * the corresponding component degrades non-fatally (ADR-0006) and reports
 * itself in componentHealth.
 */
export interface PipelineConfig {
  /** Ollama base URL for rationale generation (ADR-0003). */
  ollamaUrl?: string;
  /** Bearer key for Ollama behind an authenticating proxy. */
  ollamaApiKey?: string;
  /** Model name; generation tasks are sized for 4B–8B models (spec §8). */
  ollamaModel?: string;
  /** YouTube Data API v3 key; without it video retrieval is unavailable. */
  youtubeApiKey?: string;
  /** SearXNG instance URL for general-web retrieval; optional. */
  searxngUrl?: string;
  /** Contact email passed to polite-pool APIs (Crossref/OpenAlex). */
  mailto?: string;
}

export function configFromEnv(env: NodeJS.ProcessEnv = process.env): PipelineConfig {
  return {
    ollamaUrl: env.OLLAMA_URL || undefined,
    ollamaApiKey: env.OLLAMA_API_KEY || undefined,
    ollamaModel: env.OLLAMA_MODEL || undefined,
    youtubeApiKey: env.YOUTUBE_API_KEY || undefined,
    searxngUrl: env.SEARXNG_URL || undefined,
    mailto: env.BOWERBIRD_MAILTO || undefined,
  };
}
