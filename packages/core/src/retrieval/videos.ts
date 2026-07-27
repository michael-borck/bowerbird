import { fetchJson, type Candidate } from './candidates.js';

interface YoutubeItem {
  id?: { videoId?: string };
  snippet?: {
    title?: string;
    description?: string;
    channelTitle?: string;
    publishedAt?: string;
    thumbnails?: { medium?: { url?: string }; default?: { url?: string } };
  };
}

/**
 * Video retrieval via the YouTube Data API. Requires an API key; without
 * one this component reports unavailable rather than failing the request
 * (ADR-0006).
 */
export async function retrieveVideos(topic: string, apiKey: string): Promise<Candidate[]> {
  const url =
    'https://www.googleapis.com/youtube/v3/search?' +
    new URLSearchParams({
      part: 'snippet',
      type: 'video',
      maxResults: '5',
      q: topic,
      key: apiKey,
    }).toString();
  const data = (await fetchJson(url)) as { items?: YoutubeItem[] };
  return (data.items ?? [])
    .map((item): Candidate | null => {
      const id = item.id?.videoId;
      const s = item.snippet;
      if (!id || !s?.title) return null;
      return {
        title: s.title,
        url: `https://www.youtube.com/watch?v=${id}`,
        format: 'video',
        authors: s.channelTitle ? [s.channelTitle] : [],
        year: s.publishedAt ? new Date(s.publishedAt).getFullYear() : null,
        description: s.description || undefined,
        thumbnailUrl: s.thumbnails?.medium?.url ?? s.thumbnails?.default?.url,
        origin: 'youtube',
        databaseAttested: true,
      };
    })
    .filter((c): c is Candidate => c !== null);
}
