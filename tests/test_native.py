import io
import json
import os
import struct
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from wherefrom import native
from wherefrom.watch import file_hash

from test_shell import FakeRegistry


def framed(*messages):
    out = b""
    for m in messages:
        data = json.dumps(m).encode()
        out += struct.pack("=I", len(data)) + data
    return out


def replies(raw):
    stream, found = io.BytesIO(raw), []
    while True:
        message = native.read_message(stream)
        if message is None:
            return found
        found.append(message)


def download(file, **changes):
    message = {"type": "download", "path": str(file), "url": "https://cdn.test/f.zip",
               "original_url": "https://short.test/r", "referrer": "https://site.test/page",
               "mime": "application/zip", "size": 3, "ended": "2026-11-20T22:03:11.123Z"}
    message.update(changes)
    return message


def test_a_download_is_recorded(tmp_path, ledger):
    f = tmp_path / "f.zip"
    f.write_bytes(b"zip")
    out = io.BytesIO()
    assert native.serve(io.BytesIO(framed(download(f), download(f))), out, ledger) == 0
    assert replies(out.getvalue()) == [{"ok": True, "new": True}, {"ok": True, "new": False}]
    [record] = ledger.by_hash(file_hash(f)[0])
    assert (record.source, record.host_url, record.original_url, record.referrer_url, record.mime) == \
        ("extension", "https://cdn.test/f.zip", "https://short.test/r", "https://site.test/page", "application/zip")
    local = datetime(2026, 11, 20, 22, 3, 11, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert record.downloaded_at == local.isoformat(timespec="seconds")


def test_bad_messages_are_refused(tmp_path, ledger):
    f = tmp_path / "f.zip"
    f.write_bytes(b"zip")
    cases = {
        "unknown message": [{"type": "something"}, "not a dict", None],
        "no full path": [download("relative/f.zip"), download(f, path=None), download(f, path=123),
                         download(f, path="x" * 9000)],
        "no source": [download(f, url=None, referrer=None), download(f, url="", referrer=["list"])],
        "file not found": [download(tmp_path / "missing.zip"), download(tmp_path)],
    }
    for expected, messages in cases.items():
        for message in messages:
            assert native.handle(message, ledger) == {"ok": False, "error": expected}, message
    assert ledger.count() == 0


def test_text_fields_are_checked(tmp_path, ledger):
    f = tmp_path / "f.zip"
    f.write_bytes(b"zip")
    native.handle(download(f, mime={"not": "text"}, original_url="a\x00b", ended="yesterday"), ledger)
    [record] = ledger.all_records()
    assert (record.mime, record.original_url, record.downloaded_at) == (None, None, None)


def test_oversized_or_broken_input_ends_politely(ledger):
    out = io.BytesIO()
    assert native.serve(io.BytesIO(struct.pack("=I", native.MAX_MESSAGE + 1) + b"x"), out, ledger) == 1
    assert replies(out.getvalue())[0]["ok"] is False
    out = io.BytesIO()
    assert native.serve(io.BytesIO(struct.pack("=I", 3) + b"\xff\xfe\xfd"), out, ledger) == 1
    out = io.BytesIO()
    assert native.serve(io.BytesIO(b"\x01\x00"), out, ledger) == 0          # cut off: just stop
    assert out.getvalue() == b""


def test_host_manifests():
    chromium = native.host_manifest("chromium", "/x/wherefrom-host", extra_ids=["abcdefghijklmnopabcdefghijklmnop"])
    assert chromium["name"] == native.HOST_NAME and chromium["type"] == "stdio"
    assert chromium["allowed_origins"] == [f"chrome-extension://{native.CHROMIUM_ID}/",
                                           "chrome-extension://abcdefghijklmnopabcdefghijklmnop/"]
    assert native.host_manifest("firefox", "/x/h")["allowed_extensions"] == [native.FIREFOX_ID]


def test_the_extension_id_matches_its_key():
    import base64
    import hashlib
    from importlib import resources
    manifest = json.loads((resources.files("wherefrom") / "extension" / "manifest_chromium.json").read_text())
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(c, 16)) for c in digest) == native.CHROMIUM_ID
    firefox = json.loads((resources.files("wherefrom") / "extension" / "manifest_firefox.json").read_text())
    assert firefox["browser_specific_settings"]["gecko"]["id"] == native.FIREFOX_ID


def test_linux_setup_and_remove(tmp_path):
    home = tmp_path / "home"
    (home / ".config" / "google-chrome").mkdir(parents=True)        # Chrome is installed
    (home / ".mozilla").mkdir()                                       # and Firefox
    data = tmp_path / "data"
    summary = native.setup("linux", home, data, cmd=["/usr/bin/python3", "-P", "-m", "wherefrom", "native-host"])
    chrome_manifest = home / ".config" / "google-chrome" / "NativeMessagingHosts" / f"{native.HOST_NAME}.json"
    firefox_manifest = home / ".mozilla" / "native-messaging-hosts" / f"{native.HOST_NAME}.json"
    assert sorted(summary["registered"]) == sorted([str(chrome_manifest), str(firefox_manifest)])
    assert not (home / ".config" / "chromium").exists()               # not installed: left alone
    assert json.loads(chrome_manifest.read_text())["path"] == str(summary["launcher"])
    assert (summary["extensions"]["chromium"] / "manifest.json").is_file()
    assert (summary["extensions"]["firefox"] / "background.js").is_file()
    # Every file a manifest names is there, or the browser refuses to load it
    for kind in ("chromium", "firefox"):
        folder = summary["extensions"][kind]
        manifest = json.loads((folder / "manifest.json").read_text())
        for name in [*manifest["icons"].values(), *manifest["background"].get("scripts", []),
                     manifest["background"].get("service_worker", "background.js")]:
            assert (folder / name).is_file(), (kind, name)
    removed = native.remove("linux", home, data)
    assert str(chrome_manifest) in removed and not chrome_manifest.exists() and not (data / "browser").exists()


