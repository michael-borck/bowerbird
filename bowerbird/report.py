"""Audit report — terminal summary plus a Markdown file."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .db import history_note

ALIVE = ("live", "login_wall")


def _status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        r["status"]: r["c"]
        for r in conn.execute("SELECT status, COUNT(*) c FROM urls GROUP BY status")
    }


def build_report(conn: sqlite3.Connection, out: Path | None = None) -> str:
    total_bm = conn.execute("SELECT COUNT(*) c FROM bookmarks WHERE removed=0").fetchone()["c"]
    unique = conn.execute("SELECT COUNT(*) c FROM urls").fetchone()["c"]
    dupes = total_bm - conn.execute(
        "SELECT COUNT(DISTINCT canonical_url) c FROM bookmarks WHERE removed=0"
    ).fetchone()["c"]
    counts = _status_counts(conn)
    checked = sum(v for k, v in counts.items() if k not in ("unchecked", "skipped"))

    visited = conn.execute(
        """SELECT COUNT(DISTINCT b.canonical_url) c FROM bookmarks b
           JOIN history h ON h.canonical_url=b.canonical_url WHERE b.removed=0"""
    ).fetchone()["c"]

    lines = [
        "# Bowerbird audit report",
        f"_Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Totals",
        f"- Bookmarks in Brave: **{total_bm:,}**",
        (f"- Unique URLs after canonicalisation: **{unique:,}** "
         f"(**{dupes:,}** duplicate bookmark entries collapse)"),
        f"- Checked so far: **{checked:,}** of {unique:,}",
        f"- Bookmarks with a recorded visit: **{visited:,}** ({history_note(conn)})",
        "",
        "## Link health",
    ]
    order = ["live", "login_wall", "blocked", "suspect", "dead", "timeout", "error", "unchecked", "skipped"]
    label = {
        "live": "Live", "login_wall": "Login-walled (alive)", "blocked": "Blocked, not dead",
        "suspect": "Suspect (redirected to root)", "dead": "Dead (404/410/soft-404)",
        "timeout": "Timed out", "error": "Connection/DNS error",
        "unchecked": "Unchecked", "skipped": "Skipped (non-web scheme)",
    }
    for key in order:
        if counts.get(key):
            pct = 100 * counts[key] / unique
            lines.append(f"- {label[key]}: **{counts[key]:,}** ({pct:.1f}%)")

    lines += ["", "## Dead links by domain (top 20)"]
    dead_rows = conn.execute(
        "SELECT check_url FROM urls WHERE status='dead'"
    ).fetchall()
    by_domain: dict[str, int] = {}
    for r in dead_rows:
        host = (urlsplit(r["check_url"]).hostname or "?").removeprefix("www.")
        by_domain[host] = by_domain.get(host, 0) + 1
    for host, count in sorted(by_domain.items(), key=lambda kv: -kv[1])[:20]:
        lines.append(f"- {host}: {count}")

    lines += ["", "## Most-duplicated bookmarks (top 15)"]
    for r in conn.execute(
        """SELECT canonical_url, COUNT(*) c, MIN(title) title FROM bookmarks
           WHERE removed=0 GROUP BY canonical_url HAVING c > 1
           ORDER BY c DESC, canonical_url LIMIT 15"""
    ):
        lines.append(f"- ×{r['c']}  {r['title'][:70]}  `{r['canonical_url'][:80]}`")

    text = "\n".join(lines) + "\n"
    if out:
        out.write_text(text)
    return text
