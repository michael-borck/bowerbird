import { fetchJson, type Candidate } from './candidates.js';
import { extractPhrases } from './query.js';

interface OpenAlexWork {
  display_name?: string;
  publication_year?: number;
  doi?: string;
  cited_by_count?: number;
  authorships?: Array<{ author?: { display_name?: string } }>;
  abstract_inverted_index?: Record<string, number[]>;
  open_access?: { oa_url?: string };
  primary_location?: { landing_page_url?: string };
}

/**
 * Topical paper discovery. cite-sight-core's searchOpenAlex exists to
 * locate a SPECIFIC cited work by bibliographic match; for topic-to-sources
 * discovery we need OpenAlex's relevance-ranked full search, plus the
 * abstract (ADR-0011 rung 2 for papers) and open-access URLs.
 */
export async function searchOpenAlexTopical(
  topic: string,
  mailto?: string,
): Promise<Candidate[]> {
  // Phrase-quoted title/abstract search first: OpenAlex's plain relevance
  // blends citation counts, so generic terms ("learning", "practice")
  // surface mega-cited off-topic surveys. Fall back to plain search when
  // no phrases exist or the phrase filter matches nothing.
  const phrases = extractPhrases(topic);
  let results: OpenAlexWork[] = [];
  if (phrases.length) {
    results = await queryWorks(
      { filter: `title_and_abstract.search:${phrases.map((p) => `"${p}"`).join(' OR ')}` },
      mailto,
    );
  }
  if (!results.length) {
    results = await queryWorks({ search: topic }, mailto);
  }
  return results
    .map((w): Candidate | null => {
      if (!w.display_name) return null;
      const doi = w.doi?.replace(/^https?:\/\/doi\.org\//, '');
      const url =
        (doi ? `https://doi.org/${doi}` : undefined) ??
        w.open_access?.oa_url ??
        w.primary_location?.landing_page_url;
      if (!url) return null;
      return {
        title: w.display_name,
        url,
        format: 'paper',
        authors: (w.authorships ?? [])
          .map((a) => a.author?.display_name)
          .filter((n): n is string => Boolean(n))
          .slice(0, 6),
        year: w.publication_year ?? null,
        doi,
        description: w.abstract_inverted_index
          ? reconstructAbstract(w.abstract_inverted_index)
          : undefined,
        origin: 'openalex',
        databaseAttested: true,
      };
    })
    .filter((c): c is Candidate => c !== null);
}

async function queryWorks(
  query: Record<string, string>,
  mailto?: string,
): Promise<OpenAlexWork[]> {
  const params = new URLSearchParams({
    ...query,
    'per-page': '8',
    select:
      'display_name,publication_year,doi,cited_by_count,authorships,abstract_inverted_index,open_access,primary_location',
  });
  if (mailto) params.set('mailto', mailto);
  const data = (await fetchJson(`https://api.openalex.org/works?${params}`)) as {
    results?: OpenAlexWork[];
  };
  return data.results ?? [];
}

/**
 * OpenAlex ships abstracts as an inverted index (word → positions) for
 * copyright reasons; rebuild the readable text.
 */
export function reconstructAbstract(
  inverted: Record<string, number[]>,
  maxChars = 600,
): string {
  const words: string[] = [];
  for (const [word, positions] of Object.entries(inverted)) {
    for (const pos of positions) words[pos] = word;
  }
  const text = words.filter(Boolean).join(' ');
  return text.length <= maxChars ? text : text.slice(0, maxChars - 1).trimEnd() + '…';
}
