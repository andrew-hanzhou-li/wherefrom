"""Read the download information each system saves with a file.

- Windows: the Zone.Identifier stream ("Mark of the Web"), see zone.py.
- macOS: the "Where from" attribute (com.apple.metadata:kMDItemWhereFroms,
  a binary plist [file URL, page URL]) and the quarantine attribute, which
  holds when it was downloaded and by which app.
- Linux: user.xdg.origin.url and user.xdg.referrer.url, written by Chrome
  and Chromium (the freedesktop.org convention).
"""

import ctypes
import ctypes.util
import os
import plistlib
import sys
from datetime import datetime

from . import zone
from .zone import Mark, clean_url

MAX_ATTR_BYTES = 64 * 1024
WHERE_FROMS = "com.apple.metadata:kMDItemWhereFroms"
QUARANTINE = "com.apple.quarantine"
XDG_ORIGIN = "user.xdg.origin.url"
XDG_REFERRER = "user.xdg.referrer.url"


def parse_where_froms(data):
    """macOS kMDItemWhereFroms bytes -> (file URL, page URL)."""
    try:
        urls = plistlib.loads(data)
    except Exception:           # plistlib raises several kinds on damaged data
        return None, None
    if not isinstance(urls, list):
        return None, None
    urls = [u for u in urls if isinstance(u, str)]
    host = clean_url(urls[0]) if urls else None
    page = clean_url(urls[1]) if len(urls) > 1 else None
    return host, page


def parse_quarantine(data):
    """macOS quarantine "flags;hex seconds;app;uuid" -> (ISO time, app)."""
    try:
        parts = data.decode("utf-8", errors="replace").split(";")
        when = datetime.fromtimestamp(int(parts[1], 16)).isoformat(timespec="seconds")
        app = parts[2] or None
        return when, app
    except (IndexError, ValueError, OverflowError, OSError):
        return None, None


def _mac_getxattr(path, name):
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.getxattr.restype = ctypes.c_ssize_t
    libc.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t,
                              ctypes.c_uint32, ctypes.c_int]
    buffer = ctypes.create_string_buffer(MAX_ATTR_BYTES)
    size = libc.getxattr(os.fsencode(path), name.encode(), buffer, MAX_ATTR_BYTES, 0, 0)
    return buffer.raw[:size] if size >= 0 else None


def _linux_getxattr(path, name):
    try:
        return os.getxattr(path, name)[:MAX_ATTR_BYTES]
    except OSError:
        return None


def read_mac(path, getxattr=None):
    getxattr = getxattr or _mac_getxattr
    data = getxattr(path, WHERE_FROMS)
    if not data:
        return None
    host, page = parse_where_froms(data)
    if not host and not page:
        return None
    return Mark(None, host, page)


def read_linux(path, getxattr=None):
    getxattr = getxattr or _linux_getxattr
    host = getxattr(path, XDG_ORIGIN)
    page = getxattr(path, XDG_REFERRER)
    host = clean_url(host.decode("utf-8", errors="replace")) if host else None
    page = clean_url(page.decode("utf-8", errors="replace")) if page else None
    if not host and not page:
        return None
    return Mark(None, host, page)


def downloaded_at(path, getxattr=None):
    """When the file was downloaded, if the system saved it (macOS only)."""
    if sys.platform != "darwin" and getxattr is None:
        return None
    data = (getxattr or _mac_getxattr)(path, QUARANTINE)
    return parse_quarantine(data)[0] if data else None


def read(path):
    """The file's saved download information on this system, or None."""
    if sys.platform == "win32":
        return zone.read(path)
    try:
        if sys.platform == "darwin":
            return read_mac(path)
        if hasattr(os, "getxattr"):
            return read_linux(path)
    except (OSError, ValueError):
        return None
    return None
