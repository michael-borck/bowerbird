import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  diversify,
  classifySource,
  parsePageMeta,
  mapUrlStatus,
  toMarkdown,
  heuristicKeywords,
  extractPhrases,
  reconstructAbstract,
  formatApa,
  formatHarvard,
  toLmsHtml,
  mapOpenAlexLicensing,
} from '../dist/index.js';

const resource = (over = {}) => ({
  title: 'T',
  url: 'https://example.org',
  format: 'paper',
  sourceType: 'peer-reviewed',
  authors: [],
  year: 2024,
  venue: null,
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

test('heuristicKeywords surfaces frequent content words, not stopwords', () => {
  const text =
    'Spaced repetition is a learning technique. Spaced repetition schedules ' +
    'reviews of material over increasing intervals, and retrieval practice ' +
    'strengthens memory. The technique of spaced repetition is widely studied.';
  const q = heuristicKeywords(text);
  assert.match(q, /spaced/);
  assert.match(q, /repetition/);
  assert.doesNotMatch(q, /\bthe\b|\bis\b|\band\b/);
});

test('extractPhrases splits on stopwords and keeps multi-word phrases', () => {
  assert.deepEqual(extractPhrases('spaced repetition and retrieval practice in learning'), [
    'spaced repetition',
    'retrieval practice',
  ]);
  assert.deepEqual(extractPhrases('photosynthesis'), []);
});

test('extractPhrases breaks long stopword-free runs into bigrams', () => {
  assert.deepEqual(extractPhrases('spaced repetition retrieval practice memory consolidation'), [
    'spaced repetition',
    'retrieval practice',
    'memory consolidation',
  ]);
});

test('reconstructAbstract rebuilds text from an inverted index', () => {
  const text = reconstructAbstract({
    Testing: [0],
    effects: [1],
    improve: [2],
    retention: [3, 5],
    of: [4],
  });
  assert.equal(text, 'Testing effects improve retention of retention');
});

test('reconstructAbstract truncates at the cap', () => {
  const long = reconstructAbstract({ word: [0, 1, 2, 3, 4] }, 12);
  assert.equal(long.length <= 12, true);
  assert.match(long, /…$/);
});

test('formatApa builds a conventional reference from held metadata', () => {
  const apa = formatApa(
    resource({
      title: 'The critical role of retrieval practice',
      authors: ['Henry Roediger', 'Jeffrey Karpicke'],
      year: 2006,
      venue: 'Psychological Science',
      url: 'https://doi.org/10.1111/x',
    }),
  );
  assert.equal(
    apa,
    'Roediger, H., & Karpicke, J. (2006). The critical role of retrieval practice. *Psychological Science*. https://doi.org/10.1111/x',
  );
});

test('formatHarvard truncates long author lists with et al.', () => {
  const harvard = formatHarvard(
    resource({ authors: ['A One', 'B Two', 'C Three', 'D Four'], year: 2020, title: 'X' }),
  );
  assert.match(harvard, /et al\./);
  assert.match(harvard, /2020,/);
});

test('citations omit missing fields rather than inventing them', () => {
  const apa = formatApa(resource({ authors: [], year: null, venue: null }));
  assert.match(apa, /^\(n\.d\.\)\./);
  assert.doesNotMatch(apa, /undefined|null/);
});

test('toLmsHtml escapes content and uses inline styles only', () => {
  const html = toLmsHtml('a <b> topic', {
    resources: [
      resource({
        title: 'Maths & <scripts>',
        annotation: { source: 'llm', text: 'Covers x < y.' },
      }),
    ],
    componentHealth: {},
  });
  assert.match(html, /a &lt;b&gt; topic/);
  assert.match(html, /Maths &amp; &lt;scripts&gt;/);
  assert.match(html, /Rationale \(generated\):/);
  assert.doesNotMatch(html, /<style|<script/);
});

test('mapOpenAlexLicensing maps CC, OA and closed correctly', () => {
  assert.equal(mapOpenAlexLicensing({ license: 'cc-by', isOa: true }), 'creative-commons');
  assert.equal(mapOpenAlexLicensing({ isOa: true }), 'link-only');
  assert.equal(mapOpenAlexLicensing({ isOa: false }), 'library-subscription');
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
