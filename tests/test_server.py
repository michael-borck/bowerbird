import pytest
from fastapi.testclient import TestClient

from bowerbird import db
from bowerbird.server import create_app


@pytest.fixture
def client(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) "
                 "VALUES(1,'chromium','Brave','Test','/tmp/nonexistent')")
    rows = [
        # guid, title, url, canonical, folder
        ("g1", "Keeper", "https://e.com/a", "https://e.com/a", "Bar"),
        ("g2", "Tracking copy", "https://e.com/a?utm_source=x", "https://e.com/a", "Bar/Read Later"),
        ("g3", "Other section", "https://e.com/a#part-b", "https://e.com/a", "Bar"),
        ("g4", "Already retired", "https://e.com/b", "https://e.com/b", "_Graveyard"),
    ]
    conn.executemany(
        """INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path, root)
           VALUES(1,?,?,?,?,?,'bookmark_bar')""", rows)
    conn.commit()
    yield TestClient(create_app(tmp_path / "test.db"))
    conn.close()


def test_duplicates_ignore_anchors_and_the_graveyard(client):
    data = client.get("/api/duplicates").json()
    assert data["total"] == 1
    assert data["total_entries_collapsed"] == 1
    group = data["groups"][0]
    assert group["keep"]["guid"] == "g1"
    assert [m["guid"] for m in group["collapse"]] == ["g2"]


def test_summary_counts_copies_that_would_collapse(client):
    assert client.get("/api/summary").json()["duplicates"] == 1
