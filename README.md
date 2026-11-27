# wherefrom

Right-click any file and see where it came from: the link it was downloaded from, the page that link was on, and when. It still works after the file has been renamed, moved, or copied to a USB stick or another computer.

Works on Windows, macOS and Linux.

```
> wherefrom show "D:\Backup\final version.pdf"
D:\Backup\final version.pdf
  Downloaded from  https://example.edu/files/4471/download
  On the page      https://example.edu/courses/120/assignments/9
  First seen       2026-10-02 21:14 as C:\Users\you\Downloads\hw3.pdf
  Known from       Chrome's download history
  Same file at     C:\Users\you\Downloads\hw3.pdf
```

## Why

When a browser saves a file, the system attaches a hidden note with the address it came from: the "Mark of the Web" on Windows, "Where from" on macOS, `user.xdg.origin.url` on Linux (from Chrome). It's rarely shown and easy to lose: copying the file to a USB stick, a FAT drive, many cloud folders or an email drops it. The browser remembers too, until you clear your history.

wherefrom keeps that information in a small database of its own, next to a fingerprint (SHA-256) of each file's contents. Any later copy with the same contents, under any name and in any folder, can be traced back.

## Install

**Windows:** download `wherefrom.exe` and `wherefromw.exe` from the [latest release](https://github.com/andrew-hanzhou-li/wherefrom/releases/latest), put them in a folder such as `%LOCALAPPDATA%\Programs\wherefrom`, and run there:

```
wherefrom install --autostart
wherefrom import-browsers
```

**Any system, with Python 3.11 or later:** `pip install .` in this folder, then the same two commands.

- `install` adds **Where did this come from?** to the right-click menu of every file: Explorer on Windows (on Windows 11 under **Show more options**), GNOME Files (under **Scripts**) and KDE Dolphin on Linux. macOS has no Finder entry; use `wherefrom show` or the window (`wherefrom app`). With `--autostart` the watcher also starts when you sign in.
- `import-browsers` reads the download history of Chrome, Edge, Brave, Vivaldi, Chromium and Firefox, so files you downloaded before installing are covered too.

Nothing needs admin rights: everything is per user. The programs aren't code-signed yet, so Windows SmartScreen may warn about an unknown publisher the first time; `SHA256SUMS.txt` in the release lets you check the download.

### Optional: the browser extension

The extension records every download the moment it finishes, with the final link after redirects, the link first clicked, the page and the file type. It also covers programs and settings where the browser leaves no download note on the file.

1. Run `wherefrom browser setup`. It connects wherefrom to every browser installed for your user and prints a folder.
2. **Chrome, Edge, Brave, Vivaldi:** open the extensions page (`chrome://extensions`, `edge://extensions`, ...), turn on **Developer mode**, click **Load unpacked** and pick that folder.
3. **Firefox:** open `about:debugging` → **This Firefox** → **Load Temporary Add-on** and pick the printed `manifest.json`. Firefox removes unsigned add-ons when it restarts; to keep it, sign it for free on addons.mozilla.org (as "unlisted") and install the signed file.

It sends only finished downloads to wherefrom on your own computer, never anything about the pages you visit, and nothing from private or incognito windows. `wherefrom browser remove` undoes the setup. See [PRIVACY.md](PRIVACY.md).

Store versions (Chrome Web Store, Edge Add-ons, Firefox Add-ons) are on the way; they'll replace steps 2 and 3. `wherefrom browser setup` still has to run once, since the extension only talks to wherefrom on your computer.

## Commands

| Command | What it does |
|---|---|
| `wherefrom show FILE` | Where a file came from (`--gui` for the small window the menu opens) |
| `wherefrom app` | A window to browse and search everything recorded |
| `wherefrom search TEXT` | Files from a site or URL, or with a name, e.g. `wherefrom search canvas` |
| `wherefrom watch` | Keep recording new files in Downloads (`--folder` to add others, `--sidecars` to write sidecar files) |
| `wherefrom scan` | Record what's in Downloads once, without staying open |
| `wherefrom import-browsers` | Add your browsers' download history |
| `wherefrom export FILE` / `import FILE` | Move every record to another computer |
| `wherefrom sidecar FILE...` | Write `FILE.wherefrom.json` so the source travels with the file |
| `wherefrom browser setup` / `remove` | Connect (or disconnect) the browser extension |
| `wherefrom install` / `uninstall` | Add or remove the menu entry (and start at login) |

## Taking records with you

- **A new computer:** `wherefrom export records.json` on the old one, `wherefrom import records.json` on the new one. Each record keeps its links and dates, and is shown as "from an imported export" (a file from someone else could claim anything). Importing twice does nothing more.
- **One file, for someone else:** `wherefrom sidecar report.pdf` writes `report.pdf.wherefrom.json`. Keep the two together; wherefrom on any computer then shows the source, even if the file is renamed. A sidecar is tied to the file's fingerprint, so it never applies to different contents. A sidecar is only as trustworthy as whoever gave it to you: wherefrom says when a source came from one, and never lets a sidecar or an import outrank what your own computer recorded.

## How it works

- **Watching:** every 5 seconds the watcher lists Downloads (wherever you moved it). A file that looks the same twice in a row is finished downloading; if it has a download note, its source and fingerprint go into the database. Unfinished downloads (`.crdownload`, `.part`, ...) are skipped, and files already looked at aren't read again.
- **Browser history:** each browser's history database is copied and the copy is read. The browser's own files are never opened or changed. Only downloads whose files still exist are recorded, since a file has to be read to be fingerprinted.
- **The extension:** the browser starts wherefrom's small "native messaging" helper for each finished download and passes it one message. Browsers only let the extension named in the helper's registration talk to it.
- **Looking up:** `show` reads the file's own note and any sidecar next to it, then looks its fingerprint up in the database.

The database is `ledger.sqlite3` in `%LOCALAPPDATA%\wherefrom` (Windows), `~/Library/Application Support/wherefrom` (macOS) or `~/.local/share/wherefrom` (Linux), or in the folder named by `WHEREFROM_HOME`. If you use `WHEREFROM_HOME`, set it before `install` and `browser setup` so what they start uses it too; on Windows, set it as a user environment variable (Explorer's menu entry reads it from there).

## Privacy

Everything stays on your computer. wherefrom makes no network connections. The **Open page** button only opens `http` and `https` links, in your normal browser.

## Limits

- It only knows what a browser (or its extension) recorded. Files from programs that leave no download note, and that weren't in a browser's history, can't be traced.
- A file that was edited after downloading has a new fingerprint, so copies of the edited version aren't matched to the original download.
- Explorer and the Linux file managers only show the menu for files, not folders.

## Uninstall

`wherefrom uninstall` removes the menu entry and the start-at-login entry, and `wherefrom browser remove` the extension's connection (remove the extension itself in the browser). Then delete the program and, if you like, the database folder.

## Development

```
pip install pytest
python -m pytest
```

`python packaging/build_extension.py` builds the extension's store packages into `dist/extension`; `python packaging/make_icons.py` redraws its icons (needs Pillow).

Some tests need a particular system (Windows streams and registry, macOS attributes) or a display; they run in CI on Windows, macOS and Linux. `tests/test_extension_e2e.py` drives a real Chromium with the extension loaded (it needs Python Playwright and a display).

## Releasing

1. Put the new version in `pyproject.toml`, `wherefrom/__init__.py` and both `wherefrom/extension/manifest_*.json` (a test checks they match).
2. Merge to `main`, then tag and push: `git tag v0.3.0 && git push origin v0.3.0`.
3. CI tests, builds and publishes a GitHub Release with `wherefrom.exe`, `wherefromw.exe`, the two store packages and `SHA256SUMS.txt`. It refuses a tag that doesn't match the version.
4. Upload the store packages to the stores (see [docs/store-listing.md](docs/store-listing.md)).

## License

MIT
