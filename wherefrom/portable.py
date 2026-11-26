"""Moving records between computers: whole-ledger exports, and sidecar files
that travel with a single file.

A sidecar is a small JSON file named after the file it describes
("report.pdf.wherefrom.json"). It carries the file's SHA-256, so it only ever
applies to those exact bytes, whatever the file is called later.

Exports and sidecars can come from other people, so everything read from
them is checked: size limits, types, and URL lengths. A record learned this
way is marked as such, and only http(s) links are ever offered to open.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from .watch import file_hash

EXPORT_FORMAT = "wherefrom-ledger"
SIDECAR_FORMAT = "wherefrom-sidecar"
SIDECAR_SUFFIX = ".wherefrom.json"
VERSION = 1

MAX_SIDECAR_BYTES = 64 * 1024
MAX_EXPORT_BYTES = 200 * 1024 * 1024
MAX_TEXT = 8192                     # longest URL, name or path accepted
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TEXT_FIELDS = ("name", "path", "host_url", "referrer_url", "source", "downloaded_at",
               "recorded_at", "mime", "original_url")


class BadFile(ValueError):
    """An export or sidecar that isn't one, or is damaged."""


def record_to_dict(record):
    return {
        "sha256": record.sha256, "size": record.size, "name": record.name, "path": record.path,
        "host_url": record.host_url, "referrer_url": record.referrer_url,
        "zone_id": record.zone_id, "source": record.source,
        "downloaded_at": record.downloaded_at, "recorded_at": record.recorded_at,
        "mime": record.mime, "original_url": record.original_url,
    }


def clean_entry(entry):
    """Check one record from an export or sidecar; returns a safe dict or None."""
    if not isinstance(entry, dict):
        return None
    sha256 = entry.get("sha256")
    size = entry.get("size")
    if not isinstance(sha256, str) or not SHA256.match(sha256):
        return None
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        return None
    clean = {"sha256": sha256, "size": size}
    for field in TEXT_FIELDS:
        value = entry.get(field)
        if value is None:
            clean[field] = None
        elif isinstance(value, str) and len(value) <= MAX_TEXT and "\x00" not in value:
            clean[field] = value
        else:
            return None
    zone_id = entry.get("zone_id")
    clean["zone_id"] = zone_id if isinstance(zone_id, int) and not isinstance(zone_id, bool) else None
    if not (clean["host_url"] or clean["referrer_url"]):
        return None
    return clean


def add_entry(ledger, entry, source, path=None):
    """Put a checked entry into the ledger. `source` says how it arrived."""
    return ledger.add(entry["sha256"], entry["size"], path or entry["path"] or entry["name"] or "?",
                      source=source, downloaded_at=entry["downloaded_at"],
                      host_url=entry["host_url"], referrer_url=entry["referrer_url"],
                      mime=entry["mime"], original_url=entry["original_url"],
                      name=entry["name"])


# ---------------- Whole-ledger export / import ----------------

def export(ledger, target):
    """Write every record to a JSON file. Returns how many."""
    records = [record_to_dict(r) for r in ledger.all_records()]
    data = {"format": EXPORT_FORMAT, "version": VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"), "records": records}
    tmp = Path(str(target) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, target)             # never leave a half-written export
    return len(records)


def import_file(ledger, source_file):
    """Merge an export into the ledger. Returns (new, skipped as invalid).
    Records already there are kept once."""
    if os.path.getsize(source_file) > MAX_EXPORT_BYTES:
        raise BadFile("too big to be a wherefrom export")
    try:
        with open(source_file, encoding="utf-8") as f:
            data = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BadFile(f"not a wherefrom export ({error})") from error
    if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
        raise BadFile("not a wherefrom export")
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        raise BadFile("made by a newer wherefrom; update to import it")
    new = invalid = 0
    for entry in data.get("records") or []:
        clean = clean_entry(entry)
        if clean is None:
            invalid += 1
            continue
        # Keep the original source and dates: it was e.g. Chrome's history
        # on the other computer; the import itself is only the transport.
        if ledger.add(clean["sha256"], clean["size"], clean["path"] or clean["name"] or "?",
                      source=clean["source"] or "import", downloaded_at=clean["downloaded_at"],
                      host_url=clean["host_url"], referrer_url=clean["referrer_url"],
                      mime=clean["mime"], original_url=clean["original_url"],
                      recorded_at=clean["recorded_at"], name=clean["name"]):
            new += 1
    return new, invalid


# ---------------- Sidecars ----------------

def sidecar_path(path):
    return Path(str(path) + SIDECAR_SUFFIX)


def write_sidecar(path, record):
    """Write the sidecar for one file from one of its records."""
    data = {"format": SIDECAR_FORMAT, "version": VERSION, **record_to_dict(record)}
    data["path"] = None             # where it was on this computer means nothing elsewhere
    target = sidecar_path(path)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return target


def read_sidecar(sidecar):
    """A checked entry from a sidecar file, or None."""
    try:
        if os.path.getsize(sidecar) > MAX_SIDECAR_BYTES:
            return None
        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("format") != SIDECAR_FORMAT:
        return None
    return clean_entry(data)


def sidecars_for(path, sha256, limit=500):
    """Checked sidecar entries that describe these bytes: the file's own
    sidecar, and any in the same folder (the file may have been renamed
    without its sidecar)."""
    path = Path(path)
    found = []
    candidates = [sidecar_path(path)]
    try:
        with os.scandir(path.parent) as entries:
            for entry in entries:
                if len(candidates) > limit:
                    break
                if entry.name.endswith(SIDECAR_SUFFIX) and entry.path != str(candidates[0]):
                    candidates.append(Path(entry.path))
    except OSError:
        pass
    for candidate in candidates:
        if candidate.is_file():
            entry = read_sidecar(candidate)
            if entry and entry["sha256"] == sha256:
                found.append(entry)
    return found


def make_sidecars(ledger, paths):
    """Write sidecars for files the ledger knows. Returns (written, unknown)."""
    written, unknown = [], []
    for path in paths:
        try:
            sha256, _ = file_hash(path)
        except OSError:
            unknown.append(path)
            continue
        records = ledger.by_hash(sha256)
        if not records:
            unknown.append(path)
            continue
        written.append(write_sidecar(path, records[0]))
    return written, unknown
