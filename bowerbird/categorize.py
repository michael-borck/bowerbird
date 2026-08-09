"""Two-pass LLM categorisation (cabinet's design, with its roadmap lesson applied).

Pass A (`derive_taxonomy`): one Claude Opus call looks at the existing folder
structure plus a sample of the corpus and produces a clean, fixed taxonomy —
deriving the taxonomy *before* assigning anything prevents the synonym-sprawl
failure mode ("Finance" vs "Finances") that grows batch by batch.

Pass B (`assign`): batches of bookmarks are matched against that fixed taxonomy
with structured outputs. Assignments record their source and model so a better
model can later redo only machine-made labels. Manual assignments are never
overwritten.
"""

from __future__ import annotations

import json
import random
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit

import anthropic

TAXONOMY_MODEL = "claude-opus-5"
ASSIGN_MODEL = "claude-haiku-4-5"
BATCH_SIZE = 25

TAXONOMY_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "children": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "children"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["categories"],
    "additionalProperties": False,
}

ASSIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                            "required": ["path", "confidence"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["index", "categories"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _folder_counts(conn: sqlite3.Connection) -> Counter:
    counts: Counter = Counter()
    for row in conn.execute("SELECT folder_path FROM bookmarks WHERE removed=0"):
        for part in row["folder_path"].split("/"):
            if part and part not in ("Bookmarks bar", "Other bookmarks", "Imported From Firefox",
                                     "unfiled", "menu", "toolbar", "Imported"):
                counts[part] += 1
    return counts


def _sample_items(conn: sqlite3.Connection, n: int = 300) -> list[str]:
    rows = conn.execute(
        """SELECT b.title, b.url, b.folder_path FROM bookmarks b
           WHERE b.removed=0 GROUP BY b.canonical_url ORDER BY RANDOM() LIMIT ?""", (n,)
    ).fetchall()
    return [f"{r['title'][:80]} | {(urlsplit(r['url']).hostname or '')} | {r['folder_path'][:60]}"
            for r in rows]


def derive_taxonomy(conn: sqlite3.Connection, model: str = TAXONOMY_MODEL) -> dict:
    client = anthropic.Anthropic()
    folders = "\n".join(f"{name}: {count}" for name, count in _folder_counts(conn).most_common(80))
    sample = "\n".join(_sample_items(conn))

    response = client.messages.create(
        model=model,
        max_tokens=8000,
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": TAXONOMY_SCHEMA}},
        messages=[{
            "role": "user",
            "content": (
                "Design a category taxonomy for a personal bookmark collection of ~8,500 links "
                "belonging to an academic who teaches computing, does research, 3D prints, and has "
                "many hobbies. Requirements:\n"
                "- 12-20 top-level categories, each with 0-8 children (two levels max).\n"
                "- Merge synonyms and near-duplicates into one canonical name.\n"
                "- Names are short (1-3 words). No 'Miscellaneous'/'Other' categories.\n"
                "- The taxonomy must cover the whole collection; prefer broad, durable categories "
                "over one-off niches.\n\n"
                f"Existing folder names with bookmark counts:\n{folders}\n\n"
                f"Random sample of bookmarks (title | domain | folder):\n{sample}"
            ),
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("taxonomy request was refused")
    data = json.loads(next(b.text for b in response.content if b.type == "text"))

    paths = []
    for cat in data["categories"]:
        paths.append(cat["name"])
        paths.extend(f"{cat['name']} / {child}" for child in cat["children"])
    for path in paths:
        conn.execute("INSERT OR IGNORE INTO categories(path, source) VALUES(?, 'llm')", (path,))
    conn.commit()
    return {"top_level": len(data["categories"]), "total_paths": len(paths)}


def _system_prompt(conn: sqlite3.Connection) -> list[dict]:
    taxonomy = "\n".join(r["path"] for r in conn.execute("SELECT path FROM categories ORDER BY path"))
    return [{
        "type": "text",
        "text": (
            "You categorise bookmarks from a personal collection into a fixed taxonomy.\n\n"
            "Rules:\n"
            "- Assign 1 to 3 categories per bookmark, most relevant first, each with a "
            "confidence between 0 and 1.\n"
            "- Use ONLY paths from the taxonomy below, exactly as written. Never invent new ones.\n"
            "- Prefer the most specific applicable path (a child over its parent).\n"
            "- The bookmark's original folder is a hint about the owner's intent, not ground truth.\n"
            "- If genuinely nothing fits, return an empty categories array for that item.\n\n"
            f"Taxonomy:\n{taxonomy}"
        ),
        "cache_control": {"type": "ephemeral"},
    }]


def assign(conn: sqlite3.Connection, model: str = ASSIGN_MODEL,
           limit: int | None = None, progress_every: int = 10) -> dict:
    client = anthropic.Anthropic()
    valid_paths = {r["path"] for r in conn.execute("SELECT path FROM categories")}
    if not valid_paths:
        raise RuntimeError("no taxonomy — run `bower categorize --taxonomy` first")
    system = _system_prompt(conn)

    rows = conn.execute(
        """SELECT u.id, u.check_url, u.page_title, u.page_description,
                  (SELECT title FROM bookmarks b WHERE b.canonical_url=u.canonical_url
                   AND b.removed=0 LIMIT 1) AS title,
                  (SELECT folder_path FROM bookmarks b WHERE b.canonical_url=u.canonical_url
                   AND b.removed=0 LIMIT 1) AS folder_path
           FROM urls u
           WHERE u.status NOT IN ('skipped')
             AND NOT EXISTS (SELECT 1 FROM url_categories c WHERE c.url_id=u.id)
           ORDER BY u.id"""
        + (f" LIMIT {int(limit)}" if limit else "")
    ).fetchall()
    if not rows:
        return {"assigned": 0}

    now = datetime.now(timezone.utc).isoformat()
    cat_ids = {r["path"]: r["id"] for r in conn.execute("SELECT id, path FROM categories")}
    assigned = skipped = batches = 0

    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        lines = []
        for i, r in enumerate(batch):
            desc = (r["page_description"] or "")[:200]
            lines.append(
                f"[{i}] title: {(r['title'] or r['page_title'] or '')[:110]}\n"
                f"    url: {r['check_url'][:120]}\n"
                f"    folder: {(r['folder_path'] or '')[:80]}"
                + (f"\n    description: {desc}" if desc else "")
            )
        try:
            response = client.messages.create(
                model=model,
                max_tokens=8000,
                system=system,
                output_config={"format": {"type": "json_schema", "schema": ASSIGN_SCHEMA}},
                messages=[{"role": "user", "content": "Categorise these bookmarks:\n\n" + "\n".join(lines)}],
            )
        except anthropic.APIStatusError as exc:
            print(f"  batch at {start} failed: {exc.status_code} {exc.message}", flush=True)
            skipped += len(batch)
            continue
        if response.stop_reason == "refusal":
            skipped += len(batch)
            continue

        data = json.loads(next(b.text for b in response.content if b.type == "text"))
        for item in data.get("items", []):
            idx = item.get("index")
            if not isinstance(idx, int) or not 0 <= idx < len(batch):
                continue
            url_id = batch[idx]["id"]
            for cat in item.get("categories", [])[:3]:
                cat_id = cat_ids.get(cat.get("path"))
                if cat_id is None:
                    continue  # hallucinated path — drop, never create
                conn.execute(
                    """INSERT OR IGNORE INTO url_categories
                       (url_id, category_id, confidence, source, model, assigned_at)
                       VALUES(?,?,?,'llm',?,?)""",
                    (url_id, cat_id, float(cat.get("confidence", 0)), model, now))
            assigned += 1
        conn.commit()
        batches += 1
        if batches % progress_every == 0:
            print(f"  {min(start + BATCH_SIZE, len(rows))}/{len(rows)} processed", flush=True)

    return {"assigned": assigned, "skipped": skipped, "batches": batches}


def rebuild_index(conn: sqlite3.Connection) -> dict:
    """Rebuild the FTS5 search index from bookmarks + enrichment + categories."""
    conn.execute("DELETE FROM search")
    rows = conn.execute(
        """SELECT u.id, u.check_url, u.page_title, u.page_description, u.page_text,
                  (SELECT GROUP_CONCAT(b.title, ' ') FROM bookmarks b
                   WHERE b.canonical_url=u.canonical_url AND b.removed=0) AS titles,
                  (SELECT GROUP_CONCAT(c.path, ' ; ') FROM url_categories uc
                   JOIN categories c ON c.id=uc.category_id WHERE uc.url_id=u.id) AS topics
           FROM urls u"""
    ).fetchall()
    for r in rows:
        conn.execute(
            "INSERT INTO search(url_id, title, url, page, topics) VALUES(?,?,?,?,?)",
            (r["id"], r["titles"] or "", r["check_url"],
             " ".join(filter(None, [r["page_title"], r["page_description"], r["page_text"]])),
             r["topics"] or ""))
    conn.commit()
    return {"indexed": len(rows)}
