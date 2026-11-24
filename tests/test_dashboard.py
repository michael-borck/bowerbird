"""The dashboard's own helper functions, run in node when there is one."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = Path(__file__).resolve().parent.parent / "bowerbird" / "static" / "index.html"
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_helpers(checks: str) -> None:
    """Evaluate the page's helpers: everything before it starts wiring up the DOM."""
    page = re.search(r"<script>(.*)</script>", HTML.read_text(encoding="utf-8"), re.DOTALL)
    assert page and NODE, "the page has a script, and node is installed"
    helpers = page.group(1)[: page.group(1).index('document.querySelectorAll(".nav-item")')]
    result = subprocess.run([NODE, "-"], input=helpers + "\n" + checks, text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


@needs_node
def test_only_http_links_become_links():
    run_helpers('''
const cases = [
  ["javascript:void(0)", "bookmarklet", "bookmarklet"],
  ["JavaScript:(function(){})()", "a bookmarklet &amp; co", "a bookmarklet &amp; co"],
  ["file:///Users/me/a.pdf", "a.pdf", "a.pdf"],
  [null, "nothing", "nothing"],
  ["https://e.com/a?b=\\"c\\"", "&lt;t&gt;",
   '<a href="https://e.com/a?b=&quot;c&quot;" target="_blank" rel="noopener">&lt;t&gt;</a>'],
];
for (const [url, text, want] of cases) {
  const got = link(url, text);
  if (got !== want) throw new Error(`link(${url}) gave ${got}, wanted ${want}`);
}
''')


@needs_node
def test_a_refused_request_is_raised_with_the_servers_reason():
    run_helpers('''
let reply = { ok: false, status: 400, json: async () => ({ detail: "no snapshot recorded" }) };
globalThis.fetch = async () => reply;
const refused = (want) => (err) => { if (err.message !== want) throw err; };
post("/x", {})
  .then(() => { throw new Error("should have been refused"); }, refused("no snapshot recorded"))
  .then(() => {
    reply = { ok: false, status: 422, json: async () => ({ detail: [{ msg: "not a string" }] }) };
    return post("/x", {});
  })
  .then(() => { throw new Error("should have been refused"); }, refused("not a string"))
  .then(() => {
    reply = { ok: false, status: 500, json: async () => { throw new SyntaxError("not json"); }, statusText: "Internal Server Error" };
    return post("/x", {});
  })
  .then(() => { throw new Error("should have been refused"); }, refused("Internal Server Error"))
  .catch((err) => { console.error(err); process.exit(1); });
''')


def test_no_inline_handlers_and_every_link_goes_through_the_helper():
    html = HTML.read_text(encoding="utf-8")
    assert "onclick=" not in html
    assert re.findall(r'href="\$\{([^}]*)\}', html) == ["esc(url)"]
