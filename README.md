# wherefrom

**Right-click any file and see where you downloaded it from**: the link, the page that link was on, and when. It still works after the file has been renamed, moved, or copied to a USB stick or another computer.

**[Download for Windows](https://github.com/andrew-hanzhou-li/wherefrom/releases/latest/download/wherefrom-setup.exe)** (one double-click, no admin rights) · [macOS and Linux](#macos-and-linux) · Free and open source (MIT) · Nothing leaves your computer

<!-- Demo GIF goes here: right-click a file in Downloads > "Where did this come from?" > the window. -->

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

Handy when you need to cite where a PDF or dataset came from, find the course page a file was attached to, check where an installer really came from, or just make sense of a messy Downloads folder.

## Why not just...

- **...look in the file's Properties?** Windows does keep the link, but Explorer never shows it; you'd need `Get-Content file -Stream Zone.Identifier` in PowerShell. It's gone once the file goes through a USB stick, an email or many cloud folders, or once you click **Unblock**. macOS shows **Where from** in Get Info, but it can be lost the same way.
- **...check the browser's download history?** It's lost when you clear your history, and it can't tell you about a file that's since been renamed or moved, or a copy of it somewhere else.
- **...use a forensics tool?** Those read the same notes, for investigators. wherefrom is one right-click.

wherefrom also covers what you downloaded before installing it: setup reads the notes already on your files and your browsers' history, so it's useful from the first minute.

## Install

### Windows

**[Download wherefrom-setup.exe](https://github.com/andrew-hanzhou-li/wherefrom/releases/latest/download/wherefrom-setup.exe)** and double-click it. That's all.

It needs no admin rights and sets everything up:

- **Where did this come from?** in the right-click menu of every file (on Windows 11 under **Show more options**);
- the download history of Chrome, Edge, Brave, Opera, Vivaldi, Chromium, Firefox, LibreWolf, Waterfox, Floorp and Zen, read in the background, so files you downloaded before are covered too;
- the watcher, which records new downloads from now on and starts again when you sign in;
- **wherefrom** in the Start menu, a window to browse and search everything recorded.

The installer isn't code-signed yet, so Windows SmartScreen may say it "protected your PC": click **More info**, then **Run anyway**. `SHA256SUMS.txt` in the [release](https://github.com/andrew-hanzhou-li/wherefrom/releases/latest) lets you check the download. To update, run a newer installer; to remove wherefrom, use **Settings > Apps**.

### macOS and Linux

You need Python 3.11 or later with Tk (Debian/Ubuntu: `sudo apt install python3-tk pipx`; macOS with Homebrew: `brew install python-tk pipx`). Then:

```
pipx install git+https://github.com/andrew-hanzhou-li/wherefrom
wherefrom setup
```

If `wherefrom` isn't found after the first command, run `pipx ensurepath` and open a new terminal. (`uv tool install git+https://github.com/andrew-hanzhou-li/wherefrom` works too.)

`wherefrom setup` does in one go what the Windows installer does: the menu entry (GNOME Files under **Scripts**, KDE Dolphin; macOS has no Finder entry, so use `wherefrom app`), start at sign-in, the browser connection, the download history, and starting the watcher. Running it again is safe. On macOS, if you're asked whether Python may access your Downloads folder, allow it, or the watcher can't see new files.

### Without installing

The release also has `wherefrom.exe` and `wherefromw.exe` on their own: put them in one folder and run `wherefrom setup` there. From a copy of this repository, `pip install .` then `wherefrom setup`.

### Optional: the browser extension

You don't need it: wherefrom already reads what the browser records. The extension adds a little more for each download (the link before redirects, the file type) and covers the few downloads the browser leaves no note on.

The installer (or `wherefrom setup`) has already connected your browsers. To add the extension itself:

- **Chrome, Edge, Brave, Opera, Vivaldi** (Opera and Vivaldi less tested): open the extensions page (`chrome://extensions`, `edge://extensions`, ...), turn on **Developer mode**, click **Load unpacked** and pick `%LOCALAPPDATA%\wherefrom\browser\extension-chromium` (Windows) or the folder `wherefrom browser setup` prints.
- **Firefox (and LibreWolf, Waterfox, Floorp, Zen):** open `about:debugging` → **This Firefox** → **Load Temporary Add-on** and pick `manifest.json` in the `extension-firefox` folder next to it. Firefox removes unsigned add-ons when it restarts; to keep it, sign it for free on addons.mozilla.org (as "unlisted") and install the signed file.

Its toolbar button shows whether it's working:

- **Recording downloads**: connected to wherefrom. The popup lists recent downloads and whether each was recorded.
- **A red !**: wherefrom isn't reachable. The popup says why and how to fix it (install wherefrom, or run the one command it shows). Downloads made meanwhile wait in the extension for up to 14 days and are recorded once wherefrom answers.
- **off**: paused. Use the switch in the popup to stop and restart recording.

To never record certain sites (your bank, say), add them under **Sites not recorded** in the popup, or click **Don't record this site** next to a recent download. A site covers its subdomains, and a download counts as from that site if its link or the page it came from is on it.

It sends only finished downloads to wherefrom on your own computer, never anything about the pages you visit, and nothing from private or incognito windows. `wherefrom browser remove` undoes the connection. See [PRIVACY.md](PRIVACY.md).

## Commands

You don't need any of these for everyday use: the menu entry and the window cover it. The Windows installer doesn't add wherefrom to PATH; in a terminal, run it as `& "$env:LOCALAPPDATA\Programs\wherefrom\wherefrom.exe"` (PowerShell), or add that folder to your PATH.

| Command | What it does |
|---|---|
| `wherefrom setup` | Set everything up in one go (`--no-import`, `--no-start` to skip those steps) |
| `wherefrom doctor` | Check the setup and say how to fix anything that isn't right |
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

**Installed with wherefrom-setup.exe:** remove **wherefrom** in **Settings > Apps**. That stops the watcher and removes the menu entry, start at sign-in and the browser connection. Remove the extension itself in the browser.

**Otherwise:** `wherefrom uninstall` removes the menu entry and the start-at-login entry (on macOS it also stops the watcher), and `wherefrom browser remove` the extension's connection. Then delete the program.

Either way the database of recorded downloads is kept; delete its folder (see "How it works") if you want it gone.

## Development

```
pip install pytest
python -m pytest
```

`python packaging/build_extension.py` builds the extension's store packages into `dist/extension`; `python packaging/make_icons.py` redraws its icons (needs Pillow). `python packaging/make_social_preview.py` redraws `docs/social-preview.png`, the card shown when the repository's link is shared.

Some tests need a particular system (Windows streams and registry, macOS attributes) or a display; they run in CI on Windows, macOS and Linux. `tests/test_extension_e2e.py` drives a real Chromium with the extension loaded (it needs Python Playwright and a display). The extension's own logic has JavaScript tests in `tests/extension/` (`node --test tests/extension/logic.test.js`); pytest runs them when Node is installed.

## Releasing

1. Put the new version in `pyproject.toml`, `wherefrom/__init__.py` and both `wherefrom/extension/manifest_*.json` (a test checks they match).
2. Merge to `main`, then tag and push: `git tag v0.3.0 && git push origin v0.3.0`.
3. CI tests, builds and publishes a GitHub Release with `wherefrom-setup.exe`, `wherefrom.exe`, `wherefromw.exe`, the two store packages and `SHA256SUMS.txt`. It refuses a tag that doesn't match the version. The installer keeps its name in every release, so the README's download link always gets the newest one.
4. Upload the store packages to the stores (see [docs/store-listing.md](docs/store-listing.md)).
5. PyPI, a signed Firefox add-on and winget updates can each run by themselves on every release once set up; see [docs/distribution.md](docs/distribution.md).

## License

MIT
