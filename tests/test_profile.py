from types import SimpleNamespace

import bowerbird.categorize as categorize
from bowerbird import db, models, profile

ENVS = ("BOWERBIRD_TAXONOMY_MODEL", "BOWERBIRD_ASSIGN_MODEL", "BOWERBIRD_CHAT_MODEL")


def seeded(conn):
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) "
                 "VALUES(1,'chromium','Brave','Test','/tmp/nonexistent')")
    rows = [
        ("a", "A", "https://github.com/a", "https://github.com/a", "Bookmarks bar/3D Printing"),
        ("b", "B", "https://github.com/b", "https://github.com/b", "Bookmarks bar/3D Printing"),
        ("c", "C", "https://arxiv.org/c", "https://arxiv.org/c", "Other bookmarks/Teaching"),
    ]
    conn.executemany(
        """INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path, root)
           VALUES(1,?,?,?,?,?,'bookmark_bar')""", rows)
    conn.commit()


def test_description_comes_from_folders_and_hosts(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    seeded(conn)
    text, source = profile.describe_collection(conn, home=tmp_path)
    assert source == "folders and hosts"
    assert "3 bookmarks" in text
    assert "3D Printing" in text and "Teaching" in text
    assert "Bookmarks bar" not in text
    assert "github.com" in text and "arxiv.org" in text


def test_profile_md_replaces_the_sketch(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    seeded(conn)
    (tmp_path / "profile.md").write_text("  Papers and course notes\nfor teaching **data science**.  \n\n")
    text, source = profile.describe_collection(conn, home=tmp_path)
    assert source == "profile.md"
    assert text.endswith("Papers and course notes for teaching **data science**.")


def test_models_follow_flag_then_environment_then_default(monkeypatch):
    for var in ENVS:
        monkeypatch.delenv(var, raising=False)
    assert models.taxonomy_model() == models.TAXONOMY_DEFAULT
    assert models.assign_model() == models.ASSIGN_DEFAULT
    assert models.chat_model() == models.TAXONOMY_DEFAULT
    monkeypatch.setenv("BOWERBIRD_TAXONOMY_MODEL", "m-tax")
    monkeypatch.setenv("BOWERBIRD_ASSIGN_MODEL", "m-assign")
    assert models.taxonomy_model() == "m-tax" and models.assign_model() == "m-assign"
    assert models.chat_model() == "m-tax"                    # Ask follows the taxonomy model…
    monkeypatch.setenv("BOWERBIRD_CHAT_MODEL", "m-chat")
    assert models.chat_model() == "m-chat"                   # …unless told otherwise
    assert models.assign_model("explicit") == "explicit"     # a flag beats the environment


def test_taxonomy_prompt_describes_the_collection_from_the_data(tmp_path, monkeypatch):
    for var in ENVS:
        monkeypatch.delenv(var, raising=False)
    conn = db.connect(tmp_path / "test.db")
    seeded(conn)
    sent = {}

    class FakeAnthropic:
        def __init__(self, *args, **kwargs):
            self.messages = self

        def create(self, **kwargs):
            sent["model"] = kwargs["model"]
            sent["prompt"] = kwargs["messages"][0]["content"]
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(
                type="text", text='{"categories": [{"name": "Printing", "children": []}]}')])

    monkeypatch.setattr(categorize.anthropic, "Anthropic", FakeAnthropic)
    result = categorize.derive_taxonomy(conn)

    assert sent["model"] == models.TAXONOMY_DEFAULT
    assert "3D Printing" in sent["prompt"] and "github.com" in sent["prompt"]
    assert "academic who teaches" not in sent["prompt"]
    assert result["profile"] == "folders and hosts"
