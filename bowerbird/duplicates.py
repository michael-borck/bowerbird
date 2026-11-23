"""Within-source duplicate groups.

Two bookmarks in the same browser are duplicates when their canonical URLs
*and* fragments match. The canonical form drops the fragment because it never
changes which page you get, but `page#a` and `page#b` point at different
places, so they are kept apart here. Copies already sitting in the
`_Graveyard` folder are ignored — write-back put them there on purpose.
"""

from __future__ import annotations

import sqlite3
from urllib.parse import urlsplit

GRAVEYARD = "_Graveyard"


def in_graveyard(folder_path: str | None) -> bool:
    return (folder_path or "").split("/", 1)[0] == GRAVEYARD


def keeper_of(members: list) -> dict:
    """The copy in the most specific folder, avoiding Read Later."""
    members = [dict(m) for m in members]
    return max(members, key=lambda m: (
        "read later" not in (m["folder_path"] or "").lower(), len(m["folder_path"] or "")))


def duplicate_groups(conn: sqlite3.Connection, source_id: int | None = None) -> list[dict]:
    """One entry per group with two or more copies: the keeper and the rest."""
    sql = """SELECT b.id, b.guid, b.title, b.url, b.canonical_url, b.folder_path,
                    b.source_id, s.browser, s.profile
             FROM bookmarks b JOIN sources s ON s.id = b.source_id
             WHERE b.removed = 0"""
    params: tuple = ()
    if source_id is not None:
        sql += " AND b.source_id = ?"
        params = (source_id,)
    groups: dict[tuple, list[dict]] = {}
    for r in conn.execute(sql + " ORDER BY b.source_id, b.canonical_url, b.id", params):
        row = dict(r)
        if in_graveyard(row["folder_path"]):
            continue
        try:
            fragment = urlsplit(row["url"]).fragment
        except ValueError:
            fragment = ""
        groups.setdefault((row["source_id"], row["canonical_url"], fragment), []).append(row)

    result = []
    for (source, canonical, _), members in groups.items():
        if len(members) < 2:
            continue
        keeper = keeper_of(members)
        result.append({
            "canonical_url": canonical, "source_id": source,
            "browser": members[0]["browser"], "profile": members[0]["profile"],
            "keep": keeper,
            "collapse": [m for m in members if m["id"] != keeper["id"]],
        })
    return result
