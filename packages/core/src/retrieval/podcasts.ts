import { fetchJson, type Candidate } from './candidates.js';

interface ItunesResult {
  collectionName?: string;
  trackName?: string;
  artistName?: string;
  collectionViewUrl?: string;
  trackViewUrl?: string;
  artworkUrl600?: string;
  artworkUrl100?: string;
  releaseDate?: string;
}

/** Podcast retrieval via the free, keyless iTunes Search API. */
export async function retrievePodcasts(topic: string): Promise<Candidate[]> {
  const url =
    'https://itunes.apple.com/search?' +
    new URLSearchParams({ media: 'podcast', limit: '5', term: topic }).toString();
  const data = (await fetchJson(url)) as { results?: ItunesResult[] };
  return (data.results ?? [])
    .map((r): Candidate | null => {
      const link = r.collectionViewUrl ?? r.trackViewUrl;
      const title = r.collectionName ?? r.trackName;
      if (!link || !title) return null;
      return {
        title,
        url: link,
        format: 'podcast',
        authors: r.artistName ? [r.artistName] : [],
        year: r.releaseDate ? new Date(r.releaseDate).getFullYear() : null,
        thumbnailUrl: r.artworkUrl600 ?? r.artworkUrl100,
        origin: 'itunes',
        databaseAttested: true,
      };
    })
    .filter((c): c is Candidate => c !== null);
}
