import path from 'node:path';
import os from 'node:os';
import { randomBytes } from 'node:crypto';
import { writeFile, unlink } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import express from 'express';
import multer from 'multer';
import {
  configFromEnv,
  toMarkdown,
  extract,
  type PipelineConfig,
} from '@michaelborck/bowerbird-core';
import { loadConfig } from './config.js';
import { createRunner } from './queue.js';

const config = loadConfig();
const pipelineDefaults = configFromEnv();
const runner = await createRunner(
  config.redisUrl,
  pipelineDefaults,
  Number(process.env.SUGGEST_CONCURRENCY ?? 2),
);

const app = express();
app.use(express.json({ limit: '10mb' }));

// Component health is surfaced to the UI per ADR-0006.
app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    version: process.env.npm_package_version ?? '0.2.0',
    components: {
      verification: 'ok',
      thumbnails: 'ok',
      llm: pipelineDefaults.ollamaUrl ? 'configured' : 'unavailable',
      queue: runner.available ? 'ok' : 'unavailable',
    },
  });
});

interface SuggestBody {
  input?: string;
  maxResults?: number;
  format?: 'json' | 'markdown';
  /**
   * Per-request BYO provider (ADR-0004): held in memory for the life of
   * this call only — never logged, never queued, never persisted.
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
  const byok = Boolean(body.provider?.url);
  const pipelineConfig: PipelineConfig = byok
    ? {
        ...pipelineDefaults,
        ollamaUrl: body.provider!.url,
        ollamaApiKey: body.provider!.apiKey,
        ollamaModel: body.provider!.model,
      }
    : pipelineDefaults;
  try {
    const result = await runner.run(
      { input, maxResults: clamp(body.maxResults ?? 10, 1, 25) },
      pipelineConfig,
      byok,
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

// Document input (spec §13): extract text from PDF, DOCX, TXT or MD.
const ALLOWED_EXTENSIONS = new Set(['.pdf', '.docx', '.txt', '.md']);
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 20 * 1024 * 1024 },
});

app.post('/api/extract', upload.single('file'), async (req, res) => {
  const file = req.file;
  if (!file) {
    res.status(400).json({ error: 'file is required' });
    return;
  }
  const ext = path.extname(file.originalname).toLowerCase();
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    res.status(400).json({ error: `unsupported file type ${ext || '(none)'}` });
    return;
  }
  // cite-sight-core's extractors take a path; use a throwaway temp file.
  const tmp = path.join(os.tmpdir(), `bowerbird-${randomBytes(8).toString('hex')}${ext}`);
  try {
    await writeFile(tmp, file.buffer);
    const doc = await extract(tmp);
    res.json({ fileName: file.originalname, text: doc.text.slice(0, 200_000) });
  } catch (error) {
    res.status(422).json({
      error: error instanceof Error ? error.message : 'extraction failed',
    });
  } finally {
    await unlink(tmp).catch(() => {});
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
