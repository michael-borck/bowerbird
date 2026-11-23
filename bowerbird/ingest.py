"""Ingest bookmark stores from any registered source — strictly read-only.

Per-source reconciliation follows cabinet's scanner: bookmarks present in the
DB but gone from the browser are marked removed (never deleted); reappearing
ones are revived. Locked browser databases (Firefox places, Chromium History)
are copied to a temp location before querying.
"""

from __future__ import annotations

import json
import plistlib
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .canonical import canonicalize, is_checkable

_CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MAC_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def chrome_ts_to_iso(value: str | int | None) -> str | None:
    try:
        us = int(value or 0)
        return (_CHROME_EPOCH + timedelta(microseconds=us)).isoformat() if us > 0 else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def unix_us_to_iso(us: int | None) -> str | None:
    if not us:
        return None
    try:
        return (_UNIX_EPOCH + timedelta(microseconds=us)).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# ---------- parsers: each yields dicts with guid/title/url/folder_path/root/dates ----------

def parse_chromium(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    out: list[dict] = []

    def walk(node: dict, crumbs: list[str], root: str) -> None:
        if node.get("type") == "url":
            out.append({
                "guid": node.get("guid") or f"noguid:{node.get('id')}:{node.get('url')}",
                "title": node.get("name", ""),
                "url": node.get("url", ""),
                "folder_path": "/".join(crumbs),
                "root": root,
                "date_added": chrome_ts_to_iso(node.get("date_added")),
                "date_last_used": chrome_ts_to_iso(node.get("date_last_used")),
            })
        elif node.get("type") == "folder":
            for child in node.get("children", []):
                walk(child, crumbs + [node.get("name", "")], root)

    for root_name, root_node in data.get("roots", {}).items():
        if isinstance(root_node, dict):
            walk(root_node, [], root_name)
    return out


def parse_firefox(path: Path) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "places.sqlite"
        shutil.copy2(path, copy)
        con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            folders = {r["id"]: (r["parent"], r["title"] or "")
                       for r in con.execute("SELECT id, parent, title FROM moz_bookmarks WHERE type=2")}
            rows = con.execute(
                """SELECT b.guid, b.title, b.parent, b.dateAdded, p.url,
                          p.visit_count, p.last_visit_date
                   FROM moz_bookmarks b JOIN moz_places p ON p.id = b.fk
                   WHERE b.type = 1 AND p.url NOT LIKE 'place:%'"""
            ).fetchall()
        finally:
            con.close()

    def folder_path(parent: int) -> str:
        crumbs: list[str] = []
        seen = set()
        while parent in folders and parent not in seen:
            seen.add(parent)
            parent, title = folders[parent]
            if title:
                crumbs.append(title)
        return "/".join(reversed(crumbs))

    return [{
        "guid": r["guid"],
        "title": r["title"] or "",
        "url": r["url"],
        "folder_path": folder_path(r["parent"]),
        "root": "firefox",
        "date_added": unix_us_to_iso(r["dateAdded"]),
        "date_last_used": unix_us_to_iso(r["last_visit_date"]),
    } for r in rows]


def parse_safari(path: Path) -> list[dict]:
    data = plistlib.loads(path.read_bytes())
    out: list[dict] = []

    def walk(node: dict, crumbs: list[str]) -> None:
        node_type = node.get("WebBookmarkType")
        if node_type == "WebBookmarkTypeLeaf":
            added = node.get("DateAdded")
            out.append({
                "guid": node.get("WebBookmarkUUID") or f"safari:{node.get('URLString')}",
                "title": (node.get("URIDictionary") or {}).get("title", ""),
                "url": node.get("URLString", ""),
                "folder_path": "/".join(crumbs),
                "root": "safari",
                "date_added": added.replace(tzinfo=timezone.utc).isoformat()
                              if isinstance(added, datetime) else None,
                "date_last_used": None,
            })
        elif node_type == "WebBookmarkTypeList" or "Children" in node:
            title = node.get("Title", "")
            for child in node.get("Children", []):
                walk(child, crumbs + ([title] if title else []))

    walk(data, [])
    return out


PARSERS = {"chromium": parse_chromium, "firefox": parse_firefox, "safari": parse_safari}


# ---------- ingest ----------

def ingest_source(conn: sqlite3.Connection, source: sqlite3.Row) -> dict:
    path = Path(source["path"])
    if not path.exists():
        return {"source": f"{source['browser']}/{source['profile']}", "error": "file not found"}
    try:
        found = PARSERS[source["kind"]](path)
    except PermissionError:
        return {"source": f"{source['browser']}/{source['profile']}",
                "error": "permission denied — grant Full Disk Access to read Safari bookmarks"}

    run_id = conn.execute(
        "INSERT INTO runs(kind, started_at) VALUES('ingest', ?)",
        (datetime.now(timezone.utc).isoformat(),),
    ).lastrowid

    new = updated = 0
    for bm in found:
        if not bm["url"]:
            continue
        canonical = canonicalize(bm["url"])
        cur = conn.execute(
            "UPDATE bookmarks SET title=?, url=?, canonical_url=?, folder_path=?, root=?, "
            "date_added=?, date_last_used=?, removed=0, last_seen_run=? "
            "WHERE source_id=? AND guid=?",
            (bm["title"], bm["url"], canonical, bm["folder_path"], bm["root"],
             bm["date_added"], bm["date_last_used"], run_id, source["id"], bm["guid"]),
        )
        if cur.rowcount:
            updated += 1
        else:
            conn.execute(
                """INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path,
                       root, date_added, date_last_used, first_seen_run, last_seen_run)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (source["id"], bm["guid"], bm["title"], bm["url"], canonical, bm["folder_path"],
                 bm["root"], bm["date_added"], bm["date_last_used"], run_id, run_id),
            )
            new += 1

    gone = conn.execute(
        "UPDATE bookmarks SET removed=1 WHERE source_id=? AND last_seen_run <> ? AND removed=0",
        (source["id"], run_id),
    ).rowcount

    refresh_urls(conn)

    # Firefox places carries visit data — fold it into the history table.
    if source["kind"] == "firefox":
        for bm in found:
            if bm["date_last_used"]:
                conn.execute(
                    """INSERT INTO history(url, canonical_url, visit_count, last_visit)
                       VALUES(?,?,1,?)
                       ON CONFLICT(url) DO UPDATE SET last_visit=MAX(last_visit, excluded.last_visit)""",
                    (bm["url"], canonicalize(bm["url"]), bm["date_last_used"]),
                )

    stats = {"source": f"{source['browser']}/{source['profile']}",
             "found": len(found), "new": new, "updated": updated, "marked_removed": gone}
    conn.execute("UPDATE runs SET finished_at=?, stats=? WHERE id=?",
                 (datetime.now(timezone.utc).isoformat(), json.dumps(stats), run_id))
    conn.execute("UPDATE sources SET last_ingested=? WHERE id=?",
                 (datetime.now(timezone.utc).isoformat(), source["id"]))
    conn.commit()
    return stats


def refresh_urls(conn: sqlite3.Connection) -> None:
    """One urls row per canonical URL across all sources; prefer https probes."""
    preferred: dict[str, str] = {}
    for row in conn.execute("SELECT canonical_url, url FROM bookmarks WHERE removed=0"):
        current = preferred.get(row["canonical_url"])
        if current is None or (not current.startswith("https") and row["url"].startswith("https")):
            preferred[row["canonical_url"]] = row["url"]
    for canonical, check_url in preferred.items():
        status = "unchecked" if is_checkable(check_url) else "skipped"
        conn.execute(
            """INSERT INTO urls(canonical_url, check_url, status) VALUES(?,?,?)
               ON CONFLICT(canonical_url) DO UPDATE SET check_url=excluded.check_url
               WHERE urls.status='unchecked'""",
            (canonical, check_url, status),
        )


def ingest_chromium_history(conn: sqlite3.Connection, source: sqlite3.Row) -> dict:
    history_file = Path(source["path"]).parent / "History"
    if not history_file.exists():
        return {"history_rows": 0}
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "History"
        shutil.copy2(history_file, copy)
        hist = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        try:
            rows = hist.execute(
                "SELECT url, visit_count, last_visit_time FROM urls WHERE visit_count > 0"
            ).fetchall()
        finally:
            hist.close()
    for url, visits, last_visit in rows:
        conn.execute(
            """INSERT INTO history(url, canonical_url, visit_count, last_visit) VALUES(?,?,?,?)
               ON CONFLICT(url) DO UPDATE SET
                   visit_count = MAX(visit_count, excluded.visit_count),
                   last_visit = MAX(COALESCE(last_visit,''), COALESCE(excluded.last_visit,''))""",
            (url, canonicalize(url), visits, chrome_ts_to_iso(last_visit)),
        )
    conn.commit()
    return {"history_rows": len(rows)}
