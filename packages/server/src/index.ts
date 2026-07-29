import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { configFromEnv } from '@michaelborck/bowerbird-core';
import { loadConfig } from './config.js';
import { createRunner } from './queue.js';
import { createApp } from './app.js';

const config = loadConfig();
const pipelineDefaults = configFromEnv();
const runner = await createRunner(
  config.redisUrl,
  pipelineDefaults,
  Number(process.env.SUGGEST_CONCURRENCY ?? 2),
);

// In the Docker image the built web UI is copied alongside the server.
const webDistPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../public',
);

const app = createApp({
  pipelineDefaults,
  run: (job, cfg, byok) => runner.run(job, cfg, byok),
  queueAvailable: runner.available,
  webDistPath,
  version: process.env.npm_package_version,
  // Default on for self-hosters; the hosted free tier sets
  // BOWERBIRD_ALLOW_BATCH=0 (spec §9: batch is a tier feature).
  allowBatch: process.env.BOWERBIRD_ALLOW_BATCH !== '0',
});

app.listen(config.port, () => {
  console.log(`bowerbird server listening on :${config.port}`);
});
