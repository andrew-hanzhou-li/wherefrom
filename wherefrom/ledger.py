"""The ledger: a small SQLite file that remembers where each file came from.

The Mark of the Web is easy to lose. Copying a file to a USB stick, a cloud
folder or an email attachment drops it, and many programs never write it at
all. So wherefrom records each download's source together with a SHA-256 of
its contents. Later, any copy of the same bytes, under any name and in any
folder, can be traced back.
"""

import os
import sqlite3
import sys
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    sha256        TEXT NOT NULL,
    size          INTEGER NOT NULL,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    host_url      TEXT,
    referrer_url  TEXT,
    zone_id       INTEGER,
    source        TEXT NOT NULL,   -- how we learned it: mark, chrome, edge, firefox, extension, ...
    downloaded_at TEXT,            -- when the browser says it downloaded it, if known
    recorded_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS files_by_hash ON files (sha256);
-- One record per file, place and source URLs. (A plain UNIQUE wouldn't do:
-- SQLite counts every NULL as different, and a missing URL is common.)
CREATE UNIQUE INDEX IF NOT EXISTS files_once ON files
    (sha256, path, COALESCE(host_url, ''), COALESCE(referrer_url, ''));

-- Files the watcher has already looked at, so it doesn't hash them again
-- after a restart. A file that changes gets a new size or modified time.
CREATE TABLE IF NOT EXISTS seen (
    path   TEXT PRIMARY KEY,
    size   INTEGER NOT NULL,
    mtime  REAL NOT NULL
);
"""

# Columns added after the first version; older ledgers get them on open.
ADDED_COLUMNS = {
    "mime": "TEXT",             # the file type the server sent (from the browser extension)
    "original_url": "TEXT",     # the address first asked for, before any redirects
}

# Where a record's information came from, for people
SOURCE_NAMES = {
    "mark": "the download information saved with the file",
    "chrome": "Chrome's download history",
    "edge": "Edge's download history",
    "brave": "Brave's download history",
    "vivaldi": "Vivaldi's download history",
    "chromium": "Chromium's download history",
    "firefox": "Firefox's download history",
    "extension": "the wherefrom browser extension",
    "sidecar": "a .wherefrom.json file next to it (written by whoever had the file before)",
    "import": "an imported wherefrom export",
}


@dataclass(frozen=True)
class Record:
    sha256: str
    size: int
    name: str
    path: str
    host_url: str | None
    referrer_url: str | None
    zone_id: int | None
    source: str
    downloaded_at: str | None
    recorded_at: str
    mime: str | None = None
    original_url: str | None = None


COLUMNS = ", ".join(f.name for f in fields(Record))


def default_home():
    """Where the ledger lives: WHEREFROM_HOME if set, else the usual place for
    an app's data on each system."""
    if os.environ.get("WHEREFROM_HOME"):
        return Path(os.environ["WHEREFROM_HOME"])
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "wherefrom"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "wherefrom"
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / "wherefrom"


class Ledger:
    def __init__(self, path=None):
        if path is None:
            home = default_home()
            home.mkdir(parents=True, exist_ok=True)
            path = home / "ledger.sqlite3"
        self.path = os.path.abspath(path)
        # The watcher, the browser extension's helper and a "show" from the
        # menu can run at once; wait a little for each other instead of failing.
        self.db = sqlite3.connect(str(path), timeout=10)
        # SQLite's own lower() and LIKE only fold ASCII letters, so "Über.pdf"
        # wouldn't match "über"; search with Python's full case folding instead.
        self.db.create_function("fold", 1, lambda s: s.casefold() if isinstance(s, str) else s,
                                deterministic=True)
        self.db.executescript(SCHEMA)
        have = {row[1] for row in self.db.execute("PRAGMA table_info(files)")}
        for column, kind in ADDED_COLUMNS.items():
            if column not in have:
                self.db.execute(f"ALTER TABLE files ADD COLUMN {column} {kind}")  # nosec B608 - fixed names
        self.db.commit()

    def close(self):
        self.db.close()

    def add(self, sha256, size, path, mark=None, source="mark", downloaded_at=None,
            host_url=None, referrer_url=None, mime=None, original_url=None, recorded_at=None,
            name=None):
        """Remember one file. A mark (from marks.read) fills in
        the URLs. Returns True if this was new."""
        zone_id = None
        if mark is not None:
            host_url = host_url or mark.host_url
            referrer_url = referrer_url or mark.referrer_url
            zone_id = mark.zone_id
        if not host_url and not referrer_url:
            return False        # nothing about the source worth keeping
        path = os.fspath(path)
        if original_url == host_url:
            original_url = None     # only worth keeping when a redirect changed it
        cursor = self.db.execute(
            f"""INSERT OR IGNORE INTO files ({COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # nosec B608 - fixed column list
            (sha256, size, name or os.path.basename(path), path, host_url, referrer_url, zone_id,
             source, downloaded_at, recorded_at or datetime.now().isoformat(timespec="seconds"),
             mime, original_url),
        )
        self.db.commit()
        return cursor.rowcount == 1

    def by_hash(self, sha256):
        """Every record for these exact bytes, oldest download first."""
        rows = self.db.execute(
            f"""SELECT {COLUMNS} FROM files WHERE sha256 = ?
                ORDER BY COALESCE(downloaded_at, recorded_at)""",  # nosec B608 - fixed column list
            (sha256,),
        ).fetchall()
        return [Record(*row) for row in rows]

    def search(self, text, limit=200):
        """Records whose URLs or file name contain `text` (any case), newest
        first. An empty `text` lists everything."""
        pattern = "%" + escape_like(text.casefold()) + "%"
        rows = self.db.execute(
            f"""SELECT {COLUMNS} FROM files
                WHERE fold(COALESCE(host_url, '')) LIKE ? ESCAPE '\\'
                   OR fold(COALESCE(referrer_url, '')) LIKE ? ESCAPE '\\'
                   OR fold(name) LIKE ? ESCAPE '\\'
                ORDER BY COALESCE(downloaded_at, recorded_at) DESC
                LIMIT ?""",  # nosec B608 - fixed column list
            (pattern, pattern, pattern, limit),
        ).fetchall()
        return [Record(*row) for row in rows]

    def all_records(self):
        rows = self.db.execute(
            f"SELECT {COLUMNS} FROM files ORDER BY COALESCE(downloaded_at, recorded_at)"  # nosec B608
        ).fetchall()
        return [Record(*row) for row in rows]

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def already_seen(self, path, size, mtime):
        row = self.db.execute("SELECT size, mtime FROM seen WHERE path = ?",
                              (os.fspath(path),)).fetchone()
        return row is not None and row[0] == size and row[1] == mtime

    def mark_seen(self, path, size, mtime):
        self.db.execute("INSERT OR REPLACE INTO seen VALUES (?, ?, ?)",
                        (os.fspath(path), size, mtime))
        self.db.commit()


def escape_like(text):
    """Make % and _ in a search mean themselves, not wildcards."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
