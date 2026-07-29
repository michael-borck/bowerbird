/**
 * Bowerbird core: retrieval, verification, ranking and rationale.
 *
 * This package has no UI or transport assumptions (ADR-0001). Verification
 * extends @michaelborck/cite-sight-core rather than duplicating it
 * (ADR-0002). Every enrichment step degrades non-fatally (ADR-0006), and
 * annotation follows the ladder in ADR-0011.
 */

export type * from './types.js';
export { suggestResources } from './pipeline.js';
export { suggestBatch, toBatchMarkdown, type BatchEntry } from './batch.js';
export { recheckResources, toRecheckMarkdown, type RecheckEntry } from './recheck.js';
export { deriveCounterQueries, heuristicCounterQueries } from './retrieval/counterpoint.js';
export { configFromEnv, type PipelineConfig } from './config.js';
export { toMarkdown } from './export/markdown.js';
export { toCitations, formatApa, formatHarvard } from './export/citations.js';
export { toLmsHtml } from './export/lmsHtml.js';
export { mapOpenAlexLicensing } from './retrieval/openalexTopical.js';
export { diversify } from './rank/diversity.js';
export { classifySource } from './enrich/sourceType.js';
export { parsePageMeta, fetchPageMeta, type PageMeta } from './enrich/page.js';
export { mapUrlStatus } from './verify/verify.js';
export { deriveQuery, heuristicKeywords, extractPhrases } from './retrieval/query.js';
export { reconstructAbstract } from './retrieval/openalexTopical.js';
export type { Candidate } from './retrieval/candidates.js';

// Document input (PDF, DOCX, TXT, MD) comes straight from cite-sight-core.
export { extract, extractPdf, extractDocx } from '@michaelborck/cite-sight-core';
