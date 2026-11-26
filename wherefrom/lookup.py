"""Find out where one file came from, from its mark and from the ledger."""

import os
from dataclasses import dataclass

from . import zone
from .watch import file_hash

# Only these are offered as links to open; anything else is shown as text
OPENABLE_SCHEMES = ("http://", "https://")


@dataclass
class Finding:
    path: str
    mark: object            # zone.Mark or None
    records: list           # ledger.Record, oldest first (same bytes, any path)
    error: str | None = None

    @property
    def host_url(self):
        if self.mark and self.mark.host_url:
            return self.mark.host_url
        return next((r.host_url for r in self.records if r.host_url), None)

    @property
    def page_url(self):
        if self.mark and self.mark.referrer_url:
            return self.mark.referrer_url
        return next((r.referrer_url for r in self.records if r.referrer_url), None)

    @property
    def known(self):
        return bool(self.host_url or self.page_url)

    @property
    def first(self):
        """The earliest record of these bytes, if any."""
        return self.records[0] if self.records else None

    @property
    def other_copies(self):
        """Other places the same bytes were seen, still on disk."""
        here = os.path.normcase(os.path.abspath(self.path))
        seen = set()
        copies = []
        for record in self.records:
            there = os.path.normcase(os.path.abspath(record.path))
            if there != here and there not in seen and os.path.isfile(record.path):
                seen.add(there)
                copies.append(record.path)
        return copies


def look_up(path, ledger, read_mark=zone.read):
    """Read the file's mark and match its contents against the ledger. A mark
    found here is also saved, so copies made later can still be traced."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return Finding(path, None, [], error="Not a file (or it no longer exists).")
    mark = read_mark(path)
    try:
        sha256, size = file_hash(path)
    except OSError as error:
        return Finding(path, mark, [], error=f"Can't read the file: {error.strerror or error}")
    if mark is not None and mark.has_source:
        ledger.add(sha256, size, path, mark=mark, source="mark")
    return Finding(path, mark, ledger.by_hash(sha256))


def openable(url):
    return bool(url) and url.lower().startswith(OPENABLE_SCHEMES)
