import os
import sys

import pytest

from wherefrom import zone


def test_full_mark():
    data = (b"[ZoneTransfer]\r\nZoneId=3\r\nReferrerUrl=https://example.com/page\r\n"
            b"HostUrl=https://example.com/file.zip\r\n")
    mark = zone.parse(data)
    assert mark == zone.Mark(3, "https://example.com/file.zip", "https://example.com/page")
    assert mark.zone_name == "internet"
    assert mark.has_source


def test_only_zone_id_from_older_programs():
    mark = zone.parse(b"[ZoneTransfer]\nZoneId=3\n")
    assert mark == zone.Mark(3, None, None)
    assert not mark.has_source


def test_placeholder_urls_mean_unknown():
    mark = zone.parse(b"[ZoneTransfer]\nZoneId=3\nHostUrl=about:internet\nReferrerUrl=\n")
    assert mark.host_url is None and mark.referrer_url is None


def test_keys_any_case_and_equals_signs_inside_urls():
    mark = zone.parse(b"[zonetransfer]\nzoneid = 3\nhosturl=https://x.test/get?id=7&sig=a=b\n")
    assert mark.host_url == "https://x.test/get?id=7&sig=a=b"


def test_utf16_and_utf8_byte_order_marks():
    text = "[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://例え.jp/ファイル.pdf\r\n"
    assert zone.parse(text.encode("utf-16")).host_url == "https://例え.jp/ファイル.pdf"
    assert zone.parse(b"\xef\xbb\xbf" + text.encode("utf-8")).zone_id == 3


def test_garbage_and_empty_streams():
    assert zone.parse(b"") is None
    assert zone.parse(b"\x00\x01\x02 not ini at all") is None
    assert zone.parse(b"[ZoneTransfer]\nZoneId=three\n") is None


def test_unknown_zone_number():
    assert zone.parse(b"ZoneId=9\nHostUrl=https://x.test/a\n").zone_name == "unknown zone"


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows behavior")
def test_read_elsewhere_is_none(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hi")
    assert zone.read(f) is None


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS streams exist only on Windows")
def test_read_a_real_stream(tmp_path):
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.7")
    with open(str(f) + ":Zone.Identifier", "w") as stream:
        stream.write("[ZoneTransfer]\nZoneId=3\nHostUrl=https://example.com/report.pdf\n")
    assert zone.read(f).host_url == "https://example.com/report.pdf"
    assert zone.read(tmp_path / "missing.pdf") is None
    plain = tmp_path / "plain.txt"
    plain.write_text("no mark")
    assert zone.read(plain) is None
    assert os.path.getsize(f) == 8          # the stream isn't part of the contents
