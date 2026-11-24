from bowerbird import db, obsidian


def test_export_writes_an_index_and_keeps_names_apart_that_differ_only_in_case(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) "
                 "VALUES(1,'chromium','Brave','Test','/tmp/nonexistent')")
    conn.executemany("INSERT INTO urls(id, canonical_url, check_url, status) VALUES(?,?,?,'live')", [
        (1, "https://e.com/1", "https://e.com/1"), (2, "https://e.com/2", "https://e.com/2"),
        (3, "https://e.com/3", "https://e.com/3"), (4, "https://e.com/4", "https://e.com/4")])
    conn.executemany(
        "INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path, root) "
        "VALUES(1,?,?,?,?,'Bar','bookmark_bar')", [
            ("a", "README", "https://e.com/1", "https://e.com/1"),
            ("b", "readme", "https://e.com/2", "https://e.com/2"),
            ("c", "Readme", "https://e.com/3", "https://e.com/3"),
            ("d", "C#", "https://e.com/4", "https://e.com/4"),
        ])
    conn.commit()
    out = tmp_path / "vault"

    assert obsidian.export(conn, out) == {"bookmarks": 4, "topics": 0, "out": str(out)}

    # macOS folds case in file names: untracked, all three would be one file
    assert sorted(p.name for p in (out / "bookmarks").iterdir()) == [
        "C.md", "README.md", "Readme (3).md", "readme (2).md"]
    assert (out / "Bowerbird.md").read_text().startswith("# Bowerbird — bookmark collection")
    conn.close()
