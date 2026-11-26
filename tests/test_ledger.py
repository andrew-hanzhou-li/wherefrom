from wherefrom.ledger import Ledger, escape_like
from wherefrom.zone import Mark

from conftest import web_mark


def test_needs_a_url_to_record(ledger):
    assert not ledger.add("aa", 1, "/d/a.txt", mark=Mark(3, None, None))
    assert not ledger.add("aa", 1, "/d/a.txt")
    assert ledger.by_hash("aa") == []


def test_same_record_twice_is_kept_once(ledger):
    assert ledger.add("aa", 1, "/d/a.txt", mark=web_mark())
    assert not ledger.add("aa", 1, "/d/a.txt", mark=web_mark())
    assert len(ledger.by_hash("aa")) == 1


def test_missing_urls_dont_make_duplicates(ledger):
    for _ in range(3):
        ledger.add("aa", 1, "/d/a.txt", host_url="https://a.test/x")        # no page URL
        ledger.add("bb", 1, "/d/b.txt", referrer_url="https://b.test/page")  # no file URL
    assert len(ledger.by_hash("aa")) == 1
    assert len(ledger.by_hash("bb")) == 1


def test_by_hash_oldest_download_first(ledger):
    ledger.add("aa", 1, "/d/new.txt", source="chrome", downloaded_at="2026-11-20T10:00:00",
               host_url="https://b.test/x")
    ledger.add("aa", 1, "/d/old.txt", source="chrome", downloaded_at="2025-01-01T10:00:00",
               host_url="https://a.test/x")
    assert [r.name for r in ledger.by_hash("aa")] == ["old.txt", "new.txt"]


def test_search_urls_and_names_any_case(ledger):
    ledger.add("aa", 1, "/d/Syllabus.pdf", host_url="https://CANVAS.ucsb.edu/files/1")
    ledger.add("bb", 1, "/d/photo.jpg", referrer_url="https://example.com/gallery")
    assert [r.name for r in ledger.search("canvas")] == ["Syllabus.pdf"]
    assert [r.name for r in ledger.search("SYLLABUS")] == ["Syllabus.pdf"]
    assert [r.name for r in ledger.search("gallery")] == ["photo.jpg"]


def test_search_folds_any_letters(ledger):
    ledger.add("aa", 1, "/d/Über Größe.pdf", host_url="https://Ärzte.example/x")
    for text in ("über", "ÜBER", "größe", "GRÖSSE", "ärzte"):
        assert [r.name for r in ledger.search(text)] == ["Über Größe.pdf"], text


def test_search_wildcards_are_literal(ledger):
    ledger.add("aa", 1, "/d/a.txt", host_url="https://a.test/plain")
    ledger.add("bb", 1, "/d/100%_done.txt", host_url="https://b.test/x")
    assert [r.name for r in ledger.search("100%")] == ["100%_done.txt"]
    assert ledger.search("%") == ledger.search("100%")
    assert ledger.search("_") == ledger.search("100%")
    assert escape_like("a\\b") == "a\\\\b"


def test_seen_files(ledger):
    assert not ledger.already_seen("/d/a", 5, 1.0)
    ledger.mark_seen("/d/a", 5, 1.0)
    assert ledger.already_seen("/d/a", 5, 1.0)
    assert not ledger.already_seen("/d/a", 6, 1.0)      # it changed
    ledger.mark_seen("/d/a", 6, 2.0)
    assert ledger.already_seen("/d/a", 6, 2.0)


def test_survives_reopening(tmp_path):
    first = Ledger(tmp_path / "l.sqlite3")
    first.add("aa", 1, "/d/a.txt", host_url="https://a.test/x")
    first.close()
    again = Ledger(tmp_path / "l.sqlite3")
    assert len(again.by_hash("aa")) == 1
    again.close()


def test_default_home_is_created(tmp_path):
    db = Ledger()           # WHEREFROM_HOME points into tmp_path (conftest)
    db.close()
    assert (tmp_path / "home" / "ledger.sqlite3").is_file()
