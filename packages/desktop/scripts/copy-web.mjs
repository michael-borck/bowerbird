// Bundle the built web UI into the desktop dist. Assumes packages/web has
// been built first (the root build script guarantees the order).
import { cpSync, rmSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const webDist = path.resolve(here, '../../web/dist');
const target = path.resolve(here, '../dist/web');

if (!existsSync(webDist)) {
  console.error('packages/web/dist not found — build the web workspace first.');
  process.exit(1);
}
rmSync(target, { recursive: true, force: true });
cpSync(webDist, target, { recursive: true });
console.log(`Copied web UI into ${target}`);
