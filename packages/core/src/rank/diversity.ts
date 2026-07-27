import type { Resource, ResourceFormat } from '../types.js';

/**
 * Deliberate diversity of the return set (spec §10): balance format and
 * voice by default — one video, one paper, one practitioner piece — so the
 * retrieval layer's biases do not become the reading list's biases.
 *
 * Round-robin across formats in a fixed priority order, preserving each
 * format's internal ranking.
 */
const FORMAT_ORDER: ResourceFormat[] = [
  'paper',
  'video',
  'podcast',
  'website',
  'book',
  'report',
  'white-paper',
];

export function diversify(resources: Resource[], maxResults: number): Resource[] {
  const byFormat = new Map<ResourceFormat, Resource[]>();
  for (const r of resources) {
    const list = byFormat.get(r.format) ?? [];
    list.push(r);
    byFormat.set(r.format, list);
  }
  const out: Resource[] = [];
  while (out.length < maxResults) {
    let took = false;
    for (const format of FORMAT_ORDER) {
      const list = byFormat.get(format);
      const next = list?.shift();
      if (next) {
        out.push(next);
        took = true;
        if (out.length >= maxResults) break;
      }
    }
    if (!took) break;
  }
  return out;
}
