import json
import shutil

import pytest

from wherefrom import cli, lookup, portable
from wherefrom.ledger import Ledger
from wherefrom.watch import Watcher, file_hash

from conftest import FakeMarks, web_mark


def make_download(folder, name="report.pdf", data=b"the report"):
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / name
    f.write_bytes(data)
    return f


def test_export_and_import_to_a_new_computer(tmp_path, ledger):
    f = make_download(tmp_path / "old pc")
    sha, size = file_hash(f)
    ledger.add(sha, size, f, source="chrome", downloaded_at="2026-10-02T21:14:00",
               host_url="https://cdn.test/report.pdf", referrer_url="https://site.test/page",
               mime="application/pdf", original_url="https://short.test/r")
    assert portable.export(ledger, tmp_path / "out.json") == 1

    new_pc = Ledger(tmp_path / "new.sqlite3")
    assert portable.import_file(new_pc, tmp_path / "out.json") == (1, 0)
    assert portable.import_file(new_pc, tmp_path / "out.json") == (0, 0)      # twice is harmless
    [record] = new_pc.by_hash(sha)
    # Marked as imported, whatever the file says it was learned from
    assert (record.source, record.downloaded_at, record.mime, record.original_url) == \
        ("import", "2026-10-02T21:14:00", "application/pdf", "https://short.test/r")
    # The copied file on the new computer is traced by its contents
    copy = make_download(tmp_path / "new pc", "renamed.pdf")
    assert lookup.look_up(copy, new_pc, read_mark=FakeMarks()).host_url == "https://cdn.test/report.pdf"
    new_pc.close()


def test_import_refuses_files_that_are_not_exports(tmp_path, ledger):
    for content in ("not json", json.dumps({"format": "something else"}), json.dumps([1, 2])):
        (tmp_path / "x.json").write_text(content)
        with pytest.raises(portable.BadFile):
            portable.import_file(ledger, tmp_path / "x.json")
    (tmp_path / "x.json").write_text(json.dumps({"format": portable.EXPORT_FORMAT, "version": 99, "records": []}))
    with pytest.raises(portable.BadFile, match="newer"):
        portable.import_file(ledger, tmp_path / "x.json")


def test_damaged_records_are_skipped(tmp_path, ledger):
    good = {"sha256": "a" * 64, "size": 3, "name": "a.txt", "path": "C:\\a.txt",
            "host_url": "https://x.test/a", "source": "edge"}
    bad = [
        {**good, "sha256": "not-a-hash"},
        {**good, "size": -1},
        {**good, "size": True},
        {**good, "host_url": "x" * 10000},
        {**good, "name": "a\x00b"},
        {**good, "host_url": None, "referrer_url": None},
        {**good, "path": ["list"]},
        "a string",
    ]
    (tmp_path / "e.json").write_text(json.dumps({"format": portable.EXPORT_FORMAT, "version": 1,
                                                  "records": [good, *bad]}))
    assert portable.import_file(ledger, tmp_path / "e.json") == (1, len(bad))


def test_sidecar_travels_with_a_renamed_copy(tmp_path, ledger):
    f = make_download(tmp_path / "Downloads")
    lookup.look_up(f, ledger, read_mark=FakeMarks({"report.pdf": web_mark()}))    # learned from the mark
    written, unknown = portable.make_sidecars(ledger, [f])
    assert written == [portable.sidecar_path(f)] and unknown == []
    data = json.loads(written[0].read_text())
    assert data["path"] is None and data["host_url"] == "https://example.com/files/report.pdf"

    # Another person gets the file and its sidecar, renames the file, and asks
    usb = tmp_path / "USB"
    usb.mkdir()
    shutil.copyfile(f, usb / "final version.pdf")
    shutil.copyfile(written[0], usb / ("report.pdf" + portable.SIDECAR_SUFFIX))
    theirs = Ledger(tmp_path / "theirs.sqlite3")
    finding = lookup.look_up(usb / "final version.pdf", theirs, read_mark=FakeMarks())
    assert finding.host_url == "https://example.com/files/report.pdf"
    assert finding.first.source == "sidecar"
    theirs.close()


