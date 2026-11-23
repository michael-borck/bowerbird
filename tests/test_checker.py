import asyncio

import httpx
import pytest

import bowerbird.checker as checker
from bowerbird.checker import classify_response, youtube_video_id


def resp(status: int, url: str, requested: str | None = None) -> httpx.Response:
    r = httpx.Response(status, request=httpx.Request("GET", requested or url))
    # httpx derives .url from the request; simulate a redirect landing point
    r._request = httpx.Request("GET", url)
    return r


def test_404_and_410_are_dead():
    assert classify_response("https://e.com/a", resp(404, "https://e.com/a"), "")[0] == "dead"
    assert classify_response("https://e.com/a", resp(410, "https://e.com/a"), "")[0] == "dead"


def test_403_is_blocked_not_dead():
    for code in (401, 403, 429, 451, 500, 503):
        assert classify_response("https://e.com/a", resp(code, "https://e.com/a"), "")[0] == "blocked"


def test_login_redirect_is_login_wall():
    status, _ = classify_response(
        "https://e.com/private/doc",
        resp(200, "https://e.com/login?next=/private/doc", "https://e.com/private/doc"),
        "<html><title>Please sign in</title></html>")
    assert status == "login_wall"


def test_auth_host_is_login_wall():
    status, _ = classify_response(
        "https://docs.corp.com/x",
        resp(200, "https://accounts.google.com/o/saml", "https://docs.corp.com/x"),
        "")
    assert status == "login_wall"


def test_password_form_after_redirect_is_login_wall():
    status, _ = classify_response(
        "https://e.com/members/area",
        resp(200, "https://e.com/welcome", "https://e.com/members/area"),
        '<form><input type="password" name="p"></form>')
    assert status == "login_wall"


def test_soft_404_title_is_dead():
    status, reason = classify_response(
        "https://e.com/old-post", resp(200, "https://e.com/old-post"),
        "<title>Page Not Found - Example</title>")
    assert status == "dead"
    assert "soft-404" in reason


def test_error_phrase_in_page_text_alone_is_not_dead():
    body = ("<html><head><title>Creating a Web App from Scratch - Part 1</title></head>"
            "<script>const notFound = { title: '404: Not Found' };</script>"
            "<body><p>The old download is no longer available; see the new one.</p></body></html>")
    status, reason = classify_response(
        "https://e.com/post", resp(200, "https://e.com/post"), body)
    assert status == "live"
    assert "soft-404" not in reason


def test_error_phrase_without_a_title_is_not_dead():
    status, _ = classify_response(
        "https://e.com/x", resp(200, "https://e.com/x"), "<html><body>Page not found</body></html>")
    assert status == "live"


def test_deep_link_redirected_to_root_is_suspect():
    status, _ = classify_response(
        "https://e.com/blog/2009/deep/post",
        resp(200, "https://e.com/", "https://e.com/blog/2009/deep/post"),
        "<title>Example Home</title>")
    assert status == "suspect"


def test_plain_200_is_live():
    status, _ = classify_response(
        "https://e.com/a", resp(200, "https://e.com/a"), "<title>A fine page</title>")
    assert status == "live"


def test_youtube_video_id_forms():
    assert youtube_video_id("https://youtu.be/abc123DEF45") == "abc123DEF45"
    assert youtube_video_id("https://www.youtube.com/watch?v=abc123DEF45") == "abc123DEF45"
    assert youtube_video_id("https://www.youtube.com/shorts/abc123DEF45") == "abc123DEF45"
    assert youtube_video_id("https://www.youtube.com/embed/abc123DEF45") == "abc123DEF45"
    assert youtube_video_id("https://www.youtube.com/@channel") is None
    assert youtube_video_id("https://vimeo.com/12345") is None


def oembed_check(monkeypatch, status):
    """check_one() for a YouTube bookmark, with oEmbed answering `status`."""
    monkeypatch.setattr(checker, "RETRY_DELAY", 0)
    transport = httpx.MockTransport(lambda request: httpx.Response(status, request=request))

    async def run():
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            return await checker.check_one(client, checker.HostPacer(), "https://youtu.be/abc123DEF45")

    return asyncio.run(run())["status"]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_youtube_rate_limited_or_failing_is_blocked_not_dead(monkeypatch, status):
    assert oembed_check(monkeypatch, status) == "blocked"


def test_youtube_gone_is_still_dead(monkeypatch):
    assert oembed_check(monkeypatch, 404) == "dead"
