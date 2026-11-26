import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wherefrom.ledger import Ledger  # noqa: E402
from wherefrom.zone import Mark  # noqa: E402


@pytest.fixture
def ledger(tmp_path):
    db = Ledger(tmp_path / "ledger.sqlite3")
    yield db
    db.close()


@pytest.fixture(autouse=True)
def private_home(tmp_path, monkeypatch):
    """Never touch a real ledger, even when a test calls main()."""
    monkeypatch.setenv("WHEREFROM_HOME", str(tmp_path / "home"))


class FakeMarks:
    """Stands in for zone.read: marks by file name, and counts the reads."""

    def __init__(self, marks=None):
        self.marks = marks or {}
        self.reads = []

    def __call__(self, path):
        name = Path(path).name
        self.reads.append(name)
        return self.marks.get(name)


def web_mark(host="https://example.com/files/report.pdf", page="https://example.com/reports"):
    return Mark(3, host, page)
