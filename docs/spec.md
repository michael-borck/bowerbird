# Bowerbird: Project Spec

**Status:** draft for spec-to-code
**Date:** 26 July 2026
**Repo:** `bowerbird`
**Package:** `@michaelborck/bowerbird`
**Host:** `app.bowerbird.eduserver.au` (landing page at `bowerbird.eduserver.au`)

> Bowerbird finds and verifies supporting resources for your teaching.

---

## 1. Purpose

A tool for lecturers and teachers. Give it a topic, a document, a worksheet, or
any piece of teaching content, and it returns supporting resources: videos,
websites, podcasts, research papers, white papers and consultant reports.

Every returned resource is verified to exist and is presented with enough
context for a human to judge it quickly.

## 2. Users and their interfaces

| User | Interface | Why |
|---|---|---|
| Author (Michael) | CLI | Unix-philosophy workflow, scripting, batch |
| Colleagues and students | Hosted web UI | Will not install anything; a URL is the lowest-friction GUI |
| Power users | Desktop app, self-hosted Docker | Batch, screenshots, local model, no quotas |

The hosted web UI is the primary interface. The CLI is not a secondary
concern, but it serves one user well rather than many users adequately.

## 3. The differentiator

Perplexity, NotebookLM, Elicit and Consensus already do topic-to-sources. The
wedge here is not retrieval, it is:

1. **Verification.** Every link resolved, every DOI validated. No generated
   references, retrieval-grounded only. Hallucinated citations kill this
   category of tool instantly.
2. **Institutional plumbing.** Licensing status, library permalinks,
   accessibility checks, LMS-ready export.
3. **Pedagogical framing.** Rationale per suggestion, alignment to learning
   outcomes, and a counterpoint mode that deliberately surfaces material
   disagreeing with the source framing.

Point 3 is the one that reflects "Conversation, Not Delegation" and is the
hardest for a general-purpose tool to copy.

## 4. Two modes

**List mode (v1).** Input goes in, verified and annotated resource list comes
out. Fast, no dialogue.

**Interview mode (v2).** The tool asks first: should this reinforce the reading
or challenge it? What do students already have? Pre-class or post-class? Then
it suggests.

Interview mode is deferred to v2 for design reasons, not cost reasons. It will
be better designed after watching colleagues use list mode and seeing where
their judgement actually needs prompting.

## 5. Architecture

Mirrors the `cite-sight` monorepo layout.

```
bowerbird/
├── packages/
│   ├── core/        shared logic: retrieval, verification, ranking, rationale
│   ├── cli/         Commander.js
│   ├── server/      Express + BullMQ queue
│   ├── web/         React + Vite (also the PWA)
│   └── desktop/     shell wrapping the web UI
├── Dockerfile
├── docker-compose.yml
└── package.json     workspace root
```

**Language: TypeScript.** Rationale: `@michaelborck/cite-sight-core` is npm and
is a direct dependency; the workload is HTTP, HTML and LLM calls with no need
for Python's ML stack; and one language spans CLI, server, web, desktop and
(later) mobile.

The `document-lens` pattern of an embedded Python FastAPI sidecar is explicitly
NOT used here. That pattern earns its complexity when Python's ML stack is
required. It is not required here.

**Contract between layers.** The core is a library with no UI assumptions. The
server exposes it over JSON. The desktop shell and web UI are both clients of
that same contract, so neither is coupled to the implementation language.

## 6. Verification layer

Extend `cite-sight-core` rather than duplicating it. Both tools improve at once.

**Already available:**

- DOI resolution via Crossref, with Semantic Scholar and OpenAlex fallbacks
- URL HTTP checks, distinguishing blocked and paywalled from dead
- YouTube and Vimeo oEmbed
- Open Library for books
- Confidence scoring on metadata match quality

**To add:**

- Podcast RSS feed and episode metadata
- Generic web pages: canonical URL, publication date extraction, archive
  fallback via Wayback for dead links
- White paper and consultant report heuristics, including a
  **commercially-interested** flag. Consultant reports are marketing artefacts
  as often as evidence, and flagging that is itself a teaching moment
- Source-type labelling: peer-reviewed, practitioner, vendor, journalism,
  government
- Currency flag, plus a re-run mode that checks a saved list for link rot and
  superseded material

## 7. Thumbnails and visual confirmation

Layered, cheapest first. The purpose here is **triage**, not evidence: a
lecturer scanning fifteen results needs to spot the cookie wall, the login
gate, the parked domain and the SEO farm at a glance.

1. **oEmbed thumbnail** for YouTube, Vimeo, podcasts. Already in
   `cite-sight-core`, effectively free.
2. **og:image** for everything else. One HTTP fetch, no browser. Covers most
   articles, papers and reports.
3. **Full screenshot** as fallback when og:image is absent, or on explicit
   request.

Layer 3 uses Playwright, which bundles its own Chromium and therefore works
under either desktop shell. Screenshots are a tier feature, not a default,
because rendering arbitrary user-supplied URLs server-side is both a cost
problem and an SSRF surface.

## 8. LLM provider

