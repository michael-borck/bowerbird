import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import { suggestResources } from '@michaelborck/bowerbird-core';

const app = express();
app.use(express.json({ limit: '10mb' }));

const port = Number(process.env.PORT ?? 3000);

// Component health is surfaced to the UI per ADR-0006.
app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    version: process.env.npm_package_version ?? '0.1.0',
    components: {
      verification: 'ok',
      thumbnails: 'ok',
      llm: 'unavailable',
      queue: 'unavailable',
    },
  });
});

app.post('/api/suggest', async (req, res) => {
  try {
    const result = await suggestResources(req.body);
    res.json(result);
  } catch (error) {
    res.status(501).json({
      error: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

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

app.listen(port, () => {
  console.log(`bowerbird server listening on :${port}`);
});
