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
import subprocess  # nosec B404 - launchctl with a fixed argument list
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


FIELD_CODES = {"%f", "%F", "%u", "%U"}


def desktop_exec(args):
    """The Exec= value of a .desktop file, quoted by the freedesktop rules.
    Two layers apply: inside "...", \" ` $ and \\ are escaped with a
    backslash; then the whole value is a .desktop string, where each
    backslash is doubled again. A literal % is written %% (else "%f" in a
    path would become the file name)."""
    def quote(arg):
        if arg in FIELD_CODES:
            return arg
        if "\n" in arg or "\r" in arg:
            raise ValueError(f"can't put a line break in a .desktop file: {arg!r}")
        arg = arg.replace("%", "%%")
        if all(c.isalnum() or c in "-_./=+:%" for c in arg):
            return arg
        inner = "".join("\\" + c if c in '"`$\\' else c for c in arg)
        return '"' + inner.replace("\\", "\\\\") + '"'
    return " ".join(quote(a) for a in args)


def with_env(cmd, env):
    """Prefix the command with env NAME=value, for settings like WHEREFROM_HOME."""
    return (["env"] + [f"{k}={v}" for k, v in env.items()] + cmd) if env else cmd


def wherefrom_env():
    return {"WHEREFROM_HOME": os.environ["WHEREFROM_HOME"]} if os.environ.get("WHEREFROM_HOME") else {}


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


def linux_contents(cmd, env=None):
    env = env or {}
    full = with_env(cmd, env)
    # "--": a file named "-x.pdf" is a file, not an option
    show = desktop_exec(full + ["show", "--gui", "--"])
    exports = "".join(f"export {k}={shlex.quote(v)}\n" for k, v in env.items())
    script = (
        "#!/bin/sh\n"
        f"# {MARKER}\n"
        "# GNOME Files passes the selected files as arguments.\n"
        + exports +
        f'for f in "$@"; do {" ".join(shlex.quote(a) for a in cmd)} show --gui -- "$f" & done\n'
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
        f"Exec={desktop_exec(full + ['watch'])}\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    return {"nautilus": script, "dolphin": service_menu, "autostart": autostart}


def mac_contents(cmd, env=None):
    agent = {
        "Label": LAUNCH_AGENT,
        "Comment": MARKER,
        "ProgramArguments": cmd + ["watch"],
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Background",
    }
    if env:
        agent["EnvironmentVariables"] = dict(env)
    return {"autostart": plistlib.dumps(agent).decode("utf-8")}


def install(platform, home, autostart=False, cmd=None, env=None):
    """Write the entries for this system. Returns the files written.
    `env` (default: WHEREFROM_HOME if set) is passed to what they start."""
    cmd = cmd or command()
    env = env if env is not None else wherefrom_env()
    if platform == "darwin":
        files, contents = mac_files(home), mac_contents(cmd, env)
    else:
        files, contents = linux_files(home), linux_contents(cmd, env)
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


def uninstall(platform, home, run=subprocess.run):
    """Remove the entries install wrote. Returns the files removed. On macOS
    the running watcher is stopped too (removing the file alone would leave
    it running until the next sign-in)."""
    files = mac_files(home) if platform == "darwin" else linux_files(home)
    removed = []
    for path in files.values():
        try:
            if MARKER not in path.read_text(encoding="utf-8", errors="replace"):
                continue
        except OSError:
            continue
        if platform == "darwin":
            run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)],  # nosec B603 B607
                capture_output=True, check=False)
        path.unlink()
        removed.append(path)
    return removed