def test_a_sidecar_for_other_bytes_is_ignored(tmp_path, ledger):
    f = make_download(tmp_path, "a.pdf", b"real contents")
    fake = {"format": portable.SIDECAR_FORMAT, "version": 1, "sha256": "b" * 64, "size": 3,
            "name": "a.pdf", "host_url": "https://evil.test/claimed"}
    portable.sidecar_path(f).write_text(json.dumps(fake))
    assert not lookup.look_up(f, ledger, read_mark=FakeMarks()).known


def test_oversized_or_broken_sidecars_are_ignored(tmp_path, ledger):
    f = make_download(tmp_path, "a.pdf", b"x")
    sha, size = file_hash(f)
    big = {"format": portable.SIDECAR_FORMAT, "version": 1, "sha256": sha, "size": size,
           "name": "a.pdf", "host_url": "https://x.test/a", "padding": "x" * 100_000}
    portable.sidecar_path(f).write_text(json.dumps(big))
    assert not lookup.look_up(f, ledger, read_mark=FakeMarks()).known
    portable.sidecar_path(f).write_bytes(b"\xff\xfe garbage")
    assert not lookup.look_up(f, ledger, read_mark=FakeMarks()).known


def test_a_sidecar_with_a_non_web_link_is_kept_but_never_openable(tmp_path, ledger):
    f = make_download(tmp_path, "a.pdf", b"x")
    sha, size = file_hash(f)
    data = {"format": portable.SIDECAR_FORMAT, "version": 1, "sha256": sha, "size": size,
            "name": "a.pdf", "host_url": "file:///C:/Windows/System32/calc.exe"}
    portable.sidecar_path(f).write_text(json.dumps(data))
    finding = lookup.look_up(f, ledger, read_mark=FakeMarks())
    assert finding.host_url.startswith("file:") and not lookup.openable(finding.host_url)


def test_watcher_can_write_sidecars(tmp_path, ledger):
    downloads = tmp_path / "Downloads"
    f = make_download(downloads)
    watcher = Watcher(ledger, [downloads], read_mark=FakeMarks({"report.pdf": web_mark()}), sidecars=True)
    watcher.scan_once()
    watcher.scan_once()
    assert portable.read_sidecar(portable.sidecar_path(f))["sha256"] == file_hash(f)[0]
    watcher.scan_once()                       # its own sidecar isn't treated as a download
    assert len(ledger.all_records()) == 1


def test_cli_export_import_and_sidecar(tmp_path, capsys, monkeypatch):
    f = make_download(tmp_path / "d")
    marks = FakeMarks({"report.pdf": web_mark()})
    monkeypatch.setattr(cli, "look_up", lambda p, ledger: lookup.look_up(p, ledger, read_mark=marks))
    assert cli.main(["show", str(f)]) == 0
    assert cli.main(["export", str(tmp_path / "all.json")]) == 0
    assert "Wrote 1 record(s)" in capsys.readouterr().out
    assert cli.main(["import", str(tmp_path / "all.json")]) == 0
    assert "Imported 0 new record(s)." in capsys.readouterr().out
    assert cli.main(["import", str(tmp_path / "missing.json")]) == 1
    assert cli.main(["sidecar", str(f)]) == 0
    assert portable.sidecar_path(f).is_file()
    other = make_download(tmp_path / "d", "unknown.bin", b"never seen")
    assert cli.main(["sidecar", str(other)]) == 1
    assert "No record" in capsys.readouterr().err


def test_a_malicious_sidecar_cannot_break_the_folder(tmp_path, ledger):
    f = make_download(tmp_path, "a.pdf", b"x")
    (tmp_path / "evil.wherefrom.json").write_text('{"format": "wherefrom-sidecar", "size": ' + "9" * 5000 + "}")
    (tmp_path / "deep.wherefrom.json").write_text("[" * 100000)
    assert not lookup.look_up(f, ledger, read_mark=FakeMarks()).known       # no crash


