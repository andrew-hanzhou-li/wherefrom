import pytest

from wherefrom import app, gui
from wherefrom.ledger import Record


def record(**changes):
    base = dict(sha256="a" * 64, size=1, name="report.pdf", path="/d/report.pdf",
                host_url="https://cdn.example.com/f/report.pdf", referrer_url="https://www.example.com/page",
                zone_id=3, source="chrome", downloaded_at="2026-11-20T14:03:00", recorded_at="2026-11-21T00:00:00")
    base.update(changes)
    return Record(**base)


def test_site_of():
    assert app.site_of("https://www.example.com/a") == "example.com"
    assert app.site_of("https://cdn.example.com/a") == "cdn.example.com"
    assert app.site_of(None) == "" and app.site_of("not a url") == ""


def test_rows():
    rows = app.rows_for([record(), record(host_url=None, path="/gone.pdf", downloaded_at=None)],
                        exists=lambda p: p != "/gone.pdf")
    assert rows[0] == ("2026-11-20 14:03", "report.pdf", "cdn.example.com", "")
    assert rows[1] == ("2026-11-21 00:00", "report.pdf", "example.com", "not here any more")


def test_details_and_links():
    r = record(original_url="https://short.test/x", mime="application/pdf", source="extension")
    labels = [label for label, _ in app.details_for(r)]
    assert labels == ["Downloaded from", "On the page", "First asked for", "Saved as", "Known from", "File type"]
    assert dict(app.details_for(r))["Known from"] == "the wherefrom browser extension"
    assert app.page_link(r) == "https://www.example.com/page"
    assert app.page_link(record(referrer_url="javascript:alert(1)")) == "https://cdn.example.com/f/report.pdf"
    assert app.page_link(record(referrer_url=None, host_url="file:///etc/passwd")) is None


def test_reveal_commands():
    assert app.reveal_command("C:\\d\\a b.pdf", "win32") == ["explorer", "/select,C:\\d\\a b.pdf"]
    assert app.reveal_command("/u/a b.pdf", "darwin") == ["open", "-R", "/u/a b.pdf"]
    assert app.reveal_command("/home/u/a b.pdf", "linux") == ["xdg-open", "/home/u"]


def test_reveal_does_nothing_for_a_missing_file(monkeypatch):
    started = []
    monkeypatch.setattr(app.subprocess, "Popen", lambda args: started.append(args))
    app.reveal("/no/such/file.pdf")
    assert started == []


def test_summary():
    assert "Nothing recorded yet" in app.summary(0, 0, "")
    assert app.summary(12, 12, "") == "12 files recorded"
    assert app.summary(1000, 5000, "") == "5000 files recorded, newest 1000 shown"
    assert app.summary(3, 5000, "canvas") == "3 of 5000 files match"
    assert app.summary(1000, 5000, "e") == "1000 of 5000 files match (first 1000)"


def test_window_opens_lists_and_searches(tmp_path, ledger, monkeypatch):
    tkinter = pytest.importorskip("tkinter")
    try:
        gui.new_window().destroy()      # retries Windows' Tcl startup hiccup
    except tkinter.TclError:
        pytest.skip("no display")
    from tkinter import ttk
    f = tmp_path / "syllabus.pdf"
    f.write_bytes(b"x")
    ledger.add("b" * 64, 1, f, source="edge", host_url="https://canvas.test/files/1")
    ledger.add("c" * 64, 1, tmp_path / "photo.jpg", source="mark", host_url="https://photos.test/p.jpg")
    seen = {}

    def mainloop(self):
        self.update()
        def widgets(w):
            for child in w.winfo_children():
                yield child
                yield from widgets(child)
        table = next(w for w in widgets(self) if isinstance(w, ttk.Treeview))
        entry = next(w for w in widgets(self) if isinstance(w, ttk.Entry))
        seen["all"] = len(table.get_children())
        entry.insert(0, "canvas")
        self.after(300, self.quit)          # past the typing pause
        real(self)                          # run the real loop until quit()
        seen["found"] = [table.item(i)["values"][1] for i in table.get_children()]
        self.destroy()

    real = tkinter.Misc.mainloop
    monkeypatch.setattr(tkinter.Tk, "mainloop", mainloop)
    app.run(ledger)
    assert seen == {"all": 2, "found": ["syllabus.pdf"]}


def test_the_list_is_actually_visible(tmp_path, ledger, monkeypatch):
    # The rows can exist while another widget covers them; check what's on top
    tkinter = pytest.importorskip("tkinter")
    try:
        gui.new_window().destroy()      # retries Windows' Tcl startup hiccup
    except tkinter.TclError:
        pytest.skip("no display")
    from tkinter import ttk
    ledger.add("b" * 64, 1, tmp_path / "a.pdf", source="edge", host_url="https://canvas.test/files/1")
    seen = {}

    def mainloop(self):
        self.update()
        def widgets(w):
            for child in w.winfo_children():
                yield child
                yield from widgets(child)
        table = next(w for w in widgets(self) if isinstance(w, ttk.Treeview))
        x = table.winfo_rootx() + table.winfo_width() // 2
        y = table.winfo_rooty() + 40
        seen["on top"] = self.winfo_containing(x, y)
        seen["table"] = table
        self.destroy()

    monkeypatch.setattr(tkinter.Tk, "mainloop", mainloop)
    app.run(ledger)
    assert seen["on top"] is seen["table"]
