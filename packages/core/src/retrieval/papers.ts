import { searchCrossref } from '@michaelborck/cite-sight-core';
import { searchOpenAlexTopical } from './openalexTopical.js';
import type { Candidate } from './candidates.js';

/**
 * Papers via OpenAlex topical search (relevance-ranked, with abstracts);
 * Crossref through cite-sight-core (ADR-0002) as the fallback when
 * OpenAlex is unreachable. Results are database-attested: existence is
 * verified by construction, no separate URL probe needed.
 */
export async function retrievePapers(topic: string, mailto?: string): Promise<Candidate[]> {
  try {
    const candidates = await searchOpenAlexTopical(topic, mailto);
    if (candidates.length > 0) return dedupe(candidates);
  } catch {
    // fall through to Crossref
  }
  const works = await searchCrossref(topic, mailto);
  return dedupe(
    works.flatMap((work): Candidate[] => {
      const url = work.doi ? `https://doi.org/${work.doi}` : work.url;
      if (!url) return [];
      return [
        {
          title: work.title,
          url,
          format: 'paper',
          authors: work.authors,
          year: work.year,
          doi: work.doi,
          origin: 'crossref',
          databaseAttested: true,
        },
      ];
    }),
  );
}

function dedupe(candidates: Candidate[]): Candidate[] {
  const seen = new Set<string>();
  return candidates.filter((c) => {
    const key = (c.doi ?? c.title).toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
