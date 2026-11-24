"""Bower's local web server — FastAPI on 127.0.0.1, UI at /, JSON under /api."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import db, llm
from .duplicates import duplicate_groups, in_graveyard
from .models import chat_model
from .profile import NOISE, describe_collection

STATIC = Path(__file__).resolve().parent / "static"
LOCAL_HOSTS = ("127.0.0.1", "localhost")


class Review(BaseModel):
    decision: str  # keep | let_go | replace


class Bulk(BaseModel):
    scope: str  # replace_snapshots | let_go_no_snapshot


class DomainReview(BaseModel):
    domain: str
    decision: str  # keep | let_go


class ChatQ(BaseModel):
    question: str


def topic_of(folder_path: str) -> str:
    for part in folder_path.split("/"):
        if part not in NOISE:
            return part
    return "(uncategorised)"


def create_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Bower", docs_url=None, redoc_url=None)
    # The dashboard holds the whole collection, so it answers only to its own
    # hostnames: a page using DNS rebinding arrives under some other name.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(LOCAL_HOSTS))
    conn = db.connect(db_path)

    @app.middleware("http")
    async def refuse_cross_origin_writes(request: Request, call_next):
        origin = request.headers.get("origin")
        try:
            foreign = origin is not None and urlsplit(origin).hostname not in LOCAL_HOSTS
        except ValueError:
            foreign = True
        if request.method not in ("GET", "HEAD", "OPTIONS") and foreign:
            return JSONResponse({"detail": "writes from other origins are refused"}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/summary")
    def summary() -> dict:
        total = conn.execute("SELECT COUNT(*) c FROM bookmarks WHERE removed=0").fetchone()["c"]
        unique = conn.execute("SELECT COUNT(*) c FROM urls").fetchone()["c"]
        # Duplicates are within-source only: the same URL in two browsers is
        # intentional ("saved in 2 places"), not something to collapse.
        duplicates = sum(len(g["collapse"]) for g in duplicate_groups(conn))
        status_counts = {r["status"]: r["c"] for r in
                         conn.execute("SELECT status, COUNT(*) c FROM urls GROUP BY status")}
        checked_at = conn.execute("SELECT MAX(checked_at) m FROM urls").fetchone()["m"]
        unreachable = conn.execute(
            f"SELECT COUNT(*) c FROM urls WHERE {db.FAILED} AND status IN {db.UNREACHABLE}"
        ).fetchone()["c"]

        visited = conn.execute(
            """SELECT COUNT(DISTINCT b.canonical_url) c FROM bookmarks b
               JOIN history h ON h.canonical_url=b.canonical_url WHERE b.removed=0"""
        ).fetchone()["c"]

        # Prefer LLM categories once they exist; fall back to folder-derived topics.
        # The chart is of top-level themes, so "Parent / Child" counts towards
        # its parent: the model is told to prefer the most specific category.
        cat_topics = {r["top"]: r["c"] for r in conn.execute(
            """SELECT CASE WHEN instr(c.path, ' / ') THEN substr(c.path, 1, instr(c.path, ' / ') - 1)
                          ELSE c.path END AS top,
                      COUNT(DISTINCT uc.url_id) c
               FROM url_categories uc JOIN categories c ON c.id = uc.category_id
               GROUP BY top""")}
        topics: dict[str, int] = dict(cat_topics)
        years: dict[str, int] = {}
        domains: dict[str, int] = {}
        for r in conn.execute("SELECT folder_path, date_added, url FROM bookmarks WHERE removed=0"):
            if not cat_topics and not in_graveyard(r["folder_path"]):
                topics[topic_of(r["folder_path"])] = topics.get(topic_of(r["folder_path"]), 0) + 1
            if r["date_added"]:
                y = r["date_added"][:4]
                years[y] = years.get(y, 0) + 1
            host = (urlsplit(r["url"]).hostname or "?").removeprefix("www.")
            domains[host] = domains.get(host, 0) + 1

        sources = [dict(r) for r in conn.execute(
            """SELECT s.id, s.kind, s.browser, s.profile, s.last_ingested,
                      COUNT(b.id) FILTER (WHERE b.removed=0) AS bookmarks
               FROM sources s LEFT JOIN bookmarks b ON b.source_id=s.id
               GROUP BY s.id ORDER BY bookmarks DESC""")]

        return {
            "total_bookmarks": total,
            "unique_urls": unique,
            "duplicates": duplicates,
            "status_counts": status_counts,
            "last_checked": checked_at,
            "unreachable_confirmed": unreachable,
            "topics_source": "llm" if cat_topics else "folders",
            "visited_recently": visited,
            "topics": sorted(topics.items(), key=lambda kv: -kv[1])[:14],
            "years": sorted(years.items()),
            "domains": sorted(domains.items(), key=lambda kv: -kv[1])[:10],
            "sources": sources,
        }

    @app.get("/api/bookmarks")
    def bookmarks(
        q: str = "", status: str = "", topic: str = "", domain: str = "",
        source_id: int | None = None,
        limit: int = Query(50, le=500), offset: int = 0,
    ) -> dict:
        sql = """SELECT b.id, b.title, b.url, b.canonical_url, b.folder_path, b.date_added,
                        s.browser, s.profile,
                        u.id AS url_id, u.status, u.http_status, u.reason, u.review,
                        h.visit_count, h.last_visit
                 FROM bookmarks b
                 JOIN sources s ON s.id = b.source_id
                 LEFT JOIN urls u ON u.canonical_url = b.canonical_url
                 LEFT JOIN history h ON h.canonical_url = b.canonical_url
                 WHERE b.removed = 0"""
        params: list = []
        if q:
            # FTS5 over titles, URLs, fetched page text and topics; LIKE fallback.
            fts_query = " ".join('"' + term.replace('"', "") + '"' for term in q.split())
            try:
                hit_ids = [r["url_id"] for r in conn.execute(
                    "SELECT url_id FROM search WHERE search MATCH ? ORDER BY bm25(search) LIMIT 2000",
                    (fts_query,))]
            except sqlite3.OperationalError:
                hit_ids = None
            if hit_ids is not None:
                if not hit_ids:
                    return {"total": 0, "rows": []}
                sql += f" AND u.id IN ({','.join(str(int(i)) for i in hit_ids)})"
            else:
                sql += " AND (b.title LIKE ? OR b.url LIKE ? OR b.folder_path LIKE ?)"
                like = f"%{q}%"
                params += [like, like, like]
        if status:
            sql += " AND u.status = ?"
            params.append(status)
        if domain:
            sql += " AND b.url LIKE ?"
            params.append(f"%//%{domain}%")
        if source_id:
            sql += " AND b.source_id = ?"
            params.append(source_id)
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY b.id", params)]
        cats: dict[int, list[str]] = {}
        if rows:
            for r in conn.execute(
                """SELECT uc.url_id, c.path FROM url_categories uc
                   JOIN categories c ON c.id=uc.category_id ORDER BY uc.confidence DESC"""):
                cats.setdefault(r["url_id"], []).append(r["path"])
        for r in rows:
            r["topics"] = cats.get(r["url_id"]) or [topic_of(r["folder_path"])]
            r["topic"] = r["topics"][0]
        if topic:
            rows = [r for r in rows
                    if any(t == topic or t.startswith(topic + " / ") for t in r["topics"])]
        total = len(rows)
        return {"total": total, "rows": rows[offset:offset + limit]}

    @app.get("/api/graveyard")
    def graveyard(limit: int = Query(100, le=1000), offset: int = 0) -> dict:
        queue = f"({db.FAILED} OR status = 'suspect')"
        gone = f"{db.FAILED} AND review IS NULL"
        rows = [dict(r) for r in conn.execute(
            f"""SELECT u.id, u.check_url, u.status, u.http_status, u.reason, u.checked_at, u.review,
                       u.wayback_url, u.wayback_at,
                       (SELECT title FROM bookmarks b
                        WHERE b.canonical_url=u.canonical_url AND b.removed=0 LIMIT 1) AS title,
                       (SELECT folder_path FROM bookmarks b
                        WHERE b.canonical_url=u.canonical_url AND b.removed=0 LIMIT 1) AS folder_path
                FROM urls u
                WHERE {queue} AND u.review IS NULL
                ORDER BY CASE u.status WHEN 'dead' THEN 0 WHEN 'error' THEN 1
                         WHEN 'timeout' THEN 2 ELSE 3 END, u.id
                LIMIT ? OFFSET ?""", (limit, offset))]
        for r in rows:
            r["topic"] = topic_of(r["folder_path"] or "")
        counts = {r["status"]: r["c"] for r in conn.execute(
            f"""SELECT status, COUNT(*) c FROM urls
                WHERE {queue} AND review IS NULL GROUP BY status""")}
        reviewed = conn.execute(
            "SELECT COUNT(*) c FROM urls WHERE review IS NOT NULL").fetchone()["c"]
        snapshots = conn.execute(
            f"SELECT COUNT(*) c FROM urls WHERE {gone} AND wayback_url IS NOT NULL").fetchone()["c"]
        no_snapshot = conn.execute(
            f"""SELECT COUNT(*) c FROM urls WHERE {gone}
                AND wayback_checked_at IS NOT NULL AND wayback_url IS NULL""").fetchone()["c"]
        pending = conn.execute(
            f"""SELECT COUNT(*) c FROM urls WHERE status IN {db.UNREACHABLE}
                AND consecutive_failures < ? AND review IS NULL""",
            (db.CONFIRMED_FAILURES,)).fetchone()["c"]
        return {"counts": counts, "reviewed": reviewed, "snapshots": snapshots,
                "no_snapshot": no_snapshot, "pending": pending, "rows": rows}

    @app.get("/api/duplicates")
    def duplicates(limit: int = Query(50, le=500), offset: int = 0) -> dict:
        groups = duplicate_groups(conn)
        return {"total": len(groups),
                "total_entries_collapsed": sum(len(g["collapse"]) for g in groups),
                "groups": groups[offset:offset + limit]}

    @app.get("/api/rediscover")
    def rediscover(count: int = 6) -> dict:
        candidates = [dict(r) for r in conn.execute(
            """SELECT b.id, b.title, b.url, b.folder_path, b.date_added
               FROM bookmarks b
               JOIN urls u ON u.canonical_url = b.canonical_url
               LEFT JOIN history h ON h.canonical_url = b.canonical_url
               WHERE b.removed=0 AND u.status IN ('live','login_wall')
                 AND h.url IS NULL AND u.review IS NULL
               ORDER BY RANDOM() LIMIT 150""")]
        picked, seen_domains = [], set()
        for r in candidates:
            host = (urlsplit(r["url"]).hostname or "?").removeprefix("www.")
            if host in seen_domains:
                continue
            seen_domains.add(host)
            r["domain"] = host
            r["topic"] = topic_of(r["folder_path"])
            picked.append(r)
            if len(picked) >= count:
                break
        return {"rows": picked}


    @app.post("/api/urls/{url_id}/review")
    def review(url_id: int, body: Review) -> dict:
        if body.decision not in ("keep", "let_go", "replace"):
            raise HTTPException(400, "decision must be keep, let_go or replace")
        if body.decision == "replace":
            row = conn.execute("SELECT wayback_url FROM urls WHERE id=?", (url_id,)).fetchone()
            if row is None or not row["wayback_url"]:
                raise HTTPException(400, "no Wayback snapshot recorded for this URL")
        cur = conn.execute(
            "UPDATE urls SET review=?, reviewed_at=? WHERE id=?",
            (body.decision, datetime.now(timezone.utc).isoformat(), url_id))
        conn.commit()
        if not cur.rowcount:
            raise HTTPException(404, "no such url")
        return {"ok": True}

    @app.get("/api/topics")
    def topics() -> dict:
        rows = [dict(r) for r in conn.execute(
            """SELECT c.path, COUNT(uc.url_id) n FROM categories c
               LEFT JOIN url_categories uc ON uc.category_id=c.id
               GROUP BY c.path ORDER BY c.path""")]
        return {"topics": rows}

    @app.get("/api/topicmap")
    def topicmap() -> dict:
        nodes = [dict(r) for r in conn.execute(
            """SELECT c.id, c.path, COUNT(uc.url_id) n FROM categories c
               JOIN url_categories uc ON uc.category_id=c.id
               GROUP BY c.id HAVING n >= 5 ORDER BY n DESC""")]
        ids = {n["id"] for n in nodes}
        edges = [dict(r) for r in conn.execute(
            """SELECT a.category_id s, b.category_id t, COUNT(*) w
               FROM url_categories a JOIN url_categories b
                 ON a.url_id=b.url_id AND a.category_id < b.category_id
               GROUP BY s, t HAVING w >= 4""")]
        return {"nodes": nodes, "edges": [e for e in edges if e["s"] in ids and e["t"] in ids]}

    @app.get("/api/domains")
    def domains(limit: int = Query(150, le=500)) -> dict:
        by: dict[str, dict] = {}
        for r in conn.execute(
            """SELECT u.id, u.check_url, u.status, u.review, u.consecutive_failures,
                      (SELECT title FROM bookmarks b WHERE b.canonical_url=u.canonical_url
                       AND b.removed=0 LIMIT 1) AS title,
                      (SELECT MAX(h.last_visit) FROM history h
                       WHERE h.canonical_url=u.canonical_url) AS last_visit
               FROM urls u WHERE u.status <> 'skipped'"""):
            host = (urlsplit(r["check_url"]).hostname or "?").removeprefix("www.")
            d = by.setdefault(host, {"domain": host, "total": 0, "alive": 0, "dead": 0,
                                     "reviewed": 0, "visited": 0, "samples": []})
            d["total"] += 1
            d["alive"] += r["status"] in ("live", "login_wall")
            d["dead"] += r["status"] == "dead" or (
                r["status"] in ("error", "timeout") and r["consecutive_failures"] >= db.CONFIRMED_FAILURES)
            d["reviewed"] += r["review"] is not None
            d["visited"] += r["last_visit"] is not None
            if len(d["samples"]) < 3 and r["title"]:
                d["samples"].append(r["title"][:70])
        result = sorted((d for d in by.values() if d["total"] >= 3 and d["reviewed"] < d["total"]),
                        key=lambda d: (-d["total"]))
        return {"total": len(result), "domains": result[:limit]}


    @app.post("/api/domains/review")
    def domain_review(body: DomainReview) -> dict:
        if body.decision not in ("keep", "let_go"):
            raise HTTPException(400, "decision must be keep or let_go")
        target = body.domain.lower().removeprefix("www.")
        ids = [r["id"] for r in conn.execute(
            "SELECT id, check_url FROM urls WHERE review IS NULL AND status <> 'skipped'")
            if (urlsplit(r["check_url"]).hostname or "").lower().removeprefix("www.") == target]
        now = datetime.now(timezone.utc).isoformat()
        for url_id in ids:
            conn.execute("UPDATE urls SET review=?, reviewed_at=? WHERE id=?",
                         (body.decision, now, url_id))
        conn.commit()
        return {"updated": len(ids)}


    @app.post("/api/chat")
    def chat(body: ChatQ) -> dict:
        description, _ = describe_collection(conn)

        def ask(max_tokens: int, schema: dict, prompt: str) -> dict:
            """One structured call; failures come back as errors, not tracebacks."""
            try:
                data = llm.complete(prompt, schema, max_tokens, model=chat_model(), effort="low")
            except llm.LLMError as exc:
                raise HTTPException(503 if exc.advice else 502, str(exc)) from exc
            if data is None:
                raise HTTPException(502, "the model declined the question")
            return data

        def fts(query: str, limit: int = 15) -> list[int]:
            fts_query = " OR ".join('"' + t.replace('"', "") + '"' for t in query.split() if t)
            try:
                return [r["url_id"] for r in conn.execute(
                    "SELECT url_id FROM search WHERE search MATCH ? ORDER BY bm25(search) LIMIT ?",
                    (fts_query, limit))]
            except sqlite3.OperationalError:
                return []

        queries = ask(1500, {
            "type": "object",
            "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
            "required": ["queries"], "additionalProperties": False},
            "Produce 3-6 short full-text search queries (2-4 words each) that would find "
            "pages relevant to this question in a personal bookmark collection. "
            + description + " Question: " + body.question[:500])["queries"]

        seen: list[int] = []
        for q in [body.question] + queries:
            for url_id in fts(q):
                if url_id not in seen:
                    seen.append(url_id)
        candidates = []
        for url_id in seen[:40]:
            r = conn.execute(
                """SELECT u.id, u.check_url, u.status, u.page_description,
                          (SELECT title FROM bookmarks b WHERE b.canonical_url=u.canonical_url
                           AND b.removed=0 LIMIT 1) AS title,
                          (SELECT GROUP_CONCAT(c.path, '; ') FROM url_categories uc
                           JOIN categories c ON c.id=uc.category_id WHERE uc.url_id=u.id) AS topics
                   FROM urls u WHERE u.id=?""", (url_id,)).fetchone()
            if r:
                candidates.append(dict(r))
        if not candidates:
            return {"groups": [], "note": "Nothing in your bookmarks matches that question."}

        listing = "\n".join(
            f"[{i}] {(c['title'] or '')[:100]} | {c['check_url'][:90]} | "
            f"{(c['topics'] or '')[:80]} | {(c['page_description'] or '')[:150]}"
            for i, c in enumerate(candidates))
        data = ask(4000, {
            "type": "object",
            "properties": {
                "groups": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "theme": {"type": "string"},
                        "items": {"type": "array", "items": {
                            "type": "object",
                            "properties": {"index": {"type": "integer"},
                                           "why": {"type": "string"}},
                            "required": ["index", "why"], "additionalProperties": False}}},
                    "required": ["theme", "items"], "additionalProperties": False}},
                "note": {"type": "string"}},
            "required": ["groups", "note"], "additionalProperties": False},
            "You surface links from a personal bookmark collection — you do NOT answer "
            "the question, you point to saved links that might help. From the candidates "
            "below, pick only genuinely relevant ones, grouped by theme, each with one "
            "short line on why it's relevant to the question. If few or none are truly "
            "relevant, say so in the note rather than padding.\n\n"
            f"Question: {body.question[:500]}\n\nCandidates:\n{listing}")

        groups = []
        for g in data.get("groups", []):
            items = []
            for it in g.get("items", []):
                idx = it.get("index")
                if isinstance(idx, int) and 0 <= idx < len(candidates):
                    c = candidates[idx]
                    items.append({"title": c["title"] or c["check_url"], "url": c["check_url"],
                                  "status": c["status"], "topics": c["topics"], "why": it.get("why", "")})
            if items:
                groups.append({"theme": g.get("theme", ""), "items": items})
        return {"groups": groups, "note": data.get("note", "")}


    @app.post("/api/graveyard/bulk")
    def graveyard_bulk(body: Bulk) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        gone = f"{db.FAILED} AND review IS NULL"
        if body.scope == "replace_snapshots":
            cur = conn.execute(
                f"""UPDATE urls SET review='replace', reviewed_at=?
                    WHERE {gone} AND wayback_url IS NOT NULL""", (now,))
        elif body.scope == "let_go_no_snapshot":
            cur = conn.execute(
                f"""UPDATE urls SET review='let_go', reviewed_at=?
                    WHERE {gone} AND wayback_checked_at IS NOT NULL AND wayback_url IS NULL""", (now,))
        else:
            raise HTTPException(400, "unknown scope")
        conn.commit()
        return {"updated": cur.rowcount}

    return app
