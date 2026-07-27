import type { Resource, SuggestResult } from '../types.js';

/**
 * LMS-ready HTML (spec §10): a single self-contained fragment with inline
 * styles only, because LMS rich-text editors (Canvas, Moodle, Blackboard)
 * strip <style> blocks and external assets on paste.
 */
export function toLmsHtml(topic: string, result: SuggestResult): string {
  const items = result.resources.map(resourceHtml).join('\n');
  return [
    `<div style="font-family:sans-serif;max-width:46em">`,
    `<h2 style="margin-bottom:4px">Supporting resources: ${escape(topic)}</h2>`,
    `<p style="color:#555;font-size:0.9em">Every resource below was retrieved and verified — none are AI-generated citations.</p>`,
    items,
    `</div>`,
  ].join('\n');
}

function resourceHtml(r: Resource): string {
  const meta: string[] = [r.format, r.sourceType];
  if (r.year) meta.push(String(r.year));
  if (r.licensing !== 'unknown') meta.push(r.licensing.replace(/-/g, ' '));
  if (r.accessibilityNotes.length) meta.push(r.accessibilityNotes.join(', '));
  if (r.commerciallyInterested) meta.push('⚠ commercially interested');

  const annotation = r.annotation.text
    ? `<p style="margin:4px 0 0;font-size:0.95em">` +
      `<em style="color:#777;font-size:0.85em">` +
      (r.annotation.source === 'llm' ? 'Rationale (generated): ' : 'Description (extracted): ') +
      `</em>${escape(r.annotation.text)}</p>`
    : '';

  return (
    `<div style="border-top:1px solid #ddd;padding:10px 0">` +
    `<a href="${escape(r.url)}" style="font-weight:bold">${escape(r.title)}</a>` +
    (r.authors.length
      ? `<span style="color:#555"> — ${escape(r.authors.slice(0, 3).join(', '))}</span>`
      : '') +
    `<div style="color:#777;font-size:0.85em">${escape(meta.join(' · '))}</div>` +
    annotation +
    `</div>`
  );
}

function escape(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