def test_imports_with_odd_shapes_are_refused_cleanly(tmp_path, ledger):
    for content in ('{"format": "wherefrom-ledger", "version": 1, "records": 5}',
                    '{"format": "wherefrom-ledger", "version": 1, "x": ' + "9" * 5000 + "}",
                    "[" * 100000):
        (tmp_path / "x.json").write_text(content)
        with pytest.raises(portable.BadFile):
            portable.import_file(ledger, tmp_path / "x.json")


def test_a_sidecar_cannot_take_over_the_headline(tmp_path, ledger):
    f = make_download(tmp_path, "setup.exe", b"installer")
    sha, size = file_hash(f)
    ledger.add(sha, size, f, source="chrome", downloaded_at="2026-11-20T10:00:00",
               host_url="https://evil.example/setup.exe", referrer_url="https://evil.example/")
    fake = {"format": portable.SIDECAR_FORMAT, "version": 1, "sha256": sha, "size": size, "name": "setup.exe",
            "host_url": "https://download.microsoft.com/setup.exe", "downloaded_at": "2001-01-01T00:00:00"}
    (tmp_path / "x.wherefrom.json").write_text(json.dumps(fake))
    finding = lookup.look_up(f, ledger, read_mark=FakeMarks())
    assert finding.host_url == "https://evil.example/setup.exe"         # what this computer saw
    assert finding.first.source == "chrome"
    assert [r.source for r in finding.records] == ["chrome", "sidecar"]


def test_long_urls_are_dropped_not_fatal_and_zone_survives(tmp_path, ledger):
    f = make_download(tmp_path, "a.bin", b"a")
    sha, size = file_hash(f)
    ledger.add(sha, size, f, source="chrome", host_url="data:application/octet-stream;base64," + "A" * 20000,
               referrer_url="https://site.test/page")
    g = make_download(tmp_path, "b.bin", b"b")
    ledger.add(*file_hash(g), g, source="mark", host_url="https://x.test/b", zone_id=3)
    portable.export(ledger, tmp_path / "out.json")
    other = Ledger(tmp_path / "other.sqlite3")
    assert portable.import_file(other, tmp_path / "out.json") == (2, 0)
    assert {r.host_url: r.zone_id for r in other.all_records()} == {None: None, "https://x.test/b": 3}
    other.close()


def test_sidecars_are_not_written_through_links(tmp_path, ledger):
    import os
    if not hasattr(os, "symlink"):
        pytest.skip("no symlinks")
    f = make_download(tmp_path, "a.pdf", b"x")
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    try:
        os.symlink(victim, portable.sidecar_path(f))
    except OSError:
        pytest.skip("can't make symlinks here")
    lookup.look_up(f, ledger, read_mark=FakeMarks({"a.pdf": web_mark()}))
    assert portable.make_sidecars(ledger, [f]) == ([], [f])
    assert victim.read_text() == "keep me"


def test_two_processes_upgrading_an_old_ledger_at_once(tmp_path, monkeypatch):
    # Process A checks the columns, process B adds "mime" first, then A's
    # ALTER TABLE fails with "duplicate column name": that must be harmless.
    import sqlite3
    from wherefrom import ledger as ledger_module
    path = tmp_path / "old.sqlite3"
    Ledger(path).close()                       # a ledger that already has every column

    class StaleCheck:
        """A connection whose column check still sees the old table."""
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, *args):
            if sql.startswith("PRAGMA table_info"):
                return [r for r in self.conn.execute(sql) if r[1] not in ledger_module.ADDED_COLUMNS]
            return self.conn.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self.conn, name)

    real_connect = sqlite3.connect
    monkeypatch.setattr(ledger_module.sqlite3, "connect", lambda *a, **k: StaleCheck(real_connect(*a, **k)))
    Ledger(path).close()                       # tries ALTER TABLE on existing columns: no error
