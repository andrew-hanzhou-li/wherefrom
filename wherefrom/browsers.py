"""Import download history from browsers, so files downloaded before
wherefrom was installed can be traced too.

Browsers keep their history in SQLite files that are locked while the browser
runs, so each one is copied to a temporary folder and read from there. The
browser's own files are never opened or changed.
"""

import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from .watch import file_hash

# Chromium browsers: name -> "User Data" folder under %LOCALAPPDATA%
CHROMIUM_BROWSERS = {
    "chrome": Path("Google", "Chrome", "User Data"),
    "edge": Path("Microsoft", "Edge", "User Data"),
    "brave": Path("BraveSoftware", "Brave-Browser", "User Data"),
    "vivaldi": Path("Vivaldi", "User Data"),
}

CHROMIUM_COMPLETE = 1       # downloads.state for a finished download


def chromium_histories(local_appdata):
    """(browser, History file) for every profile of every Chromium browser."""
    found = []
    for browser, user_data in CHROMIUM_BROWSERS.items():
        root = Path(local_appdata) / user_data
        if not root.is_dir():
            continue
        for profile in sorted(root.iterdir()):
            history = profile / "History"
            if history.is_file():
                found.append((browser, history))
    return found


def firefox_histories(appdata):
    root = Path(appdata) / "Mozilla" / "Firefox" / "Profiles"
    if not root.is_dir():
        return []
    return [("firefox", p / "places.sqlite") for p in sorted(root.iterdir())
            if (p / "places.sqlite").is_file()]


def copy_database(path, folder):
    """Copy a SQLite file (and its write-ahead log, which can hold the newest
    rows) into `folder`. Returns the copy's path."""
    target = Path(folder) / path.name
    shutil.copyfile(path, target)
    for side in ("-wal", "-journal"):
        extra = Path(str(path) + side)
        if extra.is_file():
            shutil.copyfile(extra, Path(str(target) + side))
    return target


def webkit_time(microseconds):
    """Chromium time (microseconds since 1601-01-01 UTC) as local ISO text."""
    if not microseconds:
        return None
    moment = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=microseconds)
    return moment.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


def unix_time(microseconds):
    if not microseconds:
        return None
    return datetime.fromtimestamp(microseconds / 1_000_000).isoformat(timespec="seconds")


# The last URL of the redirect chain is where the bytes came from. tab_url is
# the page the download started from; older Chromium versions only have referrer.
CHROMIUM_QUERY = """
    SELECT d.target_path,
           (SELECT c.url FROM downloads_url_chains c
            WHERE c.id = d.id ORDER BY c.chain_index DESC LIMIT 1),
           {page},
           d.start_time
    FROM downloads d
    WHERE d.state = ? AND d.target_path != ''
"""
QUERY_WITH_TAB_URL = CHROMIUM_QUERY.replace("{page}", "COALESCE(NULLIF(d.tab_url, ''), d.referrer)")
QUERY_WITHOUT_TAB_URL = CHROMIUM_QUERY.replace("{page}", "d.referrer")


def chromium_downloads(db):
    """(target_path, file_url, page_url, downloaded_at) for each finished download."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(downloads)")}
    query = QUERY_WITH_TAB_URL if "tab_url" in columns else QUERY_WITHOUT_TAB_URL
    rows = db.execute(query, (CHROMIUM_COMPLETE,)).fetchall()
    # Empty strings mean "not known"
    return [(path, url or None, page_url or None, webkit_time(start))
            for path, url, page_url, start in rows]


def file_uri_to_path(uri):
    """file:///C:/Users/a/x.pdf -> C:\\Users\\a\\x.pdf (and plain paths elsewhere)."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    if len(path) > 2 and path[0] == "/" and path[2] == ":":     # /C:/...
        return path[1:].replace("/", "\\")
    return path


def firefox_downloads(db):
    rows = db.execute(
        """SELECT a.content, p.url, a.dateAdded
           FROM moz_annos a
           JOIN moz_anno_attributes n ON n.id = a.anno_attribute_id
           JOIN moz_places p ON p.id = a.place_id
           WHERE n.name = 'downloads/destinationFileURI'"""
    ).fetchall()
    found = []
    for destination, url, added in rows:
        path = file_uri_to_path(destination)
        if path:
            # Firefox doesn't keep the page a download came from
            found.append((path, url, None, unix_time(added)))
    return found


def import_history(ledger, browser, history_file):
    """Record every download from one history file whose file still exists.
    Returns (downloads in history, newly recorded)."""
    with tempfile.TemporaryDirectory() as folder:
        copy = copy_database(Path(history_file), folder)
        db = sqlite3.connect(str(copy))
        try:
            if browser == "firefox":
                downloads = firefox_downloads(db)
            else:
                downloads = chromium_downloads(db)
        finally:
            db.close()

    recorded = 0
    for path, url, page_url, downloaded_at in downloads:
        if not os.path.isfile(path):
            continue                # deleted or moved since; nothing to match
        try:
            sha256, size = file_hash(path)
        except OSError:
            continue
        if ledger.add(sha256, size, path, source=browser, downloaded_at=downloaded_at,
                      host_url=url, referrer_url=page_url):
            recorded += 1
    return len(downloads), recorded


def import_all(ledger, local_appdata=None, appdata=None):
    """Import from every browser found. Returns [(browser, file, total, new)]."""
    local_appdata = local_appdata or os.environ.get("LOCALAPPDATA", "")
    appdata = appdata or os.environ.get("APPDATA", "")
    results = []
    histories = []
    if local_appdata:
        histories += chromium_histories(local_appdata)
    if appdata:
        histories += firefox_histories(appdata)
    for browser, history in histories:
        try:
            total, new = import_history(ledger, browser, history)
        except (OSError, sqlite3.Error) as error:
            results.append((browser, history, None, str(error)))
            continue
        results.append((browser, history, total, new))
    return results
