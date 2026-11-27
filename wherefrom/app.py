"""The wherefrom window: browse and search every recorded download.

The pieces that decide what to show (rows, site names, the "show in folder"
command) are plain functions, tested without a screen; the window itself
only lays them out.
"""

import os
import subprocess
import sys
import webbrowser
from urllib.parse import urlparse

from .cli import when
from .ledger import SOURCE_NAMES
from .lookup import openable

MAX_ROWS = 1000


def site_of(url):
    """'https://www.example.com/a/b' -> 'example.com'."""
    if not url:
        return ""
    host = urlparse(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def rows_for(records, exists=os.path.isfile):
    """One row per record for the list: (date, name, site, status)."""
    rows = []
    for record in records:
        site = site_of(record.host_url) or site_of(record.referrer_url)
        status = "" if exists(record.path) else "not here any more"
        rows.append((when(record.downloaded_at or record.recorded_at), record.name, site, status))
    return rows


def details_for(record):
    """(label, value) pairs for the details under the list."""
    pairs = [("Downloaded from", record.host_url or ""), ("On the page", record.referrer_url or "")]
    if record.original_url:
        pairs.append(("First asked for", record.original_url))
    pairs += [("Saved as", record.path), ("Known from", SOURCE_NAMES.get(record.source, record.source))]
    if record.mime:
        pairs.append(("File type", record.mime))
    return pairs


def page_link(record):
    """The link "Open page" opens: the page if it's a web page, else the file's own."""
    for url in (record.referrer_url, record.host_url):
        if openable(url):
            return url
    return None


def reveal_command(path, platform=None):
    """The command that shows a file selected in the system's file manager."""
    platform = platform or sys.platform
    if platform == "win32":
        return ["explorer", f"/select,{path}"]
    if platform == "darwin":
        return ["open", "-R", path]
    return ["xdg-open", os.path.dirname(path)]     # Linux file managers can't all select a file


def reveal(path):
    if os.path.isfile(path):
        # A list of arguments, never a shell: the path is only ever a path
        subprocess.Popen(reveal_command(path))  # nosec B603


def summary(shown, total, text):
    if not total:
        return "Nothing recorded yet. Run \"wherefrom import-browsers\", or keep \"wherefrom watch\" running."
    if text:
        more = f" (first {MAX_ROWS})" if shown >= MAX_ROWS else ""
        return f"{shown} of {total} files match{more}"
    return f"{total} files recorded" + (f", newest {MAX_ROWS} shown" if total > MAX_ROWS else "")


def run(ledger):
    import tkinter as tk
    from tkinter import ttk

    from .gui import new_window
    root = new_window()
    root.title("wherefrom")
    root.geometry("980x620")
    root.minsize(640, 420)
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    elif "aqua" in style.theme_names():
        style.theme_use("aqua")

    outer = ttk.Frame(root, padding=12)
    outer.pack(fill="both", expand=True)

    top = ttk.Frame(outer)
    top.pack(fill="x")
    ttk.Label(top, text="Search").pack(side="left")
    query = tk.StringVar()
    search = ttk.Entry(top, textvariable=query)
    search.pack(side="left", fill="x", expand=True, padx=(8, 12))
    status = ttk.Label(top, foreground="#555")
    status.pack(side="right")

    # The list and its scrollbar are children of their own frame: a widget
    # packed into a frame created after it would be drawn behind that frame.
    middle = ttk.Frame(outer)
    middle.pack(fill="both", expand=True, pady=10)
    columns = ("date", "name", "site", "status")
    table = ttk.Treeview(middle, columns=columns, show="headings", selectmode="browse")
    for column, title, width, stretch in (("date", "Downloaded", 130, False), ("name", "File", 360, True),
                                          ("site", "Site", 200, True), ("status", "", 130, False)):
        table.heading(column, text=title, anchor="w")
        table.column(column, width=width, stretch=stretch, anchor="w")
    scroll = ttk.Scrollbar(middle, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    details = ttk.Frame(outer)
    details.pack(fill="x")
    details.columnconfigure(1, weight=1)
    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(10, 0))
    open_button = ttk.Button(buttons, text="Open page")
    copy_button = ttk.Button(buttons, text="Copy link")
    folder_button = ttk.Button(buttons, text="Show in folder")
    for button in (folder_button, copy_button, open_button):
        button.pack(side="right", padx=(8, 0))
        button.state(["disabled"])

    shown = []                      # records currently in the table, in order

    def show_details(record):
        for child in details.winfo_children():
            child.destroy()
        for row, (label, value) in enumerate(details_for(record)):
            ttk.Label(details, text=label, foreground="#555").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=2)
            field = ttk.Entry(details)
            field.insert(0, value)
            field.configure(state="readonly")
            field.grid(row=row, column=1, sticky="ew", pady=2)
        link = page_link(record)
        open_button.configure(command=lambda: webbrowser.open(link) if link else None)
        open_button.state(["!disabled"] if link else ["disabled"])

        def copy():
            root.clipboard_clear()
            root.clipboard_append(record.host_url or record.referrer_url or "")
        copy_button.configure(command=copy)
        copy_button.state(["!disabled"] if (record.host_url or record.referrer_url) else ["disabled"])
        folder_button.configure(command=lambda: reveal(record.path))
        folder_button.state(["!disabled"] if os.path.isfile(record.path) else ["disabled"])

    def refresh(*_):
        text = query.get().strip()
        records = ledger.search(text, limit=MAX_ROWS)
        table.delete(*table.get_children())
        shown[:] = records
        for index, row in enumerate(rows_for(records)):
            table.insert("", "end", iid=str(index), values=row)
        status.configure(text=summary(len(records), ledger.count(), text))
        for child in details.winfo_children():
            child.destroy()
        for button in (open_button, copy_button, folder_button):
            button.state(["disabled"])
        if records:
            table.selection_set("0")

    def on_select(_event):
        selected = table.selection()
        if selected:
            show_details(shown[int(selected[0])])

    pending = []

    def search_soon(*_):
        # Wait for a short pause in typing instead of searching on every key
        for job in pending:
            root.after_cancel(job)
        pending[:] = [root.after(200, refresh)]

    query.trace_add("write", search_soon)
    table.bind("<<TreeviewSelect>>", on_select)
    table.bind("<Return>", lambda e: open_button.invoke())
    table.bind("<Double-1>", lambda e: open_button.invoke())
    root.bind("<Control-f>", lambda e: search.focus_set())
    root.bind("<Escape>", lambda e: query.set(""))
    refresh()
    search.focus_set()
    root.mainloop()
