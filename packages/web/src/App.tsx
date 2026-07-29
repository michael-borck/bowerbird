import { useEffect, useState } from 'react';

interface Annotation {
  source: 'llm' | 'extracted' | 'none';
  text: string | null;
}

interface Resource {
  stance: 'supporting' | 'counterpoint';
  title: string;
  url: string;
  format: string;
  sourceType: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  verification: string;
  commerciallyInterested: boolean;
  licensing: string;
  accessibilityNotes: string[];
  annotation: Annotation;
  thumbnailUrl: string | null;
}

interface SuggestResult {
  resources: Resource[];
  componentHealth: Record<string, string>;
}

interface BatchEntry {
  topic: string;
  result: SuggestResult;
}

/**
 * BYO credentials live in browser storage only and are sent per request —
 * never persisted server-side (ADR-0004).
 */
interface Settings {
  providerUrl: string;
  apiKey: string;
  model: string;
  youtubeApiKey: string;
}

const SETTINGS_KEY = 'bowerbird-settings';
const EMPTY_SETTINGS: Settings = { providerUrl: '', apiKey: '', model: '', youtubeApiKey: '' };

function loadSettings(): Settings {
  try {
    return { ...EMPTY_SETTINGS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}') };
  } catch {
    return EMPTY_SETTINGS;
  }
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
  const [batchResult, setBatchResult] = useState<BatchEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [showSettings, setShowSettings] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState(true);
  const [batchAllowed, setBatchAllowed] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [counterpoint, setCounterpoint] = useState(false);

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((h) => {
        setLlmConfigured(h.components?.llm !== 'unavailable');
        setBatchAllowed(Boolean(h.capabilities?.batch));
      })
      .catch(() => {});
  }, []);

  function saveSettings(next: Settings) {
    setSettings(next);
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  }

  function credentialFields() {
    return {
      ...(settings.providerUrl
        ? {
            provider: {
              url: settings.providerUrl,
              apiKey: settings.apiKey || undefined,
              model: settings.model || undefined,
            },
          }
        : {}),
      ...(settings.youtubeApiKey ? { youtubeApiKey: settings.youtubeApiKey } : {}),
      ...(counterpoint ? { counterpoint: true } : {}),
    };
  }

  function topicsFromInput(): string[] {
    return topic
      .split('\n')
      .map((t) => t.trim())
      .filter(Boolean);
  }

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
    const single = doc ? doc.text : topic.trim();
    if (loading || (!single && !batchMode)) return;
    setLoading(true);
    setError(null);
    try {
      if (batchMode && !doc) {
        const topics = topicsFromInput();
        if (!topics.length) return;
        const res = await fetch('/api/batch', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ topics, ...credentialFields() }),
        });
        if (!res.ok) throw new Error((await res.json()).error ?? `HTTP ${res.status}`);
        setBatchResult((await res.json()).entries);
        setResult(null);
      } else {
        const res = await fetch('/api/suggest', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ input: single, ...credentialFields() }),
        });
        if (!res.ok) throw new Error((await res.json()).error ?? `HTTP ${res.status}`);
        setResult(await res.json());
        setBatchResult(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
      setResult(null);
      setBatchResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function download(format: string, extension: string) {
    const endpoint = batchResult ? '/api/batch' : '/api/suggest';
    const payload = batchResult
      ? { topics: topicsFromInput(), format, ...credentialFields() }
      : { input: doc ? doc.text : topic.trim(), format, ...credentialFields() };
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `bowerbird-resources.${extension}`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const llmAvailable = llmConfigured || Boolean(settings.providerUrl);
  const inputStyle = { flex: 1, padding: '10px 14px', fontSize: 16, borderRadius: 8, border: '1px solid #bbb' } as const;

  return (
    <main style={{ fontFamily: 'system-ui', maxWidth: 760, margin: '3rem auto', padding: '0 1rem', lineHeight: 1.5 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1 style={{ marginBottom: 4 }}>🪶 Bowerbird</h1>
        <button
          onClick={() => setShowSettings((s) => !s)}
          style={{ border: '1px solid #bbb', background: showSettings ? '#eef1ff' : '#fff', borderRadius: 8, padding: '6px 12px', cursor: 'pointer', fontSize: 14 }}
        >
          ⚙ Settings
        </button>
      </div>
      <p style={{ color: '#555', marginTop: 0 }}>
        Verified supporting resources for your teaching — every link checked, nothing generated.
      </p>

      {showSettings && (
        <SettingsPanel settings={settings} onSave={saveSettings} onClose={() => setShowSettings(false)} />
      )}

      <div style={{ display: 'flex', gap: 8, margin: '1.5rem 0 0.5rem', alignItems: 'flex-start' }}>
        {batchMode && !doc ? (
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder={'One topic per line, e.g.\nsupply chain resilience\nforecasting fundamentals\nlean operations'}
            rows={4}
            style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
          />
        ) : (
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run()}
            placeholder={doc ? `Using document: ${doc.name}` : 'Topic, e.g. supply chain resilience'}
            disabled={Boolean(doc)}
            style={inputStyle}
          />
        )}
        <button
          onClick={run}
          disabled={loading || (!doc && !topic.trim())}
          style={{ padding: '10px 22px', fontSize: 16, borderRadius: 8, border: 'none', background: '#4054b2', color: '#fff', cursor: 'pointer' }}
        >
          {loading ? 'Searching…' : 'Suggest'}
        </button>
      </div>
      <div style={{ marginBottom: '1.5rem', fontSize: 13, color: '#555', display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {doc ? (
          <span>
            📄 {doc.name} ({Math.round(doc.text.length / 1000)}k chars){' '}
            <button onClick={() => setDoc(null)} style={{ border: 'none', background: 'none', color: '#4054b2', cursor: 'pointer' }}>
              ✕ clear
            </button>
          </span>
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
        <label style={{ cursor: 'pointer' }}>
          <input type="checkbox" checked={counterpoint} onChange={(e) => setCounterpoint(e.target.checked)} />{' '}
          ⚖ Include counterpoints
        </label>
        {batchAllowed && !doc && (
          <label style={{ cursor: 'pointer' }}>
            <input type="checkbox" checked={batchMode} onChange={(e) => setBatchMode(e.target.checked)} />{' '}
            📚 Batch (one topic per line)
          </label>
        )}
      </div>

      {!llmAvailable && (
        <p style={{ fontSize: 13, color: '#555' }}>
          💡 No AI provider configured — results will carry extracted descriptions instead of
          teaching rationales.{' '}
          <button onClick={() => setShowSettings(true)} style={{ border: 'none', background: 'none', color: '#4054b2', cursor: 'pointer', padding: 0, fontSize: 13 }}>
            Configure one in Settings.
          </button>
        </p>
      )}

      {error && <p style={{ color: '#b3261e' }}>Error: {error}</p>}
      {loading && <p style={{ color: '#555' }}>Retrieving, verifying and annotating — this takes a moment…</p>}

      {result && (
        <>
          <ResultHeader count={result.resources.length} onDownload={download} />
          <ResourceSections resources={result.resources} />
          <Footers result={result} hasYoutubeKey={Boolean(settings.youtubeApiKey)} openSettings={() => setShowSettings(true)} />
        </>
      )}

      {batchResult && (
        <>
          <ResultHeader
            count={batchResult.reduce((n, e) => n + e.result.resources.length, 0)}
            onDownload={download}
          />
          {batchResult.map((entry) => (
            <section key={entry.topic} style={{ marginTop: 24 }}>
              <h2 style={{ fontSize: 17, borderBottom: '2px solid #e3e3e3', paddingBottom: 4 }}>
                {entry.topic}
              </h2>
              <ResourceSections resources={entry.result.resources} />
            </section>
          ))}
        </>
      )}
    </main>
  );
}

function ResultHeader({ count, onDownload }: { count: number; onDownload: (f: string, e: string) => void }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
      <h2 style={{ fontSize: 18 }}>{count} verified resources</h2>
      <span style={{ display: 'flex', gap: 6 }}>
        {(
          [
            ['markdown', 'md', 'Markdown'],
            ['html', 'html', 'LMS HTML'],
            ['apa', 'txt', 'APA'],
            ['harvard', 'txt', 'Harvard'],
          ] as const
        ).map(([format, ext, name]) => (
          <button
            key={format}
            onClick={() => onDownload(format, ext)}
            style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #bbb', background: '#fff', cursor: 'pointer', fontSize: 13 }}
          >
            ⬇ {name}
          </button>
        ))}
      </span>
    </div>
  );
}

function ResourceSections({ resources }: { resources: Resource[] }) {
  const supporting = resources.filter((r) => r.stance !== 'counterpoint');
  const counterpoints = resources.filter((r) => r.stance === 'counterpoint');
  return (
    <>
      {supporting.map((r) => (
        <ResourceCard key={r.url} r={r} />
      ))}
      {counterpoints.length > 0 && (
        <>
          <h3 style={{ fontSize: 15, marginTop: 20, color: '#6a3fb2' }}>
            ⚖ Counterpoints — material that disagrees with or complicates the framing
          </h3>
          {counterpoints.map((r) => (
            <ResourceCard key={r.url} r={r} />
          ))}
        </>
      )}
    </>
  );
}

function ResourceCard({ r }: { r: Resource }) {
  return (
    <article style={{ display: 'flex', gap: 14, padding: '14px 0', borderTop: '1px solid #e3e3e3' }}>
      {r.thumbnailUrl && (
        <img src={r.thumbnailUrl} alt="" style={{ width: 96, height: 72, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }} />
      )}
      <div>
        <a href={r.url} target="_blank" rel="noreferrer" style={{ fontWeight: 600, color: '#1a3faa' }}>
          {r.title}
        </a>
        <div style={{ fontSize: 13, color: '#555', margin: '4px 0' }}>
          {r.stance === 'counterpoint' && <Badge text="⚖ counterpoint" color="#6a3fb2" />}
          <Badge text={r.format} />
          <Badge text={r.sourceType} />
          <Badge text={r.verification} color={VERIFY_COLOR[r.verification]} />
          {r.licensing !== 'unknown' && <Badge text={r.licensing.replace(/-/g, ' ')} color="#2e6f40" />}
          {r.accessibilityNotes.map((note) => (
            <Badge key={note} text={`♿ ${note}`} color="#376a9e" />
          ))}
          {r.commerciallyInterested && <Badge text="⚠ commercially interested" color="#a06a00" />}
          {r.year && <span style={{ marginRight: 8 }}>{r.year}</span>}
          {r.authors.length > 0 && <span>{r.authors.slice(0, 3).join(', ')}</span>}
          {r.venue && <span style={{ color: '#888' }}> · {r.venue}</span>}
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
  );
}

function Footers({
  result,
  hasYoutubeKey,
  openSettings,
}: {
  result: SuggestResult;
  hasYoutubeKey: boolean;
  openSettings: () => void;
}) {
  return (
    <>
      {result.componentHealth.videos === 'unavailable' && !hasYoutubeKey && (
        <p style={{ fontSize: 13, color: '#555', marginTop: 16, padding: '10px 14px', background: '#f4f6ff', borderRadius: 8 }}>
          🎬 Want video results too? Add your own YouTube API key in{' '}
          <button onClick={openSettings} style={{ border: 'none', background: 'none', color: '#4054b2', cursor: 'pointer', padding: 0, fontSize: 13 }}>
            Settings
          </button>
          , or{' '}
          <a href="https://github.com/michael-borck/bowerbird#self-hosting" style={{ color: '#4054b2' }}>
            self-host
          </a>{' '}
          / grab the{' '}
          <a href="https://github.com/michael-borck/bowerbird/releases/latest" style={{ color: '#4054b2' }}>
            desktop app
          </a>
          .
        </p>
      )}
      <p style={{ fontSize: 12, color: '#888', marginTop: 12 }}>
        Components:{' '}
        {Object.entries(result.componentHealth)
          .map(([k, v]) => `${k} ${v === 'ok' ? '✓' : `(${v})`}`)
          .join(' · ')}
      </p>
    </>
  );
}

function SettingsPanel({
  settings,
  onSave,
  onClose,
}: {
  settings: Settings;
  onSave: (s: Settings) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(settings);
  const [detecting, setDetecting] = useState(false);
  const [detectNote, setDetectNote] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);

  async function detectOllama() {
    setDetecting(true);
    setDetectNote(null);
    try {
      const res = await fetch('/api/detect-ollama');
      const data = await res.json();
      if (data.available) {
        setDraft((d) => ({ ...d, providerUrl: data.url, model: data.models[0] ?? d.model }));
        setModels(data.models);
        setDetectNote(`Found Ollama with ${data.models.length} model(s).`);
      } else {
        setDetectNote('No local Ollama found — install from ollama.com, or use the hosted service as-is.');
      }
    } catch {
      setDetectNote('Detection failed.');
    } finally {
      setDetecting(false);
    }
  }

  const field = { display: 'block', width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #bbb', fontSize: 14, marginTop: 4 } as const;
  const label = { fontSize: 13, color: '#444', display: 'block', marginTop: 12 } as const;

  return (
    <section style={{ border: '1px solid #ccd', borderRadius: 10, padding: '14px 18px', margin: '1rem 0', background: '#fafbff' }}>
      <strong style={{ fontSize: 15 }}>Settings</strong>
      <p style={{ fontSize: 12, color: '#777', margin: '4px 0 0' }}>
        Keys are stored in this browser only and sent per request — never saved on the server.
      </p>

      <label style={label}>
        AI provider URL (Ollama or compatible)
        <input style={field} value={draft.providerUrl} placeholder="http://localhost:11434"
          onChange={(e) => setDraft({ ...draft, providerUrl: e.target.value })} />
      </label>
      <button onClick={detectOllama} disabled={detecting}
        style={{ marginTop: 6, padding: '5px 10px', borderRadius: 6, border: '1px solid #bbb', background: '#fff', cursor: 'pointer', fontSize: 12 }}>
        {detecting ? 'Detecting…' : '🔍 Detect local Ollama'}
      </button>
      {detectNote && <span style={{ fontSize: 12, color: '#555', marginLeft: 8 }}>{detectNote}</span>}

      <label style={label}>
        API key (if the provider needs one)
        <input style={field} type="password" value={draft.apiKey}
          onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })} />
      </label>

      <label style={label}>
        Model
        {models.length > 0 ? (
          <select style={field} value={draft.model} onChange={(e) => setDraft({ ...draft, model: e.target.value })}>
            {models.map((m) => <option key={m}>{m}</option>)}
          </select>
        ) : (
          <input style={field} value={draft.model} placeholder="llama3.1:8b"
            onChange={(e) => setDraft({ ...draft, model: e.target.value })} />
        )}
      </label>

      <label style={label}>
        YouTube API key (enables video search)
        <input style={field} type="password" value={draft.youtubeApiKey}
          onChange={(e) => setDraft({ ...draft, youtubeApiKey: e.target.value })} />
      </label>

      <div style={{ marginTop: 14, display: 'flex', gap: 8 }}>
        <button onClick={() => { onSave(draft); onClose(); }}
          style={{ padding: '7px 16px', borderRadius: 6, border: 'none', background: '#4054b2', color: '#fff', cursor: 'pointer' }}>
          Save
        </button>
        <button onClick={onClose}
          style={{ padding: '7px 16px', borderRadius: 6, border: '1px solid #bbb', background: '#fff', cursor: 'pointer' }}>
          Cancel
        </button>
      </div>
    </section>
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
