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
  const items = (data.items ?? []).filter(
    (item) => item.id?.videoId && item.snippet?.title,
  );

  // One batched details call covers captions (accessibility, spec §10) and
  // Creative Commons licensing. Failure is non-fatal (ADR-0006): the videos
  // still return, just without those fields.
  const details = await fetchVideoDetails(
    items.map((i) => i.id!.videoId!),
    apiKey,
  ).catch(() => new Map<string, VideoDetails>());

  return items.map((item): Candidate => {
    const id = item.id!.videoId!;
    const s = item.snippet!;
    const detail = details.get(id);
    return {
      title: s.title!,
      url: `https://www.youtube.com/watch?v=${id}`,
      format: 'video',
      authors: s.channelTitle ? [s.channelTitle] : [],
      year: s.publishedAt ? new Date(s.publishedAt).getFullYear() : null,
      description: s.description || undefined,
      thumbnailUrl: s.thumbnails?.medium?.url ?? s.thumbnails?.default?.url,
      venue: s.channelTitle,
      licensing:
        detail?.license === 'creativeCommon' ? 'creative-commons' : 'link-only',
      accessibilityNotes: detail?.captions ? ['captions available'] : [],
      origin: 'youtube',
      databaseAttested: true,
    };
  });
}

interface VideoDetails {
  captions: boolean;
  license?: string;
}

async function fetchVideoDetails(
  ids: string[],
  apiKey: string,
): Promise<Map<string, VideoDetails>> {
  if (!ids.length) return new Map();
  const url =
    'https://www.googleapis.com/youtube/v3/videos?' +
    new URLSearchParams({
      part: 'contentDetails,status',
      id: ids.join(','),
      key: apiKey,
    }).toString();
  const data = (await fetchJson(url)) as {
    items?: Array<{
      id?: string;
      contentDetails?: { caption?: string };
      status?: { license?: string };
    }>;
  };
  const map = new Map<string, VideoDetails>();
  for (const item of data.items ?? []) {
    if (!item.id) continue;
    map.set(item.id, {
      captions: item.contentDetails?.caption === 'true',
      license: item.status?.license,
    });
  }
  return map;
}
