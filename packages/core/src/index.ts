/**
 * Bowerbird core: retrieval, verification, ranking and rationale.
 *
 * This package has no UI or transport assumptions (ADR-0001). Verification
 * extends @michaelborck/cite-sight-core rather than duplicating it (ADR-0002).
 */

export type SourceType =
  | 'peer-reviewed'
  | 'practitioner'
  | 'vendor'
  | 'journalism'
  | 'government';

export type ResourceFormat =
  | 'video'
  | 'website'
  | 'podcast'
  | 'paper'
  | 'white-paper'
  | 'report'
  | 'book';

/**
 * Verification outcome for a single resource. Per ADR-0006, `unverified`
 * (the check could not run) is distinct from `dead` (the check ran and the
 * resource is gone). Unverifiable resources are flagged, never hidden.
 */
export type VerificationStatus =
  | 'verified'
  | 'paywalled'
  | 'blocked'
  | 'dead'
  | 'unverified';

export type LicensingStatus =
  | 'oer'
  | 'creative-commons'
  | 'library-subscription'
  | 'link-only'
  | 'unknown';

/**
 * Which rung of the annotation ladder produced the text (ADR-0011):
 * 'llm' is a relational rationale, 'extracted' is a descriptive fallback
 * (og:description, abstract, RSS summary), 'none' means neither was
 * available. UIs must render the distinction — an extracted description is
 * never presented as a generated rationale.
 */
export type AnnotationSource = 'llm' | 'extracted' | 'none';

export interface Annotation {
  source: AnnotationSource;
  /** Rationale or description; null when source is 'none'. */
  text: string | null;
}

export interface Resource {
  title: string;
  url: string;
  format: ResourceFormat;
  sourceType: SourceType;
  verification: VerificationStatus;
  /** Consultant reports are marketing artefacts as often as evidence. */
  commerciallyInterested: boolean;
  licensing: LicensingStatus;
  /** Why this one, what it adds, what it does not cover — or an extractive description (ADR-0011). */
  annotation: Annotation;
  /** oEmbed or og:image URL; null when unavailable (ADR-0005). */
  thumbnailUrl: string | null;
  accessibilityNotes: string[];
}

export interface SuggestRequest {
  /** A topic string, or extracted text from an uploaded document. */
  input: string;
  maxResults?: number;
}

export interface SuggestResult {
  resources: Resource[];
  /** Health of each enrichment component for this request (ADR-0006). */
  componentHealth: Record<string, 'ok' | 'degraded' | 'unavailable'>;
}

/**
 * List mode (v1): input goes in, a verified and annotated resource list
 * comes out. Not yet implemented — this is the contract stub.
 */
export async function suggestResources(
  request: SuggestRequest,
): Promise<SuggestResult> {
  void request;
  throw new Error('Not implemented yet: see docs/spec.md section 13 (v1 scope)');
}
