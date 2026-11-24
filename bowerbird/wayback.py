"""Internet Archive snapshot lookup for dead links.

Uses the free Wayback availability API, one request every few seconds (their
polite rate these days). Only links that are dead — or unreachable on two
separate runs — are looked up. A found snapshot doesn't change any bookmark by
itself — it enables the 'replace' review decision, which write-back later
applies.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime

import httpx

from . import __version__
from .db import FAILED

API = "https://archive.org/wayback/available"
REQUEST_INTERVAL = 4.0
USER_AGENT = f"bowerbird/{__version__} (bookmark auditor; https://github.com/michael-borck/bowerbird)"


async def run_wayback(conn: sqlite3.Connection, limit: int | None = None,
                      progress_every: int = 50) -> dict:
    rows = conn.execute(
        f"""SELECT id, check_url FROM urls
            WHERE {FAILED} AND wayback_checked_at IS NULL
              AND (review IS NULL OR review='replace') ORDER BY id"""
        + (f" LIMIT {int(limit)}" if limit else "")
    ).fetchall()
    if not rows:
        return {"checked": 0}

    found = done = throttled = 0
    async with httpx.AsyncClient(timeout=20.0,
                                 headers={"User-Agent": USER_AGENT}) as client:
        for row in rows:
            snapshot_url = snapshot_ts = None
            answered = False
            for attempt in range(4):
                try:
                    resp = await client.get(API, params={"url": row["check_url"]})
                except httpx.HTTPError:
                    await asyncio.sleep(30)
                    continue
                if resp.status_code == 429:
                    throttled += 1
                    await asyncio.sleep(60 * (attempt + 1))  # back off hard, then retry
                    continue
                if resp.status_code != 200:
                    await asyncio.sleep(15)
                    continue
                try:
                    closest = (resp.json().get("archived_snapshots") or {}).get("closest") or {}
                except ValueError:
                    break  # non-JSON 200 — treat as unanswered, retry next run
                answered = True
                if closest.get("available"):
                    snapshot_url = closest["url"].replace(
                        "http://web.archive.org", "https://web.archive.org")
                    snapshot_ts = closest.get("timestamp")
                break

            if answered:
                # Only a genuine API answer marks the row checked; throttled or
                # failed lookups stay eligible for the next run.
                conn.execute(
                    "UPDATE urls SET wayback_url=?, wayback_at=?, wayback_checked_at=? WHERE id=?",
                    (snapshot_url, snapshot_ts, datetime.now(UTC).isoformat(), row["id"]))
                conn.commit()  # per row — an open transaction across sleeps starves other writers
                found += bool(snapshot_url)
                done += 1
            if done and done % progress_every == 0:
                print(f"  {done}/{len(rows)} answered, {found} snapshots, {throttled} throttles", flush=True)
            await asyncio.sleep(REQUEST_INTERVAL)

    return {"checked": done, "snapshots_found": found, "throttled_responses": throttled}
