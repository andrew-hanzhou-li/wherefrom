"""Menu and start-at-login entries on Linux and macOS (Windows is in shell.py).

Linux: a GNOME Files (Nautilus) script and a KDE Dolphin service menu, both
named "Where did this come from?", and an autostart entry for the watcher.
macOS: a LaunchAgent for the watcher. (Finder's right-click menu needs a
signed app extension; use "wherefrom show" or "wherefrom app" there.)

Every file written starts with a MARKER line, and uninstall only removes
files that still contain it, so a file of the same name made by someone
else is left alone.
"""

import os
import plistlib
import shlex
import sys
from pathlib import Path

MARKER = "Added by 'wherefrom install'; 'wherefrom uninstall' removes it."
MENU_TEXT = "Where did this come from?"
LAUNCH_AGENT = "local.wherefrom.watch"


def command():
    """wherefrom's command as a list: the packaged program, or Python with -P
    so a module planted in the clicked file's folder can't be imported."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-P", "-m", "wherefrom"]


def desktop_exec(args):
    """Quote for the Exec= line of a .desktop file (freedesktop rules)."""
    def quote(arg):
        if arg.startswith("%"):
            return arg                      # a field code like %f
        if all(c.isalnum() or c in "-_./=+:" for c in arg):
            return arg
        escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
        return f'"{escaped}"'
    return " ".join(quote(a) for a in args)


def linux_files(home, config_home=None, data_home=None):
    home = Path(home)
    config = Path(config_home or os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    data = Path(data_home or os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return {
        "nautilus": data / "nautilus" / "scripts" / MENU_TEXT,
        "dolphin": data / "kio" / "servicemenus" / "wherefrom.desktop",
        "autostart": config / "autostart" / "wherefrom.desktop",
    }


def mac_files(home):
    return {"autostart": Path(home) / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT}.plist"}


def linux_contents(cmd):
    show = desktop_exec(cmd + ["show", "--gui"])
    script = (
        "#!/bin/sh\n"
        f"# {MARKER}\n"
        "# GNOME Files passes the selected files as arguments.\n"
        f'for f in "$@"; do {" ".join(shlex.quote(a) for a in cmd)} show --gui "$f" & done\n'
    )
    service_menu = (
        f"# {MARKER}\n"
        "[Desktop Entry]\n"
        "Type=Service\n"
        "MimeType=all/allfiles;\n"
        "X-KDE-ServiceTypes=KonqPopupMenu/Plugin\n"
        "Actions=wherefrom\n\n"
        "[Desktop Action wherefrom]\n"
        f"Name={MENU_TEXT}\n"
        "Icon=document-properties\n"
        f"Exec={show} %f\n"
    )
    autostart = (
        f"# {MARKER}\n"
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=wherefrom watcher\n"
        "Comment=Records where new downloads came from\n"
        f"Exec={desktop_exec(cmd + ['watch'])}\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    return {"nautilus": script, "dolphin": service_menu, "autostart": autostart}


def mac_contents(cmd):
    agent = {
        "Label": LAUNCH_AGENT,
        "Comment": MARKER,
        "ProgramArguments": cmd + ["watch"],
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Background",
    }
    return {"autostart": plistlib.dumps(agent).decode("utf-8")}


def install(platform, home, autostart=False, cmd=None):
    """Write the entries for this system. Returns the files written."""
    cmd = cmd or command()
    if platform == "darwin":
        files, contents = mac_files(home), mac_contents(cmd)
    else:
        files, contents = linux_files(home), linux_contents(cmd)
    written = []
    for kind, path in files.items():
        if kind == "autostart" and not autostart:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents[kind], encoding="utf-8")
        if kind in ("nautilus", "dolphin"):
            path.chmod(0o755)               # both file managers want these executable
        written.append(path)
    return written


def uninstall(platform, home):
    """Remove the entries install wrote. Returns the files removed."""
    files = mac_files(home) if platform == "darwin" else linux_files(home)
    removed = []
    for path in files.values():
        try:
            if MARKER in path.read_text(encoding="utf-8", errors="replace"):
                path.unlink()
                removed.append(path)
        except OSError:
            pass
    return removed
