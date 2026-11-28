import sqlite3
from datetime import datetime, timezone

from wherefrom import browsers

# Chromium stores times as microseconds since 1601-01-01 UTC
EPOCH_1601 = 11644473600 * 1_000_000


def chromium_time(moment):
    return EPOCH_1601 + int(moment.timestamp() * 1_000_000)


def make_chromium_history(path, rows, with_tab_url=True):
    """A History file with the columns wherefrom reads (real ones have more)."""
    db = sqlite3.connect(path)
    tab = ", tab_url TEXT" if with_tab_url else ""
    db.execute(f"CREATE TABLE downloads (id INTEGER PRIMARY KEY, target_path TEXT, start_time INTEGER,"
               f" state INTEGER, referrer TEXT{tab})")
    db.execute("CREATE TABLE downloads_url_chains (id INTEGER, chain_index INTEGER, url TEXT)")
    for i, row in enumerate(rows, start=1):
        target, chain, referrer, tab_url, state, start = row
        if with_tab_url:
            db.execute("INSERT INTO downloads VALUES (?, ?, ?, ?, ?, ?)",
                       (i, target, start, state, referrer, tab_url))
        else:
            db.execute("INSERT INTO downloads VALUES (?, ?, ?, ?, ?)", (i, target, start, state, referrer))
        for index, url in enumerate(chain):
            db.execute("INSERT INTO downloads_url_chains VALUES (?, ?, ?)", (i, index, url))
    db.commit()
    db.close()


