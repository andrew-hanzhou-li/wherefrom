import shutil
import sys

import pytest

from wherefrom import cli, gui, lookup
from wherefrom.zone import Mark

from conftest import FakeMarks, web_mark


def test_mark_is_read_and_remembered_for_copies(tmp_path, ledger):
    original = tmp_path / "Downloads" / "report.pdf"
    original.parent.mkdir()
    original.write_bytes(b"the report")
    marks = FakeMarks({"report.pdf": web_mark()})
    first = lookup.look_up(original, ledger, read_mark=marks)
    assert first.host_url == "https://example.com/files/report.pdf"

    # Copied to a USB stick and renamed: the mark is gone, the bytes are the same
    copy = tmp_path / "USB" / "Final version.pdf"
    copy.parent.mkdir()
    shutil.copyfile(original, copy)
    later = lookup.look_up(copy, ledger, read_mark=FakeMarks())
    assert later.known
    assert later.page_url == "https://example.com/reports"
    assert later.other_copies == [str(original)]


def test_mark_wins_over_older_records(tmp_path, ledger):
    f = tmp_path / "a.zip"
    f.write_bytes(b"a")
    ledger.add(lookup.file_hash(f)[0], 1, "/old/a.zip", host_url="https://old.test/a.zip")
    finding = lookup.look_up(f, ledger, read_mark=FakeMarks({"a.zip": Mark(3, "https://new.test/a.zip", None)}))
    assert finding.host_url == "https://new.test/a.zip"
    assert finding.page_url is None


def test_unknown_and_missing_files(tmp_path, ledger):
    f = tmp_path / "made-here.txt"
    f.write_text("x")
    finding = lookup.look_up(f, ledger, read_mark=FakeMarks())
    assert not finding.known
    assert "No record" in "\n".join(cli.describe(finding))
    assert lookup.look_up(tmp_path, ledger).error
    assert lookup.look_up(tmp_path / "gone.txt", ledger).error


def test_openable_only_web_links():
    assert lookup.openable("https://x.test/a")
    assert lookup.openable("HTTP://x.test/a")
    for url in (None, "", "file:///C:/Windows/System32/calc.exe", "javascript:alert(1)",
                "ms-settings:", "\\\\server\\share\\x.exe"):
        assert not lookup.openable(url)


def test_describe_lists_everything(tmp_path, ledger):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"a")
    sha = lookup.file_hash(f)[0]
    ledger.add(sha, 1, str(f), source="chrome", downloaded_at="2026-11-20T14:03:11",
               host_url="https://cdn.test/a.pdf", referrer_url="https://site.test/page")
    text = "\n".join(cli.describe(lookup.look_up(f, ledger, read_mark=FakeMarks())))
    assert "Downloaded from  https://cdn.test/a.pdf" in text
    assert "On the page      https://site.test/page" in text
    assert "2026-11-20 14:03" in text
    assert "Chrome's download history" in text


def test_gui_rows_match_the_text(tmp_path, ledger):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"a")
    finding = lookup.look_up(f, ledger, read_mark=FakeMarks({"a.pdf": web_mark()}))
    labels = [label for label, _ in gui.rows_for(finding)]
    assert labels[:2] == ["Downloaded from", "On the page"]
    assert gui.rows_for(lookup.look_up(tmp_path / "nope", ledger))[0][0] == ""


def test_main_show_and_search(tmp_path, capsys, monkeypatch):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"a")
    marks = FakeMarks({"a.pdf": web_mark()})
    monkeypatch.setattr(cli, "look_up", lambda p, ledger: lookup.look_up(p, ledger, read_mark=marks))
    assert cli.main(["show", str(f)]) == 0
    assert "example.com/files/report.pdf" in capsys.readouterr().out
    assert cli.main(["search", "EXAMPLE.com"]) == 0
    assert str(f) in capsys.readouterr().out
    assert cli.main(["search", "nothing-like-this"]) == 1
    assert cli.main(["show", str(tmp_path / "missing")]) == 1



def test_main_scan(tmp_path, capsys):
    (tmp_path / "x.txt").write_text("x")
    assert cli.main(["scan", "--folder", str(tmp_path)]) == 0
    assert "0 new file(s)" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows message")
def test_install_needs_windows():
    assert cli.main(["install"]) == 2


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert "wherefrom 0." in capsys.readouterr().out


def test_main_import_browsers(tmp_path, capsys, monkeypatch):
    from test_browsers import make_chromium_history
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    profile = tmp_path / "Local" / "Google" / "Chrome" / "User Data" / "Default"
    profile.mkdir(parents=True)
    make_chromium_history(profile / "History", [(str(f), ["https://dl.test/x.bin"], "", "", 1, 0)])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("WHEREFROM_HOME", str(tmp_path / "home"))
    assert cli.main(["import-browsers"]) == 0
    assert "chrome: 1 downloads in history, 1 new file(s) recorded (Default)" in capsys.readouterr().out
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty"))
    assert cli.main(["import-browsers"]) == 1


def test_main_watch_stops_on_ctrl_c(tmp_path, capsys, monkeypatch):
    def interrupted(self, interval):
        assert interval == 2.5
        raise KeyboardInterrupt
    monkeypatch.setattr(cli.Watcher, "run", interrupted)
    assert cli.main(["watch", "--folder", str(tmp_path), "--interval", "2.5"]) == 0
    assert "Watching " + str(tmp_path) in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32" or not __import__("os").environ.get("CI"),
                    reason="writes the real registry; only on a throwaway CI machine")
def test_main_install_and_uninstall(capsys):
    assert cli.main(["install", "--autostart"]) == 0
    assert "right-click menu" in capsys.readouterr().out
    assert cli.main(["uninstall"]) == 0


def test_gui_window_opens_and_closes(tmp_path, ledger, monkeypatch):
    tkinter = pytest.importorskip("tkinter")
    try:
        tkinter.Tk().destroy()
    except tkinter.TclError:
        pytest.skip("no display")
    opened = []

    def mainloop(self):
        self.update()
        opened.append(self.title())
        self.destroy()
    monkeypatch.setattr(tkinter.Tk, "mainloop", mainloop)
    f = tmp_path / "a.pdf"
    f.write_bytes(b"a")
    gui.show(lookup.look_up(f, ledger, read_mark=FakeMarks({"a.pdf": web_mark()})))
    gui.show(lookup.look_up(tmp_path / "missing.pdf", ledger))
    assert opened == ["Where did this come from?"] * 2
