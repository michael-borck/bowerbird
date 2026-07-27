import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  diversify,
  classifySource,
  parsePageMeta,
  mapUrlStatus,
  toMarkdown,
} from '../dist/index.js';

const resource = (over = {}) => ({
  title: 'T',
  url: 'https://example.org',
  format: 'paper',
  sourceType: 'peer-reviewed',
  authors: [],
  year: 2024,
  verification: 'verified',
  commerciallyInterested: false,
  licensing: 'unknown',
  annotation: { source: 'none', text: null },
  thumbnailUrl: null,
  accessibilityNotes: [],
  ...over,
});

test('diversify round-robins across formats instead of clustering', () => {
  const input = [
    resource({ title: 'p1' }),
    resource({ title: 'p2' }),
    resource({ title: 'p3' }),
    resource({ title: 'v1', format: 'video' }),
    resource({ title: 'b1', format: 'book' }),
  ];
  const out = diversify(input, 4).map((r) => r.title);
  assert.deepEqual(out, ['p1', 'v1', 'b1', 'p2']);
});

test('diversify respects maxResults and exhaustion', () => {
  const out = diversify([resource(), resource()], 10);
  assert.equal(out.length, 2);
});

test('classifySource flags consultancy hosts as commercially interested', () => {
  const { sourceType, commerciallyInterested } = classifySource({
    title: 'Report',
    url: 'https://www.mckinsey.com/insights/ai-report',
    format: 'report',
    authors: [],
    year: null,
    origin: 'searxng',
    databaseAttested: false,
  });
  assert.equal(sourceType, 'vendor');
  assert.equal(commerciallyInterested, true);
});

test('classifySource labels papers peer-reviewed and government by TLD', () => {
  const paper = classifySource({
    title: 'P', url: 'https://doi.org/10.1/x', format: 'paper',
    authors: [], year: null, doi: '10.1/x', origin: 'openalex', databaseAttested: true,
  });
  assert.equal(paper.sourceType, 'peer-reviewed');
  const gov = classifySource({
    title: 'G', url: 'https://www.abs.gov.au/stats', format: 'website',
    authors: [], year: null, origin: 'searxng', databaseAttested: false,
  });
  assert.equal(gov.sourceType, 'government');
});

test('parsePageMeta reads og tags in either attribute order and decodes entities', () => {
  const html = `<head>
    <meta property="og:image" content="https://x.example/img.png">
    <meta content="Tom &amp; Jerry&#039;s guide" property="og:description">
    <meta name="description" content="fallback">
  </head>`;
  const meta = parsePageMeta(html);
  assert.equal(meta.ogImage, 'https://x.example/img.png');
  assert.equal(meta.description, "Tom & Jerry's guide");
});

test('parsePageMeta falls back to name=description', () => {
  const meta = parsePageMeta('<meta name="description" content="plain desc">');
  assert.equal(meta.description, 'plain desc');
});

test('mapUrlStatus never upgrades inconclusive checks', () => {
  assert.equal(mapUrlStatus('live'), 'verified');
  assert.equal(mapUrlStatus('redirect'), 'verified');
  assert.equal(mapUrlStatus('blocked'), 'blocked');
  assert.equal(mapUrlStatus('dead'), 'dead');
  assert.equal(mapUrlStatus('timeout'), 'unverified');
  assert.equal(mapUrlStatus('error'), 'unverified');
});

test('toMarkdown distinguishes generated rationale from extracted description', () => {
  const md = toMarkdown('quantum computing', {
    resources: [
      resource({ annotation: { source: 'llm', text: 'Covers the basics.' } }),
      resource({ annotation: { source: 'extracted', text: 'A survey paper.' } }),
    ],
    componentHealth: { papers: 'ok', llm: 'degraded' },
  });
  assert.match(md, /Rationale \(generated\): Covers the basics\./);
  assert.match(md, /Description \(extracted\): A survey paper\./);
  assert.match(md, /Degraded components this run: llm \(degraded\)/);
  assert.match(md, /none are LLM-generated citations/);
});
