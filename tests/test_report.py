from bowerbird import db, report


def test_report_counts_duplicates_the_way_the_dashboard_does(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    conn.executemany("INSERT INTO sources(id, kind, browser, profile, path) "
                     "VALUES(?,'chromium',?,'Test',?)",
                     [(1, "Brave", "/tmp/brave"), (2, "Chrome", "/tmp/chrome")])
    # The same link in two browsers is deliberate; twice in one browser is a duplicate.
    conn.executemany(
        "INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path, root) "
        "VALUES(?,?,?,?,?,'Bar','bookmark_bar')", [
            (1, "a", "One", "https://e.com/a", "https://e.com/a"),
            (1, "b", "One again", "https://e.com/a", "https://e.com/a"),
            (2, "c", "One elsewhere", "https://e.com/a", "https://e.com/a"),
            (2, "d", "Two", "https://e.com/b", "https://e.com/b"),
        ])
    conn.commit()

    text = report.build_report(conn)

    assert "- Bookmarks in Brave, Chrome: **4**" in text
    assert "**1** duplicate entries within one browser" in text
    assert "- ×2  One  `https://e.com/a`" in text
    conn.close()
