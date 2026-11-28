"""`wherefrom doctor`: check every part of the setup and say how to fix what
isn't right. It only reads: it creates and changes nothing (the ledger isn't
even opened for writing, and the watcher's lock is only probed).

Each check is (ok, what, fix): `fix` is shown only when `ok` is False.
`ok` is None for something that's only information (not a problem).
"""

import json
import sys
from pathlib import Path

from . import __version__, browsers, desktop, lock, native, shell
from .ledger import default_home
from .watch import downloads_folder

SETUP = 'Run "wherefrom setup" to fix it.'


def check_database(data_home):
    path = Path(data_home) / "ledger.sqlite3"
    if not path.is_file():
        return [(False, f"No database yet at {path}", SETUP)]
    import sqlite3
    try:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            count = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        finally:
            db.close()
    except sqlite3.Error as error:
        return [(False, f"The database at {path} can't be read: {error}",
                 "Close other programs using it and try again. If it keeps failing, move the file "
                 "away (wherefrom starts a new one) and run \"wherefrom import-browsers\".")]
    return [(True, f"Database: {count} file(s) recorded ({path})", "")]


def check_watcher(data_home):
    folder = downloads_folder()
    if lock.is_held(lock.watch_lock(data_home, [folder])):
        return [(True, f"The watcher is running (watching {folder})", "")]
    if lock.any_watcher(data_home):
        return [(True, "A watcher is running (for other folders than Downloads)", "")]
    return [(False, f"The watcher isn't running, so new downloads in {folder} aren't recorded",
             'Run "wherefrom setup", or sign out and in again if it starts at sign-in.')]


def program_in(command):
    """The program a registry command starts: the quoted part, or up to ".exe"."""
    if not isinstance(command, str) or not command.strip():
        return None
    command = command.strip()
    if command.startswith('"'):
        end = command.find('"', 1)
        return command[1:end] if end > 1 else None
    lower = command.lower()
    end = lower.find(".exe")
    return command[:end + 4] if end != -1 else command.split()[0]


def check_windows(registry):
    found = []
    command = registry.get_value(shell.MENU_KEY + r"\command", "")
    exe = program_in(command)
    if not exe:
        found.append((False, "No right-click entry", SETUP))
    elif not Path(exe).is_file():
        found.append((False, f"The right-click entry points to a program that's gone: {exe}", SETUP))
    else:
        found.append((True, "Right-click entry: \"Where did this come from?\" (Windows 11: under \"Show more options\")", ""))
    at_login = program_in(registry.get_value(shell.RUN_KEY, shell.RUN_VALUE))
    if not at_login:
        found.append((False, "The watcher doesn't start at sign-in", SETUP))
    elif not Path(at_login).is_file():
        found.append((False, f"Start at sign-in points to a program that's gone: {at_login}", SETUP))
    else:
        found.append((True, "The watcher starts at sign-in", ""))
    for kind, label in (("chromium", "Chrome, Edge, Brave, Opera, Vivaldi"), ("firefox", "Firefox and browsers built on it")):
        manifest = registry.get_value(native.WINDOWS_KEYS[kind][0] + "\\" + native.HOST_NAME, "")
        found.append(check_host_manifest(manifest, label))
    return found


def check_files(platform, home):
    files = desktop.mac_files(home) if platform == "darwin" else desktop.linux_files(home)
    found = []
    if platform != "darwin":
        menus = [files["nautilus"], files["dolphin"]]
        found.append((True, "Right-click entry for GNOME Files and KDE Dolphin", "") if any(p.is_file() for p in menus)
                     else (False, "No right-click entry", SETUP))
    found.append((True, "The watcher starts at sign-in", "") if files["autostart"].is_file()
                 else (False, "The watcher doesn't start at sign-in", SETUP))
    for kind, label in (("chromium", "Chrome-based browsers"), ("firefox", "Firefox and browsers built on it")):
        registered = [d / f"{native.HOST_NAME}.json" for d in native.manifest_dirs(platform, home)[kind]]
        present = [p for p in registered if p.is_file()]
        found.append(check_host_manifest(str(present[0]) if present else "", label))
    return found


def check_host_manifest(manifest, label):
    """The browser connection: registered, and pointing at a helper that exists."""
    if not isinstance(manifest, str) or not manifest.strip():   # only matters with the extension: information
        return (None, f"Browser extension not connected for {label} (only needed with the extension: "
                      f"wherefrom browser setup)", "")
    try:
        helper = json.loads(Path(manifest).read_text(encoding="utf-8")).get("path", "")
    except (OSError, ValueError):
        return (False, f"The browser connection for {label} is damaged ({manifest})", 'Run "wherefrom browser setup".')
    if not Path(helper).is_file():
        return (False, f"The browser connection for {label} points to a helper that's gone ({helper})",
                'Run "wherefrom browser setup".')
    return (True, f"Browser extension connected for {label}", "")


def check_browsers(platform, home):
    from .ledger import SOURCE_NAMES
    names = {name for name, _ in browsers.all_histories(platform, home)}
    found = sorted(SOURCE_NAMES.get(n, n).replace("'s download history", "") for n in names)
    if not found:
        return [(None, "No browser history found to read (Chrome, Edge, Brave, Opera, Vivaldi, Firefox and others)", "")]
    return [(None, "Browser history it can read: " + ", ".join(found), "")]


def run(platform=None, home=None, data_home=None, registry=None, out=None):
    """Print the checks. Returns 0 if nothing is wrong, else 1."""
    platform = platform or sys.platform
    home = Path(home or Path.home())
    data_home = Path(data_home or default_home())
    out = out or sys.stdout
    program = sys.executable if getattr(sys, "frozen", False) else f"{sys.executable} -m wherefrom"
    checks = [(None, f"wherefrom {__version__} ({program})", "")]
    checks += check_database(data_home)
    checks += check_watcher(data_home)
    if platform == "win32":
        checks += check_windows(registry or shell.WindowsRegistry())
    else:
        checks += check_files(platform, home)
    checks += check_browsers(platform, home)

    problems = 0
    for ok, what, fix in checks:
        mark = "  " if ok is None else ("ok" if ok else "!!")
        print(f"{mark} {what}", file=out)
        if ok is False:
            problems += 1
            print(f"   -> {fix}", file=out)
    print(file=out)
    if problems:
        print(f"{problems} thing(s) to fix. Most are fixed by: wherefrom setup", file=out)
        return 1
    print("Everything looks fine.", file=out)
    return 0
