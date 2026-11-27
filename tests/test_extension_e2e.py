"""The whole chain in a real Chromium: the unpacked extension sees a download
finish, the browser starts wherefrom's native host, and the ledger gets it.

Needs Python Playwright and a Chromium that can load extensions (not the
headless shell); skipped otherwise. Set WHEREFROM_CHROMIUM to a browser path
if Playwright's own isn't installed.
"""
import http.server
import os
import sys
import threading
import time

import pytest

from wherefrom import native
from wherefrom.ledger import Ledger

playwright = pytest.importorskip("playwright.sync_api")


class Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/page":
            body = b'<a id="get" href="/redirect">Get the report</a>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/files/report.csv")
            self.end_headers()
            return
        else:
            body = b"a,b\n1,2\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="report.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.mark.skipif(sys.platform != "linux" and not os.environ.get("CI"), reason="drives a real browser")
def test_a_real_download_reaches_the_ledger(tmp_path):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    home, profile, data = tmp_path / "home", tmp_path / "profile", tmp_path / "data"
    (home / ".config" / "chromium").mkdir(parents=True)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    summary = native.setup("linux" if sys.platform.startswith("linux") else sys.platform, home, data,
                           cmd=[sys.executable, "-P", "-m", "wherefrom", "native-host"])
    # A browser run with --user-data-dir looks for hosts in that folder too
    (profile / "NativeMessagingHosts").mkdir(parents=True)
    (profile / "NativeMessagingHosts" / f"{native.HOST_NAME}.json").write_text(
        summary["manifests"]["chromium"].read_text())
    extension = str(summary["extensions"]["chromium"])
    env = {**os.environ, "HOME": str(home), "WHEREFROM_HOME": str(data), "PYTHONPATH": repo}

    with playwright.sync_playwright() as p:
        options = dict(headless=False, env=env, accept_downloads=True, downloads_path=str(tmp_path / "dl"),
                       args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"])
        if os.environ.get("WHEREFROM_CHROMIUM"):
            options["executable_path"] = os.environ["WHEREFROM_CHROMIUM"]
        try:
            context = p.chromium.launch_persistent_context(str(profile), **options)
        except Exception as error:          # no display, or no browser that loads extensions
            pytest.skip(f"can't start a browser with extensions: {error}")
        page = context.new_page()
        page.goto(base + "/page")
        with page.expect_download() as info:
            page.click("#get")
        info.value.path()                   # wait until it's saved
        ledger = Ledger(data / "ledger.sqlite3")
        records = []
        for _ in range(100):                # the host runs in its own process; give it a moment
            records = ledger.all_records()
            if records:
                break
            time.sleep(0.1)
        context.close()
    server.shutdown()
    assert len(records) == 1, "the extension's message never reached the ledger"
    record = records[0]
    assert record.source == "extension"
    assert record.host_url == base + "/files/report.csv"         # after the redirect
    assert record.original_url == base + "/redirect"
    assert record.referrer_url == base + "/page"
    assert record.mime == "text/csv"