def make_firefox_places(path, downloads):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT);
        CREATE TABLE moz_anno_attributes (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE moz_annos (id INTEGER PRIMARY KEY, place_id INTEGER, anno_attribute_id INTEGER,
                                content TEXT, dateAdded INTEGER);
        INSERT INTO moz_anno_attributes VALUES (1, 'downloads/destinationFileURI');
        INSERT INTO moz_anno_attributes VALUES (2, 'downloads/metaData');
    """)
    for i, (url, destination, added) in enumerate(downloads, start=1):
        db.execute("INSERT INTO moz_places VALUES (?, ?)", (i, url))
        db.execute("INSERT INTO moz_annos VALUES (NULL, ?, 1, ?, ?)", (i, destination, added))
        db.execute("INSERT INTO moz_annos VALUES (NULL, ?, 2, '{}', ?)", (i, added))
    db.commit()
    db.close()


def test_webkit_time():
    moment = datetime(2026, 11, 20, 18, 30, tzinfo=timezone.utc)
    local = moment.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    assert browsers.webkit_time(chromium_time(moment)) == local
    assert browsers.webkit_time(0) is None


def test_file_uri_to_path():
    assert browsers.file_uri_to_path("file:///C:/Users/a/My%20File.pdf") == "C:\\Users\\a\\My File.pdf"
    assert browsers.file_uri_to_path("file:///home/a/x%23y.pdf") == "/home/a/x#y.pdf"
    assert browsers.file_uri_to_path("https://x.test/a") is None


def test_chromium_import_records_existing_files(tmp_path, ledger):
    kept = tmp_path / "kept.zip"
    kept.write_bytes(b"zip bytes")
    history = tmp_path / "History"
    when = chromium_time(datetime(2026, 11, 1, tzinfo=timezone.utc))
    make_chromium_history(history, [
        # redirect chain: the last URL is the one the bytes came from
        (str(kept), ["https://short.test/r", "https://cdn.test/kept.zip"], "https://site.test/ref",
         "https://site.test/downloads", 1, when),
        (str(tmp_path / "deleted.zip"), ["https://cdn.test/deleted.zip"], "", "", 1, when),
        (str(tmp_path / "cancelled.zip"), ["https://cdn.test/c.zip"], "", "", 2, when),
    ])
    total, new = browsers.import_history(ledger, "chrome", history)
    assert (total, new) == (2, 1)       # cancelled isn't counted; deleted can't be matched
    [record] = ledger.search("cdn.test")
    assert record.host_url == "https://cdn.test/kept.zip"
    assert record.referrer_url == "https://site.test/downloads"     # the tab's page
    assert record.source == "chrome"
    assert record.downloaded_at.startswith("2026-1")


def test_chromium_without_tab_url_uses_referrer(tmp_path, ledger):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"a")
    make_chromium_history(tmp_path / "History", [
        (str(f), ["https://cdn.test/a.pdf"], "https://site.test/ref", None, 1, 0),
    ], with_tab_url=False)
    browsers.import_history(ledger, "edge", tmp_path / "History")
    assert ledger.search("cdn.test")[0].referrer_url == "https://site.test/ref"


def test_firefox_import(tmp_path, ledger):
    f = tmp_path / "Résumé final.pdf"
    f.write_bytes(b"pdf")
    places = tmp_path / "places.sqlite"
    uri = "file://" + "/".join(["", *f.as_posix().lstrip("/").split("/")[:-1], "R%C3%A9sum%C3%A9%20final.pdf"])
    make_firefox_places(places, [("https://jobs.test/cv.pdf", uri, 1_764_000_000_000_000)])
    total, new = browsers.import_history(ledger, "firefox", places)
    assert (total, new) == (1, 1)
    record = ledger.search("jobs.test")[0]
    assert record.name == "Résumé final.pdf"
    assert record.referrer_url is None


def test_the_browsers_own_file_is_not_changed(tmp_path, ledger):
    history = tmp_path / "History"
    make_chromium_history(history, [])
    before = history.read_bytes()
    browsers.import_history(ledger, "chrome", history)
    assert history.read_bytes() == before


def test_import_all_finds_profiles(tmp_path, ledger):
    local = tmp_path / "Local"
    roaming = tmp_path / "Roaming"
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    for browser_dir, profile in ((("Google", "Chrome"), "Default"), (("Microsoft", "Edge"), "Profile 1")):
        folder = local.joinpath(*browser_dir, "User Data", profile)
        folder.mkdir(parents=True)
        make_chromium_history(folder / "History", [(str(f), ["https://dl.test/x.bin"], "", "", 1, 0)])
    ff = roaming / "Mozilla" / "Firefox" / "Profiles" / "abc.default"
    ff.mkdir(parents=True)
    make_firefox_places(ff / "places.sqlite", [])
    broken = local / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default"
    broken.mkdir(parents=True)
    (broken / "History").write_bytes(b"not a database")
    results = browsers.import_all(ledger, local_appdata=local, appdata=roaming)
    summary = {(r[0], r[2], r[3]) for r in results if r[2] is not None}
    # Both browsers downloaded the same file from the same URL: one record
    assert summary == {("chrome", 1, 1), ("edge", 1, 0), ("firefox", 0, 0)}
    assert [r[0] for r in results if r[2] is None] == ["brave"]   # reported, not a crash
    record = ledger.search("dl.test")[0]
    assert record.referrer_url is None          # empty in the history means unknown


def test_mac_and_linux_layouts(tmp_path):
    home = tmp_path / "home"
    mac = home / "Library" / "Application Support"
    for folder in (mac / "Google" / "Chrome" / "Default", mac / "Microsoft Edge" / "Profile 2"):
        folder.mkdir(parents=True)
        make_chromium_history(folder / "History", [])
    ff = mac / "Firefox" / "Profiles" / "x.default-release"
    ff.mkdir(parents=True)
    make_firefox_places(ff / "places.sqlite", [])
    found = browsers.all_histories("darwin", home)
    assert sorted(b for b, _ in found) == ["chrome", "edge", "firefox"]

    linux_home = tmp_path / "lhome"
    for folder in (".config/google-chrome/Default", "snap/chromium/common/chromium/Default",
                   ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default"):
        (linux_home / folder).mkdir(parents=True)
        make_chromium_history(linux_home / folder / "History", [])
    for folder in (".mozilla/firefox/abc.default", "snap/firefox/common/.mozilla/firefox/def.default"):
        (linux_home / folder).mkdir(parents=True)
        make_firefox_places(linux_home / folder / "places.sqlite", [])
    found = browsers.all_histories("linux", linux_home)
    assert sorted(b for b, _ in found) == ["brave", "chrome", "chromium", "firefox", "firefox"]


def test_import_all_on_linux(tmp_path, ledger):
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    profile = tmp_path / "home" / ".config" / "google-chrome" / "Default"
    profile.mkdir(parents=True)
    make_chromium_history(profile / "History", [(str(f), ["https://dl.test/x.bin"], "", "", 1, 0)])
    results = browsers.import_all(ledger, platform="linux", home=tmp_path / "home")
    assert [(r[0], r[2], r[3]) for r in results] == [("chrome", 1, 1)]


def test_more_browsers_are_found_on_windows(tmp_path, ledger):
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    f = tmp_path / "y.bin"
    f.write_bytes(b"y")
    # Opera's main profile is the folder itself
    opera = roaming / "Opera Software" / "Opera Stable"
    opera.mkdir(parents=True)
    make_chromium_history(opera / "History", [(str(f), ["https://opera.test/y.bin"], "", "", 1, 0)])
    chromium = local / "Chromium" / "User Data" / "Default"
    chromium.mkdir(parents=True)
    make_chromium_history(chromium / "History", [])
    for fork in ("librewolf", "Waterfox", "Floorp", "zen"):
        profile = roaming / fork / "Profiles" / "abc.default"
        profile.mkdir(parents=True)
        make_firefox_places(profile / "places.sqlite", [])
    found = browsers.all_histories("win32", local_appdata=local, appdata=roaming)
    assert sorted(b for b, _ in found) == ["chromium", "floorp", "librewolf", "opera", "waterfox", "zen"]
    # A browser built on Firefox is read as Firefox, whatever it's called
    results = browsers.import_all(ledger, local_appdata=local, appdata=roaming)
    assert all(r[2] is not None for r in results), results
    assert ledger.search("opera.test")[0].source == "opera"


def test_more_browsers_are_found_on_mac_and_linux(tmp_path):
    home = tmp_path / "home"
    mac = home / "Library" / "Application Support"
    (mac / "com.operasoftware.Opera").mkdir(parents=True)
    make_chromium_history(mac / "com.operasoftware.Opera" / "History", [])
    for fork in ("librewolf", "zen"):
        profile = mac / fork / "Profiles" / "p.default"
        profile.mkdir(parents=True)
        make_firefox_places(profile / "places.sqlite", [])
    assert sorted(b for b, _ in browsers.all_histories("darwin", home)) == ["librewolf", "opera", "zen"]

    linux = tmp_path / "lhome"
    (linux / ".config" / "opera").mkdir(parents=True)
    make_chromium_history(linux / ".config" / "opera" / "History", [])
    for folder in (".librewolf/a.default", ".floorp/b.default", ".var/app/app.zen_browser.zen/.zen/c.default"):
        (linux / folder).mkdir(parents=True)
        make_firefox_places(linux / folder / "places.sqlite", [])
    assert sorted(b for b, _ in browsers.all_histories("linux", linux)) == ["floorp", "librewolf", "opera", "zen"]


def test_every_browser_has_a_name_people_can_read():
    from wherefrom.ledger import SOURCE_NAMES
    names = set(browsers.CHROMIUM_BROWSERS) | set(browsers.CHROMIUM_MAC) | set(browsers.CHROMIUM_LINUX) | \
        set(browsers.OPERA_WINDOWS) | set(browsers.FIREFOX_FORKS_WINDOWS) | set(browsers.FIREFOX_FORKS_MAC) | \
        set(browsers.FIREFOX_FORKS_LINUX) | {"firefox"}
    assert names <= set(SOURCE_NAMES), names - set(SOURCE_NAMES)
