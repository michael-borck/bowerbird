import json
import sqlite3

import bowerbird.cli as cli
import bowerbird.ingest as ingest
from bowerbird import db
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
    monkeypatch.setattr(cli, "detect", lambda: [])    # nothing from the machine running the tests
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
