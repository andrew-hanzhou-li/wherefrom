"""The small window opened from Explorer's right-click menu."""

import os
import webbrowser

from .cli import SOURCE_NAMES, when
from .lookup import openable


def rows_for(finding):
    """(label, value) pairs to show, in order."""
    if finding.error:
        return [("", finding.error)]
    if not finding.known:
        return [("", "No record of where this file came from.\n"
                     "It has no Mark of the Web, and wherefrom hasn't seen these contents before.")]
    rows = []
    if finding.host_url:
        rows.append(("Downloaded from", finding.host_url))
    if finding.page_url:
        rows.append(("On the page", finding.page_url))
    first = finding.first
    if first:
        rows.append(("First seen", f"{when(first.downloaded_at or first.recorded_at)}, as {first.path}"))
        rows.append(("Known from", SOURCE_NAMES.get(first.source, first.source)))
    for copy in finding.other_copies:
        rows.append(("Same file at", copy))
    return rows


def show(finding):
    # Imported here so the rest of wherefrom works on Pythons without Tk
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Where did this come from?")
    root.minsize(520, 0)
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")        # looks like the rest of Windows

    frame = ttk.Frame(root, padding=16)
    frame.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    title = ttk.Label(frame, text=os.path.basename(finding.path), font=("Segoe UI", 11, "bold"))
    title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

    for row, (label, value) in enumerate(rows_for(finding), start=1):
        if label:
            ttk.Label(frame, text=label, foreground="#555").grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=3)
            # A read-only entry, so the text can be selected and copied
            field = ttk.Entry(frame)
            field.insert(0, value)
            field.configure(state="readonly")
            field.grid(row=row, column=1, sticky="ew", pady=3)
        else:
            ttk.Label(frame, text=value, wraplength=480, justify="left").grid(
                row=row, column=0, columnspan=2, sticky="w")

    buttons = ttk.Frame(frame)
    buttons.grid(row=99, column=0, columnspan=2, sticky="e", pady=(14, 0))
    link = finding.page_url if openable(finding.page_url) else finding.host_url
    if openable(link):
        ttk.Button(buttons, text="Open page",
                   command=lambda: webbrowser.open(link)).pack(side="left", padx=(0, 8))

        def copy_link():
            root.clipboard_clear()
            root.clipboard_append(finding.host_url or link)
        ttk.Button(buttons, text="Copy link", command=copy_link).pack(side="left", padx=(0, 8))
    close = ttk.Button(buttons, text="Close", command=root.destroy)
    close.pack(side="left")
    close.focus_set()
    root.bind("<Escape>", lambda event: root.destroy())
    root.bind("<Return>", lambda event: root.destroy())
    root.mainloop()
