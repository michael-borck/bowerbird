"""Write the cleaned bookmark tree back to a Chromium-family browser.

Safety model:
  - Dry-run by default; --apply is required to touch the file.
  - Refuses to run while the browser is open (its exit would clobber our write).
  - Timestamped backup of the original file is written first, always.
  - Nothing is hard-deleted: within-source duplicates collapse onto their
    keeper, 'replace' decisions swap in the Wayback URL, and 'let_go'
    bookmarks move to a "_Graveyard" folder for a final manual look.
  - The stored checksum is dropped so the browser recomputes it on load.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .db import data_home

BROWSER_PROCESSES = {"Brave": "Brave Browser", "Chrome": "Google Chrome",
                     "Edge": "Microsoft Edge", "Vivaldi": "Vivaldi", "Chromium": "Chromium"}


def _browser_running(browser: str) -> bool:
    name = BROWSER_PROCESSES.get(browser, browser)
    return subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0


def _chrome_now() -> str:
    delta = datetime.now(timezone.utc) - datetime(1601, 1, 1, tzinfo=timezone.utc)
    return str(int(delta.total_seconds() * 1_000_000))


def _plan(conn: sqlite3.Connection, source: sqlite3.Row) -> dict:
    """Compute per-guid actions for one source from the review/dupe state."""
    url_state = {r["canonical_url"]: r for r in conn.execute(
        "SELECT canonical_url, status, review, wayback_url FROM urls")}

    groups: dict[str, list[sqlite3.Row]] = {}
    for r in conn.execute(
        "SELECT guid, title, folder_path, canonical_url FROM bookmarks "
        "WHERE removed=0 AND source_id=? ORDER BY id", (source["id"],)):
        groups.setdefault(r["canonical_url"], []).append(r)

    remove: set[str] = set()
    let_go: set[str] = set()
    replace: dict[str, str] = {}

    for canonical, members in groups.items():
        if len(members) > 1:
            keeper = max(members, key=lambda m: (
                "read later" not in m["folder_path"].lower(), len(m["folder_path"])))
            remove.update(m["guid"] for m in members if m["guid"] != keeper["guid"])
            members = [keeper]
        state = url_state.get(canonical)
        if state is None:
            continue
        guid = members[0]["guid"]
        if state["review"] == "replace" and state["wayback_url"]:
            replace[guid] = state["wayback_url"]
        elif state["review"] == "let_go":
            let_go.add(guid)

    return {"remove": remove, "let_go": let_go, "replace": replace}


def writeback(conn: sqlite3.Connection, source_id: int, apply: bool = False) -> dict:
    source = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if source is None:
        raise SystemExit(f"no source with id {source_id}")
    if source["kind"] != "chromium":
        raise SystemExit(f"write-back supports Chromium-family browsers only, not {source['kind']}")

    path = Path(source["path"])
    data = json.loads(path.read_text())
    plan = _plan(conn, source)
    graveyard_nodes: list[dict] = []
    stats = {"duplicates_removed": 0, "replaced_with_wayback": 0, "moved_to_graveyard": 0}
    max_id = 0

    def walk(node: dict) -> dict | None:
        nonlocal max_id
        try:
            max_id = max(max_id, int(node.get("id", 0)))
        except (TypeError, ValueError):
            pass
        if node.get("type") == "url":
            guid = node.get("guid")
            if guid in plan["remove"]:
                stats["duplicates_removed"] += 1
                return None
            if guid in plan["let_go"]:
                stats["moved_to_graveyard"] += 1
                graveyard_nodes.append(node)
                return None
            if guid in plan["replace"]:
                stats["replaced_with_wayback"] += 1
                node = dict(node, url=plan["replace"][guid])
            return node
        if node.get("type") == "folder":
            node = dict(node)
            node["children"] = [c for c in (walk(child) for child in node.get("children", []))
                                if c is not None]
            return node
        return node

    for root_name, root in list(data.get("roots", {}).items()):
        if isinstance(root, dict):
            data["roots"][root_name] = walk(root)

    if graveyard_nodes:
        bar = data["roots"].get("bookmark_bar", {})
        bar.setdefault("children", []).append({
            "type": "folder",
            "id": str(max_id + 1),
            "guid": str(uuid.uuid4()),
            "name": "_Graveyard",
            "date_added": _chrome_now(),
            "date_modified": _chrome_now(),
            "children": graveyard_nodes,
        })
    data.pop("checksum", None)

    result = {"source": f"{source['browser']}/{source['profile']}", "applied": False, **stats}
    if not apply:
        return result

    if _browser_running(source["browser"]):
        raise SystemExit(
            f"{source['browser']} is running — close it first, or it will overwrite the change on exit")

    backup_dir = data_home() / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{source['browser']}-{source['profile']}-Bookmarks-{stamp}.json"
    shutil.copy2(path, backup)

    tmp = path.with_suffix(".bower-tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=3))
    tmp.replace(path)
    # Brave also keeps Bookmarks.bak; leave it — it's the browser's own fallback.

    result.update(applied=True, backup=str(backup))
    return result
