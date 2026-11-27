# Publishing the browser extension

Text to paste into each store's forms, and the steps around it. The packages come from a GitHub Release (`wherefrom-chromium-<version>.zip`, `wherefrom-firefox-<version>.zip`) or from `python packaging/build_extension.py`.

| Store | Account | Package | Reaches |
|---|---|---|---|
| [Firefox Add-ons](https://addons.mozilla.org/developers/) | free | `wherefrom-firefox-*.zip` | Firefox |
| [Chrome Web Store](https://chrome.google.com/webstore/devconsole) | one-time $5 fee | `wherefrom-chromium-*.zip` | Chrome, Brave, Vivaldi, Edge |
| [Edge Add-ons](https://partner.microsoft.com/dashboard/microsoftedge/) | free | `wherefrom-chromium-*.zip` | Edge |

## Listing text (all stores)

**Name:** wherefrom

**Summary** (Chrome allows 132 characters):

> Remembers where each download came from, so the wherefrom app can tell you later, even after the file is renamed or moved.

**Description:**

> wherefrom answers "where did this file come from?" Right-click any file and see the link it was downloaded from, the page that link was on, and when, even after it's been renamed, moved, or copied to a USB stick.
>
> This extension is the browser half. When a download finishes, it tells the wherefrom program on your computer the final link (after redirects), the link you clicked, the page it was on and the file type. That covers downloads the browser leaves no note on.
>
> It needs the free wherefrom program, which keeps everything in a database on your own computer:
> https://github.com/andrew-hanzhou-li/wherefrom
> Install it, then run `wherefrom browser setup` once.
>
> Private by design: nothing leaves your computer. There's no server, account or analytics. It never sees the pages you browse, only finished downloads, and never anything from private or incognito windows. Open source (MIT).

**Category:** Tools (Chrome: Productivity → Tools; Firefox: Download Management)

**Homepage / support:** https://github.com/andrew-hanzhou-li/wherefrom

**Privacy policy URL:** https://github.com/andrew-hanzhou-li/wherefrom/blob/main/PRIVACY.md

**Images:** the 128px icon is in the package (`icons/icon-128.png`). Chrome also needs at least one 1280×800 (or 640×400) screenshot: the `wherefrom app` window or the "Where did this come from?" window showing a recent download works well.

## Chrome Web Store (and Edge) privacy tab

**Single purpose:**

> Tell the wherefrom program on the user's computer where each finished download came from, so the user can look up a file's source later.

**Permission justifications:**

- `downloads`: To notice when a download finishes and read its link, referrer, file path, type and size. Nothing is changed or started.
- `nativeMessaging`: To pass each finished download's details to the wherefrom program installed on the same computer. This is the only place they go.

**Remote code:** No, I am not using remote code.

**Data usage:** tick **Web history** (the download's link and the page it came from). Then tick all three certifications: not sold to third parties, not used for purposes unrelated to the single purpose, not used for creditworthiness or lending. The data stays on the user's computer, but declaring it is the safe reading of the form.

**Notes for the reviewer:**

> The extension works together with the open-source desktop program wherefrom (https://github.com/andrew-hanzhou-li/wherefrom), through native messaging. Without the program it does nothing and logs one console warning per download. To test it on Windows: run wherefrom-setup.exe from the latest GitHub release, then in a terminal `%LOCALAPPDATA%\Programs\wherefrom\wherefrom.exe browser setup --extension-id <this item's ID>`, download any file, and run `wherefrom.exe search <site>` from the same folder. The download is listed with "Known from: the wherefrom browser extension". The code is one unminified file, background.js.

## Firefox Add-ons

- Choose **On this site** (listed) to be found by others, or **On your own** (unlisted) to only get a signed file for yourself.
- Source code: not needed. Nothing is minified or built.
- The manifest declares `data_collection_permissions: none`, which Mozilla has required for new add-ons since November 2025. Nothing leaves the computer, so this is accurate. Firefox ESR 115 may show a harmless "Reading manifest" warning about this key.
- The add-on ID is fixed by the manifest (`wherefrom@andrew-hanzhou-li.github.io`), so the program already allows it. Nothing to change after approval.

## After Chrome or Edge approves it

The stores give the extension its own ID; the package carries no `key`, so it differs from the "Load unpacked" ID. Add each store's ID to `STORE_IDS` in `wherefrom/native.py` and release a new version, so `wherefrom browser setup` allows it without `--extension-id`. Until then, users of the store version run `wherefrom browser setup --extension-id <id>`.
