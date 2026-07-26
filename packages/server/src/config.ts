/**
 * Server configuration, read once from the environment. In the Docker
 * deployment these come from the .env file next to docker-compose.yml —
 * see .env.example at the repo root for documentation of each value.
 */
export interface ServerConfig {
  port: number;
  redisUrl: string;
  /** Ollama instance used for rationale generation. */
  ollamaUrl: string;
  /**
   * The server's own bearer key for its Ollama instance (sent as
   * `Authorization: Bearer <key>`), for Ollama behind an authenticating
   * proxy. Empty when Ollama needs no auth. Distinct from users' BYO keys,
   * which are never persisted server-side (ADR-0004).
   */
  ollamaApiKey: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): ServerConfig {
  return {
    port: Number(env.PORT ?? 3000),
    redisUrl: env.REDIS_URL ?? 'redis://localhost:6379',
    ollamaUrl: env.OLLAMA_URL ?? 'http://localhost:11434',
    ollamaApiKey: env.OLLAMA_API_KEY ?? '',
  };
}
