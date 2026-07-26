# Bowerbird

> Finds and verifies supporting resources for your teaching.

Give Bowerbird a topic, a document, a worksheet, or any piece of teaching
content, and it returns supporting resources: videos, websites, podcasts,
research papers, white papers and consultant reports. Every returned resource
is **verified to exist** and presented with enough context for a human to
judge it quickly.

**[Try the hosted version](https://app.bowerbird.eduserver.au)** · **[Download the desktop app](https://github.com/michael-borck/bowerbird/releases/latest)** · **[Self-host with Docker](#self-hosting)**

---

## How Bowerbird differs from other topic-to-source tools

Perplexity, NotebookLM, Elicit and Consensus already do topic-to-sources
retrieval. Bowerbird's wedge is not retrieval — it is what happens *after*
retrieval:

| | Bowerbird | General topic-to-source tools |
|---|---|---|
| **Verification** | Every link resolved, every DOI validated against Crossref / Semantic Scholar / OpenAlex. Retrieval-grounded only — no generated references, ever. | Citations may be generated or unchecked; hallucinated references are a known failure mode. |
| **Institutional plumbing** | Licensing status (OER, Creative Commons, library-subscription, link-only), library permalinks, accessibility notes (captions, transcripts, tagged PDFs), LMS-ready export. | Links only; the lecturer does the licensing and accessibility legwork. |
| **Pedagogical framing** | A rationale per suggestion (why this one, what it adds, what it doesn't cover), source-type labels (peer-reviewed / practitioner / vendor / journalism / government), a *commercially-interested* flag on consultant material, and (v2) a counterpoint mode that deliberately surfaces disagreeing material. | Relevance-ranked lists with no teaching rationale. |
| **Deliberate diversity** | Balances format and voice by default — one video, one paper, one practitioner piece, an explicit pass for non-Anglo sources — so the retrieval layer's biases don't become the reading list's biases. | Whatever ranks highest, which is often five similar blog posts. |
| **Deployment freedom** | Hosted, self-hosted Docker, desktop app, CLI, npm library. Local LLM via Ollama — your content never has to leave your machine. | Hosted SaaS only. |

The framing is *conversation, not delegation*: Bowerbird gives you the
evidence and context to exercise your own judgement quickly, rather than
handing you an answer to paste.

## Interfaces

| You are | Use | Get it |
|---|---|---|
| A colleague or student | Hosted web UI | [app.bowerbird.eduserver.au](https://app.bowerbird.eduserver.au) |
| A power user | Desktop app | [Latest release](https://github.com/michael-borck/bowerbird/releases/latest) |
| Self-hosting | Docker | [See below](#self-hosting) |
| Scripting / batch | CLI | `npm install -g @michaelborck/bowerbird-cli` |
| Building on it | Library | `npm install @michaelborck/bowerbird-core` |

### Free hosted vs self-host / desktop

| | Free hosted | Self-host / Desktop |
|---|---|---|
| Input | One topic or document | Batch: a semester of topics at once |
| Thumbnails | oEmbed and og:image | Full screenshots |
| Verification | Yes | Yes |
| LLM | Quota'd, or bring your own key | Local Ollama, or your own key |
| Export | Markdown | Markdown, LMS HTML, reading list, citations |

## Self-hosting

The self-host deployment is the same web UI, bundled into a single Docker
image with the server:

```bash
git clone https://github.com/michael-borck/bowerbird.git
cd bowerbird
docker compose up -d
# open http://localhost:3000
```

Or pull the image directly:

```bash
docker run -p 3000:3000 ghcr.io/michael-borck/bowerbird:latest
```

Configuration lives in a `.env` file next to `docker-compose.yml` — copy
[`.env.example`](.env.example) and fill it in (`OLLAMA_URL`, and
`OLLAMA_API_KEY` if your Ollama sits behind an authenticating proxy).
Alternatively, bring your own API key under **Settings → AI provider**. BYO keys are held in browser
storage and passed per request only — they are **never persisted server-side**
([ADR-0004](docs/adr/0004-byok-keys-never-persisted-server-side.md)).

## Architecture

TypeScript monorepo. The core is a library with no UI assumptions; the server
exposes it over JSON; web and desktop are both clients of that same contract.

```
bowerbird/
├── packages/
│   ├── core/        shared logic: retrieval, verification, ranking, rationale
│   ├── cli/         Commander.js CLI
│   ├── server/      Express + BullMQ queue
│   ├── web/         React + Vite (also the PWA)
│   └── desktop/     shell wrapping the web UI (deferred — see ADR-0007)
├── Dockerfile
├── docker-compose.yml
└── package.json     workspace root
```

Verification extends [`@michaelborck/cite-sight-core`](https://www.npmjs.com/package/@michaelborck/cite-sight-core)
rather than duplicating it, so both tools improve at once.

A core principle throughout: **degradation is non-fatal**. If verification,
thumbnail generation or the LLM is unavailable, Bowerbird still returns
results with the affected fields clearly flagged — it never fails a whole
request because one enrichment step failed.

## Documentation

- [Project specification](docs/spec.md)
- [Architecture Decision Records](docs/adr/)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Development

```bash
npm install
npm run build
npm test
```

Requires Node 20+.

## License

[MIT](LICENSE) © Michael Borck
