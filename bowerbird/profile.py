"""Who the collection belongs to, as far as the LLM prompts need to know.

No prompt ships a fixed description of the owner. Each one gets either the
owner's own words from $BOWERBIRD_HOME/profile.md or a sketch read from the
data: how many bookmarks, the owner's folder names, the most-saved hosts.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from .db import data_home

PROFILE_FILE = "profile.md"
PROFILE_CAP = 600

# Folder-path tokens that are containers, not topics.
NOISE = {"Bookmarks bar", "Other bookmarks", "Mobile bookmarks", "Imported From Firefox",
         "unfiled", "Imported", "menu", "toolbar", "BookmarksBar", "BookmarksMenu",
         "com.apple.ReadingList", ""}


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").removeprefix("www.")
    except ValueError:
        return ""


def top_folders(conn: sqlite3.Connection) -> Counter:
    """Folder-name segments, containers excluded, most used first."""
    counts: Counter = Counter()
    for row in conn.execute("SELECT folder_path FROM bookmarks WHERE removed=0"):
        for part in row["folder_path"].split("/"):
            if part not in NOISE:
                counts[part] += 1
    return counts


def top_hosts(conn: sqlite3.Connection) -> Counter:
    counts: Counter = Counter()
    for row in conn.execute("SELECT url FROM bookmarks WHERE removed=0"):
        host = host_of(row["url"])
        if host:
            counts[host] += 1
    return counts


def load_profile(home: str | Path | None = None) -> str | None:
    """The owner's own description, or None when there is no profile.md."""
    path = Path(home or data_home()) / PROFILE_FILE
    try:
        text = path.read_text()
    except OSError:
        return None
    return " ".join(text.split())[:PROFILE_CAP] or None


def describe_collection(conn: sqlite3.Connection, home: str | Path | None = None) -> tuple[str, str]:
    """(description, source); source is 'profile.md' or 'folders and hosts'."""
    own = load_profile(home)
    if own:
        return f"The owner describes their collection like this: {own}", "profile.md"

    total = conn.execute("SELECT COUNT(*) c FROM bookmarks WHERE removed=0").fetchone()["c"]
    folders = [name for name, _ in top_folders(conn).most_common(10)]
    hosts = [host for host, _ in top_hosts(conn).most_common(10)]
    parts = [f"It holds {total:,} bookmarks."]
    if folders:
        parts.append("The owner's own folders include " + ", ".join(folders) + ".")
    if hosts:
        parts.append("The most-saved sites are " + ", ".join(hosts) + ".")
    return " ".join(parts), "folders and hosts"
