"""URL canonicalisation — produces a dedupe key, not a replacement URL.

The canonical form unifies scheme to https, strips www./m., drops fragments,
tracking parameters and trailing slashes, sorts the query, and folds YouTube's
many URL shapes onto youtube.com/watch?v=ID.

Neither function raises, whatever the bookmark looks like: they arrive from
other people's exports and synced devices, and a malformed one is still a
bookmark.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "yclid", "twclid",
    "igshid", "mc_cid", "mc_eid", "mkt_tok", "spm", "si", "_hsenc", "_hsmi",
    "vero_id", "cmpid", "ncid", "sr_share", "ref_src", "ref_url", "share_id",
}

YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "www.youtube.com", "music.youtube.com"}
# Params that don't change which video you land on.
YOUTUBE_DROP = {"feature", "ab_channel", "pp", "index", "app", "sns", "annotation_id", "src_vid"}

_UNUSABLE = object()


def _port(parts):
    """The port, or _UNUSABLE when the text is not one a client could use."""
    try:
        return parts.port
    except ValueError:  # "http://host:abc/"
        return _UNUSABLE


def is_checkable(url: str) -> bool:
    """http(s) URLs pointing at a public host that a client can actually request."""
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or _port(parts) is _UNUSABLE:
        return False
    host = (parts.hostname or "").lower()
    if not host or host == "localhost" or host.endswith(".local"):
        return False
    try:
        if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback:
            return False
    except ValueError:
        pass  # not an IP literal — a normal hostname
    return True


def canonicalize(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    if parts.scheme not in ("http", "https"):
        return url.strip()

    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.startswith("utm_") and k not in TRACKING_PARAMS]

    if host == "youtu.be":
        video_id = path.strip("/").split("/")[0]
        host, path = "youtube.com", "/watch"
        query = [("v", video_id)] + [(k, v) for k, v in query if k != "v"]
    if host in YOUTUBE_HOSTS:
        host = "youtube.com"
        query = [(k, v) for k, v in query if k not in YOUTUBE_DROP]

    host = host.removeprefix("www.")

    port = _port(parts)
    if port is _UNUSABLE:
        port = None  # still a bookmark, so still a key
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"

    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit(("https", netloc, path, urlencode(sorted(query)), ""))
