"""Bower CLI: sources, ingest, check, report, stats, serve."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from . import db
from .checker import run_check
from .ingest import ingest_chromium_history, ingest_source
from .report import build_report
from .sources import detect, register


def main() -> None:
    parser = argparse.ArgumentParser(prog="bower", description="Bookmark audit and dashboard")
    parser.add_argument("--db", type=Path, default=None, help="database path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sources", help="detect and register browser bookmark stores")

    sub.add_parser("sync", help="one-shot incremental update: ingest, check, enrich, categorise, index")

    p_ingest = sub.add_parser("ingest", help="import bookmarks from registered sources (read-only)")
    p_ingest.add_argument("--source-id", type=int, default=None, help="only this source")
    p_ingest.add_argument("--no-history", action="store_true", help="skip browser-history joins")

    p_check = sub.add_parser("check", help="validate links")
    p_check.add_argument("--limit", type=int, default=None)
    p_check.add_argument("--concurrency", type=int, default=30)
    p_check.add_argument("--recheck", action="store_true", help="re-validate already-checked URLs")

    p_report = sub.add_parser("report", help="write reports/report.md and print it")
    p_report.add_argument("--out", type=Path, default=db.data_home() / "reports/report.md")

    sub.add_parser("stats", help="one-line status counts")

    p_enrich = sub.add_parser("enrich", help="fetch page titles/descriptions for alive URLs")
    p_enrich.add_argument("--limit", type=int, default=None)
    p_enrich.add_argument("--concurrency", type=int, default=30)

    p_cat = sub.add_parser("categorize", help="LLM categorisation (two-pass)")
    p_cat.add_argument("--taxonomy", action="store_true", help="pass A: derive the taxonomy")
    p_cat.add_argument("--assign", action="store_true", help="pass B: assign categories")
    p_cat.add_argument("--limit", type=int, default=None)
    p_cat.add_argument("--model", default=None, help="override the assignment model")

    sub.add_parser("index", help="rebuild the full-text search index")

    p_wb = sub.add_parser("wayback", help="look up Internet Archive snapshots for dead links")
    p_wb.add_argument("--limit", type=int, default=None)

    p_obs = sub.add_parser("obsidian", help="export topics + bookmark stubs as an Obsidian folder")
    p_obs.add_argument("--out", type=Path, default=db.data_home() / "exports/obsidian")

    p_write = sub.add_parser("writeback", help="write the cleaned tree back to a browser (dry-run by default)")
    p_write.add_argument("--source-id", type=int, required=True)
    p_write.add_argument("--apply", action="store_true",
                         help="actually write the file (backup is taken first; browser must be closed)")

    p_serve = sub.add_parser("serve", help="run the dashboard at http://127.0.0.1:8420")
    p_serve.add_argument("--port", type=int, default=8420)

    args = parser.parse_args()
    conn = db.connect(args.db)

    if args.cmd == "sync":
        # Every stage is incremental: ingest reconciles by guid, check probes only
        # unchecked URLs, enrich and categorise touch only what they haven't seen.
        register(conn, detect())
        for source in conn.execute("SELECT * FROM sources").fetchall():
            stats = ingest_source(conn, source)
            if source["kind"] == "chromium" and "error" not in stats:
                stats |= ingest_chromium_history(conn, source)
            print(json.dumps(stats))
        print(json.dumps({"check": asyncio.run(run_check(conn))}))
        from .enrich import run_enrich
        print(json.dumps({"enrich": asyncio.run(run_enrich(conn))}))
        try:
            from .categorize import assign
            print(json.dumps({"categorize": assign(conn)}))
        except Exception as exc:  # no taxonomy yet, or no API credentials
            print(json.dumps({"categorize": f"skipped: {exc}"}))
        from .categorize import rebuild_index
        print(json.dumps({"index": rebuild_index(conn)}))
    elif args.cmd == "sources":
        found = detect()
        register(conn, found)
        for row in conn.execute("SELECT * FROM sources ORDER BY id"):
            print(f"  [{row['id']}] {row['browser']:<9} {row['profile']:<20} ({row['kind']})  {row['path']}")
    elif args.cmd == "ingest":
        register(conn, detect())
        rows = conn.execute(
            "SELECT * FROM sources" + (f" WHERE id={int(args.source_id)}" if args.source_id else "")
        ).fetchall()
        for source in rows:
            stats = ingest_source(conn, source)
            if source["kind"] == "chromium" and not args.no_history and "error" not in stats:
                stats |= ingest_chromium_history(conn, source)
            print(json.dumps(stats))
    elif args.cmd == "check":
        stats = asyncio.run(run_check(conn, limit=args.limit,
                                      concurrency=args.concurrency, recheck=args.recheck))
        print(json.dumps(stats, indent=2))
    elif args.cmd == "report":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        print(build_report(conn, args.out))
        print(f"written to {args.out}")
    elif args.cmd == "stats":
        for row in conn.execute("SELECT status, COUNT(*) c FROM urls GROUP BY status ORDER BY c DESC"):
            print(f"{row['status']:>10}  {row['c']:,}")
    elif args.cmd == "enrich":
        from .enrich import run_enrich
        print(json.dumps(asyncio.run(run_enrich(conn, limit=args.limit,
                                                concurrency=args.concurrency))))
    elif args.cmd == "categorize":
        from .categorize import assign, derive_taxonomy
        from .llm import LLMError
        try:
            if args.taxonomy:
                print(json.dumps(derive_taxonomy(conn)))
            if args.assign or not args.taxonomy:
                print(json.dumps(assign(conn, model=args.model, limit=args.limit)))
        except LLMError as exc:
            raise SystemExit(f"bowerbird: {exc}") from exc
    elif args.cmd == "index":
        from .categorize import rebuild_index
        print(json.dumps(rebuild_index(conn)))
    elif args.cmd == "obsidian":
        from .obsidian import export
        print(json.dumps(export(conn, args.out)))
    elif args.cmd == "wayback":
        from .wayback import run_wayback
        print(json.dumps(asyncio.run(run_wayback(conn, limit=args.limit))))
    elif args.cmd == "writeback":
        from .writeback import writeback
        result = writeback(conn, args.source_id, apply=args.apply)
        print(json.dumps(result, indent=2))
        if not args.apply:
            print("dry run — nothing written; re-run with --apply to write (browser must be closed)")
    elif args.cmd == "serve":
        import uvicorn
        from .server import create_app
        conn.close()
        uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
