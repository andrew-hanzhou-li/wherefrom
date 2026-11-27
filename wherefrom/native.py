"""The browser extension's partner: a native messaging host, and its setup.

Browsers start the host program when the extension sends a message and talk
to it over stdin/stdout: each message is a 4-byte length (native byte order)
followed by that much UTF-8 JSON. The browser only lets the extension IDs
listed in the host's manifest connect.

Setup writes, per system:
- the host manifest(s) and a small launcher next to the ledger;
- where each browser looks for them (registry keys on Windows, files on
  macOS and Linux);
- the unpacked extension, ready for "Load unpacked" (Chromium browsers) or
  "Load Temporary Add-on" (Firefox).
"""

import json
import os
import shlex
import shutil
import struct
import sys
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from .ledger import Ledger, default_home
from .watch import file_hash

HOST_NAME = "com.wherefrom.host"
CHROMIUM_ID = "oihchieldoakdhphjlofnphcpmmiooka"       # fixed by the manifest's public key
FIREFOX_ID = "wherefrom@andrew-hanzhou-li.github.io"
MAX_MESSAGE = 1024 * 1024
MAX_TEXT = 8192

# Where Chromium browsers look for host manifests, per system
WINDOWS_KEYS = {
    "chromium": [r"Software\Google\Chrome\NativeMessagingHosts", r"Software\Microsoft\Edge\NativeMessagingHosts",
                 r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
                 r"Software\Chromium\NativeMessagingHosts"],
    "firefox": [r"Software\Mozilla\NativeMessagingHosts"],
}
MAC_DIRS = {
    "chromium": ["Google/Chrome", "Microsoft Edge", "BraveSoftware/Brave-Browser", "Chromium", "Vivaldi"],
    "firefox": ["Mozilla"],
}
LINUX_DIRS = {
    "chromium": [".config/google-chrome", ".config/microsoft-edge", ".config/BraveSoftware/Brave-Browser",
                 ".config/chromium", ".config/vivaldi"],
    "firefox": [".mozilla"],
}


# ---------------- The host ----------------

def read_message(stream):
    """One message from the browser, or None at the end of input."""
    header = stream.read(4)
    if len(header) < 4:
        return None
    length = struct.unpack("=I", header)[0]
    if length > MAX_MESSAGE:
        raise ValueError(f"message of {length} bytes is too big")
    data = stream.read(length)
    if len(data) < length:
        return None
    return json.loads(data.decode("utf-8"))


def write_message(stream, message):
    data = json.dumps(message).encode("utf-8")
    stream.write(struct.pack("=I", len(data)) + data)
    stream.flush()


def text(value):
    """A string field from the extension, or None if it isn't a sane one."""
    if isinstance(value, str) and 0 < len(value) <= MAX_TEXT and "\x00" not in value:
        return value
    return None


def browser_time(value):
    """The extension's ISO time (UTC, "Z") as local time without a zone, like
    the rest of the ledger."""
    value = text(value)
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


def handle(message, ledger):
    """Record one finished download. Returns the reply for the extension."""
    if not isinstance(message, dict) or message.get("type") != "download":
        return {"ok": False, "error": "unknown message"}
    path = text(message.get("path"))
    url = text(message.get("url"))
    referrer = text(message.get("referrer"))
    if not path or not os.path.isabs(path):
        return {"ok": False, "error": "no full path"}
    if not (url or referrer):
        return {"ok": False, "error": "no source"}
    if not os.path.isfile(path):
        return {"ok": False, "error": "file not found"}
    try:
        sha256, size = file_hash(path)
    except OSError as error:
        return {"ok": False, "error": f"can't read the file: {error.strerror or error}"}
    new = ledger.add(sha256, size, path, source="extension", host_url=url, referrer_url=referrer,
                     mime=text(message.get("mime")), original_url=text(message.get("original_url")),
                     downloaded_at=browser_time(message.get("ended")))
    return {"ok": True, "new": new}


def serve(stdin=None, stdout=None, ledger=None):
    """Answer messages until the browser closes the connection."""
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    own = ledger is None
    ledger = ledger or Ledger()
    try:
        while True:
            try:
                message = read_message(stdin)
            except (ValueError, UnicodeDecodeError) as error:
                write_message(stdout, {"ok": False, "error": str(error)})
                return 1
            if message is None:
                return 0
            write_message(stdout, handle(message, ledger))
    finally:
        if own:
            ledger.close()


# ---------------- Setup ----------------

def launcher_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "native-host"]
    return [sys.executable, "-P", "-m", "wherefrom", "native-host"]


