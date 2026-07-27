import { fetchJson, type Candidate } from './candidates.js';

interface OpenLibraryDoc {
  title?: string;
  key?: string;
  author_name?: string[];
  first_publish_year?: number;
  cover_i?: number;
  first_sentence?: string[];
}

/** Book retrieval via the free, keyless Open Library search API. */
export async function retrieveBooks(topic: string): Promise<Candidate[]> {
  const url =
    'https://openlibrary.org/search.json?' +
    new URLSearchParams({ q: topic, limit: '5' }).toString();
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
        origin: 'openlibrary',
        databaseAttested: true,
      };
    })
    .filter((c): c is Candidate => c !== null);
}
