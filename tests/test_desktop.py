import os
import plistlib
import shlex
import subprocess
import sys

import pytest

from wherefrom import cli, desktop
from wherefrom.watch import downloads_folder

CMD = ["/opt/My Python/bin/python3", "-P", "-m", "wherefrom"]


LINUX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the Nautilus script's name has a '?', which Windows can't store")


@LINUX_ONLY
def test_linux_install_and_uninstall(tmp_path):
    written = desktop.install("linux", tmp_path, autostart=True, cmd=CMD, env={})
    files = desktop.linux_files(tmp_path, tmp_path / ".config", tmp_path / ".local" / "share")
    assert sorted(written) == sorted(files.values())
    script = files["nautilus"].read_text()
    assert script.startswith("#!/bin/sh") and os.access(files["nautilus"], os.X_OK)
    assert "'/opt/My Python/bin/python3' -P -m wherefrom show --gui -- \"$f\"" in script
    menu = files["dolphin"].read_text()
    assert 'Exec="/opt/My Python/bin/python3" -P -m wherefrom show --gui -- %f' in menu
    assert "Name=Where did this come from?" in menu
    assert 'Exec="/opt/My Python/bin/python3" -P -m wherefrom watch' in files["autostart"].read_text()
    assert sorted(desktop.uninstall("linux", tmp_path)) == sorted(files.values())
    assert not any(p.exists() for p in files.values())


def test_uninstall_leaves_files_it_did_not_write(tmp_path):
    files = desktop.linux_files(tmp_path, tmp_path / ".config", tmp_path / ".local" / "share")
    files["autostart"].parent.mkdir(parents=True)
    files["autostart"].write_text("[Desktop Entry]\nName=someone else's wherefrom.desktop\n")
    assert desktop.uninstall("linux", tmp_path) == []
    assert files["autostart"].exists()


@LINUX_ONLY
def test_autostart_only_when_asked(tmp_path):
    desktop.install("linux", tmp_path, autostart=False, cmd=CMD)
    files = desktop.linux_files(tmp_path, tmp_path / ".config", tmp_path / ".local" / "share")
    assert files["nautilus"].exists() and not files["autostart"].exists()


def test_mac_launch_agent(tmp_path):
    [agent] = desktop.install("darwin", tmp_path, autostart=True, cmd=CMD)
    data = plistlib.loads(agent.read_bytes())
    assert data["ProgramArguments"] == CMD + ["watch"] and data["RunAtLoad"] is True
    assert desktop.install("darwin", tmp_path, autostart=False, cmd=CMD) == []   # no menu on macOS
    ran = []
    assert desktop.uninstall("darwin", tmp_path, run=lambda args, **kw: ran.append(args)) == [agent]
    assert ran[0][:2] == ["launchctl", "bootout"] and ran[0][-1] == str(agent)   # stop the running one


def test_desktop_exec_quoting():
    assert desktop.desktop_exec(["/usr/bin/python3", "-P", "%f"]) == "/usr/bin/python3 -P %f"
    # Inside quotes: \" ` $ \\ get a backslash; then every backslash is doubled
    # again for the .desktop string layer, so one literal backslash is four
    assert desktop.desktop_exec(['/a b/$x"y`z\\w']) == '"/a b/\\\\$x\\\\"y\\\\`z\\\\\\\\w"'
    assert desktop.desktop_exec(["/opt/50%fun/py", "%f"]) == "/opt/50%%fun/py %f"
    with pytest.raises(ValueError):
        desktop.desktop_exec(["/a\nInjected=1"])


