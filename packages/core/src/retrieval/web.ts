import { fetchJson, type Candidate } from './candidates.js';

interface SearxngResult {
  title?: string;
  url?: string;
  content?: string;
}

/**
 * General-web retrieval via a SearXNG instance (self-hosted metasearch;
 * there is no good keyless public web-search API). Optional — without a
 * configured instance this component reports unavailable (ADR-0006).
 * Web results are NOT database-attested: they get a full URL check.
 */
export async function retrieveWeb(topic: string, searxngUrl: string): Promise<Candidate[]> {
  const base = searxngUrl.replace(/\/$/, '');
  const url =
    `${base}/search?` +
    new URLSearchParams({ q: topic, format: 'json', safesearch: '1' }).toString();
  const data = (await fetchJson(url)) as { results?: SearxngResult[] };
  return (data.results ?? [])
    .slice(0, 8)
    .map((r): Candidate | null => {
      if (!r.title || !r.url) return null;
      return {
        title: r.title,
        url: r.url,
        format: 'website',
        authors: [],
        year: null,
        description: r.content || undefined,
        origin: 'searxng',
        databaseAttested: false,
      };
    })
    .filter((c): c is Candidate => c !== null);
}
