"""Obsidian export — a drop-in folder for an existing vault.

Layout:
  <out>/Bowerbird.md                 index note
  <out>/topics/<Topic - Child>.md    one note per category, listing its links
  <out>/bookmarks/<title>.md         stub per bookmark: frontmatter + [[topic]] links

Stubs give Obsidian's graph view and Dataview something to chew on; topic notes
are the human-browsable layer. bowerbird only ever writes inside <out>.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

SAFE_RE = re.compile(r'[\\/:*?"<>|#^\[\]]')


def _safe(name: str, cap: int = 80) -> str:
    return SAFE_RE.sub("", name).strip().rstrip(".")[:cap] or "untitled"


def _topic_file(path: str) -> str:
    return _safe(path.replace(" / ", " - "))


def export(conn: sqlite3.Connection, out: Path) -> dict:
    topics_dir = out / "topics"
    marks_dir = out / "bookmarks"
    topics_dir.mkdir(parents=True, exist_ok=True)
    marks_dir.mkdir(parents=True, exist_ok=True)

    rows = conn.execute(
        """SELECT u.id, u.check_url, u.status, u.review, u.page_description,
                  (SELECT title FROM bookmarks b WHERE b.canonical_url=u.canonical_url
                   AND b.removed=0 LIMIT 1) AS title,
                  (SELECT MIN(date_added) FROM bookmarks b
                   WHERE b.canonical_url=u.canonical_url AND b.removed=0) AS date_added
           FROM urls u
           WHERE u.status <> 'skipped' AND (u.review IS NULL OR u.review <> 'let_go')
             AND EXISTS (SELECT 1 FROM bookmarks b
                         WHERE b.canonical_url=u.canonical_url AND b.removed=0)"""
    ).fetchall()

    cats: dict[int, list[str]] = defaultdict(list)
    for r in conn.execute(
        """SELECT uc.url_id, c.path FROM url_categories uc
           JOIN categories c ON c.id=uc.category_id ORDER BY uc.confidence DESC"""):
        cats[r["url_id"]].append(r["path"])

    by_topic: dict[str, list[sqlite3.Row]] = defaultdict(list)
    used_names: dict[str, int] = {}
    written = 0

    for r in rows:
        topics = cats.get(r["id"], [])
        for t in topics:
            by_topic[t].append(r)

        base = _safe(r["title"] or r["check_url"])
        # Counted without case: on a Mac, "Readme.md" would land on top of "README.md".
        count = used_names[base.casefold()] = used_names.get(base.casefold(), 0) + 1
        fname = base if count == 1 else f"{base} ({r['id']})"
        wikilinks = " ".join(f"[[{_topic_file(t)}]]" for t in topics)
        front = [
            "---",
            f'url: "{r["check_url"]}"',
            f"status: {r['status']}",
            f"added: {(r['date_added'] or '')[:10]}",
            "topics:", *[f'  - "{t}"' for t in topics],
            "---",
        ]
        body = [
            f"# {r['title'] or r['check_url']}",
            "",
            f"<{r['check_url']}>",
            "",
            (r["page_description"] or "").strip(),
            "",
            wikilinks,
        ]
        (marks_dir / f"{fname}.md").write_text("\n".join(front + body).strip() + "\n")
        written += 1

    for topic, members in sorted(by_topic.items()):
        lines = [f"# {topic}", ""]
        for r in sorted(members, key=lambda m: (m["title"] or "").lower()):
            mark = "" if r["status"] in ("live", "login_wall") else f" *({r['status']})*"
            lines.append(f"- [{r['title'] or r['check_url']}]({r['check_url']}){mark}")
        (topics_dir / f"{_topic_file(topic)}.md").write_text("\n".join(lines) + "\n")

    top_level = sorted({t.split(" / ")[0] for t in by_topic})
    index = ["# Bowerbird — bookmark collection", "",
             f"{written} bookmarks across {len(by_topic)} topics.", ""]
    for top in top_level:
        index.append(f"## {top}")
        for t in sorted(t for t in by_topic if t == top or t.startswith(top + " / ")):
            index.append(f"- [[{_topic_file(t)}]] ({len(by_topic[t])})")
        index.append("")
    (out / "Bowerbird.md").write_text("\n".join(index))

    return {"bookmarks": written, "topics": len(by_topic), "out": str(out)}