@pytest.mark.skipif(sys.platform == "win32", reason="runs a POSIX shell")
def test_the_nautilus_script_passes_odd_names_safely(tmp_path):
    # Run the generated script with a stand-in for python that records its arguments
    record = tmp_path / "args.txt"
    fake = tmp_path / "fake python"
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {shlex.quote(str(record))}\n")
    fake.chmod(0o755)
    desktop.install("linux", tmp_path, cmd=[str(fake), "-P", "-m", "wherefrom"])
    script = desktop.linux_files(tmp_path, tmp_path / ".config", tmp_path / ".local" / "share")["nautilus"]
    odd = "a file; rm -rf ~ $(echo x) `id`.pdf"
    subprocess.run([str(script), odd], check=True)
    import time
    for _ in range(50):
        if record.exists() and odd in record.read_text():
            break
        time.sleep(0.05)
    assert record.read_text().splitlines()[-1] == odd       # one argument, nothing run


def test_downloads_folder(tmp_path):
    config = tmp_path / ".config"
    config.mkdir()
    (config / "user-dirs.dirs").write_text('XDG_DESKTOP_DIR="$HOME/Desktop"\nXDG_DOWNLOAD_DIR="$HOME/Téléchargements"\n',
                                           encoding="utf-8")
    assert downloads_folder("linux", tmp_path, config) == tmp_path / "Téléchargements"
    assert downloads_folder("linux", tmp_path, tmp_path / "none") == tmp_path / "Downloads"
    assert downloads_folder("darwin", tmp_path) == tmp_path / "Downloads"


@pytest.mark.skipif(sys.platform == "win32", reason="the Windows entry is tested in test_shell")
def test_cli_install_and_uninstall(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(desktop.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    assert cli.main(["install", "--autostart"]) == 0
    out = capsys.readouterr().out
    assert "Wrote" in out and "start when you sign in" in out
    assert cli.main(["uninstall"]) == 0
    assert "Removed" in capsys.readouterr().out


def test_xdg_config_home_is_followed(tmp_path, monkeypatch):
    # GitHub's Linux machines (and some desktops) move ~/.config; Chrome follows it
    from wherefrom import browsers, native
    custom = tmp_path / "elsewhere"
    (custom / "google-chrome" / "Default").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom))
    assert browsers.linux_path(tmp_path, ".config/google-chrome") == custom / "google-chrome"
    assert browsers.linux_path(tmp_path, ".mozilla/firefox") == tmp_path / ".mozilla" / "firefox"
    summary = native.setup("linux", tmp_path, tmp_path / "data", cmd=["/usr/bin/python3"])
    assert summary["registered"] == [str(custom / "google-chrome" / "NativeMessagingHosts" / f"{native.HOST_NAME}.json")]


@LINUX_ONLY
def test_wherefrom_home_reaches_what_the_entries_start(tmp_path):
    env = {"WHEREFROM_HOME": "/data/my ledger"}
    desktop.install("linux", tmp_path, autostart=True, cmd=CMD, env=env)
    files = desktop.linux_files(tmp_path, tmp_path / ".config", tmp_path / ".local" / "share")
    assert "export WHEREFROM_HOME='/data/my ledger'" in files["nautilus"].read_text()
    assert 'Exec=env "WHEREFROM_HOME=/data/my ledger" "/opt/My Python/bin/python3"' in files["autostart"].read_text()
    [agent] = desktop.install("darwin", tmp_path, autostart=True, cmd=CMD, env=env)
    assert plistlib.loads(agent.read_bytes())["EnvironmentVariables"] == env


@LINUX_ONLY
def test_a_file_named_like_an_option_is_still_a_file(tmp_path):
    record = tmp_path / "args.txt"
    fake = tmp_path / "fake python"
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {shlex.quote(str(record))}\n")
    fake.chmod(0o755)
    desktop.install("linux", tmp_path, cmd=[str(fake)], env={})
    script = desktop.linux_files(tmp_path, tmp_path / ".config", tmp_path / ".local" / "share")["nautilus"]
    subprocess.run([str(script), "-x.pdf"], check=True)
    import time
    for _ in range(50):
        if record.exists() and "-x.pdf" in record.read_text():
            break
        time.sleep(0.05)
    assert record.read_text().splitlines()[-2:] == ["--", "-x.pdf"]
