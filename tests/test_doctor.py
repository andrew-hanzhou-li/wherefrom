"""`wherefrom doctor`: it reads the setup and says how to fix what's wrong."""
import io
import json
import sys

import pytest

from wherefrom import doctor, lock, native, shell
from wherefrom.ledger import Ledger


class FakeRegistry:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key, name):
        return self.values.get((key, name))


def report(**kwargs):
    out = io.StringIO()
    code = doctor.run(out=out, **kwargs)
    return code, out.getvalue()


def test_a_fresh_computer_gets_told_what_to_do(tmp_path):
    code, text = report(platform="win32", home=tmp_path / "home", data_home=tmp_path / "data", registry=FakeRegistry())
    assert code == 1
    assert "No database yet" in text and "No right-click entry" in text and "doesn't start at sign-in" in text
    assert 'wherefrom setup' in text
    assert "not connected" in text and "only needed with the extension" in text   # optional: not counted


def test_a_complete_windows_setup_is_fine(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    Ledger(data / "ledger.sqlite3").close()
    exe = tmp_path / "wherefromw.exe"
    exe.write_bytes(b"")
    launcher = tmp_path / "wherefrom-host.bat"
    launcher.write_text("@echo off")
    manifest = tmp_path / "host.json"
    manifest.write_text(json.dumps({"path": str(launcher)}))
    registry = FakeRegistry({
        (shell.MENU_KEY + r"\command", ""): f'"{exe}" show --gui -- "%1"',
        (shell.RUN_KEY, shell.RUN_VALUE): f'"{exe}" watch',
        (native.WINDOWS_KEYS["chromium"][0] + "\\" + native.HOST_NAME, ""): str(manifest),
        (native.WINDOWS_KEYS["firefox"][0] + "\\" + native.HOST_NAME, ""): str(manifest),
    })
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(doctor, "downloads_folder", lambda: downloads)
    held = lock.hold(lock.watch_lock(data, [downloads]))      # a watcher is running
    try:
        code, text = report(platform="win32", home=tmp_path / "home", data_home=data, registry=registry)
    finally:
        held.close()
    assert code == 0, text
    assert "Everything looks fine." in text
    assert "The watcher is running" in text and "Database: 0 file(s)" in text


def test_a_moved_program_and_a_broken_connection_are_caught(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    Ledger(data / "ledger.sqlite3").close()
    registry = FakeRegistry({
        (shell.MENU_KEY + r"\command", ""): f'"{tmp_path / "gone" / "wherefromw.exe"}" show --gui -- "%1"',
        (shell.RUN_KEY, shell.RUN_VALUE): "x",
        (native.WINDOWS_KEYS["chromium"][0] + "\\" + native.HOST_NAME, ""): str(tmp_path / "missing.json"),
    })
    monkeypatch.setattr(doctor, "downloads_folder", lambda: tmp_path)
    code, text = report(platform="win32", home=tmp_path, data_home=data, registry=registry)
    assert code == 1
    assert "points to a program that's gone" in text
    assert "is damaged" in text
    assert "watcher isn't running" in text


@pytest.mark.skipif(sys.platform == "win32", reason="the Nautilus script's name has a '?', which Windows can't store")
def test_linux_setup_files_are_checked(tmp_path, monkeypatch):
    home, data = tmp_path / "home", tmp_path / "data"
    (home / ".config" / "chromium").mkdir(parents=True)
    from wherefrom import desktop
    desktop.install("linux", home, autostart=True, cmd=[sys.executable, "-m", "wherefrom"])
    native.setup("linux", home, data, cmd=[sys.executable, "-m", "wherefrom", "native-host"])
    data.mkdir(exist_ok=True)
    Ledger(data / "ledger.sqlite3").close()
    monkeypatch.setattr(doctor, "downloads_folder", lambda: tmp_path)
    code, text = report(platform="linux", home=home, data_home=data)
    assert "Right-click entry for GNOME Files and KDE Dolphin" in text
    assert "The watcher starts at sign-in" in text
    assert "Browser extension connected for Chrome-based browsers" in text
    assert code == 1 and "watcher isn't running" in text           # the only thing left


def test_odd_registry_values_dont_crash_it(tmp_path, monkeypatch):
    assert doctor.program_in(r'"C:\Program Files\w\wherefromw.exe" show --gui -- "%1"') == r"C:\Program Files\w\wherefromw.exe"
    assert doctor.program_in(r"C:\Program Files\w\wherefromw.exe show --gui") == r"C:\Program Files\w\wherefromw.exe"
    assert doctor.program_in("/usr/bin/wherefrom watch") == "/usr/bin/wherefrom"
    for odd in (None, "", "   ", '"', 5, b"bytes"):
        assert doctor.program_in(odd) is None, odd
    data = tmp_path / "data"
    data.mkdir()
    registry = FakeRegistry({(shell.MENU_KEY + r"\command", ""): 5, (shell.RUN_KEY, shell.RUN_VALUE): "   ",
                             (native.WINDOWS_KEYS["chromium"][0] + "\\" + native.HOST_NAME, ""): 7})
    monkeypatch.setattr(doctor, "downloads_folder", lambda: tmp_path)
    code, text = report(platform="win32", home=tmp_path, data_home=data, registry=registry)
    assert code == 1 and "No right-click entry" in text and "doesn't start at sign-in" in text


def test_the_command_changes_nothing(tmp_path, monkeypatch, capsys):
    from wherefrom import cli
    home = tmp_path / "fresh"
    monkeypatch.setenv("WHEREFROM_HOME", str(home))
    monkeypatch.setattr(doctor, "downloads_folder", lambda: tmp_path)
    monkeypatch.setattr(shell, "WindowsRegistry", lambda: FakeRegistry())
    assert cli.main(["doctor"]) == 1
    assert "No database yet" in capsys.readouterr().out
    assert not home.exists()                    # no database, no folder, no lock file


def test_checking_the_lock_leaves_it_as_it_was(tmp_path):
    path = lock.watch_lock(tmp_path, [tmp_path / "Downloads"])
    assert lock.is_held(path) is False          # no file: nothing created
    assert not path.exists()
    held = lock.hold(path)
    assert lock.is_held(path) is True and lock.any_watcher(tmp_path) is True
    held.close()
    before = path.read_bytes()                  # (Windows locks block reading while held)
    assert before                               # the watcher's own note: its process id
    assert lock.is_held(path) is False and lock.any_watcher(tmp_path) is False
    assert path.read_bytes() == before          # the probe wrote nothing
