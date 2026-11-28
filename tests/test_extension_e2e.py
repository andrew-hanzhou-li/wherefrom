"""The whole chain in a real Chromium: the unpacked extension sees a download
finish, the browser starts wherefrom's native host, and the ledger gets it;
plus the popup, the welcome page, waiting downloads and skipped sites.

Needs Python Playwright and a Chromium that can load extensions (not the
headless shell); skipped otherwise, except on CI, where that's a failure.
Set WHEREFROM_CHROMIUM to a browser path if Playwright's own isn't
installed, and WHEREFROM_SCREENSHOTS to a folder to keep screenshots of the
popup and the welcome page.
"""
import contextlib
import http.server
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from wherefrom import native
from wherefrom.ledger import Ledger

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(sys.platform != "linux" and not os.environ.get("CI"), reason="drives a real browser")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POPUP = f"chrome-extension://{native.CHROMIUM_ID}/popup.html"


class Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/page"):
            body = b'<a id="get" href="/redirect">Get the report</a>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/files/report.csv")
            self.end_headers()
            return
        else:
            body = f"a,b\n1,{time.time_ns()}\n".encode()        # different contents every time
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="report.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()


class Browser:
    """A Chromium with the extension loaded, its own profile, and wherefrom's
    host set up (or not, until `connect()`)."""

    def __init__(self, p, tmp_path, connected=True):
        self.home, self.profile, self.data = tmp_path / "home", tmp_path / "profile", tmp_path / "data"
        (self.home / ".config" / "chromium").mkdir(parents=True)
        self.summary = native.setup("linux" if sys.platform.startswith("linux") else sys.platform, self.home, self.data,
                                    cmd=[sys.executable, "-P", "-m", "wherefrom", "native-host"],
                                    env={"WHEREFROM_HOME": str(self.data)})
        # setup also registered the host for the home folder's Chromium; keep only the
        # profile's copy, so "not connected" really means not found
        for registered in self.summary["registered"]:
            Path(registered).unlink()
        (self.profile / "NativeMessagingHosts").mkdir(parents=True)
        if connected:
            self.connect()
        extension = str(self.summary["extensions"]["chromium"])
        env = {**os.environ, "HOME": str(self.home), "WHEREFROM_HOME": str(self.data), "PYTHONPATH": REPO}
        options = dict(headless=False, env=env, accept_downloads=True, downloads_path=str(tmp_path / "dl"),
                       args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"])
        if os.environ.get("WHEREFROM_CHROMIUM"):
            options["executable_path"] = os.environ["WHEREFROM_CHROMIUM"]
        try:
            self.context = p.chromium.launch_persistent_context(str(self.profile), **options)
        except Exception as error:          # no display, or no browser that loads extensions
            if os.environ.get("CI"):
                raise
            pytest.skip(f"can't start a browser with extensions: {error}")
        self.ledger = Ledger(self.data / "ledger.sqlite3")

    def connect(self):
        """Register wherefrom's host where this browser looks (its profile folder)."""
        (self.profile / "NativeMessagingHosts" / f"{native.HOST_NAME}.json").write_text(
            self.summary["manifests"]["chromium"].read_text())

    def download(self, url):
        page = self.context.new_page()
        page.goto(url)
        with page.expect_download() as info:
            page.click("#get")
        saved = info.value.path()           # wait until it's saved
        page.close()
        return Path(saved).name             # Playwright saves under its own (random) name

    def records(self, count=1, seconds=15):
        records = []
        deadline = time.time() + seconds
        while time.time() < deadline:      # the host runs in its own process; give it a moment
            records = self.ledger.all_records()
            if len(records) >= count:
                break
            time.sleep(0.2)
        return records

    def popup(self):
        page = self.context.new_page()
        page.set_viewport_size({"width": 360, "height": 640})
        page.goto(POPUP)
        return page

    def worker(self):
        if self.context.service_workers:
            return self.context.service_workers[0]
        return self.context.wait_for_event("serviceworker", timeout=10000)

    def open_tabs(self, page):
        """This extension's pages open in tabs, asked of Chrome itself:
        Playwright doesn't list tabs an extension opens on its own."""
        return self.worker().evaluate(
            "chrome.runtime.getContexts({contextTypes: ['TAB']}).then(cs => cs.map(c => c.documentUrl))"
            f".then(urls => urls.filter(u => u && u.endsWith('/{page}')))")

    def stored(self):
        """What the extension keeps (for messages when a test fails)."""
        try:
            return self.worker().evaluate("chrome.storage.local.get(null)")
        except Exception as error:
            return f"(couldn't read: {error})"

    def close(self):
        self.ledger.close()
        self.context.close()


def screenshot(page, name):
    folder = os.environ.get("WHEREFROM_SCREENSHOTS")
    if not folder:
        return
    Path(folder).mkdir(parents=True, exist_ok=True)
    for scheme in ("light", "dark"):
        page.emulate_media(color_scheme=scheme)
        page.wait_for_timeout(200)
        page.screenshot(path=str(Path(folder) / f"{name}-{scheme}.png"), full_page=True)
    page.emulate_media(color_scheme="light")


def test_a_real_download_reaches_the_ledger_and_the_popup(tmp_path):
    with site() as port, playwright.sync_playwright() as p:
        base = f"http://127.0.0.1:{port}"
        browser = Browser(p, tmp_path)
        try:
            name = browser.download(base + "/page")
            records = browser.records()
            assert len(records) == 1, "the extension's message never reached the ledger"
            record = records[0]
            assert record.source == "extension"
            assert record.host_url == base + "/files/report.csv"         # after the redirect
            assert record.original_url == base + "/redirect"
            assert record.referrer_url == base + "/page"
            assert record.mime == "text/csv"

            # Connected at install: no welcome tab
            assert browser.open_tabs("welcome.html") == []
            popup = browser.popup()
            playwright.expect(popup.locator("#status")).to_contain_text("Recording downloads", timeout=15000)
            playwright.expect(popup.locator("#status")).to_contain_text("Connected to wherefrom")
            playwright.expect(popup.locator("#recent li")).to_have_count(1)
            playwright.expect(popup.locator("#recent li").first).to_contain_text(name)
            playwright.expect(popup.locator("#recent li").first).to_contain_text("127.0.0.1")
            playwright.expect(popup.locator("#recent li .chip").first).to_have_text("Recorded")
            screenshot(popup, "popup-connected")

            # Pausing: the icon says "off" and new downloads aren't sent
            popup.locator("#record").click()
            playwright.expect(popup.locator("#status")).to_contain_text("Paused")
            screenshot(popup, "popup-paused")
            browser.download(base + "/page")
            time.sleep(3)
            assert len(browser.ledger.all_records()) == 1, "a download was recorded while paused"
            popup.locator("#record").click()
            playwright.expect(popup.locator("#status")).to_contain_text("Recording downloads", timeout=15000)
        finally:
            browser.close()


def test_downloads_wait_until_wherefrom_is_there(tmp_path):
    with site() as port, playwright.sync_playwright() as p:
        browser = Browser(p, tmp_path, connected=False)
        try:
            # Installed without wherefrom: the welcome page opens by itself
            opened = []
            deadline = time.time() + 30
            while time.time() < deadline and not opened:
                opened = browser.open_tabs("welcome.html")
                time.sleep(0.5)
            assert opened, f"the welcome page didn't open; stored: {browser.stored()}"
            welcome = browser.context.new_page()           # a copy Playwright can drive
            welcome.set_viewport_size({"width": 900, "height": 900})
            welcome.goto(f"chrome-extension://{native.CHROMIUM_ID}/welcome.html")
            playwright.expect(welcome.locator("#status")).to_contain_text("isn't set up", timeout=15000)
            screenshot(welcome, "welcome")

            browser.download(f"http://127.0.0.1:{port}/page")
            popup = browser.popup()
            playwright.expect(popup.locator("#status")).to_contain_text("isn't set up", timeout=15000)
            playwright.expect(popup.locator("#recent li .chip").first).to_have_text("Waiting")
            playwright.expect(popup.locator("#dropped")).to_contain_text("1 download is waiting")
            screenshot(popup, "popup-not-set-up")
            assert browser.ledger.all_records() == []

            # wherefrom appears; "Check again" sends what was waiting
            browser.connect()
            popup.get_by_role("button", name="Check again").click()
            playwright.expect(popup.locator("#status")).to_contain_text("Recording downloads", timeout=15000)
            playwright.expect(popup.locator("#recent li .chip").first).to_have_text("Recorded")
            assert len(browser.records()) == 1
            # and the welcome page notices on its own
            playwright.expect(welcome.locator("h1")).to_have_text("You're all set", timeout=15000)
        finally:
            browser.close()


def test_a_skipped_site_is_not_recorded_but_others_are(tmp_path):
    with site() as port, playwright.sync_playwright() as p:
        browser = Browser(p, tmp_path)
        try:
            popup = browser.popup()
            playwright.expect(popup.locator("#status")).to_contain_text("Recording downloads", timeout=15000)
            popup.locator("#sites summary").click()
            popup.locator("#site").fill("http://localhost/whatever")
            popup.locator("#add-site button").click()
            playwright.expect(popup.locator("#excluded li")).to_have_count(1)
            playwright.expect(popup.locator("#excluded li").first).to_contain_text("localhost")
            screenshot(popup, "popup-sites")

            browser.download(f"http://localhost:{port}/page")      # skipped
            browser.download(f"http://127.0.0.1:{port}/page")      # recorded
            records = browser.records()
            time.sleep(2)                                           # the skipped one would have arrived by now
            records = browser.ledger.all_records()
            assert [r.host_url for r in records] == [f"http://127.0.0.1:{port}/files/report.csv"]
            playwright.expect(popup.locator("#recent li")).to_have_count(1)  # skipped downloads aren't listed either

            # A typo is refused with a reason
            popup.locator("#site").fill("not a site")
            popup.locator("#add-site button").click()
            playwright.expect(popup.locator("#site-error")).to_contain_text("doesn't look like a site")
        finally:
            browser.close()
