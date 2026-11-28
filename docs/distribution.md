# Getting wherefrom to people

Every release (pushing a `v*` tag, see the README's "Releasing") already publishes a GitHub Release with the Windows installer, the standalone programs, both store packages and checksums. The README's download link always points at the newest installer.

Three more channels are built into CI and switched off until you set them up once. Each needs an account or key that only you can create, so CI can't do it alone. After the setup, each runs by itself on every release.

| Channel | What people get | One-time setup | Switch |
|---|---|---|---|
| PyPI | `pipx install wherefrom` | Trusted publisher on pypi.org (no token) | variable `PYPI_PUBLISH` = `true` |
| Firefox, signed | An `.xpi` on each release that Firefox keeps after a restart | addons.mozilla.org API key | variable `AMO_SIGN` = `true`, secrets `AMO_JWT_ISSUER`, `AMO_JWT_SECRET` |
| winget updates | `winget upgrade` picks up each release | A GitHub token | variable `WINGET_UPDATE` = `true`, secret `WINGET_TOKEN` |

Variables and secrets live in the repository's **Settings > Secrets and variables > Actions** (the **Variables** and **Secrets** tabs).

## PyPI

1. Sign in at https://pypi.org (create an account if needed; turn on two-factor sign-in, which PyPI requires).
2. **Your account > Publishing > Add a new pending publisher**, GitHub tab:
   - PyPI project name: `wherefrom` (it was free as of 2026-11-28)
   - Owner: `andrew-hanzhou-li`, Repository: `wherefrom`
   - Workflow name: `ci.yml`, Environment name: `pypi`
3. Set the variable `PYPI_PUBLISH` to `true`.

The next release publishes to PyPI with no password or token stored anywhere. Then the README's macOS/Linux install can become `pipx install wherefrom`.

## Firefox (signed, unlisted)

1. Sign in at https://addons.mozilla.org/developers/ and open **Manage API Keys** (https://addons.mozilla.org/developers/addon/api/key/).
2. Generate credentials. Add the **JWT issuer** as secret `AMO_JWT_ISSUER` and the **JWT secret** as secret `AMO_JWT_SECRET`.
3. Set the variable `AMO_SIGN` to `true`.

Each release then gets `wherefrom-firefox-<version>.xpi`, signed by Mozilla. Opening it in Firefox (or dragging it onto a Firefox window) installs it for good. "Unlisted" means it isn't in the public add-on catalog. A public listing is a separate, manual submission (see [store-listing.md](store-listing.md)).

## winget updates

Turn this on only after the first winget submission ([microsoft/winget-pkgs#490652](https://github.com/microsoft/winget-pkgs/pull/490652)) is merged; it updates an existing package.

1. Create a classic personal access token with the `public_repo` scope (GitHub > Settings > Developer settings > Personal access tokens > Tokens (classic)). It must belong to the account that owns the `winget-pkgs` fork (`andrew-hanzhou-li`).
2. Add it as secret `WINGET_TOKEN`.
3. Set the variable `WINGET_UPDATE` to `true`.

Each release then opens a winget update PR from your fork, the same kind as the first submission.

## Stores (manual)

The Chrome Web Store and Edge Add-ons have no switch here: each listing is a form you fill in once (text in [store-listing.md](store-listing.md)), then you upload the new `wherefrom-chromium-<version>.zip` from each release. When a store approves the extension, add its ID to `STORE_IDS` in `wherefrom/native.py`.

## Not tested yet

These three jobs only run once switched on, so they haven't run yet. If one fails on its first release, the GitHub Release itself is already published (they run after it), so fix the job and re-run it from the Actions tab.
