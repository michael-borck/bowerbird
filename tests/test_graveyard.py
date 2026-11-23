import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

import bowerbird.checker as checker
import bowerbird.wayback as wayback
from bowerbird import db
from bowerbird.server import create_app

OLD = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
FRESH = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def add_url(conn, url, status="unchecked", failures=0, checked_at=None, **extra):
    columns = ["canonical_url", "check_url", "status", "consecutive_failures", "checked_at", *extra]
    cur = conn.execute(
        f"INSERT INTO urls({','.join(columns)}) VALUES({','.join('?' * len(columns))})",
        (url, url, status, failures, checked_at, *extra.values()))
    conn.commit()
    return cur.lastrowid


def state(conn):
    return {r["check_url"]: (r["status"], r["consecutive_failures"])
            for r in conn.execute("SELECT check_url, status, consecutive_failures FROM urls")}


@pytest.fixture
def probed(monkeypatch):
    """Answer every probe from a mock server; returns the URLs it was asked for."""
    real, requested = httpx.AsyncClient, []

    class MockClient(real):
        def __init__(self, *args, **kwargs):
            def handle(request):
                requested.append(str(request.url))
                code = 404 if "gone" in request.url.host else 200
                return httpx.Response(code, text="<title>Page</title>", request=request)
            super().__init__(*args, transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(checker.httpx, "AsyncClient", MockClient)
    return requested


def test_check_probes_new_links_and_retries_stale_failures(conn, probed):
    add_url(conn, "https://new.example/a")
    add_url(conn, "https://stale.example/a", "error", 1, OLD)
    add_url(conn, "https://recent.example/a", "timeout", 1, FRESH)
    add_url(conn, "https://healed.example/a", "error", 4, OLD)
    add_url(conn, "https://fine.example/a", "live", 0, OLD)

    asyncio.run(checker.run_check(conn))

    assert sorted(probed) == ["https://healed.example/a", "https://new.example/a", "https://stale.example/a"]
    assert state(conn) == {
        "https://new.example/a": ("live", 0),
        "https://stale.example/a": ("live", 0),       # answered this time
        "https://recent.example/a": ("timeout", 1),   # too soon to ask again
        "https://healed.example/a": ("live", 0),      # confirmed earlier, healed now
        "https://fine.example/a": ("live", 0),
    }


def test_a_second_failure_confirms_the_link(conn, probed):
    add_url(conn, "https://gone.example/a", "error", 1, OLD)
    add_url(conn, "https://once.example/a", "error", 1, OLD)

    asyncio.run(checker.run_check(conn))

    assert state(conn)["https://gone.example/a"] == ("dead", 2)
    assert state(conn)["https://once.example/a"] == ("live", 0)


def test_recheck_probes_everything(conn, probed):
    add_url(conn, "https://fine.example/a", "live", 0, OLD)
    add_url(conn, "https://recent.example/a", "timeout", 1, FRESH)

    asyncio.run(checker.run_check(conn, recheck=True))

    assert len(probed) == 2


@pytest.fixture
def client(conn, tmp_path):
    return TestClient(create_app(tmp_path / "test.db"), base_url="http://127.0.0.1")


def seed_graveyard(conn):
    add_url(conn, "https://e.com/dead", "dead", 1, OLD, wayback_checked_at=OLD)
    add_url(conn, "https://e.com/once", "error", 1, OLD, wayback_checked_at=OLD)
    add_url(conn, "https://e.com/twice", "timeout", 2, OLD, wayback_checked_at=OLD)
    add_url(conn, "https://e.com/suspect", "suspect", 0, OLD)


def test_graveyard_lists_only_confirmed_failures(client, conn):
    seed_graveyard(conn)
    data = client.get("/api/graveyard").json()
    assert sorted(r["check_url"] for r in data["rows"]) == [
        "https://e.com/dead", "https://e.com/suspect", "https://e.com/twice"]
    assert data["pending"] == 1
    assert data["counts"] == {"dead": 1, "suspect": 1, "timeout": 1}


def test_bulk_decisions_leave_unconfirmed_failures_alone(client, conn):
    seed_graveyard(conn)
    assert client.post("/api/graveyard/bulk", json={"scope": "let_go_no_snapshot"}).json() == {"updated": 2}
    assert dict(conn.execute("SELECT check_url, review FROM urls")) == {
        "https://e.com/dead": "let_go", "https://e.com/twice": "let_go",
        "https://e.com/once": None, "https://e.com/suspect": None}


def test_dashboard_counts_only_confirmed_failures_as_dead(client, conn):
    seed_graveyard(conn)
    assert client.get("/api/summary").json()["unreachable_confirmed"] == 1
    assert client.get("/api/domains").json()["domains"][0]["dead"] == 2


def test_wayback_looks_up_only_confirmed_failures(conn, monkeypatch):
    add_url(conn, "https://e.com/dead", "dead", 1, OLD)
    add_url(conn, "https://e.com/once", "error", 1, OLD)
    add_url(conn, "https://e.com/twice", "timeout", 2, OLD)
    asked = []

    def answer(request):
        asked.append(request.url.params["url"])
        return httpx.Response(200, json={"archived_snapshots": {}}, request=request)

    real = httpx.AsyncClient
    monkeypatch.setattr(wayback.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(answer), **kw))
    monkeypatch.setattr(wayback, "REQUEST_INTERVAL", 0)

    assert asyncio.run(wayback.run_wayback(conn)) == {
        "checked": 2, "snapshots_found": 0, "throttled_responses": 0}
    assert sorted(asked) == ["https://e.com/dead", "https://e.com/twice"]
