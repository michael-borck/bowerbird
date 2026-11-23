"""SQLite schema, migrations and connection helpers.

Two-layer model (bowerbird's Candidate/Resource split):
  - `sources` + `bookmarks` mirror each browser's tree verbatim — re-ingest
    reconciles, never destroys.
  - `urls` holds one row per canonical URL — validation, enrichment and review
    decisions live here and survive re-ingests from any source.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def data_home() -> Path:
    """Where the database, backups, reports and exports live.

    Resolution: $BOWERBIRD_HOME if set; else the current directory when it
    already holds a bowerbird.db; else ~/.bowerbird.
    """
    if os.environ.get("BOWERBIRD_HOME"):
        home = Path(os.environ["BOWERBIRD_HOME"]).expanduser()
    elif (Path.cwd() / "bowerbird.db").exists():
        home = Path.cwd()
    else:
        home = Path.home() / ".bowerbird"
    home.mkdir(parents=True, exist_ok=True)
    return home


def default_db_path() -> Path:
    return data_home() / "bowerbird.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    browser TEXT NOT NULL,
    profile TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    last_ingested TEXT
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL DEFAULT 1 REFERENCES sources(id),
    guid TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    folder_path TEXT NOT NULL DEFAULT '',
    root TEXT NOT NULL DEFAULT '',
    date_added TEXT,
    date_last_used TEXT,
    removed INTEGER NOT NULL DEFAULT 0,
    first_seen_run INTEGER,
    last_seen_run INTEGER,
    UNIQUE(source_id, guid)
);
CREATE INDEX IF NOT EXISTS idx_bookmarks_canonical ON bookmarks(canonical_url);

CREATE TABLE IF NOT EXISTS urls (
    id INTEGER PRIMARY KEY,
    canonical_url TEXT UNIQUE NOT NULL,
    check_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unchecked',
    http_status INTEGER,
    final_url TEXT,
    reason TEXT,
    elapsed_ms INTEGER,
    checked_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    enrich_attempts INTEGER NOT NULL DEFAULT 0,
    review TEXT,
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status);

CREATE TABLE IF NOT EXISTS history (
    url TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL,
    visit_count INTEGER NOT NULL DEFAULT 0,
    last_visit TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_canonical ON history(canonical_url);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    stats TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL DEFAULT 'llm'
);

CREATE TABLE IF NOT EXISTS url_categories (
    url_id INTEGER NOT NULL REFERENCES urls(id),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    confidence REAL,
    source TEXT NOT NULL DEFAULT 'llm',
    model TEXT,
    assigned_at TEXT,
    PRIMARY KEY (url_id, category_id)
);
CREATE INDEX IF NOT EXISTS idx_url_categories_cat ON url_categories(category_id);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
    url_id UNINDEXED, title, url, page, topics
);
"""

# Valid `urls.status` values:
#   unchecked  never probed
#   live       2xx and no login/soft-404 signals
#   login_wall reached a login page — the resource is behind an account, counts as alive
#   blocked    401/403/407/429/451/5xx — refused us, NOT proof it's gone
#   dead       404/410, or oEmbed says the video is gone, or a confident soft-404
#   suspect    2xx but smells wrong (deep link redirected to the site root)
#   timeout    request timed out
#   error      DNS/TLS/connection failure
#   skipped    non-http(s) scheme, private/loopback host, or a URL no client can request
#
# `urls.review` decisions: keep | let_go | replace

# A dead link is dead on sight. An unreachable one (DNS failure, timeout) may
# just be a bad hour at either end, so it only counts as gone once it has
# failed on two separate runs — see checker.RECHECK_AFTER. The graveyard, the
# Wayback lookup and the bulk decisions all use this.
CONFIRMED_FAILURES = 2
UNREACHABLE = "('error', 'timeout')"
FAILED = (f"(status = 'dead' OR (status IN {UNREACHABLE}"
          f" AND consecutive_failures >= {CONFIRMED_FAILURES}))")


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a pre-sources Phase 1 database up to the current schema."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    if "bookmarks" in tables and "source_id" not in _columns(conn, "bookmarks"):
        brave = str(Path.home()
                    / "Library/Application Support/BraveSoftware/Brave-Browser/Default/Bookmarks")
        conn.execute(
            "INSERT OR IGNORE INTO sources(kind, browser, profile, path) VALUES(?,?,?,?)",
            ("chromium", "Brave", "Default", brave),
        )
        source_id = conn.execute("SELECT id FROM sources WHERE path=?", (brave,)).fetchone()[0]
        conn.execute("ALTER TABLE bookmarks RENAME TO bookmarks_old")
        conn.executescript(SCHEMA)
        conn.execute(
            """INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path,
                   root, date_added, date_last_used, removed, first_seen_run, last_seen_run)
               SELECT ?, guid, title, url, canonical_url, folder_path,
                   root, date_added, date_last_used, removed, first_seen_run, last_seen_run
               FROM bookmarks_old""",
            (source_id,),
        )
        conn.execute("DROP TABLE bookmarks_old")

    if "urls" in tables and "review" not in _columns(conn, "urls"):
        conn.execute("ALTER TABLE urls ADD COLUMN review TEXT")
        conn.execute("ALTER TABLE urls ADD COLUMN reviewed_at TEXT")

    if "urls" in tables and "page_title" not in _columns(conn, "urls"):
        conn.execute("ALTER TABLE urls ADD COLUMN page_title TEXT")
        conn.execute("ALTER TABLE urls ADD COLUMN page_description TEXT")
        conn.execute("ALTER TABLE urls ADD COLUMN enriched_at TEXT")

    if "urls" in tables and "page_text" not in _columns(conn, "urls"):
        conn.execute("ALTER TABLE urls ADD COLUMN page_text TEXT")

    if "urls" in tables and "wayback_url" not in _columns(conn, "urls"):
        conn.execute("ALTER TABLE urls ADD COLUMN wayback_url TEXT")
        conn.execute("ALTER TABLE urls ADD COLUMN wayback_at TEXT")
        conn.execute("ALTER TABLE urls ADD COLUMN wayback_checked_at TEXT")

    if "urls" in tables and "enrich_attempts" not in _columns(conn, "urls"):
        conn.execute("ALTER TABLE urls ADD COLUMN enrich_attempts INTEGER NOT NULL DEFAULT 0")
        # Enrichment used to record a failed fetch as done; give those another try.
        conn.execute("""UPDATE urls SET enriched_at=NULL
                        WHERE enriched_at IS NOT NULL AND page_title IS NULL
                          AND page_description IS NULL AND page_text IS NULL""")

    conn.commit()


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or default_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.executescript(SCHEMA)
    conn.executescript(FTS_SCHEMA)
    _migrate(conn)
    return conn
