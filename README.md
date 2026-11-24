# Bowerbird

Like its namesake bowerbird, it collects — then, unlike you, it curates.
Bowerbird audits, cleans, categorises and helps you rediscover your browser
bookmarks, entirely on your own machine.

```
pip install bowerbird-bookmarks
bowerbird ingest  # read your browsers' bookmarks (read-only)
bowerbird check   # validate every link
bowerbird serve   # dashboard at http://127.0.0.1:8420
```

## What it does

- **Multi-browser ingest** — Chrome, Brave, Edge, Vivaldi (one Chromium parser),
  Firefox (`places.sqlite`) and Safari (read-only). Sources are facets, not
  silos: the same link saved in two browsers is one URL, tracked once.
- **Link validation** that doesn't lie: only 404/410 (or a confirmed soft-404)
  counts as *dead*; a bot-wall 403 is *blocked, not dead*; reaching a login page
  counts as *alive*; YouTube videos are checked via oEmbed because deleted
  videos still return 200. A link that cannot be reached at all only joins the
  graveyard after failing twice, on checks hours apart.
- **Canonicalisation and duplicate detection** (tracking params stripped,
  youtu.be unified, per-source dupe groups with a keeper heuristic).
- **LLM thematic analysis** (Claude, two-pass): a taxonomy is derived from your
  collection first, then bookmarks are assigned 1–3 categories with confidence.
  Categories are tags — one bookmark can live in many. Each bookmark goes to
  the model once; later syncs only send what is new.
- **Full-text search** (SQLite FTS5) over titles, URLs, topics, and the visible
  text of every reachable page.
- **Ask your bookmarks** — ask a question, get *links from your own collection*
  grouped by theme with a line on why each is relevant. Never answers from the
  open web.
- **Graveyard & Wayback** — dead links get Internet Archive snapshot lookup,
  per-row or bulk replace, and bulk retire for the unrecoverable.
- **Domain triage** — review a whole domain in one decision.
- **Obsidian export** — topic notes plus per-bookmark stubs with frontmatter
  and wikilinks; drop the folder into your vault.
- **Topic map** — a force-directed graph of your collection's themes.
- **Safe write-back** — regenerate the browser's bookmarks file: duplicate
  copies and dead links moved to a `_Graveyard` folder (never deleted),
  Wayback replacements applied. Dry-run by default, timestamped backup
  always, refuses to run while the browser is open.

## Requirements

- macOS (browser profile discovery is macOS-path based for now)
- Python 3.12+
- An LLM API for the categorisation and Ask features — an Anthropic API key
  (`ANTHROPIC_API_KEY`), or any OpenAI-compatible endpoint (see Configuration).
  Everything else works without one.

## Data location

Everything lives in `$BOWERBIRD_HOME` (default `~/.bowerbird`): the SQLite database,
write-back backups, reports and exports. A `bowerbird.db` in the current directory is respected. Your browsers' own files are only ever
written by the explicit `bowerbird writeback --apply`, and backed up first.

## Configuration

- `~/.bowerbird/profile.md` — a sentence or two about you and what you
  collect. Categorisation and Ask use it to make sense of your collection.
  Without it, bowerbird describes the collection from your folder names and
  most-saved hosts.
- Provider: Anthropic by default. For any OpenAI-compatible endpoint — OpenAI,
  OpenRouter, Ollama, LM Studio — set `BOWERBIRD_LLM_PROVIDER=openai`,
  `OPENAI_BASE_URL` (an Ollama server is `http://localhost:11434/v1`) and, if
  the server needs one, `OPENAI_API_KEY`. A local server keeps categorisation
  on your machine.
- Model IDs: `BOWERBIRD_TAXONOMY_MODEL` (taxonomy, and Ask unless overridden),
  `BOWERBIRD_ASSIGN_MODEL` (assignment), `BOWERBIRD_CHAT_MODEL` (Ask alone).
  With another provider you set them; the built-in defaults are Anthropic's.

## Commands

| Command | What it does |
|---|---|
| `bowerbird sync` | one-shot incremental update: ingest → check → enrich → categorise → index |
| `bowerbird sources` | detect and register installed browsers |
| `bowerbird ingest` | import bookmarks, plus visit dates for bookmarked pages (read-only, reconciling) |
| `bowerbird check` | validate links (`--recheck` to re-probe) |
| `bowerbird enrich` | fetch page titles/descriptions/text for search |
| `bowerbird categorize --taxonomy` / `--assign` | two-pass LLM categorisation |
| `bowerbird index` | rebuild the full-text search index |
| `bowerbird wayback` | look up Internet Archive snapshots for dead links |
| `bowerbird report` | write a Markdown audit report |
| `bowerbird obsidian` | export an Obsidian-ready folder |
| `bowerbird writeback --source-id N [--apply]` | write the cleaned tree back |
| `bowerbird serve` | the dashboard (Library, Ask, Graveyard, Duplicates, Domains, Topic map) |

## Notes

The dashboard answers only to `127.0.0.1` and `localhost` and refuses writes
sent from other origins, so another website cannot read or change your
collection through it.

The CLI is also installed under the short alias `bower`, and the Python module
is `import bowerbird`.

## Status

Beta. Built and used in anger on a 9,600-bookmark collection; APIs and schema
may still change. Issues and ideas welcome.
