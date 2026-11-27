import os
import plistlib
import subprocess
import sys
from datetime import datetime

import pytest

from wherefrom import lookup, marks


def test_where_froms_plist():
    data = plistlib.dumps(["https://cdn.test/file.zip", "https://site.test/page"], fmt=plistlib.FMT_BINARY)
    assert marks.parse_where_froms(data) == ("https://cdn.test/file.zip", "https://site.test/page")
    only = plistlib.dumps(["https://cdn.test/file.zip"], fmt=plistlib.FMT_BINARY)
    assert marks.parse_where_froms(only) == ("https://cdn.test/file.zip", None)
    for bad in (b"garbage", plistlib.dumps({"a": 1}), plistlib.dumps([1, 2]), b""):
        assert marks.parse_where_froms(bad) == (None, None)


def test_quarantine():
    moment = int(datetime(2026, 11, 20, 14, 3).timestamp())
    when, app = marks.parse_quarantine(f"0083;{moment:x};Safari;ABCD-1234".encode())
    assert when == "2026-11-20T14:03:00" and app == "Safari"
    assert marks.parse_quarantine(b"nonsense") == (None, None)
    assert marks.parse_quarantine(b"0083;zz;Safari;x") == (None, None)


def test_read_mac_and_linux_with_fake_attributes():
    attrs = {marks.WHERE_FROMS: plistlib.dumps(["https://a.test/x", "https://b.test/p"], fmt=plistlib.FMT_BINARY)}
    mark = marks.read_mac("/x", getxattr=lambda p, n: attrs.get(n))
    assert (mark.host_url, mark.referrer_url, mark.zone_id) == ("https://a.test/x", "https://b.test/p", None)
    assert marks.read_mac("/x", getxattr=lambda p, n: None) is None
    linux = {marks.XDG_ORIGIN: b"https://a.test/x", marks.XDG_REFERRER: b"https://b.test/p"}
    mark = marks.read_linux("/x", getxattr=lambda p, n: linux.get(n))
    assert (mark.host_url, mark.referrer_url) == ("https://a.test/x", "https://b.test/p")
    assert marks.read_linux("/x", getxattr=lambda p, n: None) is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux attributes")
def test_real_linux_attributes(tmp_path, ledger):
    f = tmp_path / "chrome-download.pdf"
    f.write_bytes(b"pdf")
    try:
        os.setxattr(f, marks.XDG_ORIGIN, b"https://cdn.test/chrome-download.pdf")
        os.setxattr(f, marks.XDG_REFERRER, b"https://site.test/page")
    except OSError:
        pytest.skip("this filesystem has no user attributes")
    finding = lookup.look_up(f, ledger)          # the real reader, no fakes
    assert (finding.host_url, finding.page_url) == ("https://cdn.test/chrome-download.pdf", "https://site.test/page")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS attributes")
def test_real_mac_attributes(tmp_path, ledger):
    f = tmp_path / "safari-download.zip"
    f.write_bytes(b"zip")
    plist = plistlib.dumps(["https://cdn.test/safari-download.zip", "https://site.test/page"], fmt=plistlib.FMT_BINARY)
    subprocess.run(["xattr", "-wx", marks.WHERE_FROMS, plist.hex(), str(f)], check=True)
    moment = int(datetime(2026, 11, 20, 14, 3).timestamp())
    subprocess.run(["xattr", "-w", marks.QUARANTINE, f"0083;{moment:x};Safari;ABCD", str(f)], check=True)
    finding = lookup.look_up(f, ledger)
    assert (finding.host_url, finding.page_url) == ("https://cdn.test/safari-download.zip", "https://site.test/page")
    assert finding.first.downloaded_at == "2026-11-20T14:03:00"
