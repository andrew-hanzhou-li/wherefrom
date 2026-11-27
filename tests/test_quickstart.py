"""`wherefrom setup` and the watcher's single-instance lock."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from wherefrom import cli, desktop, lock, quickstart


def test_runs_every_step_and_reports_failures(ledger, capsys):
    ran = []

    def ok(name):
        return lambda: ran.append(name) or f"{name} done"

    def broken():
        ran.append("extension")
        raise OSError("no registry")

    steps = [("menu", ok("menu")), ("extension", broken), ("history", ok("history")), ("watcher", ok("watcher"))]
    assert quickstart.run(ledger, steps=steps) == 1
    assert ran == ["menu", "extension", "history", "watcher"]           # carried on after the failure
    out = capsys.readouterr().out
    assert "FAILED (extension): no registry" in out and "1 step(s) failed" in out


def test_skips_history_and_watcher_when_asked(ledger, capsys):
    ran = []
    steps = [(name, (lambda n=name: ran.append(n) or n)) for name in ("menu", "extension", "history", "watcher")]
    assert quickstart.run(ledger, do_import=False, do_start=False, steps=steps) == 0
    assert ran == ["menu", "extension"]
    assert "Done." in capsys.readouterr().out


def test_no_browser_history_is_not_a_failure(ledger, monkeypatch):
    monkeypatch.setattr(quickstart.browsers, "import_all", lambda ledger: [])
    history = dict(quickstart.default_steps(ledger))["history"]
    assert "no Chrome" in history()


def test_watcher_command_prefers_the_windowless_program(tmp_path, monkeypatch):
    exe = tmp_path / "wherefrom.exe"
    exe.write_bytes(b"")
    (tmp_path / "wherefromw.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "platform", "win32")
    assert quickstart.watcher_command() == [str(tmp_path / "wherefromw.exe"), "watch"]
    (tmp_path / "wherefromw.exe").unlink()                             # only the console one: use it
    assert quickstart.watcher_command() == [str(exe), "watch"]


def test_start_watcher_on_macos_goes_through_launchd(tmp_path):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    quickstart.start_watcher("darwin", tmp_path, run=run)
    plist = desktop.mac_files(tmp_path)["autostart"]
    assert calls[0][:2] == ["launchctl", "bootstrap"] and calls[0][-1] == str(plist)

    def refused(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "Bootstrap failed: 1: Operation not permitted")

    with pytest.raises(OSError, match="not permitted"):
        quickstart.start_watcher("darwin", tmp_path, run=refused)


def test_start_watcher_on_linux_detaches(tmp_path):
    started = []
    quickstart.start_watcher("linux", tmp_path, popen=lambda cmd, **kw: started.append((cmd, kw)))
    cmd, kwargs = started[0]
    assert cmd[-1] == "watch" and kwargs["start_new_session"] is True
    assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process flags")
def test_start_watcher_on_windows_detaches(tmp_path):
    started = []
    quickstart.start_watcher("win32", tmp_path, popen=lambda cmd, **kw: started.append((cmd, kw)))
    cmd, kwargs = started[0]
    assert cmd[-1] == "watch" and kwargs["creationflags"] & subprocess.DETACHED_PROCESS


def test_the_lock_is_held_by_one_holder_at_a_time(tmp_path):
    path = tmp_path / "locks" / "x.lock"
    first = lock.hold(path)
    assert first is not None
    assert lock.hold(path) is None                                      # same process, second try
    other = subprocess.run([sys.executable, "-c",
                            "import sys; sys.path.insert(0, sys.argv[2]); from pathlib import Path;"
                            "from wherefrom import lock; print(lock.hold(Path(sys.argv[1])) is None)",
                            str(path), str(Path(__file__).resolve().parent.parent)],
                           capture_output=True, text=True, check=True)
    assert other.stdout.strip() == "True"                               # another process
    first.close()
    again = lock.hold(path)                                             # free once released
    assert again is not None
    again.close()


def test_a_second_watcher_for_the_same_folders_exits_at_once(tmp_path, capsys):
    watched = tmp_path / "Downloads"
    watched.mkdir()
    root = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": root}
    proc = subprocess.Popen([sys.executable, "-u", "-P", "-m", "wherefrom", "watch", "--folder", str(watched),
                             "--interval", "0.2"], env=env, stdout=subprocess.PIPE, text=True)
    try:
        assert "Watching" in proc.stdout.readline()                    # the first one holds the lock
        assert cli.main(["watch", "--folder", str(watched)]) == 0      # returns instead of watching
        assert "already running" in capsys.readouterr().out
    finally:
        proc.terminate()
        proc.wait(timeout=10)
