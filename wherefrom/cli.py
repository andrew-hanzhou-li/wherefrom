"""wherefrom: remember where your downloaded files came from."""

import argparse
import sys
import time
from pathlib import Path
from datetime import datetime

from . import __version__, browsers, desktop, portable, shell
from .ledger import SOURCE_NAMES, Ledger
from .lookup import look_up
from .watch import Watcher, downloads_folder

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
        zone = f" (zone: {finding.mark.zone_name})" if finding.mark.zone_id is not None else ""
        lines.append(f"  Known from       {SOURCE_NAMES['mark']}{zone}")
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
    from . import lock
    folders = args.folder or [downloads_folder()]
    path = lock.watch_lock(Path(ledger.path).parent, folders)
    held = lock.hold(path)
    for _ in range(8):           # something only checking (wherefrom doctor) lets go within moments
        if held is not None:
            break
        time.sleep(0.25)
        held = lock.hold(path)
    if held is None:
        print("A wherefrom watcher for " + ", ".join(str(f) for f in folders) + " is already running.")
        return 0
    print("Watching " + ", ".join(str(f) for f in folders) + " (Ctrl+C to stop)")
    try:
        Watcher(ledger, folders, sidecars=args.sidecars).run(interval=args.interval)
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


def cmd_native_host(args, ledger):
    # Started by the browser; stdin/stdout carry the extension's messages,
    # so nothing else may be printed here.
    from . import native
    return native.serve(ledger=ledger)


def cmd_browser(args, ledger):
    from . import native
    if args.action == "remove":
        for item in native.remove():
            print(f"Removed {item}")
        print("Remove the extension itself from the browser's extensions page.")
        return 0
    summary = native.setup(extra_ids=args.extension_id or ())
    folders = summary["extensions"]
    print("wherefrom can now receive downloads from its browser extension.")
    if not summary["registered"]:
        print("No supported browser was found for this user; install one and run this again.")
    print()
    print("Chrome, Edge, Brave, Opera, Vivaldi: open the extensions page (e.g. chrome://extensions),")
    print("turn on Developer mode, choose \"Load unpacked\" and pick:")
    print(f"  {folders['chromium']}")
    print("Firefox: open about:debugging > This Firefox > Load Temporary Add-on and pick")
    print(f"  {folders['firefox'] / 'manifest.json'}")
    print("(Firefox removes unsigned add-ons when it restarts; see the README to keep it.)")
    return 0


def cmd_app(args, ledger):
    from . import app
    app.run(ledger)
    return 0


def cmd_export(args, ledger):
    count = portable.export(ledger, args.file)
    print(f"Wrote {count} record(s) to {args.file}. On another computer: wherefrom import {args.file}")
    return 0


def cmd_import_file(args, ledger):
    try:
        new, invalid = portable.import_file(ledger, args.file)
    except (OSError, portable.BadFile) as error:
        print(f"Can't import {args.file}: {error}", file=sys.stderr)
        return 1
    print(f"Imported {new} new record(s)" + (f"; skipped {invalid} damaged one(s)" if invalid else "") + ".")
    return 0


def cmd_sidecar(args, ledger):
    written, unknown = portable.make_sidecars(ledger, args.files)
    for path in written:
        print(f"Wrote {path}")
    for path in unknown:
        print(f"No record for {path}; nothing written", file=sys.stderr)
    return 0 if written else 1


def cmd_import(args, ledger):
    def reading(browser, history):
        # Every downloaded file still on disk gets read, which can take a while
        print(f"Reading {browser} ({history.parent.name})...", flush=True)
    results = browsers.import_all(ledger, on_start=reading)
    if not results:
        print("No browser history found (Chrome, Edge, Brave, Opera, Vivaldi, Firefox and others).")
        return 1
    for browser, history, total, new in results:
        if total is None:
            print(f"{browser}: couldn't read {history}: {new}")
        else:
            print(f"{browser}: {total} downloads in history, {new} new file(s) recorded"
                  f" ({history.parent.name})")
    return 0


def cmd_doctor(args, ledger):
    from . import doctor
    return doctor.run()


def cmd_setup(args, ledger):
    from . import quickstart
    return quickstart.run(ledger, do_import=not args.no_import, do_start=not args.no_start)


def cmd_install(args, ledger):
    if sys.platform == "win32":
        shell.install(shell.WindowsRegistry(), autostart=args.autostart)
        print("Added \"Where did this come from?\" to the right-click menu of files.")
        print("(On Windows 11 it's under \"Show more options\".)")
    else:
        for path in desktop.install(sys.platform, Path.home(), autostart=args.autostart):
            print(f"Wrote {path}")
        if sys.platform == "darwin":
            print("Finder has no menu entry; use \"wherefrom show FILE\" or \"wherefrom app\".")
        else:
            print("Added \"Where did this come from?\" to GNOME Files (Scripts) and KDE Dolphin.")
    if args.autostart:
        print("The watcher will also start when you sign in.")
    return 0


def cmd_uninstall(args, ledger):
    if sys.platform == "win32":
        shell.uninstall(shell.WindowsRegistry())
    else:
        for path in desktop.uninstall(sys.platform, Path.home()):
            print(f"Removed {path}")
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

    setup = sub.add_parser("setup", help="set everything up in one go: menu entry, start at sign-in, "
                                         "browser connection, download history, and start watching")
    setup.add_argument("--no-import", action="store_true", help="skip reading the browsers' download history")
    setup.add_argument("--no-start", action="store_true", help="don't start the watcher now")
    setup.set_defaults(run=cmd_setup)

    doctor = sub.add_parser("doctor", help="check the setup and say how to fix anything that isn't right")
    doctor.set_defaults(run=cmd_doctor, no_ledger=True)

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
            command.add_argument("--sidecars", action="store_true",
                                 help="also write a .wherefrom.json next to each new file, so its "
                                      "source travels with it")
        command.set_defaults(run=run)

    browser = sub.add_parser("browser", help="set up (or remove) the browser extension's connection")
    browser.add_argument("action", choices=["setup", "remove"])
    browser.add_argument("--extension-id", action="append",
                         help="also allow this Chromium extension ID (e.g. after publishing it to a store)")
    browser.set_defaults(run=cmd_browser)

    host = sub.add_parser("native-host", help="(started by the browser extension; not for typing)")
    host.add_argument("browser_args", nargs=argparse.REMAINDER)     # what the browser passes; unused
    host.set_defaults(run=cmd_native_host)

    window = sub.add_parser("app", help="a window to browse and search everything recorded")
    window.set_defaults(run=cmd_app)

    export = sub.add_parser("export", help="save every record to a file, e.g. for a new computer")
    export.add_argument("file")
    export.set_defaults(run=cmd_export)

    imp_file = sub.add_parser("import", help="add the records from a wherefrom export")
    imp_file.add_argument("file")
    imp_file.set_defaults(run=cmd_import_file)

    side = sub.add_parser("sidecar", help="write FILE.wherefrom.json so the source travels with the file")
    side.add_argument("files", nargs="+", metavar="file")
    side.set_defaults(run=cmd_sidecar)

    imp = sub.add_parser("import-browsers", help="add your browsers' download history")
    imp.set_defaults(run=cmd_import)

    install = sub.add_parser("install", help="add the right-click menu entry (Windows, Linux)")
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
    if getattr(args, "no_ledger", False):       # doctor only looks; opening the ledger would create it
        return args.run(args, None)
    ledger = Ledger()
    try:
        return args.run(args, ledger)
    finally:
        ledger.close()
