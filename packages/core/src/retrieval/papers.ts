import { searchOpenAlex, searchCrossref } from '@michaelborck/cite-sight-core';
import type { Candidate } from './candidates.js';

/**
 * Papers come from the academic databases cite-sight-core already speaks to
 * (ADR-0002). Results are database-attested: existence is verified by
 * construction, no separate URL probe needed.
 */
export async function retrievePapers(topic: string, mailto?: string): Promise<Candidate[]> {
  // OpenAlex first (richer, no key); Crossref as the second opinion.
  const [openalex, crossref] = await Promise.allSettled([
    searchOpenAlex(topic, mailto),
    searchCrossref(topic, mailto),
  ]);
  const works = [
    ...(openalex.status === 'fulfilled' ? openalex.value : []),
    ...(crossref.status === 'fulfilled' ? crossref.value : []),
  ];
  if (openalex.status === 'rejected' && crossref.status === 'rejected') {
    throw new Error('all paper databases unreachable');
  }

  const seen = new Set<string>();
  const candidates: Candidate[] = [];
  for (const work of works) {
    const key = (work.doi ?? work.title).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    const url = work.doi ? `https://doi.org/${work.doi}` : work.url;
    if (!url) continue;
    candidates.push({
      title: work.title,
      url,
      format: 'paper',
      authors: work.authors,
      year: work.year,
      doi: work.doi,
      origin: work.source === 'crossref' ? 'crossref' : 'openalex',
      databaseAttested: true,
    });
  }
  return candidates;
}
