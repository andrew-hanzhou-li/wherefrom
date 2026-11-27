"""`wherefrom setup`: everything a new user needs, in one go.

1. the right-click menu entry and start at sign-in (`install --autostart`);
2. the browser extension's connection (`browser setup`);
3. the browsers' download history (`import-browsers`), unless --no-import;
4. the watcher, started now in the background, unless --no-start.

Each step runs even if an earlier one failed. The exit code is 0 only if all
of them worked, so an installer can tell. Finding no browser history is not a
failure.
"""

import os
import subprocess
import sys
from pathlib import Path

from . import browsers, desktop, shell


def watcher_command():
    """How to start the watcher without a console window."""
    cmd = desktop.command()
    if sys.platform == "win32":
        exe = Path(cmd[0])
        quiet = exe.with_name("wherefromw.exe" if getattr(sys, "frozen", False) else "pythonw.exe")
        if quiet.is_file():
            cmd = [str(quiet), *cmd[1:]]
    return [*cmd, "watch"]


def start_watcher(platform=None, home=None, popen=subprocess.Popen, run=subprocess.run):
    """Start the watcher so it keeps running after this command ends. On macOS
    through launchd, from the LaunchAgent `install --autostart` wrote, so
    `uninstall` (launchctl bootout) stops it again."""
    platform = platform or sys.platform
    if platform == "darwin":
        plist = desktop.mac_files(Path(home or Path.home()))["autostart"]
        uid = os.getuid() if hasattr(os, "getuid") else 0
        result = run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)],  # nosec B603 B607
                     capture_output=True, text=True, check=False)
        # Already loaded (setup run again) is fine: it's running
        if result.returncode not in (0, 5, 37) and "already" not in (result.stderr or ""):
            raise OSError(f"launchctl bootstrap failed: {(result.stderr or '').strip()}")
        return
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP   # no console, not tied to ours
        popen(watcher_command(), creationflags=flags, close_fds=True, **quiet)  # nosec B603
    else:
        popen(watcher_command(), start_new_session=True, close_fds=True, **quiet)  # nosec B603


def run(ledger, do_import=True, do_start=True, steps=None):
    """Run the steps; print one line per step. Returns the exit code."""
    steps = steps or default_steps(ledger)
    chosen = [(name, step) for name, step in steps
              if not (name == "history" and not do_import) and not (name == "watcher" and not do_start)]
    failed = 0
    for name, step in chosen:
        try:
            print(f"- {step()}", flush=True)
        except Exception as error:     # each step on its own; report and carry on
            failed += 1
            print(f"- FAILED ({name}): {error}", flush=True)
    if failed:
        print(f"\n{failed} step(s) failed; see above. Running \"wherefrom setup\" again is safe.")
        return 1
    print("\nDone. Right-click a downloaded file and choose \"Where did this come from?\","
          " or run \"wherefrom app\" to browse everything recorded.")
    return 0


def default_steps(ledger):
    def menu():
        if sys.platform == "win32":
            shell.install(shell.WindowsRegistry(), autostart=True)
            return ("Added \"Where did this come from?\" to the right-click menu of files"
                    " (on Windows 11 under \"Show more options\"); the watcher starts at sign-in.")
        desktop.install(sys.platform, Path.home(), autostart=True)
        where = "Finder has no menu entry; use \"wherefrom app\"" if sys.platform == "darwin" \
            else "Added \"Where did this come from?\" to GNOME Files (Scripts) and KDE Dolphin"
        return f"{where}; the watcher starts at sign-in."

    def extension():
        from . import native
        summary = native.setup()
        if not summary["registered"]:
            return "Browser extension: no supported browser found for this user (optional; skipped)."
        return ("Browser extension connection is ready (optional: see \"Optional: the browser"
                " extension\" in the README to add the extension itself).")

    def history():
        results = browsers.import_all(ledger)
        if not results:
            return "Download history: no Chrome, Edge, Brave, Vivaldi or Firefox history found."
        parts = [f"{browser} {new} new" if total is not None else f"{browser} unreadable ({new})"
                 for browser, history_file, total, new in results]
        return "Download history imported: " + ", ".join(parts) + "."

    def watcher():
        start_watcher()
        return "The watcher is running and records new downloads from now on."

    return [("menu", menu), ("extension", extension), ("history", history), ("watcher", watcher)]
