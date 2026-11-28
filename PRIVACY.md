# Privacy policy

This covers the wherefrom program and its browser extension. Last updated: 2026-11-28.

## In short

Nothing leaves your computer. wherefrom has no server, no account, no analytics and no ads, and it makes no network connections.

## What the extension handles

When a download finishes, the extension passes these details to the wherefrom program on the same computer, using the browser's "native messaging":

- where the file was saved on your computer;
- the link it was downloaded from (after redirects), and the link first clicked;
- the page the link was on (the referrer), if the browser knows it;
- the file's type, size and when the download finished.

It sends nothing else: not the pages you visit, not your browsing history, not page contents. Besides downloads, it only asks the program whether it's there and which version it is. Downloads in private or incognito windows are never sent, and neither are downloads you've paused recording for or from sites you've chosen not to record. A data: link (a file a page made itself) is sent as its type only, never its contents.

## What the extension keeps in your browser

In the browser's storage for extensions, on your computer only:

- your settings: whether recording is paused, and the sites not to record;
- the last 8 downloads it handled (file name, site, time, whether it was recorded), for its popup;
- downloads waiting for the wherefrom program, while it can't be reached: the same details it would send, for up to 14 days.

Removing a download from the browser's download list removes it here too. **Clear** in the popup empties the list; removing the extension deletes everything it kept.

## What the program keeps

The wherefrom program stores those details, with a fingerprint (SHA-256) of each file's contents, in a database file on your computer (`ledger.sqlite3`, see the README for where). It can also read your browsers' own download history when you run `wherefrom import-browsers`. Nothing is sent anywhere.

You decide what leaves your computer: `wherefrom export` and `wherefrom sidecar` write files that you can choose to share.

## Removing your data

Delete the database folder. Uninstalling wherefrom (Settings > Apps on Windows, or `wherefrom uninstall` and `wherefrom browser remove`) undoes the setup, and removing the extension in the browser stops it at once.

## Sharing and selling

Your data is never sold or shared, and never used for anything except showing you where your files came from.

## Contact

Open an issue at https://github.com/andrew-hanzhou-li/wherefrom/issues.
