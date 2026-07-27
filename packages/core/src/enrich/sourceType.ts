import type { SourceType } from '../types.js';
import type { Candidate } from '../retrieval/candidates.js';

const GOV_TLDS = /\.(gov|gov\.[a-z]{2}|mil)(\/|$)/i;
const EDU_TLDS = /\.(edu|edu\.[a-z]{2}|ac\.[a-z]{2})(\/|$)/i;
const NEWS_HOSTS =
  /(bbc\.|reuters\.|apnews\.|theguardian\.|nytimes\.|abc\.net\.au|smh\.com\.au|theconversation\.)/i;
const CONSULTANCY_HOSTS =
  /(mckinsey|bcg\.com|bain\.com|deloitte|pwc\.com|kpmg|accenture|gartner|forrester)/i;
const VENDOR_PATH_HINTS = /(\/blog\/|\/resources\/|\/whitepaper|\/ebook|\/case-stud)/i;

/**
 * Heuristic source-type labelling and the commercially-interested flag
 * (spec §6). Consultant reports are marketing artefacts as often as
 * evidence; flagging that is itself a teaching moment.
 */
export function classifySource(candidate: Candidate): {
  sourceType: SourceType;
  commerciallyInterested: boolean;
} {
  if (candidate.format === 'paper' || candidate.doi) {
    return { sourceType: 'peer-reviewed', commerciallyInterested: false };
  }
  const url = candidate.url;
  if (GOV_TLDS.test(url)) return { sourceType: 'government', commerciallyInterested: false };
  if (CONSULTANCY_HOSTS.test(url)) {
    return { sourceType: 'vendor', commerciallyInterested: true };
  }
  if (NEWS_HOSTS.test(url)) return { sourceType: 'journalism', commerciallyInterested: false };
  if (EDU_TLDS.test(url)) return { sourceType: 'practitioner', commerciallyInterested: false };
  if (candidate.format === 'website' && VENDOR_PATH_HINTS.test(url)) {
    return { sourceType: 'vendor', commerciallyInterested: true };
  }
  return { sourceType: 'practitioner', commerciallyInterested: false };
}
