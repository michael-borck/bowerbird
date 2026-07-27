import { useState } from 'react';

interface Annotation {
  source: 'llm' | 'extracted' | 'none';
  text: string | null;
}

interface Resource {
  title: string;
  url: string;
  format: string;
  sourceType: string;
  authors: string[];
  year: number | null;
  verification: string;
  commerciallyInterested: boolean;
  annotation: Annotation;
  thumbnailUrl: string | null;
}

interface SuggestResult {
  resources: Resource[];
  componentHealth: Record<string, string>;
}

const VERIFY_COLOR: Record<string, string> = {
  verified: '#1a7f4e',
  blocked: '#a06a00',
  paywalled: '#a06a00',
  dead: '#b3261e',
  unverified: '#666',
};

export function App() {
  const [topic, setTopic] = useState('');
  const [doc, setDoc] = useState<{ name: string; text: string } | null>(null);
  const [result, setResult] = useState<SuggestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function uploadDoc(file: File) {
    setError(null);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/extract', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      setDoc({ name: data.fileName, text: data.text });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    }
  }

  async function run() {
    const input = doc ? doc.text : topic.trim();
    if (!input || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/suggest', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ input }),
      });
      if (!res.ok) throw new Error((await res.json()).error ?? `HTTP ${res.status}`);
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function downloadMarkdown() {
    const res = await fetch('/api/suggest', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ input: doc ? doc.text : topic.trim(), format: 'markdown' }),
    });
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'bowerbird-resources.md';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <main style={{ fontFamily: 'system-ui', maxWidth: 760, margin: '3rem auto', padding: '0 1rem', lineHeight: 1.5 }}>
      <h1 style={{ marginBottom: 4 }}>🪶 Bowerbird</h1>
      <p style={{ color: '#555', marginTop: 0 }}>
        Verified supporting resources for your teaching — every link checked, nothing generated.
      </p>

      <div style={{ display: 'flex', gap: 8, margin: '1.5rem 0 0.5rem' }}>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          placeholder={doc ? `Using document: ${doc.name}` : 'Topic, e.g. supply chain resilience'}
          disabled={Boolean(doc)}
          style={{ flex: 1, padding: '10px 14px', fontSize: 16, borderRadius: 8, border: '1px solid #bbb' }}
        />
        <button
          onClick={run}
          disabled={loading || (!doc && !topic.trim())}
          style={{ padding: '10px 22px', fontSize: 16, borderRadius: 8, border: 'none', background: '#4054b2', color: '#fff', cursor: 'pointer' }}
        >
          {loading ? 'Searching…' : 'Suggest'}
        </button>
      </div>
      <div style={{ marginBottom: '1.5rem', fontSize: 13, color: '#555' }}>
        {doc ? (
          <>
            📄 {doc.name} ({Math.round(doc.text.length / 1000)}k chars){' '}
            <button onClick={() => setDoc(null)} style={{ border: 'none', background: 'none', color: '#4054b2', cursor: 'pointer' }}>
              ✕ clear
            </button>
          </>
        ) : (
          <label style={{ cursor: 'pointer', color: '#4054b2' }}>
            📎 …or upload a document (PDF, DOCX, TXT, MD)
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md"
              style={{ display: 'none' }}
              onChange={(e) => e.target.files?.[0] && uploadDoc(e.target.files[0])}
            />
          </label>
        )}
      </div>

      {error && <p style={{ color: '#b3261e' }}>Error: {error}</p>}
      {loading && <p style={{ color: '#555' }}>Retrieving, verifying and annotating — this takes a moment…</p>}

      {result && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <h2 style={{ fontSize: 18 }}>{result.resources.length} verified resources</h2>
            <button onClick={downloadMarkdown} style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid #bbb', background: '#fff', cursor: 'pointer' }}>
              ⬇ Markdown
            </button>
          </div>

          {result.resources.map((r) => (
            <article key={r.url} style={{ display: 'flex', gap: 14, padding: '14px 0', borderTop: '1px solid #e3e3e3' }}>
              {r.thumbnailUrl && (
                <img src={r.thumbnailUrl} alt="" style={{ width: 96, height: 72, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }} />
              )}
              <div>
                <a href={r.url} target="_blank" rel="noreferrer" style={{ fontWeight: 600, color: '#1a3faa' }}>
                  {r.title}
                </a>
                <div style={{ fontSize: 13, color: '#555', margin: '4px 0' }}>
                  <Badge text={r.format} />
                  <Badge text={r.sourceType} />
                  <Badge text={r.verification} color={VERIFY_COLOR[r.verification]} />
                  {r.commerciallyInterested && <Badge text="⚠ commercially interested" color="#a06a00" />}
                  {r.year && <span style={{ marginRight: 8 }}>{r.year}</span>}
                  {r.authors.length > 0 && <span>{r.authors.slice(0, 3).join(', ')}</span>}
                </div>
                {r.annotation.text && (
                  <p style={{ margin: '4px 0 0', fontSize: 14 }}>
                    <em style={{ color: '#777', fontStyle: 'normal', fontSize: 12 }}>
                      {r.annotation.source === 'llm' ? 'Rationale (generated): ' : 'Description (extracted): '}
                    </em>
                    {r.annotation.text}
                  </p>
                )}
              </div>
            </article>
          ))}

          <p style={{ fontSize: 12, color: '#888', marginTop: 16 }}>
            Components:{' '}
            {Object.entries(result.componentHealth)
              .map(([k, v]) => `${k} ${v === 'ok' ? '✓' : `(${v})`}`)
              .join(' · ')}
          </p>
        </>
      )}
    </main>
  );
}

function Badge({ text, color = '#4054b2' }: { text: string; color?: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 8px',
        marginRight: 6,
        borderRadius: 10,
        fontSize: 12,
        color: '#fff',
        background: color,
      }}
    >
      {text}
    </span>
  );
}
