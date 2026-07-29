import { checkUrl, lookupDoi } from '@michaelborck/cite-sight-core';
import type { Resource, VerificationStatus } from './types.js';
import { mapUrlStatus } from './verify/verify.js';

export interface RecheckEntry {
  resource: Resource;
  previous: VerificationStatus;
  current: VerificationStatus;
  changed: boolean;
}

const RECHECK_CONCURRENCY = 4;

/**
 * Link-rot re-run mode (spec §6): take a previously saved result list and
 * re-verify every resource, reporting what changed. DOI-bearing resources
 * are re-checked against the academic databases (a DOI that resolves is
 * alive regardless of publisher bot-walls); everything else gets a fresh
 * HTTP probe.
 */
export async function recheckResources(resources: Resource[]): Promise<RecheckEntry[]> {
  const entries: RecheckEntry[] = new Array(resources.length);
  let next = 0;
  const workers = Array.from(
    { length: Math.min(RECHECK_CONCURRENCY, resources.length) },
    async () => {
      while (next < resources.length) {
        const i = next++;
        const resource = resources[i];
        const current = await recheckOne(resource);
        entries[i] = {
          resource,
          previous: resource.verification,
          current,
          changed: current !== resource.verification,
        };
      }
    },
  );
  await Promise.all(workers);
  return entries;
}

async function recheckOne(resource: Resource): Promise<VerificationStatus> {
  try {
    const doi = resource.url.match(/doi\.org\/(10\..+)$/)?.[1];
    if (doi) {
      const work = await lookupDoi(doi);
      return work ? 'verified' : 'dead';
    }
    const result = await checkUrl(resource.url);
    return mapUrlStatus(result.status);
  } catch {
    return 'unverified';
  }
}

/** Human-readable report, changes first. */
export function toRecheckMarkdown(entries: RecheckEntry[]): string {
  const changed = entries.filter((e) => e.changed);
  const lines = [
    `# Link check: ${entries.length} resources, ${changed.length} changed`,
    '',
  ];
  for (const entry of [...changed, ...entries.filter((e) => !e.changed)]) {
    const marker = entry.changed ? '⚠' : '✓';
    lines.push(
      `- ${marker} [${entry.resource.title}](${entry.resource.url}) — ` +
        (entry.changed ? `${entry.previous} → **${entry.current}**` : entry.current),
    );
  }
  return lines.join('\n');
}
