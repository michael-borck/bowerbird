import asyncio

import httpx
import pytest

import bowerbird.enrich as enrich
from bowerbird import db


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    conn.executemany("INSERT INTO urls(id, canonical_url, check_url, status) VALUES(?,?,?,'live')", [
        (1, "https://ok.example/a", "https://ok.example/a"),
        (2, "https://down.example/a", "https://down.example/a"),
        (3, "https://wobbly.example/a", "https://wobbly.example/a"),
        (4, "https://docs.example/a.pdf", "https://docs.example/a.pdf"),
        (5, "https://tired.example/a", "https://tired.example/a"),
    ])
    conn.execute("UPDATE urls SET enrich_attempts=? WHERE id=5", (enrich.MAX_ATTEMPTS,))
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def serve(monkeypatch):
    """Answer every fetch from a mock server."""
    real = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(enrich.httpx, "AsyncClient",
                            lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    return install


def state(conn):
    return {r["id"]: (r["enriched_at"] is not None, r["enrich_attempts"], r["page_title"])
            for r in conn.execute("SELECT id, enriched_at, enrich_attempts, page_title FROM urls")}


def internet(request):
    host = request.url.host
    if host == "down.example":
        return httpx.Response(503, request=request)
    if host == "wobbly.example":
        raise httpx.ConnectError("connection reset", request=request)
    if host == "docs.example":
        return httpx.Response(200, content=b"%PDF-1.4",
                              headers={"content-type": "application/pdf"}, request=request)
    return httpx.Response(200, text="<html><head><title>A fine page</title></head><body>text</body></html>",
                          headers={"content-type": "text/html; charset=utf-8"}, request=request)


def test_failed_fetches_stay_unenriched_and_are_counted(conn, serve):
    serve(internet)
    assert asyncio.run(enrich.run_enrich(conn)) == {"enriched": 2, "with_metadata": 1, "failed": 2}
    assert state(conn) == {
        1: (True, 0, "A fine page"),    # HTML: enriched
        2: (False, 1, None),            # server error: to be tried again
        3: (False, 1, None),            # connection dropped: to be tried again
        4: (True, 0, None),             # not HTML: done, nothing to get
        5: (False, 3, None),            # gave up earlier: not asked again
    }


def test_a_failed_fetch_is_retried_on_the_next_run(conn, serve):
    serve(internet)
    asyncio.run(enrich.run_enrich(conn))

    def recovered(request):
        return httpx.Response(200, text="<title>Back up</title>",
                              headers={"content-type": "text/html"}, request=request)

    serve(recovered)
    assert asyncio.run(enrich.run_enrich(conn)) == {"enriched": 2, "with_metadata": 2, "failed": 0}
    assert state(conn)[2] == (True, 1, "Back up")


def test_nothing_is_asked_for_once_everything_is_settled(conn, serve):
    serve(internet)
    asyncio.run(enrich.run_enrich(conn))
    conn.execute("DELETE FROM urls WHERE enriched_at IS NULL")
    conn.commit()
    assert asyncio.run(enrich.run_enrich(conn)) == {"enriched": 0}


def test_databases_from_before_keep_trying_their_failed_fetches(tmp_path):
    path = tmp_path / "old.db"
    stamped = "2026-01-01T00:00:00+00:00"
    conn = db.connect(path)
    conn.execute("INSERT INTO urls(canonical_url, check_url, status, enriched_at, page_title) "
                 "VALUES('https://e.com/empty','https://e.com/empty','live',?,NULL)", (stamped,))
    conn.execute("INSERT INTO urls(canonical_url, check_url, status, enriched_at, page_title) "
                 "VALUES('https://e.com/kept','https://e.com/kept','live',?,'Kept')", (stamped,))
    conn.execute("ALTER TABLE urls DROP COLUMN enrich_attempts")   # as before this column existed
    conn.commit()
    conn.close()

    conn = db.connect(path)
    assert [tuple(r) for r in conn.execute(
        "SELECT canonical_url, enriched_at, enrich_attempts FROM urls ORDER BY canonical_url")] == [
        ("https://e.com/empty", None, 0),        # failed back then: one more chance
        ("https://e.com/kept", stamped, 0)]      # had a title: left alone
    conn.execute("UPDATE urls SET enriched_at=? WHERE canonical_url='https://e.com/empty'", (stamped,))
    conn.commit()
    conn.close()

    conn = db.connect(path)                     # and only the once
    assert conn.execute("SELECT COUNT(*) FROM urls WHERE enriched_at IS NOT NULL").fetchone()[0] == 2
    conn.close()
