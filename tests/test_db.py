import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from bowerbird import db

LATE_COLUMNS = ("page_title", "page_description", "enriched_at", "page_text", "wayback_url",
                "wayback_at", "wayback_checked_at", "enrich_attempts", "categorized_at")


def columns(conn):
    return {r[1] for r in conn.execute("PRAGMA table_info(urls)")}


def test_a_fresh_database_gets_the_whole_schema_without_the_migration_path(tmp_path):
    conn = db.connect(tmp_path / "fresh.db")
    assert set(LATE_COLUMNS) <= columns(conn)
    conn.close()


def test_a_database_from_before_this_column_existed_ends_up_the_same(tmp_path):
    """Drop every column added since the first release, then let _migrate restore them."""
    path = tmp_path / "old.db"
    conn = db.connect(path)
    for column in LATE_COLUMNS:
        conn.execute(f"ALTER TABLE urls DROP COLUMN {column}")
    conn.close()

    conn = db.connect(path)
    fresh = db.connect(tmp_path / "fresh.db")
    assert set(LATE_COLUMNS) <= columns(conn)
    assert columns(conn) == columns(fresh)
    conn.close()
    fresh.close()


def test_foreign_keys_are_enforced(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    conn.execute("INSERT INTO categories(id, path) VALUES(1,'Printing')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO url_categories(url_id, category_id) VALUES(99, 1)")
    conn.execute("INSERT INTO urls(id, canonical_url, check_url) VALUES(1,'https://e.com/a','https://e.com/a')")
    conn.execute("INSERT INTO url_categories(url_id, category_id) VALUES(1, 1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM categories WHERE id=1")
    conn.close()


def test_urls_are_forgotten_once_no_bookmark_has_pointed_at_them_for_a_month(tmp_path):
    import bowerbird.ingest as ingest

    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    conn = db.connect(tmp_path / "test.db")
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) "
                 "VALUES(1,'chromium','Brave','Test','/tmp/nonexistent')")
    conn.executemany("INSERT INTO runs(id, kind, started_at) VALUES(?,'ingest',?)",
                     [(1, "2026-01-01T00:00:00+00:00"), (2, recent)])
    conn.executemany("INSERT INTO bookmarks(source_id, guid, url, canonical_url, removed, last_seen_run) "
                     "VALUES(1,?,?,?,1,?)", [
                         ("a", "https://e.com/gone-long", "https://e.com/gone-long", 1),
                         ("b", "https://e.com/gone-new", "https://e.com/gone-new", 2)])
    conn.execute("INSERT INTO bookmarks(source_id, guid, url, canonical_url, last_seen_run) "
                 "VALUES(1,'c','https://e.com/kept','https://e.com/kept',2)")
    conn.executemany("INSERT INTO urls(id, canonical_url, check_url) VALUES(?,?,?)", [
        (1, "https://e.com/gone-long", "https://e.com/gone-long"),
        (2, "https://e.com/gone-new", "https://e.com/gone-new"),
        (3, "https://e.com/kept", "https://e.com/kept")])
    conn.execute("INSERT INTO categories(id, path) VALUES(1,'Printing')")
    conn.execute("INSERT INTO url_categories(url_id, category_id) VALUES(1, 1)")
    conn.execute("INSERT INTO search(url_id, title, url, page, topics) "
                 "VALUES('1','t','https://e.com/gone-long','','')")
    conn.commit()

    ingest.prune_urls(conn)

    assert [r[0] for r in conn.execute("SELECT canonical_url FROM urls ORDER BY id")] == [
        "https://e.com/gone-new",     # its bookmark went recently: still within the month
        "https://e.com/kept"]         # bookmarked
    assert conn.execute("SELECT COUNT(*) FROM url_categories").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM search").fetchone()[0] == 0
    conn.close()