Follow the existing pattern: **self-hosted Ollama behind a bearer key, with
BYOK as an option**, configured under Settings, as in `document-lens`
(Settings → AI provider).

**Model size.** The generation tasks are short and structured: a sentence of
rationale per resource, tags, a few discussion prompts. 4B to 8B is sufficient.
This keeps local inference viable and keeps the quality gap between hosted and
desktop small.

**Security requirement: never persist a BYOK key server-side.** Browser storage
only, passed per request, held in memory for the life of the call. This is not
an optimisation to revisit later; storing colleagues' API keys on a
university-adjacent server is a liability to avoid from day one.

**Desktop first-run.** Reuse the optional Ollama detection and install flow
from `talk-buddy`. Make the "use the hosted service instead" path equally
prominent: a multi-gigabyte model download is a poor first run on campus wifi
or a student laptop.

## 9. Tiering

The free hosted tier is constrained by inference concurrency and fetch cost,
not by a per-token bill, since inference is self-hosted.

| | Free hosted | Self-host / Desktop |
|---|---|---|
| Input | One topic or document | Batch: a semester of topics at once |
| Thumbnails | oEmbed and og:image | Full screenshots |
| Verification | Yes | Yes |
| LLM | Quota'd, or BYO key | Local Ollama, or own key |
| Export | Markdown | Markdown, LMS HTML, reading list, citations |

Queue with BullMQ so a single long generation cannot block the box. The
constraint to enforce is concurrency, not spend.

## 10. Output and export

Each suggestion carries:

- Source type and commercially-interested flag
- Rationale: why this one, what it adds, what it does not cover
- Licensing status: OER, Creative Commons, library-subscription, link-only
- Accessibility notes: captions, transcript, tagged PDF
- Optional: learning outcome tag, cognitive level, core versus extension tier

Export targets: markdown, LMS-ready HTML, Harvard and APA, reading list format,
QR codes for slides.

**Deliberate diversity of return set.** Balance format and voice by default:
not five US blog posts. One video, one paper, one practitioner piece, plus an
explicit pass for non-Anglo sources. Otherwise the retrieval layer's biases
become the reading list's biases.

## 11. Deployment matrix

| Target | Mechanism | Status |
|---|---|---|
| CLI | npm global install | v1 |
| Library | npm package | v1 |
| Web UI | Hosted at app.bowerbird.eduserver.au | v1 |
| Docker | Image with web UI bundled, Docker Hub + GHCR | v1 |
| Desktop | Installers with auto-update, signed and notarised | v1 or v1.1 |
| PWA | Same web UI, manifest and service worker | v1.1 |
| iOS / Android | Capacitor over the same web UI | Deferred |

Release pipeline copied from `cite-sight`: a `v*` tag triggers installers, npm
publish and multi-arch Docker images.

**Desktop shell decision deferred.** Build core plus CLI plus hosted web first.
Choose the shell once there is evidence colleagues want a desktop icon rather
than a URL. Both shells are available in-house: `cite-sight` is Electron,
`document-lens` and `career-compass` are Tauri.

**Mobile deferred.** PWA first. Capacitor only if something concrete forces it,
such as a procurement requirement or a genuine offline need. An Apple Developer
account is already held, so the blocker is review overhead, not access.

## 12. Robustness principle

Steal the `document-lens` pattern: **degradation is non-fatal**. If
verification, thumbnail generation or the LLM is unavailable, still return
results with the affected fields clearly flagged as unavailable. Never fail the
whole request because one enrichment step failed. Surface component health in
the UI.

## 13. v1 scope

**In:**

- List mode
- Topic and document input (PDF, DOCX, TXT, MD)
- Verification for papers, videos, books, generic web pages, podcasts
- oEmbed and og:image thumbnails
- Rationale per suggestion, source-type labelling, commercially-interested flag
- Markdown export
- CLI, hosted web UI, Docker

**Out (v2 and later):**

- Interview mode
- Counterpoint mode
- Full screenshots
- Learning outcome and cognitive level tagging
- Library holdings integration and reading list export
- Link rot re-run mode
- Mobile

## 14. Open decisions

1. **Hosted free tier quota shape.** Requests per user per day, versus
   concurrency cap, versus both.
2. **Canonical analyser repo.** `cite-sight` references
   `michael-borck/lens-analysers`; `document-lens` references
   `michael-borck/document-analyser`. Confirm before either is cited as a
   dependency.
3. **Whether the desktop shell is Electron or Tauri**, deferred per section 11.
4. **Whether to log anything about usage.** Cheap to add now, annoying to
   retrofit. Only matters if a study might later be extracted from how
   colleagues actually use the tool.

## 15. Reference repos

Read these locally rather than reconstructing their patterns from description:

| Repo | What to take from it |
|---|---|
| `cite-sight` | Monorepo layout, release workflow, verification core |
| `document-lens` | AI provider settings and BYOK, non-fatal backend degradation, Tauri migration plan |
| `career-compass` | Tauri packaging, signing and update pipeline |
| `talk-buddy` | Optional post-install Ollama detection and setup flow |
