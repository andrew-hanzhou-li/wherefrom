"""Build the browser extension's store packages:

    dist/extension/wherefrom-chromium-<version>.zip   Chrome Web Store, Edge Add-ons
    dist/extension/wherefrom-firefox-<version>.zip    addons.mozilla.org

    python packaging/build_extension.py [output folder]

The Chromium package leaves out the manifest's "key": the Chrome Web Store
refuses a first upload that has one, and gives the extension its own ID. That
store ID then has to be allowed too (see native.STORE_IDS).
"""

import json
import sys
import zipfile
from importlib import resources
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wherefrom import __version__, native  # noqa: E402

KINDS = ("chromium", "firefox")
# A fixed time for every entry, so the same files always make the same zip
ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def store_manifest(kind):
    package = resources.files("wherefrom") / "extension"
    manifest = json.loads((package / f"manifest_{kind}.json").read_text(encoding="utf-8"))
    manifest.pop("key", None)
    if manifest["version"] != __version__:
        raise SystemExit(f"manifest_{kind}.json says version {manifest['version']}, "
                         f"but wherefrom is {__version__}; make them match")
    return manifest


def build(out_dir):
    """Write one zip per browser family into out_dir. Returns their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    package = resources.files("wherefrom") / "extension"
    built = []
    for kind in KINDS:
        manifest = store_manifest(kind)
        path = out_dir / f"wherefrom-{kind}-{__version__}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            def add(name, data):
                archive.writestr(zipfile.ZipInfo(name, ZIP_TIME), data, zipfile.ZIP_DEFLATED)
            add("manifest.json", json.dumps(manifest, indent=2) + "\n")
            for name in native.EXTENSION_FILES:
                add(name, package.joinpath(*name.split("/")).read_bytes())
        built.append(path)
    return built


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for path in build(argv[0] if argv else ROOT / "dist" / "extension"):
        print(path)


if __name__ == "__main__":
    main()
