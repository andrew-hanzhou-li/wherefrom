"""The store packages (packaging/build_extension.py) and the version numbers
a release has to keep in step."""

import importlib.util
import json
import struct
import tomllib
import zipfile
from importlib import resources
from pathlib import Path

from wherefrom import __version__, native

ROOT = Path(__file__).resolve().parent.parent


def load_builder():
    spec = importlib.util.spec_from_file_location("build_extension", ROOT / "packaging" / "build_extension.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_version_number_matches():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    package = resources.files("wherefrom") / "extension"
    manifests = {kind: json.loads((package / f"manifest_{kind}.json").read_text())["version"]
                 for kind in ("chromium", "firefox")}
    assert {project, *manifests.values()} == {__version__}, (project, manifests, __version__)


def test_icons_are_pngs_of_their_size():
    package = resources.files("wherefrom") / "extension"
    for name in native.EXTENSION_ICONS:
        data = package.joinpath(*name.split("/")).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", name
        width, height = struct.unpack(">II", data[16:24])
        size = int(name.rsplit("-", 1)[1].split(".")[0])
        assert (width, height) == (size, size), name


def test_store_packages(tmp_path):
    built = load_builder().build(tmp_path)
    assert [p.name for p in built] == [f"wherefrom-chromium-{__version__}.zip", f"wherefrom-firefox-{__version__}.zip"]
    for path in built:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))     # at the top, as the stores require
            assert names == {"manifest.json", *native.EXTENSION_FILES}
            # Every file the manifest names is in the package
            named = [*manifest["icons"].values(), *manifest["background"].get("scripts", [])]
            named += [manifest["background"]["service_worker"]] if "service_worker" in manifest["background"] else []
            assert set(named) <= names
    chromium = json.loads(zipfile.ZipFile(built[0]).read("manifest.json"))
    assert "key" not in chromium                                      # the Chrome Web Store refuses it
    firefox = json.loads(zipfile.ZipFile(built[1]).read("manifest.json"))
    gecko = firefox["browser_specific_settings"]["gecko"]
    assert gecko["id"] == native.FIREFOX_ID
    assert gecko["data_collection_permissions"] == {"required": ["none"]}   # needed by new AMO add-ons


def test_store_packages_are_reproducible(tmp_path):
    builder = load_builder()
    first = [p.read_bytes() for p in builder.build(tmp_path / "a")]
    second = [p.read_bytes() for p in builder.build(tmp_path / "b")]
    assert first == second


def test_store_ids_are_allowed_by_the_host(monkeypatch):
    monkeypatch.setattr(native, "STORE_IDS", ("storeidstoreidstoreidstoreidstor",))
    origins = native.host_manifest("chromium", "/x/h")["allowed_origins"]
    assert "chrome-extension://storeidstoreidstoreidstoreidstor/" in origins
    assert f"chrome-extension://{native.CHROMIUM_ID}/" in origins


def page_references(html):
    """Relative files an extension page loads (scripts, styles, images)."""
    import re
    refs = re.findall(r'<(?:script|img)[^>]*\ssrc="([^"]+)"', html) + re.findall(r'<link[^>]*\shref="([^"]+)"', html)
    return [r for r in refs if "://" not in r]


def test_every_extension_file_is_shipped_and_every_reference_exists():
    folder = resources.files("wherefrom") / "extension"
    on_disk = {p.name for p in Path(str(folder)).iterdir() if p.is_file() and not p.name.startswith("manifest_")}
    on_disk |= {f"icons/{p.name}" for p in (Path(str(folder)) / "icons").iterdir()}
    assert on_disk == set(native.EXTENSION_FILES), "native.EXTENSION_FILES must list every extension file"
    for kind in ("chromium", "firefox"):
        manifest = json.loads((folder / f"manifest_{kind}.json").read_text())
        pages = [manifest["action"]["default_popup"], "welcome.html"]
        for page in pages:
            assert page in native.EXTENSION_FILES
            html = (folder / page).read_text(encoding="utf-8")
            for ref in page_references(html):
                assert ref in native.EXTENSION_FILES, (page, ref)


def test_extension_pages_have_no_inline_scripts_or_remote_resources():
    import re
    folder = resources.files("wherefrom") / "extension"
    for name in native.EXTENSION_FILES:
        if not name.endswith(".html"):
            continue
        html = (folder / name).read_text(encoding="utf-8")
        # MV3 refuses inline scripts and handlers; every <script> must load a file
        assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>", html), name
        assert not re.search(r"\son[a-z]+=", html), name
        for ref in re.findall(r'<(?:script|img)[^>]*\ssrc="([^"]+)"|<link[^>]*\shref="([^"]+)"', html):
            ref = ref[0] or ref[1]
            assert "://" not in ref, (name, ref)            # nothing loaded from the web


def test_permissions_are_the_justified_few():
    folder = resources.files("wherefrom") / "extension"
    for kind in ("chromium", "firefox"):
        manifest = json.loads((folder / f"manifest_{kind}.json").read_text())
        assert manifest["permissions"] == ["downloads", "nativeMessaging", "storage", "alarms"]
        assert "host_permissions" not in manifest and "content_scripts" not in manifest


def test_a_pip_install_carries_every_extension_file():
    """pipx/pip installs get only what package-data names; a file left out
    breaks `wherefrom setup` on macOS and Linux."""
    import fnmatch
    patterns = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["package-data"]["wherefrom"]
    for name in (*native.EXTENSION_FILES, "manifest_chromium.json", "manifest_firefox.json"):
        assert any(fnmatch.fnmatch(f"extension/{name}", p) for p in patterns), name
