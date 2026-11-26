# wherefrom

Right-click any file in Explorer and see where it came from: the link it was downloaded from, the page that link was on, and when, even if the file has since been renamed, moved, or copied to a USB stick.

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

When a browser saves a file, Windows attaches a hidden note to it (the "Mark of the Web", in a stream called `Zone.Identifier`) with the address it came from. But Windows never shows it, and it's easy to lose: copying the file to a USB stick, a FAT drive, many cloud folders or an email drops it. The browser remembers too, until you clear your history.

wherefrom keeps that information in a small database of its own, next to a fingerprint (SHA-256) of each file's contents. Any later copy with the same contents, under any name and in any folder, can be traced back.

## Install

Download `wherefrom.exe` and `wherefromw.exe` from the latest CI run's artifacts, put them in a folder of your choice (for example `%LOCALAPPDATA%\Programs\wherefrom`), and run there:

```
wherefrom install --autostart
wherefrom import-browsers
```

Or, with Python 3.11 or later: `pip install .` in this folder, then the same two commands.

- `install` adds **Where did this come from?** to the right-click menu of every file (on Windows 11 it's under **Show more options**). With `--autostart` the watcher also starts when you sign in.
- `import-browsers` reads the download history of Chrome, Edge, Brave, Vivaldi and Firefox, so files you downloaded before installing are covered too.

Nothing needs admin rights: everything is per user.

## Commands

| Command | What it does |
|---|---|
| `wherefrom show FILE` | Where a file came from (`--gui` for the window the menu opens) |
| `wherefrom search TEXT` | Files from a site or URL, or with a name, e.g. `wherefrom search canvas` |
| `wherefrom watch` | Keep recording new files in Downloads (`--folder` to add others) |
| `wherefrom scan` | Record what's in Downloads once, without staying open |
| `wherefrom import-browsers` | Add your browsers' download history |
| `wherefrom install` / `uninstall` | Add or remove the menu entry (and start at login) |

## How it works

- **Watching:** every 5 seconds the watcher lists Downloads. A file that looks the same twice in a row is finished downloading; if it has a Mark of the Web, its source and fingerprint go into the database. Unfinished downloads (`.crdownload`, `.part`, ...) are skipped, and files already looked at aren't read again.
- **Browser history:** each browser's history database is copied and the copy is read. The browser's own files are never opened or changed. Only downloads whose files still exist are recorded, since a file has to be read to be fingerprinted.
- **Looking up:** `show` reads the file's own mark first, then looks its fingerprint up in the database.

The database is `%LOCALAPPDATA%\wherefrom\ledger.sqlite3` (or the folder in `WHEREFROM_HOME`).

## Privacy

Everything stays on your computer. wherefrom makes no network connections. The **Open page** button in the window only opens `http` and `https` links, in your normal browser.

## Limits

- It only knows what a browser recorded. Files from programs that don't write a Mark of the Web, and that weren't in a browser's history, can't be traced.
- A file that was edited after downloading has a new fingerprint, so copies of the edited version aren't matched to the original download.
- Explorer only shows the menu for files, not folders.

## Uninstall

`wherefrom uninstall` removes the menu entry and the start-at-login entry. Then delete the program and, if you like, the database folder.

## Development

```
pip install pytest
python -m pytest
```

Tests that need Windows (real `Zone.Identifier` streams, the registry, the window) run in CI on `windows-latest`.

## License

MIT
