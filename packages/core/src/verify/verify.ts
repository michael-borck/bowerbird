import { checkUrl } from '@michaelborck/cite-sight-core';
import type { VerificationStatus } from '../types.js';
import type { Candidate } from '../retrieval/candidates.js';

/**
 * Map cite-sight-core's UrlStatus onto Bowerbird's VerificationStatus.
 * `unverified` means the check could not run or was inconclusive — never
 * silently upgraded (ADR-0006).
 */
export function mapUrlStatus(status: string): VerificationStatus {
  switch (status) {
    case 'live':
    case 'redirect':
      return 'verified';
    case 'blocked':
      return 'blocked';
    case 'dead':
      return 'dead';
    default:
      return 'unverified';
  }
}

export async function verifyCandidate(candidate: Candidate): Promise<VerificationStatus> {
  // Academic-database results are existence-attested by retrieval itself:
  // the DOI/entry came out of Crossref/OpenAlex/iTunes/Open Library seconds
  // ago. Probing doi.org links additionally hits publisher bot-walls and
  // reports false "blocked".
  if (candidate.databaseAttested) return 'verified';
  try {
    const result = await checkUrl(candidate.url);
    return mapUrlStatus(result.status);
  } catch {
    return 'unverified';
  }
}
