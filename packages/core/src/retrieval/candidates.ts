import type { LicensingStatus, ResourceFormat } from '../types.js';

/** A retrieved-but-not-yet-enriched resource. */
export interface Candidate {
  title: string;
  url: string;
  format: ResourceFormat;
  authors: string[];
  year: number | null;
  doi?: string;
  /** Journal, publisher or channel, when the source provides it. */
  venue?: string;
  /** Licensing signal from the retrieval source (spec §3: institutional plumbing). */
  licensing?: LicensingStatus;
  accessibilityNotes?: string[];
  /** Description text supplied by the retrieval source, if any (ADR-0011 rung 2). */
  description?: string;
  thumbnailUrl?: string;
  /** Where this candidate came from, for provenance and source-typing. */
  origin: 'openalex' | 'crossref' | 'itunes' | 'openlibrary' | 'youtube' | 'searxng';
  /** True when the origin is an academic database, so existence is already attested. */
  databaseAttested: boolean;
}

const FETCH_TIMEOUT_MS = 8000;

export async function fetchJson(url: string, headers: Record<string, string> = {}): Promise<unknown> {
  const res = await fetch(url, {
    headers: { accept: 'application/json', ...headers },
    signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${new URL(url).host}`);
  return res.json();
}
