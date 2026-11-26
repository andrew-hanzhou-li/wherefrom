"""Watch folders (normally Downloads) and record each new file's source while
its Mark of the Web is still there."""

import hashlib
import os
import time
from pathlib import Path

from . import zone

# Browsers download into these and rename the file when it's complete; the
# last one is wherefrom's own sidecar files
PARTIAL_SUFFIXES = (".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload",
                    ".wherefrom.json")


def file_hash(path, chunk_size=1024 * 1024):
    """(sha256 hex, size) of a file, read in chunks so big files are fine."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def downloads_folder():
    """The user's Downloads folder (the usual place; a moved one can be
    given with --folder)."""
    return Path.home() / "Downloads"


class Watcher:
    """Each scan lists the folders. A file is recorded once it has the same
    size and modified time in two scans in a row, so it isn't read while a
    browser is still writing it."""

    def __init__(self, ledger, folders, read_mark=zone.read, sidecars=False):
        self.ledger = ledger
        self.folders = [Path(f) for f in folders]
        self.read_mark = read_mark
        self.sidecars = sidecars        # also write a .wherefrom.json next to each file
        self.pending = {}           # path -> (size, mtime) from the last scan
        # The ledger's own files change every time it records something; if
        # they're in a watched folder, reading them would never end
        self.own_files = os.path.normcase(ledger.path)

    def scan_once(self):
        """Look at every file once. Returns how many new sources were recorded."""
        recorded = 0
        present = set()
        for folder in self.folders:
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue            # folder missing or unreadable right now
            for entry in entries:
                if entry.name.lower().endswith(PARTIAL_SUFFIXES):
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                path = entry.path
                if os.path.normcase(os.path.abspath(path)).startswith(self.own_files):
                    continue
                present.add(path)
                state = (stat.st_size, stat.st_mtime)
                if self.ledger.already_seen(path, *state):
                    continue
                if self.pending.get(path) == state:
                    del self.pending[path]
                    recorded += self.record(path, state)
                else:
                    self.pending[path] = state
        # Forget files that were deleted or moved away before they settled
        for path in list(self.pending):
            if path not in present:
                del self.pending[path]
        return recorded

    def record(self, path, state):
        mark = self.read_mark(path)
        if mark is None or not mark.has_source:
            self.ledger.mark_seen(path, *state)     # nothing to learn from this one
            return 0
        try:
            sha256, size = file_hash(path)
        except OSError:
            return 0                # locked or gone; try again next scan
        added = self.ledger.add(sha256, size, path, mark=mark, source="mark")
        if self.sidecars:
            from .portable import write_sidecar
            try:
                write_sidecar(path, self.ledger.by_hash(sha256)[0])
            except OSError:
                pass                # a read-only folder: the ledger still has it
        self.ledger.mark_seen(path, *state)
        return 1 if added else 0

    def run(self, interval=5.0, scans=None):
        """Scan every `interval` seconds, forever (or `scans` times, for tests)."""
        done = 0
        while scans is None or done < scans:
            self.scan_once()
            done += 1
            if scans is None or done < scans:
                time.sleep(interval)
