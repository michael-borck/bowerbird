import path from 'node:path';
import os from 'node:os';
import { randomBytes } from 'node:crypto';
import { writeFile, unlink } from 'node:fs/promises';
import express from 'express';
import multer from 'multer';
import {
  toMarkdown,
  toCitations,
  toLmsHtml,
  extract,
  type PipelineConfig,
  type SuggestResult,
} from '@michaelborck/bowerbird-core';

/**
 * The HTTP app, embeddable: the hosted server (index.ts) mounts it behind
 * the BullMQ runner, and the Electron desktop shell mounts the same app
 * with an inline runner. One contract, two homes (ADR-0001).
 */
export interface AppOptions {
  pipelineDefaults: PipelineConfig;
  run: (
    job: { input: string; maxResults: number },
    config: PipelineConfig,
    byok: boolean,
  ) => Promise<SuggestResult>;
  queueAvailable: boolean;
  webDistPath: string;
  version?: string;
}

interface SuggestBody {
  input?: string;
  maxResults?: number;
  format?: 'json' | 'markdown' | 'html' | 'apa' | 'harvard';
  /**
   * Per-request BYO credentials (ADR-0004): held in memory for the life
   * of this call only — never logged, never queued, never persisted.
   * Any BYO credential routes the request around the queue, because job
   * payloads land in Redis.
   */
  provider?: { url?: string; apiKey?: string; model?: string };
  youtubeApiKey?: string;
}

export function createApp(options: AppOptions): express.Express {
  const app = express();
  app.use(express.json({ limit: '10mb' }));

  // Component health is surfaced to the UI per ADR-0006.
  app.get('/api/health', (_req, res) => {
    res.json({
      status: 'ok',
      version: options.version ?? '0.0.0',
      components: {
        verification: 'ok',
        thumbnails: 'ok',
        llm: options.pipelineDefaults.ollamaUrl ? 'configured' : 'unavailable',
        queue: options.queueAvailable ? 'ok' : 'unavailable',
      },
    });
  });

  // Local Ollama discovery for the settings panel (talk-buddy pattern):
  // on desktop "local" is the user's machine; on the hosted box it is the
  // service's own Ollama, which is harmless to report.
  app.get('/api/detect-ollama', async (_req, res) => {
    const base = process.env.OLLAMA_DETECT_URL ?? 'http://localhost:11434';
    try {
      const r = await fetch(`${base}/api/tags`, { signal: AbortSignal.timeout(2000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as { models?: Array<{ name?: string }> };
      res.json({
        available: true,
        url: base,
        models: (data.models ?? []).map((m) => m.name).filter(Boolean),
      });
    } catch {
      res.json({ available: false, url: base, models: [] });
    }
  });

  app.post('/api/suggest', async (req, res) => {
    const body = req.body as SuggestBody;
    const input = body.input?.trim();
    if (!input) {
      res.status(400).json({ error: 'input is required' });
      return;
    }
    const byok = Boolean(body.provider?.url || body.youtubeApiKey);
    const pipelineConfig: PipelineConfig = {
      ...options.pipelineDefaults,
      ...(body.provider?.url
        ? {
            ollamaUrl: body.provider.url,
            ollamaApiKey: body.provider.apiKey,
            ollamaModel: body.provider.model,
          }
        : {}),
      ...(body.youtubeApiKey ? { youtubeApiKey: body.youtubeApiKey } : {}),
    };
    try {
      const result = await options.run(
        { input, maxResults: clamp(body.maxResults ?? 10, 1, 25) },
        pipelineConfig,
        byok,
      );
      const topicLabel = input.slice(0, 120);
      switch (body.format) {
        case 'markdown':
          res.type('text/markdown').send(toMarkdown(topicLabel, result));
          break;
        case 'html':
          res.type('text/html').send(toLmsHtml(topicLabel, result));
          break;
        case 'apa':
        case 'harvard':
          res.type('text/plain').send(toCitations(result, body.format));
          break;
        default:
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

  app.use(express.static(options.webDistPath));
  app.get('*', (_req, res) => {
    res.sendFile(path.join(options.webDistPath, 'index.html'), (err) => {
      if (err) res.status(404).send('Web UI not bundled in this build.');
    });
  });

  return app;
}

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Number.isFinite(n) ? n : min));
}
