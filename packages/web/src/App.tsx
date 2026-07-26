import { useEffect, useState } from 'react';

interface Health {
  status: string;
  components: Record<string, string>;
}

export function App() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <main style={{ fontFamily: 'system-ui', maxWidth: 640, margin: '4rem auto', padding: '0 1rem' }}>
      <h1>Bowerbird</h1>
      <p>Finds and verifies supporting resources for your teaching.</p>
      <p>
        The web UI is under construction — see the{' '}
        <a href="https://github.com/michael-borck/bowerbird">repository</a> for
        the spec and roadmap.
      </p>
      {health && (
        <p style={{ color: '#666' }}>
          Server: {health.status} · components:{' '}
          {Object.entries(health.components)
            .map(([k, v]) => `${k}=${v}`)
            .join(', ')}
        </p>
      )}
    </main>
  );
}
