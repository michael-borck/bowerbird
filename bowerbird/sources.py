"""Detect installed browsers and their bookmark stores (macOS paths).

Chromium-family browsers share one JSON format; profiles are discovered via
each browser's "Local State" file. Firefox uses places.sqlite per profile.
Safari is a single binary plist (read-only for us — it's iCloud-synced and has
no sanctioned write path; macOS may also require Full Disk Access to read it).
"""

from __future__ import annotations

import configparser
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

APP_SUPPORT = Path.home() / "Library/Application Support"

CHROMIUM_BROWSERS = {
    "Brave": APP_SUPPORT / "BraveSoftware/Brave-Browser",
    "Chrome": APP_SUPPORT / "Google/Chrome",
    "Edge": APP_SUPPORT / "Microsoft Edge",
    "Vivaldi": APP_SUPPORT / "Vivaldi",
    "Chromium": APP_SUPPORT / "Chromium",
    "Arc": APP_SUPPORT / "Arc/User Data",
    "Opera": Path.home() / "Library/Application Support/com.operasoftware.Opera",
}


@dataclass
class DetectedSource:
    kind: str      # chromium | firefox | safari
    browser: str
    profile: str
    path: str      # the bookmarks file itself


def _chromium_profiles(base: Path) -> dict[str, str]:
    """profile_dir -> display name, from Local State when available."""
    names: dict[str, str] = {}
    local_state = base / "Local State"
    if local_state.exists():
        try:
            info = json.loads(local_state.read_text()).get("profile", {}).get("info_cache", {})
            names = {d: (v.get("name") or d) for d, v in info.items()}
        except (json.JSONDecodeError, OSError):
            pass
    if not names and (base / "Default").is_dir():
        names = {"Default": "Default"}
    return names


def detect() -> list[DetectedSource]:
    found: list[DetectedSource] = []

    for browser, base in CHROMIUM_BROWSERS.items():
        if not base.is_dir():
            continue
        for profile_dir, name in _chromium_profiles(base).items():
            bookmarks = base / profile_dir / "Bookmarks"
            if bookmarks.exists():
                found.append(DetectedSource("chromium", browser, name, str(bookmarks)))

    ff_root = APP_SUPPORT / "Firefox"
    profiles_ini = ff_root / "profiles.ini"
    if profiles_ini.exists():
        ini = configparser.ConfigParser()
        ini.read(profiles_ini)
        for section in ini.sections():
            if not section.startswith("Profile"):
                continue
            rel = ini[section].get("IsRelative", "1") == "1"
            prof_path = (ff_root / ini[section]["Path"]) if rel else Path(ini[section]["Path"])
            places = prof_path / "places.sqlite"
            if places.exists():
                found.append(DetectedSource(
                    "firefox", "Firefox", ini[section].get("Name", prof_path.name), str(places)))

    safari = Path.home() / "Library/Safari/Bookmarks.plist"
    try:
        if safari.exists():
            found.append(DetectedSource("safari", "Safari", "Default", str(safari)))
    except PermissionError:
        pass  # no Full Disk Access — Safari stays undetected

    return found


def register(conn: sqlite3.Connection, sources: list[DetectedSource]) -> None:
    for s in sources:
        conn.execute(
            """INSERT INTO sources(kind, browser, profile, path) VALUES(?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET browser=excluded.browser, profile=excluded.profile""",
            (s.kind, s.browser, s.profile, s.path),
        )
    conn.commit()
