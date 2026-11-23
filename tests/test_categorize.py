import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

import bowerbird.categorize as categorize
from bowerbird import db
from bowerbird.llm import LLMError

REFUSED = object()
REQUEST = httpx.Request("POST", "https://api.anthropic.com")
NOTHING_FITS = {"items": [{"index": i, "categories": []} for i in range(3)]}
MIXED = {"items": [
    {"index": 0, "categories": [{"path": "Printing", "confidence": 0.9}]},
    {"index": 1, "categories": []},
    {"index": 2, "categories": []},
]}


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    conn.execute("INSERT INTO categories(id, path) VALUES(1,'Printing')")
    conn.executemany("INSERT INTO urls(id, canonical_url, check_url, status) VALUES(?,?,?,'live')",
                     [(i, f"https://e.com/{i}", f"https://e.com/{i}") for i in range(1, 4)])
    conn.commit()
    yield conn
    conn.close()


def model_that(monkeypatch, reply):
    """Stand in for the Anthropic SDK; `reply` gives each answer in turn.

    Returns the list of prompts the model was asked.
    """
    asked = []
    replies = iter(reply) if isinstance(reply, list) else None

    class FakeAnthropic:
        def __init__(self, *args, **kwargs):
            self.messages = self

        def create(self, **kwargs):
            asked.append(kwargs["messages"][0]["content"])
            result = next(replies) if replies else reply(kwargs)
            if isinstance(result, Exception):
                raise result
            if result is REFUSED:
                return SimpleNamespace(stop_reason="refusal", content=[])
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=json.dumps(result))])

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.delenv("BOWERBIRD_LLM_PROVIDER", raising=False)
    return asked


def categorised(conn):
    return {r["id"]: r["n"] for r in conn.execute(
        "SELECT url_id id, COUNT(*) n FROM url_categories GROUP BY url_id")}


def test_links_the_model_leaves_uncategorised_are_not_paid_for_again_every_run(conn, monkeypatch):
    asked = model_that(monkeypatch, lambda kwargs: NOTHING_FITS)
    assert categorize.assign(conn) == {"assigned": 3, "skipped": 0, "batches": 1}
    assert categorize.assign(conn) == {"assigned": 0}
    assert len(asked) == 1


def test_only_links_without_a_category_are_sent_and_all_marked_seen(conn, monkeypatch):
    asked = model_that(monkeypatch, lambda kwargs: MIXED)
    assert categorize.assign(conn) == {"assigned": 3, "skipped": 0, "batches": 1}
    assert categorised(conn) == {1: 1}
    assert conn.execute("SELECT COUNT(*) FROM urls WHERE categorized_at IS NOT NULL").fetchone()[0] == 3
    assert categorize.assign(conn) == {"assigned": 0}
    assert len(asked) == 1


def test_a_batch_the_provider_could_not_answer_is_tried_again_next_run(conn, monkeypatch):
    too_busy = anthropic.RateLimitError(message="slow down", response=httpx.Response(429, request=REQUEST), body=None)
    asked = model_that(monkeypatch, [too_busy, MIXED])

    assert categorize.assign(conn) == {"assigned": 0, "skipped": 3, "batches": 0}
    assert conn.execute("SELECT COUNT(*) FROM urls WHERE categorized_at IS NULL").fetchone()[0] == 3
    assert categorize.assign(conn) == {"assigned": 3, "skipped": 0, "batches": 1}
    assert len(asked) == 2


def test_a_refused_batch_is_not_asked_again_either(conn, monkeypatch):
    asked = model_that(monkeypatch, lambda kwargs: REFUSED)
    assert categorize.assign(conn) == {"assigned": 0, "skipped": 3, "batches": 0}
    assert categorize.assign(conn) == {"assigned": 0}
    assert len(asked) == 1


def test_a_setup_problem_stops_the_run_at_once(conn, monkeypatch):
    bad_key = anthropic.AuthenticationError(
        message="invalid x-api-key", response=httpx.Response(401, request=REQUEST), body=None)
    model_that(monkeypatch, lambda kwargs: bad_key)
    with pytest.raises(LLMError):
        categorize.assign(conn)


def test_databases_from_before_count_categorised_links_as_seen(tmp_path):
    path = tmp_path / "old.db"
    conn = db.connect(path)
    conn.execute("INSERT INTO categories(id, path) VALUES(1,'Printing')")
    conn.executemany("INSERT INTO urls(id, canonical_url, check_url, status) VALUES(?,?,?,'live')",
                     [(1, "https://e.com/1", "https://e.com/1"), (2, "https://e.com/2", "https://e.com/2")])
    conn.execute("INSERT INTO url_categories(url_id, category_id, confidence, assigned_at) "
                 "VALUES(1, 1, 0.9, '2026-01-01T00:00:00+00:00')")
    conn.execute("ALTER TABLE urls DROP COLUMN categorized_at")    # as before this column existed
    conn.commit()
    conn.close()

    conn = db.connect(path)
    assert [tuple(r) for r in conn.execute("SELECT id, categorized_at FROM urls ORDER BY id")] == [
        (1, "2026-01-01T00:00:00+00:00"),     # has a category: the model has seen it
        (2, None)]                            # none yet: still to be asked
    conn.close()
