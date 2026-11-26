"""Read the "Mark of the Web" that Windows keeps on downloaded files.

Browsers save it in a hidden NTFS stream named Zone.Identifier, next to the
file's normal contents. It looks like this:

    [ZoneTransfer]
    ZoneId=3
    ReferrerUrl=https://example.com/downloads
    HostUrl=https://example.com/files/report.pdf

HostUrl is the file's own address and ReferrerUrl the page that linked to it.
Either can be missing: older programs write only ZoneId, and some browsers
leave out one of the two.
"""

import os
import sys
from dataclasses import dataclass

ZONE_NAMES = {
    0: "this computer",
    1: "local network",
    2: "trusted site",
    3: "internet",
    4: "restricted site",
}

# Values some browsers write instead of a real address
PLACEHOLDER_URLS = {"", "about:internet", "about:blank"}

# Don't read more than this from a stream: a real one is a few hundred bytes
MAX_STREAM_BYTES = 64 * 1024


@dataclass(frozen=True)
class Mark:
    zone_id: int | None
    host_url: str | None
    referrer_url: str | None

    @property
    def zone_name(self):
        return ZONE_NAMES.get(self.zone_id, "unknown zone")

    @property
    def has_source(self):
        return bool(self.host_url or self.referrer_url)


def decode(data):
    """Bytes of a Zone.Identifier stream as text. Most are plain ASCII, but
    some programs write UTF-16 or add a UTF-8 byte order mark."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse(data):
    """Turn the bytes of a Zone.Identifier stream into a Mark (None if empty)."""
    values = {}
    for line in decode(data).splitlines():
        line = line.strip()
        if not line or line.startswith(("[", ";", "#")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip()

    try:
        zone_id = int(values["zoneid"])
    except (KeyError, ValueError):
        zone_id = None
    host_url = clean_url(values.get("hosturl"))
    referrer_url = clean_url(values.get("referrerurl"))
    if zone_id is None and host_url is None and referrer_url is None:
        return None
    return Mark(zone_id, host_url, referrer_url)


def clean_url(url):
    if url is None or url.lower() in PLACEHOLDER_URLS:
        return None
    return url


def read(path):
    """The Mark of the Web on a file, or None if it has none. Only Windows
    (NTFS) has these streams; elsewhere this always returns None."""
    if sys.platform != "win32":
        return None
    try:
        with open(os.fspath(path) + ":Zone.Identifier", "rb") as stream:
            return parse(stream.read(MAX_STREAM_BYTES))
    except OSError:
        return None