def test_mac_setup(tmp_path):
    home = tmp_path / "home"
    (home / "Library" / "Application Support" / "Microsoft Edge").mkdir(parents=True)
    summary = native.setup("darwin", home, tmp_path / "data", cmd=["/usr/bin/python3"])
    assert summary["registered"] == [str(home / "Library" / "Application Support" / "Microsoft Edge" /
                                         "NativeMessagingHosts" / f"{native.HOST_NAME}.json")]


def test_windows_setup_with_a_fake_registry(tmp_path):
    reg = FakeRegistry()
    summary = native.setup("win32", tmp_path, tmp_path / "data", registry=reg, env={},
                           cmd=["C:\\Program Files\\Python\\python.exe", "-P", "-m", "wherefrom", "native-host"])
    key = native.WINDOWS_KEYS["chromium"][0] + "\\" + native.HOST_NAME
    assert reg.values[(key, "")] == str(summary["manifests"]["chromium"])
    assert reg.values[(native.WINDOWS_KEYS["firefox"][0] + "\\" + native.HOST_NAME, "")] == str(summary["manifests"]["firefox"])
    bat = summary["launcher"].read_bytes()            # bytes: the \r\n must be exact
    assert bat == (b'@echo off\r\n"C:\\Program Files\\Python\\python.exe" "-P" "-m" "wherefrom" "native-host" %*\r\n')
    native.remove("win32", tmp_path, tmp_path / "data", registry=reg)
    assert reg.values == {}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher")
def test_the_launcher_runs_the_host_with_the_browsers_arguments(tmp_path):
    folder = tmp_path / "browser"
    launcher = native.write_launcher(folder, sys.platform, cmd=[sys.executable, "-c",
                                     "import sys; print(sys.argv[1:])"])
    out = subprocess.run([str(launcher), "chrome-extension://abc/", "--parent-window=0"],
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == "['chrome-extension://abc/', '--parent-window=0']"


def test_the_real_command_speaks_the_protocol(tmp_path):
    # The whole path the browser uses: start "python -P -m wherefrom native-host",
    # send a framed message, read the framed reply.
    f = tmp_path / "f.zip"
    f.write_bytes(b"zip")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONPATH": repo, "WHEREFROM_HOME": str(tmp_path / "home")}
    result = subprocess.run([sys.executable, "-P", "-m", "wherefrom", "native-host", "chrome-extension://x/"],
                            input=framed(download(f)), capture_output=True, env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert replies(result.stdout) == [{"ok": True, "new": True}]


def test_bat_launcher_keeps_odd_paths_literal(tmp_path):
    bat = native.write_launcher(tmp_path, "win32", cmd=["C:\\Users\\Tom&Jerry\\100%PATH%\\python.exe", "-P"],
                                env={"WHEREFROM_HOME": "D:\\50% done"})
    text = bat.read_bytes().decode()
    assert '"C:\\Users\\Tom&Jerry\\100%%PATH%%\\python.exe" "-P" %*' in text       # & quoted, % doubled
    assert 'set "WHEREFROM_HOME=D:\\50%% done"' in text
    with pytest.raises(ValueError):
        native.bat_quote('a"b')


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher")
def test_the_launcher_carries_wherefrom_home(tmp_path):
    launcher = native.write_launcher(tmp_path, sys.platform, env={"WHEREFROM_HOME": "/data/my ledger"},
                                     cmd=[sys.executable, "-c", "import os; print(os.environ['WHEREFROM_HOME'])"])
    out = subprocess.run([str(launcher)], capture_output=True, text=True, check=True, env={"PATH": os.environ["PATH"]})
    assert out.stdout.strip() == "/data/my ledger"


def test_remove_leaves_other_files_alone(tmp_path):
    home, data = tmp_path / "home", tmp_path / "data"
    (home / ".config" / "google-chrome").mkdir(parents=True)
    native.setup("linux", home, data, cmd=["/usr/bin/python3"], env={})
    mine = data / "browser" / "notes.txt"
    mine.write_text("not wherefrom's")
    native.remove("linux", home, data)
    assert mine.read_text() == "not wherefrom's"
    assert sorted(p.name for p in (data / "browser").iterdir()) == ["notes.txt"]


def test_firefox_on_mac_is_found_by_its_profile_folder(tmp_path):
    home = tmp_path / "home"
    (home / "Library" / "Application Support" / "Firefox").mkdir(parents=True)     # no Mozilla folder yet
    summary = native.setup("darwin", home, tmp_path / "data", cmd=["/usr/bin/python3"], env={})
    expected = home / "Library" / "Application Support" / "Mozilla" / "NativeMessagingHosts" / f"{native.HOST_NAME}.json"
    assert summary["registered"] == [str(expected)] and expected.is_file()
