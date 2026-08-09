"""Page-metadata enrichment for search (bowerbird's fetchPageMeta pattern).

Fetches title + description/og:description for alive URLs, capped at 128 KB per
page. Feeds the FTS index and gives the categoriser page context.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .checker import BODY_CAP, HEADERS, HostPacer, TITLE_RE

DESC_RE = re.compile(
    r'<meta[^>]+(?:name=["\']description["\']|property=["\']og:description["\'])'
    r'[^>]+content=["\']([^"\']{1,500})', re.I)
DESC_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']{1,500})["\'][^>]+'
    r'(?:name=["\']description["\']|property=["\']og:description["\'])', re.I)
STRIP_RE = re.compile(r"<(script|style|noscript|svg|head)[^>]*>.*?</\1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")

ENRICHABLE = ("live", "login_wall", "suspect")


def visible_text(html: str, cap: int = 4000) -> str:
    """First few KB of a page's visible text, for full-text search."""
    text = TAG_RE.sub(" ", STRIP_RE.sub(" ", html))
    return _unescape(text)[:cap]


def _unescape(text: str) -> str:
    import html
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


async def run_enrich(conn: sqlite3.Connection, limit: int | None = None,
                     concurrency: int = 30, progress_every: int = 200) -> dict:
    rows = conn.execute(
        f"""SELECT id, check_url FROM urls
            WHERE status IN {ENRICHABLE!r} AND enriched_at IS NULL ORDER BY id"""
        + (f" LIMIT {int(limit)}" if limit else "")
    ).fetchall()
    if not rows:
        return {"enriched": 0}

    pacer = HostPacer()
    sem = asyncio.Semaphore(concurrency)
    done = ok = 0

    async with httpx.AsyncClient(follow_redirects=True, timeout=12.0,
                                 limits=httpx.Limits(max_connections=concurrency)) as client:

        async def fetch(row: sqlite3.Row) -> tuple[int, str | None, str | None, str | None]:
            async with sem:
                await pacer.wait(urlsplit(row["check_url"]).hostname or "")
                try:
                    async with client.stream("GET", row["check_url"], headers=HEADERS) as resp:
                        if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", "html"):
                            return row["id"], None, None, None
                        body = b""
                        async for chunk in resp.aiter_bytes():
                            body += chunk
                            if len(body) >= BODY_CAP * 2:
                                break
                    text = body.decode("utf-8", errors="replace")
                    title_m = TITLE_RE.search(text)
                    desc_m = DESC_RE.search(text) or DESC_RE_REV.search(text)
                    return (row["id"],
                            _unescape(title_m.group(1))[:300] if title_m else None,
                            _unescape(desc_m.group(1))[:500] if desc_m else None,
                            visible_text(text) or None)
                except httpx.HTTPError:
                    return row["id"], None, None, None

        for coro in asyncio.as_completed([fetch(r) for r in rows]):
            url_id, title, desc, page_text = await coro
            conn.execute(
                "UPDATE urls SET page_title=?, page_description=?, page_text=?, enriched_at=? WHERE id=?",
                (title, desc, page_text, datetime.now(timezone.utc).isoformat(), url_id))
            done += 1
            ok += bool(title or desc)
            if done % progress_every == 0:
                conn.commit()
                print(f"  {done}/{len(rows)} enriched ({ok} with metadata)", flush=True)
        conn.commit()

    return {"enriched": done, "with_metadata": ok}
