from bowerbird.canonical import canonicalize, is_checkable


def test_strips_tracking_params():
    assert canonicalize("https://example.com/a?utm_source=x&utm_medium=y&id=7") == \
        "https://example.com/a?id=7"
    assert canonicalize("http://example.com/a?fbclid=abc") == "https://example.com/a"


def test_scheme_and_www_unify():
    assert canonicalize("http://www.example.com/a") == canonicalize("https://example.com/a")


def test_trailing_slash():
    assert canonicalize("https://example.com/path/") == "https://example.com/path"
    assert canonicalize("https://example.com/") == "https://example.com/"


def test_query_order_insensitive():
    assert canonicalize("https://e.com/x?b=2&a=1") == canonicalize("https://e.com/x?a=1&b=2")


def test_youtube_variants_unify():
    forms = [
        "https://youtu.be/kCc8FmEb1nY",
        "https://www.youtube.com/watch?v=kCc8FmEb1nY",
        "https://m.youtube.com/watch?v=kCc8FmEb1nY&feature=share",
        "https://www.youtube.com/watch?v=kCc8FmEb1nY&ab_channel=AndrejKarpathy",
    ]
    assert len({canonicalize(u) for u in forms}) == 1
    assert canonicalize(forms[0]) == "https://youtube.com/watch?v=kCc8FmEb1nY"


def test_youtube_timestamp_kept():
    assert "t=2147s" in canonicalize("https://www.youtube.com/watch?v=abc123def45&t=2147s")


def test_non_http_passthrough():
    assert canonicalize("javascript:void(0)") == "javascript:void(0)"


def test_default_port_dropped_custom_kept():
    assert canonicalize("https://example.com:443/a") == "https://example.com/a"
    assert ":8080" in canonicalize("http://example.com:8080/a")


def test_is_checkable():
    assert is_checkable("https://example.com")
    assert not is_checkable("javascript:void(0)")
    assert not is_checkable("chrome://settings")
    assert not is_checkable("http://localhost:3000")
    assert not is_checkable("http://192.168.1.10/admin")
    assert not is_checkable("file:///Users/me/doc.html")
