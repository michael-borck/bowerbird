import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

import bowerbird.profile
from bowerbird import db
from bowerbird.categorize import rebuild_index
from bowerbird.server import create_app

LOCAL = "http://127.0.0.1"


@pytest.fixture
def conn(tmp_path):
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
    yield conn
    conn.close()


@pytest.fixture
def client(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(bowerbird.profile, "data_home", lambda: tmp_path)
    return TestClient(create_app(tmp_path / "test.db"), base_url=LOCAL)


def test_duplicates_ignore_anchors_and_the_graveyard(client):
    data = client.get("/api/duplicates").json()
    assert data["total"] == 1
    assert data["total_entries_collapsed"] == 1
    group = data["groups"][0]
    assert group["keep"]["guid"] == "g1"
    assert [m["guid"] for m in group["collapse"]] == ["g2"]


def test_summary_counts_copies_that_would_collapse(client):
    assert client.get("/api/summary").json()["duplicates"] == 1


def test_local_hostnames_are_served(client):
    assert client.get("/api/summary").status_code == 200
    assert client.get("/api/summary", headers={"host": "localhost:8420"}).status_code == 200


def test_foreign_hostname_is_refused(client):
    # DNS rebinding: the request reaches 127.0.0.1 but under the attacker's name
    assert client.get("/api/bookmarks", headers={"host": "evil.example:8420"}).status_code == 400


def test_writes_from_other_origins_are_refused(client, conn):
    body = {"decision": "keep"}
    assert client.post("/api/urls/1/review", json=body,
                       headers={"origin": "https://evil.example"}).status_code == 403
    conn.execute("INSERT INTO urls(canonical_url, check_url) VALUES('https://e.com/k','https://e.com/k')")
    conn.commit()
    assert client.post("/api/urls/1/review", json=body,
                       headers={"origin": LOCAL + ":8420"}).status_code == 200
    assert client.post("/api/urls/1/review", json=body).status_code == 200   # not from a browser


class FakeMessages:
    """Stands in for anthropic.Anthropic().messages."""

    def __init__(self, raise_=None):
        self.raise_ = raise_
        self.prompts = []

    def create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        if self.raise_:
            raise self.raise_
        schema = kwargs["output_config"]["format"]["schema"]
        if "queries" in schema["properties"]:
            answer = {"queries": ["keeper"]}
        else:
            answer = {"groups": [{"theme": "Testing", "items": [{"index": 0, "why": "it is the keeper"}]}],
                      "note": ""}
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(answer))])


def fake_anthropic(monkeypatch, messages):
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: SimpleNamespace(messages=messages))


def test_chat_answers_with_links_from_the_collection(client, conn, monkeypatch):
    conn.execute("INSERT INTO urls(canonical_url, check_url, status) VALUES('https://e.com/a','https://e.com/a','live')")
    conn.commit()
    rebuild_index(conn)
    messages = FakeMessages()
    fake_anthropic(monkeypatch, messages)

    data = client.post("/api/chat", json={"question": "which copy do I keep?"}).json()

    item = data["groups"][0]["items"][0]
    assert item["url"] == "https://e.com/a" and item["why"] == "it is the keeper"
    assert "Read Later" in messages.prompts[0]      # the collection is described from its folders


def test_chat_without_api_key_says_so(client, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    no_key = TypeError("Could not resolve authentication method. Expected one of api_key, auth_token")
    fake_anthropic(monkeypatch, FakeMessages(raise_=no_key))

    resp = client.post("/api/chat", json={"question": "hi"})
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_chat_reports_api_failures_instead_of_crashing(client, monkeypatch):
    down = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_anthropic(monkeypatch, FakeMessages(raise_=down))

    resp = client.post("/api/chat", json={"question": "hi"})
    assert resp.status_code == 502
    assert "Connection error" in resp.json()["detail"]
