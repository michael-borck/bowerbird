import json
import sqlite3

from bowerbird import cli, db, ingest
from bowerbird.ingest import chrome_ts_to_iso, ingest_source, unix_us_to_iso

ADDED = "13300000000000000"


def chromium_file(path, *urls):
    """A Chromium Bookmarks file holding one bookmark per URL."""
    children = [{"type": "url", "id": str(10 + i), "guid": f"g{i}", "name": f"Bookmark {i}",
                 "url": url, "date_added": ADDED}
                for i, url in enumerate(urls)]
    path.write_text(json.dumps({"roots": {"bookmark_bar": {
        "type": "folder", "id": "1", "guid": "root", "name": "Bookmarks bar", "children": children}}}))
    return path


def test_one_malformed_bookmark_does_not_cost_the_source(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    path = chromium_file(tmp_path / "Bookmarks", "https://e.com/ok", "http://e.com:abc/bad-port",
                         "http://e.com/\n", "https://e.com/strange-date")
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) "
                 "VALUES(1,'chromium','Brave','Test',?)", (str(path),))
    conn.commit()

    assert ingest_source(conn, conn.execute("SELECT * FROM sources").fetchone()) == {
        "source": "Brave/Test", "found": 4, "new": 4, "updated": 0, "marked_removed": 0}

    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 4
    assert dict(conn.execute("SELECT check_url, status FROM urls")) == {
        "https://e.com/ok": "unchecked", "http://e.com:abc/bad-port": "skipped",
        "http://e.com/\n": "skipped", "https://e.com/strange-date": "unchecked"}
    assert conn.execute("SELECT finished_at FROM runs").fetchone()[0] is not None


def test_impossible_dates_become_unknown():
    assert chrome_ts_to_iso("13300000000000000") is not None
    assert chrome_ts_to_iso("99999999999999999999") is None
    assert unix_us_to_iso(1700000000000000) is not None
    assert unix_us_to_iso(10 ** 25) is None


def test_a_source_that_fails_does_not_stop_the_others_and_recovers(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "detect", list)    # nothing from the machine running the tests
    flaky = chromium_file(tmp_path / "flaky", "https://e.com/first", "https://e.com/boom", "https://e.com/last")
    fine = chromium_file(tmp_path / "fine", "https://e.com/fine")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    db_path = tmp_path / "cli.db"
    conn = db.connect(db_path)
    conn.executemany("INSERT INTO sources(id, kind, browser, profile, path) VALUES(?,'chromium',?,'Test',?)", [
        (1, "Flaky", str(flaky)), (2, "Fine", str(fine)), (3, "Broken", str(broken))])
    conn.commit()
    conn.close()

    real = ingest.canonicalize

    def flaky(url):
        if "boom" in url:
            raise RuntimeError("failed half-way")
        return real(url)

    monkeypatch.setattr(ingest, "canonicalize", flaky)
    monkeypatch.setattr("sys.argv", ["bowerbird", "--db", str(db_path), "ingest", "--no-history"])
    cli.main()

    reported = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["source"] for line in reported] == ["Flaky/Test", "Fine/Test", "Broken/Test"]
    assert "RuntimeError" in reported[0]["error"] and "JSONDecodeError" in reported[2]["error"]
    assert reported[1]["new"] == 1
    conn = sqlite3.connect(db_path)
    # the half-finished source left nothing behind, not even an open run
    assert [r[0] for r in conn.execute("SELECT url FROM bookmarks")] == ["https://e.com/fine"]
    assert conn.execute("SELECT COUNT(*) FROM runs WHERE finished_at IS NULL").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sources WHERE last_ingested IS NOT NULL").fetchone()[0] == 1

    monkeypatch.setattr(ingest, "canonicalize", real)   # whatever was wrong is fixed: the next run just works
    cli.main()
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 4


STAMP = 13300000000000000                 # Chrome timestamps: microseconds since 1601
DAY = 86_400 * 1_000_000


def chromium_history(path, *visits):
    """A Chromium History file: (url, visit_count, last_visit_time)."""
    hist = sqlite3.connect(path)
    hist.execute("CREATE TABLE urls (url TEXT PRIMARY KEY, visit_count INTEGER, last_visit_time INTEGER)")
    hist.executemany("INSERT INTO urls VALUES(?,?,?)", visits)
    hist.commit()
    hist.close()
    return path


def test_only_visits_to_bookmarked_pages_are_kept(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    bookmarks = chromium_file(tmp_path / "Bookmarks", "https://e.com/kept")
    chromium_history(tmp_path / "History",
                     ("https://e.com/kept?utm_source=x", 3, STAMP),        # the bookmark, with tracking
                     ("https://e.com/private-search", 9, STAMP + DAY),     # nobody's business
                     ("https://e.com/never-opened", 0, 0))
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) "
                 "VALUES(1,'chromium','Brave','Test',?)", (str(bookmarks),))
    conn.commit()
    source = conn.execute("SELECT * FROM sources").fetchone()
    assert source is not None
    ingest_source(conn, source)

    assert ingest.ingest_chromium_history(conn, source) == {"history_rows": 1}
    assert [tuple(r) for r in conn.execute("SELECT url, visit_count FROM history")] == [
        ("https://e.com/kept?utm_source=x", 3)]
    first = chrome_ts_to_iso(STAMP) or ""
    assert db.history_note(conn) == f"Brave history back to {first[:10]}"


def test_visits_to_pages_no_longer_bookmarked_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "detect", list)
    bookmarks = chromium_file(tmp_path / "Bookmarks", "https://e.com/kept")
    db_path = tmp_path / "cli.db"
    conn = db.connect(db_path)
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) "
                 "VALUES(1,'chromium','Brave','Test',?)", (str(bookmarks),))
    conn.executemany("INSERT INTO history(url, canonical_url, visit_count) VALUES(?,?,1)",
                     [("https://e.com/kept", "https://e.com/kept"), ("https://e.com/gone", "https://e.com/gone")])
    conn.commit()
    conn.close()

    monkeypatch.setattr("sys.argv", ["bowerbird", "--db", str(db_path), "ingest", "--no-history"])
    cli.main()

    conn = sqlite3.connect(db_path)
    assert [r[0] for r in conn.execute("SELECT url FROM history")] == ["https://e.com/kept"]


def test_a_visit_counts_for_a_bookmark_saved_in_a_later_source(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "detect", list)
    first = chromium_file(tmp_path / "first", "https://e.com/mine")
    second = chromium_file(tmp_path / "second", "https://e.com/theirs")
    chromium_history(tmp_path / "History", ("https://e.com/theirs", 2, STAMP))
    db_path = tmp_path / "cli.db"
    conn = db.connect(db_path)
    conn.executemany("INSERT INTO sources(id, kind, browser, profile, path) VALUES(?,'chromium',?,'Test',?)",
                     [(1, "Brave", str(first)), (2, "Chrome", str(second))])
    conn.commit()
    conn.close()

    monkeypatch.setattr("sys.argv", ["bowerbird", "--db", str(db_path), "ingest"])
    cli.main()

    conn = sqlite3.connect(db_path)
    assert [r[0] for r in conn.execute("SELECT url FROM history")] == ["https://e.com/theirs"]
