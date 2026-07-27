import { fetchJson, type Candidate } from './candidates.js';
import { extractPhrases } from './query.js';

interface OpenLibraryDoc {
  title?: string;
  key?: string;
  author_name?: string[];
  first_publish_year?: number;
  cover_i?: number;
  first_sentence?: string[];
  publisher?: string[];
  ebook_access?: 'public' | 'borrowable' | 'printdisabled' | 'no_ebook';
}

function bookLicensing(access?: OpenLibraryDoc['ebook_access']) {
  if (access === 'public') return 'oer' as const;
  if (access === 'borrowable' || access === 'printdisabled')
    return 'library-subscription' as const;
  return 'link-only' as const;
}

/** Book retrieval via the free, keyless Open Library search API. */
export async function retrieveBooks(topic: string): Promise<Candidate[]> {
  // Phrase-quoted query where possible, same reasoning as papers: plain
  // multi-word queries match generic single terms and surface noise.
  const phrases = extractPhrases(topic);
  const q = phrases.length ? phrases.map((p) => `"${p}"`).join(' OR ') : topic;
  const url =
    'https://openlibrary.org/search.json?' +
    new URLSearchParams({ q, limit: '5' }).toString();
  const data = (await fetchJson(url)) as { docs?: OpenLibraryDoc[] };
  return (data.docs ?? [])
    .map((d): Candidate | null => {
      if (!d.title || !d.key) return null;
      return {
        title: d.title,
        url: `https://openlibrary.org${d.key}`,
        format: 'book',
        authors: d.author_name ?? [],
        year: d.first_publish_year ?? null,
        description: d.first_sentence?.[0],
        thumbnailUrl: d.cover_i
          ? `https://covers.openlibrary.org/b/id/${d.cover_i}-M.jpg`
          : undefined,
        venue: d.publisher?.[0],
        licensing: bookLicensing(d.ebook_access),
        origin: 'openlibrary',
        databaseAttested: true,
      };
    })
    .filter((c): c is Candidate => c !== null);
}
