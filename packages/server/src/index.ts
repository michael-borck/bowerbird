import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import {
  suggestResources,
  configFromEnv,
  toMarkdown,
  type PipelineConfig,
} from '@michaelborck/bowerbird-core';
import { loadConfig } from './config.js';

const config = loadConfig();
const pipelineDefaults = configFromEnv();
const app = express();
app.use(express.json({ limit: '10mb' }));

// Component health is surfaced to the UI per ADR-0006.
app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    version: process.env.npm_package_version ?? '0.1.1',
    components: {
      verification: 'ok',
      thumbnails: 'ok',
      llm: pipelineDefaults.ollamaUrl ? 'configured' : 'unavailable',
      queue: 'unavailable',
    },
  });
});

interface SuggestBody {
  input?: string;
  maxResults?: number;
  format?: 'json' | 'markdown';
  /**
   * Per-request BYO provider (ADR-0004): held in memory for the life of
   * this call only — never logged, never persisted.
   */
  provider?: { url?: string; apiKey?: string; model?: string };
}

app.post('/api/suggest', async (req, res) => {
  const body = req.body as SuggestBody;
  const input = body.input?.trim();
  if (!input) {
    res.status(400).json({ error: 'input is required' });
    return;
  }
  const pipelineConfig: PipelineConfig = {
    ...pipelineDefaults,
    ...(body.provider?.url
      ? {
          ollamaUrl: body.provider.url,
          ollamaApiKey: body.provider.apiKey,
          ollamaModel: body.provider.model,
        }
      : {}),
  };
  try {
    const result = await suggestResources(
      { input, maxResults: clamp(body.maxResults ?? 10, 1, 25) },
      pipelineConfig,
    );
    if (body.format === 'markdown') {
      res.type('text/markdown').send(toMarkdown(input.slice(0, 120), result));
    } else {
      res.json(result);
    }
  } catch (error) {
    res.status(500).json({
      error: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Number.isFinite(n) ? n : min));
}

// In the Docker image the built web UI is copied alongside the server.
const webDist = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../public',
);
app.use(express.static(webDist));
app.get('*', (_req, res) => {
  res.sendFile(path.join(webDist, 'index.html'), (err) => {
    if (err) res.status(404).send('Web UI not bundled in this build.');
  });
});

app.listen(config.port, () => {
  console.log(`bowerbird server listening on :${config.port}`);
});
