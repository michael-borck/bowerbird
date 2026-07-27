import type { Resource, SuggestResult } from '../types.js';

/**
 * APA 7 and Harvard (AGPS) reference formatting from the metadata we hold.
 * Deliberately conservative: fields we lack are omitted rather than
 * guessed — an incomplete citation is honest, an invented one is not.
 */

export function formatApa(r: Resource): string {
  const authors = apaAuthors(r.authors);
  const year = r.year ? `(${r.year}).` : '(n.d.).';
  const title = r.format === 'paper' ? `${r.title}.` : `*${r.title}*.`;
  const venue = r.venue ? (r.format === 'paper' ? `*${r.venue}*.` : `${r.venue}.`) : '';
  return [authors, year, title, venue, r.url].filter(Boolean).join(' ');
}

export function formatHarvard(r: Resource): string {
  const authors = harvardAuthors(r.authors);
  const year = r.year ? `${r.year},` : 'n.d.,';
  const title = `'${r.title}',`;
  const venue = r.venue ? `${r.venue},` : '';
  return [authors, year, title, venue, `viewed at ${r.url}`].filter(Boolean).join(' ');
}

export function toCitations(result: SuggestResult, style: 'apa' | 'harvard'): string {
  const format = style === 'apa' ? formatApa : formatHarvard;
  return result.resources.map(format).join('\n\n');
}

/** "Ada Lovelace" → "Lovelace, A." */
function surnameInitials(name: string): { surname: string; initials: string } {
  const parts = name.trim().split(/\s+/);
  const surname = parts[parts.length - 1];
  const initials = parts
    .slice(0, -1)
    .map((p) => p[0].toUpperCase() + '.')
    .join(' ');
  return { surname, initials };
}

function apaAuthors(authors: string[]): string {
  if (!authors.length) return '';
  const formatted = authors.slice(0, 20).map((a) => {
    const { surname, initials } = surnameInitials(a);
    return initials ? `${surname}, ${initials}` : surname;
  });
  if (formatted.length === 1) return formatted[0];
  return `${formatted.slice(0, -1).join(', ')}, & ${formatted[formatted.length - 1]}`;
}

function harvardAuthors(authors: string[]): string {
  if (!authors.length) return '';
  const formatted = authors.slice(0, 3).map((a) => {
    const { surname, initials } = surnameInitials(a);
    return initials ? `${surname}, ${initials.replace(/\./g, '')}` : surname;
  });
  const suffix = authors.length > 3 ? ' et al.' : '';
  if (formatted.length === 1) return formatted[0] + suffix;
  return (
    `${formatted.slice(0, -1).join(', ')} & ${formatted[formatted.length - 1]}` + suffix
  );
}
