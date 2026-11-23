"""Link validation.

Policy (learned from cite-sight, extended for bookmarks):
  - GET, never HEAD — many servers 403 HEAD.
  - Only 404/410 mean dead. 401/403/429/451/5xx mean blocked — refused, not gone.
  - Reaching a login page means the bookmark is alive behind an account (login_wall).
   - A deep link that 200s after redirecting to the site root is suspect (soft-404).
   - A soft-404 needs the error in the page <title>. The same words in page
     text or script (release notes, nav links, bundled 404 components) are
     ordinary content.
   - YouTube videos are checked via the oEmbed API — the watch page itself
     returns 200 even for deleted videos.
   - An unreachable link (DNS failure, timeout) may just be a bad hour at one
     end or the other: it is probed again on later runs and only joins the
     graveyard once it has failed twice.
   - A URL no client can request is skipped; an unexpected error on one URL is
     recorded against that URL instead of ending the run.
  - Per-host pacing + bounded global concurrency; one retry on 429/5xx/timeout.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote, urlsplit

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.8",
}

BODY_CAP = 65536
DEFAULT_HOST_INTERVAL = 1.0
HOST_INTERVALS = {"www.youtube.com": 0.3, "youtube.com": 0.3}
RETRY_DELAY = 5.0
# An unreachable link is probed again on later runs, so an outage heals by
# itself — but not more often than this, or two checks in the same bad hour
# would confirm each other.
RECHECK_AFTER = timedelta(hours=6)

AUTH_HOST_RE = re.compile(
    r"^(accounts\.google\.com|login\.microsoftonline\.com|login\.live\.com|"
    r"id\.atlassian\.com|(auth|login|signin|sso|idp|identity)\.)|(\.okta\.com|\.auth0\.com)$"
)
LOGIN_PATH_RE = re.compile(
    r"/(log-?in|sign-?in|sign_in|users/sign_in|account/login|auth|sso|session/new|"
    r"wp-login\.php|oauth2?|authorize)([/?#]|$)", re.I
)
LOGIN_TITLE_RE = re.compile(r"\b(log ?in|sign ?in|authenticate|authentication required)\b", re.I)
SOFT404_RE = re.compile(
    r"(page (you('re| are)? looking for )?(was |could )?not( be)? found|"
    r"404 not found|page doesn.t exist|no longer (available|exists)|"
    r"content (is )?unavailable|video unavailable|this page isn.t available)", re.I
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


class HostPacer:
    """Serialises requests per host with a minimum interval between them."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._next_ok: dict[str, float] = {}

    async def wait(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            delay = self._next_ok.get(host, 0.0) - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            interval = HOST_INTERVALS.get(host, DEFAULT_HOST_INTERVAL)
            self._next_ok[host] = time.monotonic() + interval


def youtube_video_id(url: str) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return parts.path.strip("/").split("/")[0] or None
    if host in ("youtube.com", "music.youtube.com"):
        if parts.path == "/watch":
            return (parse_qs(parts.query).get("v") or [None])[0]
        m = re.match(r"^/(embed|shorts|live|v)/([\w-]{6,})", parts.path)
        if m:
            return m.group(2)
    return None


def classify_response(requested: str, resp: httpx.Response, body: str) -> tuple[str, str]:
    """Returns (status, reason) for a completed non-YouTube response."""
    code = resp.status_code
    final = str(resp.url)
    if code in (404, 410):
        return "dead", f"http {code}"
    if code in (401, 403, 407, 429, 451) or code >= 500:
        return "blocked", f"http {code}"
    if code >= 400:
        return "blocked", f"http {code}"

    fparts = urlsplit(final)
    fhost = (fparts.hostname or "").lower()
    title_m = TITLE_RE.search(body)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""

    if AUTH_HOST_RE.search(fhost) or LOGIN_PATH_RE.search(fparts.path):
        return "login_wall", f"landed on {fhost}{fparts.path}"
    if 'type="password"' in body and (final.rstrip("/") != requested.rstrip("/") or LOGIN_TITLE_RE.search(title)):
        return "login_wall", "password form on arrival"

    if SOFT404_RE.search(title):
        return "dead", f"soft-404 ({title[:60]})"

    rparts = urlsplit(requested)
    if len(rparts.path) > 1 and fparts.path in ("", "/") and fhost and not rparts.query:
        return "suspect", f"deep link redirected to root of {fhost}"

    return "live", title[:100]


async def check_one(client: httpx.AsyncClient, pacer: HostPacer, url: str) -> dict:
    vid = youtube_video_id(url)
    probe = (
        f"https://www.youtube.com/oembed?format=json&url={quote('https://www.youtube.com/watch?v=' + vid)}"
        if vid else url
    )
    host = urlsplit(probe).hostname or ""
    started = time.monotonic()

    for attempt in (1, 2):
        await pacer.wait(host)
        try:
            async with client.stream("GET", probe, headers=HEADERS) as resp:
                if vid:
                    await resp.aread()
                    code = resp.status_code
                    if code == 200:
                        status, reason = "live", "oembed ok"
                    elif code == 401:
                        status, reason = "live", "oembed 401: exists, embedding disabled"
                    elif code == 403:
                        status, reason = "blocked", "oembed 403: private video"
                    elif code == 429 or code >= 500:
                        status, reason = "blocked", f"oembed {code}: refused us, not gone"
                    else:
                        status, reason = "dead", f"oembed {code}: video gone"
                else:
                    body = b""
                    ctype = resp.headers.get("content-type", "")
                    if resp.status_code < 400 and ("html" in ctype or not ctype):
                        async for chunk in resp.aiter_bytes():
                            body += chunk
                            if len(body) >= BODY_CAP:
                                break
                    status, reason = classify_response(
                        url, resp, body.decode("utf-8", errors="replace")
                    )
                http_status, final = resp.status_code, str(resp.url)
        except httpx.TimeoutException:
            status, reason, http_status, final = "timeout", "timed out", None, None
        except httpx.HTTPError as exc:
            status, reason, http_status, final = "error", f"{type(exc).__name__}: {exc}"[:200], None, None
        except (httpx.InvalidURL, ValueError) as exc:
            # No client can ever request this URL, so there is nothing to retry next run.
            status, reason = "skipped", f"malformed URL ({exc})"[:200]
            http_status = final = None

        if attempt == 1 and (status == "timeout" or (http_status in (429,) or (http_status or 0) >= 500)):
            await asyncio.sleep(RETRY_DELAY)
            continue
        break

    return {
        "status": status, "reason": reason, "http_status": http_status,
        "final_url": final if final != url else None,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


async def run_check(
    conn: sqlite3.Connection,
    limit: int | None = None,
    concurrency: int = 30,
    timeout: float = 15.0,
    recheck: bool = False,
    progress_every: int = 100,
) -> dict:
    if recheck:
        where, params = "status <> 'skipped'", []
    else:
        # First probes, plus another go at unreachable links whose last probe is old enough.
        cutoff = (datetime.now(timezone.utc) - RECHECK_AFTER).isoformat()
        where = ("status = 'unchecked' OR (status IN ('error','timeout')"
                 " AND COALESCE(checked_at, '') <= ?)")
        params = [cutoff]
    rows = conn.execute(
        f"SELECT id, check_url FROM urls WHERE {where} ORDER BY id"
        + (f" LIMIT {int(limit)}" if limit else ""), params
    ).fetchall()
    if not rows:
        return {"checked": 0}

    pacer = HostPacer()
    sem = asyncio.Semaphore(concurrency)
    done = 0
    counts: dict[str, int] = {}

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout, http2=False,
        limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=10),
    ) as client:

        async def worker(row: sqlite3.Row) -> tuple[int, dict]:
            async with sem:
                try:
                    return row["id"], await check_one(client, pacer, row["check_url"])
                except Exception as exc:  # one bad row must not cost us the whole run
                    return row["id"], {"status": "error", "reason": f"{type(exc).__name__}: {exc}"[:200],
                                       "http_status": None, "final_url": None, "elapsed_ms": None}

        for coro in asyncio.as_completed([worker(r) for r in rows]):
            url_id, result = await coro
            conn.execute(
                """UPDATE urls SET status=?, http_status=?, final_url=?, reason=?,
                   elapsed_ms=?, checked_at=?,
                   consecutive_failures = CASE WHEN ? IN ('dead','timeout','error')
                       THEN consecutive_failures + 1 ELSE 0 END
                   WHERE id=?""",
                (result["status"], result["http_status"], result["final_url"],
                 result["reason"], result["elapsed_ms"],
                 datetime.now(timezone.utc).isoformat(), result["status"], url_id),
            )
            counts[result["status"]] = counts.get(result["status"], 0) + 1
            done += 1
            if done % progress_every == 0:
                conn.commit()
                print(f"  {done}/{len(rows)} checked  {counts}", flush=True)
        conn.commit()

    return {"checked": done, **counts}
