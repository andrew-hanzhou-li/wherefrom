import hashlib
import os

from wherefrom.watch import Watcher, file_hash

import pytest

from conftest import FakeMarks, web_mark


@pytest.fixture
def downloads(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    return folder


def test_file_hash_streams_in_chunks(tmp_path):
    f = tmp_path / "big.bin"
    data = os.urandom(3 * 1024 * 1024 + 17)
    f.write_bytes(data)
    assert file_hash(f, chunk_size=1024 * 1024) == (hashlib.sha256(data).hexdigest(), len(data))


def test_recorded_once_it_has_settled(downloads, ledger):
    marks = FakeMarks({"report.pdf": web_mark()})
    watcher = Watcher(ledger, [downloads], read_mark=marks)
    (downloads / "report.pdf").write_bytes(b"pdf bytes")
    assert watcher.scan_once() == 0          # first sight: might still be downloading
    assert watcher.scan_once() == 1          # same size and time: done
    sha = hashlib.sha256(b"pdf bytes").hexdigest()
    [record] = ledger.by_hash(sha)
    assert record.host_url == "https://example.com/files/report.pdf"
    assert record.source == "mark"
    assert watcher.scan_once() == 0          # not again


def test_a_file_that_keeps_changing_waits(downloads, ledger):
    watcher = Watcher(ledger, [downloads], read_mark=FakeMarks({"a.zip": web_mark()}))
    f = downloads / "a.zip"
    f.write_bytes(b"1")
    watcher.scan_once()
    f.write_bytes(b"12")
    assert watcher.scan_once() == 0          # grew since the last scan
    assert watcher.scan_once() == 1


def test_partial_downloads_are_skipped(downloads, ledger):
    marks = FakeMarks({"a.zip.crdownload": web_mark(), "b.part": web_mark()})
    watcher = Watcher(ledger, [downloads], read_mark=marks)
    (downloads / "a.zip.crdownload").write_bytes(b"x")
    (downloads / "b.part").write_bytes(b"y")
    watcher.scan_once()
    watcher.scan_once()
    assert marks.reads == []


def test_files_without_a_source_are_not_read_again(downloads, ledger):
    marks = FakeMarks()
    watcher = Watcher(ledger, [downloads], read_mark=marks)
    (downloads / "notes.txt").write_text("made here")
    for _ in range(4):
        watcher.scan_once()
    assert marks.reads == ["notes.txt"]


def test_restart_does_not_redo_work(downloads, ledger):
    marks = FakeMarks({"a.pdf": web_mark()})
    (downloads / "a.pdf").write_bytes(b"a")
    first = Watcher(ledger, [downloads], read_mark=marks)
    first.scan_once()
    first.scan_once()
    second = Watcher(ledger, [downloads], read_mark=marks)
    second.scan_once()
    second.scan_once()
    assert marks.reads == ["a.pdf"]


def test_deleted_before_settling_is_forgotten(downloads, ledger):
    watcher = Watcher(ledger, [downloads], read_mark=FakeMarks({"a.pdf": web_mark()}))
    f = downloads / "a.pdf"
    f.write_bytes(b"a")
    watcher.scan_once()
    f.unlink()
    assert watcher.scan_once() == 0
    assert watcher.pending == {}


def test_folders_and_links_are_not_followed(downloads, ledger):
    marks = FakeMarks({"inside.pdf": web_mark(), "link.pdf": web_mark()})
    (downloads / "sub").mkdir()
    (downloads / "sub" / "inside.pdf").write_bytes(b"x")
    outside = downloads.parent / "outside.pdf"
    outside.write_bytes(b"secret")
    try:
        os.symlink(outside, downloads / "link.pdf")
    except OSError:
        pass                                  # no symlink rights (Windows without dev mode)
    watcher = Watcher(ledger, [downloads], read_mark=marks)
    watcher.scan_once()
    watcher.scan_once()
    assert marks.reads == []


def test_missing_folder_is_not_an_error(downloads, ledger):
    watcher = Watcher(ledger, [downloads / "nope", downloads], read_mark=FakeMarks())
    assert watcher.scan_once() == 0


def test_run_a_fixed_number_of_scans(downloads, ledger):
    (downloads / "a.pdf").write_bytes(b"a")
    watcher = Watcher(ledger, [downloads], read_mark=FakeMarks({"a.pdf": web_mark()}))
    watcher.run(interval=0, scans=2)
    assert len(ledger.search("example.com")) == 1


def test_its_own_ledger_is_ignored(tmp_path):
    from wherefrom.ledger import Ledger
    ledger = Ledger(tmp_path / "ledger.sqlite3")      # inside the watched folder
    marks = FakeMarks({"a.pdf": web_mark()})
    (tmp_path / "a.pdf").write_bytes(b"a")
    watcher = Watcher(ledger, [tmp_path], read_mark=marks)
    for _ in range(3):
        watcher.scan_once()
    ledger.close()
    assert marks.reads == ["a.pdf"]
