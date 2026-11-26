"""wherefrom: remember where your downloaded files came from."""

import argparse
import sys
from datetime import datetime

from . import __version__, browsers, shell
from .ledger import Ledger
from .lookup import look_up
from .watch import Watcher, downloads_folder

SOURCE_NAMES = {
    "mark": "the file's Mark of the Web",
    "chrome": "Chrome's download history",
    "edge": "Edge's download history",
    "brave": "Brave's download history",
    "vivaldi": "Vivaldi's download history",
    "firefox": "Firefox's download history",
}


def when(text):
    """'2026-11-20T14:03:11' -> '2026-11-20 14:03'."""
    if not text:
        return "unknown"
    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text


def describe(finding):
    """The lines `show` prints for one file."""
    lines = [finding.path]
    if finding.error:
        return lines + ["  " + finding.error]
    if not finding.known:
        lines.append("  No record of where this file came from.")
        lines.append("  It has no Mark of the Web, and its contents don't match any file")
        lines.append("  wherefrom has seen. (Run 'wherefrom import-browsers' to add your")
        lines.append("  browsers' download history.)")
        return lines
    if finding.host_url:
        lines.append(f"  Downloaded from  {finding.host_url}")
    if finding.page_url:
        lines.append(f"  On the page      {finding.page_url}")
    first = finding.first
    if first:
        lines.append(f"  First seen       {when(first.downloaded_at or first.recorded_at)}"
                     f" as {first.path}")
        lines.append(f"  Known from       {SOURCE_NAMES.get(first.source, first.source)}")
    elif finding.mark:
        lines.append(f"  Known from       {SOURCE_NAMES['mark']} (zone: {finding.mark.zone_name})")
    for copy in finding.other_copies:
        lines.append(f"  Same file at     {copy}")
    return lines


def cmd_show(args, ledger):
    if args.gui:
        from . import gui
        gui.show(look_up(args.file, ledger))
        return 0
    finding = look_up(args.file, ledger)
    print("\n".join(describe(finding)))
    return 1 if finding.error else 0


def cmd_search(args, ledger):
    records = ledger.search(args.text)
    if not records:
        print(f"Nothing recorded matches {args.text!r}.")
        return 1
    for record in records:
        print(f"{when(record.downloaded_at or record.recorded_at)}  {record.path}")
        print(f"                  {record.host_url or record.referrer_url}")
    return 0


def cmd_watch(args, ledger):
    folders = args.folder or [downloads_folder()]
    print("Watching " + ", ".join(str(f) for f in folders) + " (Ctrl+C to stop)")
    try:
        Watcher(ledger, folders).run(interval=args.interval)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_scan(args, ledger):
    folders = args.folder or [downloads_folder()]
    watcher = Watcher(ledger, folders)
    watcher.scan_once()             # files must look the same twice in a row
    recorded = watcher.scan_once()
    print(f"Recorded the source of {recorded} new file(s) in "
          + ", ".join(str(f) for f in folders))
    return 0


def cmd_import(args, ledger):
    results = browsers.import_all(ledger)
    if not results:
        print("No browser history found (Chrome, Edge, Brave, Vivaldi or Firefox).")
        return 1
    for browser, history, total, new in results:
        if total is None:
            print(f"{browser}: couldn't read {history}: {new}")
        else:
            print(f"{browser}: {total} downloads in history, {new} new file(s) recorded"
                  f" ({history.parent.name})")
    return 0


def cmd_install(args, ledger):
    shell.install(shell.WindowsRegistry(), autostart=args.autostart)
    print("Added \"Where did this come from?\" to the right-click menu of files.")
    print("(On Windows 11 it's under \"Show more options\".)")
    if args.autostart:
        print("The watcher will also start when you sign in.")
    return 0


def cmd_uninstall(args, ledger):
    shell.uninstall(shell.WindowsRegistry())
    print("Removed the menu entry and the start-at-login entry. The ledger is kept;")
    print("delete it by hand if you want: " + str(ledger_path_hint()))
    return 0


def ledger_path_hint():
    from .ledger import default_home
    return default_home() / "ledger.sqlite3"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="wherefrom", description="Remember where your downloaded files came from.")
    parser.add_argument("--version", action="version", version=f"wherefrom {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="where a file came from")
    show.add_argument("file")
    show.add_argument("--gui", action="store_true", help="show it in a small window")
    show.set_defaults(run=cmd_show)

    search = sub.add_parser("search", help="files from a site, URL or with a name")
    search.add_argument("text")
    search.set_defaults(run=cmd_search)

    for name, run, help_text in (
        ("watch", cmd_watch, "keep recording new downloads"),
        ("scan", cmd_scan, "record the files in a folder once"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--folder", action="append",
                             help="folder to watch (default: Downloads); can repeat")
        if name == "watch":
            command.add_argument("--interval", type=float, default=5.0,
                                 help="seconds between checks (default 5)")
        command.set_defaults(run=run)

    imp = sub.add_parser("import-browsers", help="add your browsers' download history")
    imp.set_defaults(run=cmd_import)

    install = sub.add_parser("install", help="add the right-click menu entry (Windows)")
    install.add_argument("--autostart", action="store_true",
                         help="also start the watcher when you sign in")
    install.set_defaults(run=cmd_install)

    uninstall = sub.add_parser("uninstall", help="remove the menu and start-at-login entries")
    uninstall.set_defaults(run=cmd_uninstall)
    return parser


def main(argv=None):
    # Redirected output on Windows uses the old code page, which can't hold
    # every file name or URL; print "?" for those characters instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if args.command in ("install", "uninstall") and sys.platform != "win32":
        print("install and uninstall are for Windows.", file=sys.stderr)
        return 2
    ledger = Ledger()
    try:
        return args.run(args, ledger)
    finally:
        ledger.close()