def write_launcher(folder, platform, cmd=None):
    """Host manifests can't pass arguments, so they point at this script."""
    cmd = cmd or launcher_command()
    folder.mkdir(parents=True, exist_ok=True)
    if platform == "win32":
        path = folder / "wherefrom-host.bat"
        quoted = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        # newline="": write the \r\n as given (text mode on Windows would
        # turn each \n into \r\n again, giving \r\r\n)
        path.write_text(f"@echo off\r\n{quoted} %*\r\n", encoding="utf-8", newline="")
    else:
        path = folder / "wherefrom-host"
        path.write_text("#!/bin/sh\nexec " + " ".join(shlex.quote(c) for c in cmd) + ' "$@"\n', encoding="utf-8")
        path.chmod(0o755)
    return path


def host_manifest(kind, launcher, extra_ids=()):
    manifest = {"name": HOST_NAME, "description": "wherefrom: records where downloads came from",
                "path": str(launcher), "type": "stdio"}
    if kind == "firefox":
        manifest["allowed_extensions"] = [FIREFOX_ID]
    else:
        manifest["allowed_origins"] = [f"chrome-extension://{i}/" for i in (CHROMIUM_ID, *extra_ids)]
    return manifest


def copy_extension(target, kind):
    """The unpacked extension for one browser family, ready to load."""
    target.mkdir(parents=True, exist_ok=True)
    package = resources.files("wherefrom") / "extension"
    (target / "background.js").write_bytes((package / "background.js").read_bytes())
    (target / "manifest.json").write_bytes((package / f"manifest_{kind}.json").read_bytes())
    return target


def manifest_dirs(platform, home):
    if platform == "darwin":
        support = Path(home) / "Library" / "Application Support"
        return {kind: [support / d / "NativeMessagingHosts" for d in dirs] for kind, dirs in MAC_DIRS.items()}
    linux = {kind: [Path(home) / d / "NativeMessagingHosts" for d in dirs] for kind, dirs in LINUX_DIRS.items()}
    linux["firefox"] = [Path(home) / ".mozilla" / "native-messaging-hosts"]
    return linux


def setup(platform=None, home=None, data_home=None, registry=None, extra_ids=(), cmd=None):
    """Register the host and write the extension folders. Returns a summary
    dict: launcher, manifests, registered places, extension folders."""
    platform = platform or sys.platform
    home = Path(home or Path.home())
    data_home = Path(data_home or default_home())
    folder = data_home / "browser"
    launcher = write_launcher(folder, platform, cmd)
    summary = {"launcher": launcher, "manifests": {}, "registered": [], "extensions": {}}
    for kind in ("chromium", "firefox"):
        manifest_path = folder / f"{HOST_NAME}.{kind}.json"
        manifest_path.write_text(json.dumps(host_manifest(kind, launcher, extra_ids), indent=2), encoding="utf-8")
        summary["manifests"][kind] = manifest_path
        summary["extensions"][kind] = copy_extension(folder / f"extension-{kind}", kind)
        if platform == "win32":
            registry = registry or _windows_registry()
            for key in WINDOWS_KEYS[kind]:
                registry.set_value(f"{key}\\{HOST_NAME}", "", str(manifest_path))
                summary["registered"].append(f"HKCU\\{key}\\{HOST_NAME}")
        else:
            for directory in manifest_dirs(platform, home)[kind]:
                # Only where that browser is installed (its folder exists)
                if not directory.parent.is_dir():
                    continue
                directory.mkdir(exist_ok=True)
                target = directory / f"{HOST_NAME}.json"
                shutil.copyfile(manifest_path, target)
                summary["registered"].append(str(target))
    return summary


def remove(platform=None, home=None, data_home=None, registry=None):
    """Undo setup. Returns what was removed."""
    platform = platform or sys.platform
    home = Path(home or Path.home())
    data_home = Path(data_home or default_home())
    removed = []
    if platform == "win32":
        registry = registry or _windows_registry()
        for keys in WINDOWS_KEYS.values():
            for key in keys:
                if registry.get_value(f"{key}\\{HOST_NAME}", ""):
                    registry.delete_key(f"{key}\\{HOST_NAME}")
                    removed.append(f"HKCU\\{key}\\{HOST_NAME}")
    else:
        for directories in manifest_dirs(platform, home).values():
            for directory in directories:
                target = directory / f"{HOST_NAME}.json"
                try:
                    if json.loads(target.read_text(encoding="utf-8")).get("name") == HOST_NAME:
                        target.unlink()
                        removed.append(str(target))
                except (OSError, ValueError):
                    pass
    folder = data_home / "browser"
    if folder.is_dir():
        shutil.rmtree(folder)
        removed.append(str(folder))
    return removed


def _windows_registry():
    from .shell import WindowsRegistry
    return WindowsRegistry()
