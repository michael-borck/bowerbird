import json

import pytest

from bowerbird import db
from bowerbird.writeback import _plan, writeback


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def seed(conn, bookmarks_path="/tmp/nonexistent"):
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) VALUES(1,'chromium','Brave','Test',?)",
                 (str(bookmarks_path),))
    rows = [
        # guid, title, url, canonical, folder
        ("g1", "Keeper", "https://e.com/a", "https://e.com/a", "Bar/Deep/Specific"),
        ("g2", "Dupe of keeper", "https://e.com/a?utm_source=x", "https://e.com/a", "Bar/Read Later"),
        ("g3", "Dead page", "https://e.com/dead", "https://e.com/dead", "Bar"),
        ("g4", "Replaced page", "https://e.com/old", "https://e.com/old", "Bar"),
        ("g5", "Fine page", "https://e.com/fine", "https://e.com/fine", "Bar"),
    ]
    for guid, title, url, canonical, folder in rows:
        conn.execute(
            """INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path, root)
               VALUES(1,?,?,?,?,?, 'bookmark_bar')""", (guid, title, url, canonical, folder))
    conn.execute("INSERT INTO urls(canonical_url, check_url, status, review) VALUES"
                 "('https://e.com/a','https://e.com/a','live',NULL),"
                 "('https://e.com/dead','https://e.com/dead','dead','let_go'),"
                 "('https://e.com/old','https://e.com/old','dead','replace'),"
                 "('https://e.com/fine','https://e.com/fine','live',NULL)")
    conn.execute("UPDATE urls SET wayback_url='https://web.archive.org/web/2020/https://e.com/old' "
                 "WHERE canonical_url='https://e.com/old'")
    conn.commit()


def source_of(conn):
    return conn.execute("SELECT * FROM sources").fetchone()


def test_plan_decisions(conn):
    seed(conn)
    plan = _plan(conn, source_of(conn))
    assert plan["collapse"] == {"g2"}       # a tracking-param copy collapses onto the more-specific one
    assert plan["let_go"] == {"g3"}
    assert list(plan["replace"]) == ["g4"]
    assert "web.archive.org" in plan["replace"]["g4"]


def test_plan_keeps_anchor_variants_apart(conn):
    seed(conn)
    for guid, url in (("g6", "https://e.com/a#part-a"), ("g7", "https://e.com/a#part-b"),
                      ("g8", "https://e.com/a#part-a")):
        conn.execute(
            """INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path, root)
               VALUES(1,?,?,?,'https://e.com/a','Bar','bookmark_bar')""", (guid, guid, url))
    conn.commit()
    plan = _plan(conn, source_of(conn))
    # #part-a saved twice collapses onto its first copy; #part-b is a different destination
    assert plan["collapse"] == {"g2", "g8"}


def test_plan_leaves_the_graveyard_alone(conn):
    seed(conn)
    conn.execute("UPDATE bookmarks SET folder_path='_Graveyard' WHERE guid IN ('g2','g3')")
    conn.commit()
    plan = _plan(conn, source_of(conn))
    assert plan["collapse"] == set()
    assert plan["let_go"] == set()


def make_bookmarks_file(tmp_path):
    def url_node(node_id, guid, name, url):
        return {"type": "url", "id": str(node_id), "guid": guid, "name": name,
                "url": url, "date_added": "13300000000000000"}
    data = {
        "checksum": "stale",
        "roots": {
            "bookmark_bar": {"type": "folder", "id": "1", "guid": "root1", "name": "Bookmarks bar",
                             "children": [
                                 url_node(10, "g1", "Keeper", "https://e.com/a"),
                                 url_node(11, "g2", "Dupe of keeper", "https://e.com/a?utm_source=x"),
                                 {"type": "folder", "id": "12", "guid": "f1", "name": "Sub",
                                  "children": [
                                      url_node(13, "g3", "Dead page", "https://e.com/dead"),
                                      url_node(14, "g4", "Replaced page", "https://e.com/old"),
                                      url_node(15, "g5", "Fine page", "https://e.com/fine"),
                                  ]},
                             ]},
            "other": {"type": "folder", "id": "2", "guid": "root2", "name": "Other", "children": []},
        },
    }
    path = tmp_path / "Bookmarks"
    path.write_text(json.dumps(data))
    return path


def test_writeback_dry_run_counts(conn, tmp_path):
    path = make_bookmarks_file(tmp_path)
    seed(conn, bookmarks_path=path)
    result = writeback(conn, 1, apply=False)
    assert result == {"source": "Brave/Test", "applied": False, "duplicates_collapsed": 1,
                      "replaced_with_wayback": 1, "moved_to_graveyard": 1}
    # dry run must not touch the file
    assert "stale" in path.read_text()


def test_writeback_apply_transforms_tree(conn, tmp_path, monkeypatch):
    path = make_bookmarks_file(tmp_path)
    seed(conn, bookmarks_path=path)
    monkeypatch.setattr("bowerbird.writeback._browser_running", lambda b: False)
    monkeypatch.setattr("bowerbird.writeback.data_home", lambda: tmp_path)

    result = writeback(conn, 1, apply=True)
    assert result["applied"] is True

    data = json.loads(path.read_text())
    assert "checksum" not in data
    bar = data["roots"]["bookmark_bar"]["children"]
    guids = {n["guid"] for n in bar if n["type"] == "url"}
    assert "g2" not in guids                              # dupe left its place…
    sub = next(n for n in bar if n.get("name") == "Sub")
    sub_urls = {n["guid"]: n for n in sub["children"]}
    assert "g3" not in sub_urls                           # …as did the retired link
    assert sub_urls["g4"]["url"].startswith("https://web.archive.org/")
    graveyard = next(n for n in bar if n.get("name") == "_Graveyard")
    assert {c["guid"] for c in graveyard["children"]} == {"g2", "g3"}   # …into the graveyard, not deleted
    assert (tmp_path / "backups").exists() and any((tmp_path / "backups").iterdir())


def test_writeback_is_idempotent_and_reuses_the_graveyard(conn, tmp_path, monkeypatch):
    path = make_bookmarks_file(tmp_path)
    seed(conn, bookmarks_path=path)
    monkeypatch.setattr("bowerbird.writeback._browser_running", lambda b: False)
    monkeypatch.setattr("bowerbird.writeback.data_home", lambda: tmp_path)

    writeback(conn, 1, apply=True)
    first = path.read_text()

    # nothing re-ingested in between: a second apply changes nothing and reports nothing
    again = writeback(conn, 1, apply=True)
    assert {k: v for k, v in again.items() if k != "backup"} == {
        "source": "Brave/Test", "applied": True, "duplicates_collapsed": 0,
        "replaced_with_wayback": 0, "moved_to_graveyard": 0}
    assert path.read_text() == first

    # a later retirement lands in the same folder
    conn.execute("UPDATE urls SET review='let_go' WHERE canonical_url='https://e.com/fine'")
    conn.commit()
    assert writeback(conn, 1, apply=True)["moved_to_graveyard"] == 1
    bar = json.loads(path.read_text())["roots"]["bookmark_bar"]["children"]
    yards = [n for n in bar if n.get("name") == "_Graveyard"]
    assert len(yards) == 1
    assert {c["guid"] for c in yards[0]["children"]} == {"g2", "g3", "g5"}


def test_writeback_refuses_running_browser(conn, tmp_path, monkeypatch):
    path = make_bookmarks_file(tmp_path)
    seed(conn, bookmarks_path=path)
    monkeypatch.setattr("bowerbird.writeback._browser_running", lambda b: True)
    with pytest.raises(SystemExit):
        writeback(conn, 1, apply=True)
