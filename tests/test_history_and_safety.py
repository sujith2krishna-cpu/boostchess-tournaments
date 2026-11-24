"""History (never delete), bad fetches, determinism, retries, command-line behaviour."""
import json
from datetime import datetime, timedelta

import pytest
import requests

import build_events as be
from conftest import (NOW, build, by_id, load_doc, load_events, make_html, padding, row)

NEXT_DAY = NOW + timedelta(days=1)


# ---- history ------------------------------------------------------------
def test_event_that_disappears_is_kept_and_marked_gone(data_dir):
    build(data_dir, [row("Stays", "400001"), row("Leaves", "400002")])
    build(data_dir, [row("Stays", "400001")], now=NEXT_DAY)
    events = by_id(data_dir)
    assert events["aicf-400002"]["gone_from_source"] is True
    assert events["aicf-400002"]["last_seen"] == "2026-11-24"
    assert events["aicf-400001"]["gone_from_source"] is False
    assert events["aicf-400001"]["last_seen"] == "2026-11-25"
    assert events["aicf-400001"]["first_seen"] == "2026-11-24"
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert meta["gone_from_source_count"] == 1 and meta["total"] == 2 and meta["scraped_count"] == 1


def test_gone_event_that_comes_back_is_live_again(data_dir):
    build(data_dir, [row("A", "400001")])
    build(data_dir, [row("B", "400002")], now=NEXT_DAY)
    build(data_dir, [row("A", "400001"), row("B", "400002")], now=NEXT_DAY + timedelta(days=1))
    event = by_id(data_dir)["aicf-400001"]
    assert event["gone_from_source"] is False and event["first_seen"] == "2026-11-24"


def test_changed_dates_and_place_for_same_code_take_the_new_values(data_dir):
    build(data_dir, [row("Cup", "400001", start="10-12-2026", end="12-12-2026", place="Pune")])
    build(data_dir, [row("Cup", "400001", start="15-12-2026", end="17-12-2026", place="Nagpur")],
          now=NEXT_DAY)
    events = load_events(data_dir)
    assert len(events) == 1
    assert (events[0]["start"], events[0]["end"]) == ("2026-12-15", "2026-12-17")
    assert (events[0]["city"], events[0]["state"]) == ("Nagpur", "Maharashtra")
    assert events[0]["first_seen"] == "2026-11-24"


def test_same_code_on_two_different_events_keeps_both(data_dir):
    build(data_dir, [row("Rapid Cup", "507610", start="18-11-2026"),
                     row("Blitz Cup", "507610", start="21-11-2026")])
    ids = sorted(by_id(data_dir))
    assert len(ids) == 2 and ids[0] == "aicf-507610" and ids[1].startswith("aicf-507610-")


def test_exact_duplicate_rows_collapse_to_one(data_dir):
    report = build(data_dir, [row("Same", "400001", place="Jabalpur, MP"),
                              row("Same", "400001", place="Jabalpur\xa0, MP")])
    assert len(load_events(data_dir)) == 1 and report["duplicate_rows_collapsed"] == 1


# ---- bad fetch: existing data untouched ---------------------------------
def snapshot(folder):
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


def test_too_few_rows_stops_and_leaves_data_untouched(data_dir):
    build(data_dir, padding(150))
    before = snapshot(data_dir)
    with pytest.raises(be.SourceError, match="only 5 event rows"):
        be.run(data_dir, html=make_html(padding(5)), now=NEXT_DAY)  # the real minimum of 100
    assert snapshot(data_dir) == before


def test_less_than_half_of_previous_run_stops(data_dir):
    build(data_dir, padding(300))
    before = snapshot(data_dir)
    with pytest.raises(be.SourceError, match="fewer than half"):
        be.run(data_dir, html=make_html(padding(120)), now=NEXT_DAY)
    assert snapshot(data_dir) == before


def test_page_without_the_events_table_stops(data_dir):
    build(data_dir, padding(150))
    before = snapshot(data_dir)
    with pytest.raises(be.SourceError, match="table was not found"):
        be.run(data_dir, html="<html><body><p>Maintenance</p></body></html>", now=NEXT_DAY)
    assert snapshot(data_dir) == before


def test_mostly_unreadable_dates_means_layout_changed(data_dir):
    rows = [row(f"E{i}", str(400000 + i), start="soon", end="later") for i in range(150)]
    with pytest.raises(be.SourceError, match="dates"):
        be.run(data_dir, html=make_html(rows), now=NOW)
    assert not (data_dir / "events.json").exists()


def test_failed_download_leaves_data_untouched(data_dir):
    build(data_dir, padding(150))
    before = snapshot(data_dir)

    def broken():
        raise be.SourceError("Could not fetch: boom")

    with pytest.raises(be.SourceError):
        be.run(data_dir, fetch=broken, now=NEXT_DAY)
    assert snapshot(data_dir) == before


def test_broken_previous_file_is_not_overwritten(data_dir):
    (data_dir / "events.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(be.BuildError, match="cannot be read"):
        build(data_dir, [row()])
    assert (data_dir / "events.json").read_text(encoding="utf-8") == "{ not json"


# ---- fetching -----------------------------------------------------------
class FakeResponse:
    def __init__(self, status_code=200, content=b"<html></html>"):
        self.status_code, self.content = status_code, content


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(be.time, "sleep", lambda s: None)


def test_fetch_sends_clear_user_agent_and_timeout(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(url=url, headers=headers, timeout=timeout)
        return FakeResponse(content="café".encode("utf-8"))

    monkeypatch.setattr(be.requests, "get", fake_get)
    assert be.fetch_html() == "café"
    assert seen["url"] == "https://aicf.in/all-events/"
    assert seen["headers"]["User-Agent"].startswith("BoostchessBot (+https://github.com/")
    assert seen["timeout"] == be.REQUEST_TIMEOUT_SECONDS


def test_fetch_retries_once_after_a_network_error(monkeypatch, no_sleep):
    calls = []

    def fake_get(url, headers, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise requests.ConnectionError("down")
        return FakeResponse()

    monkeypatch.setattr(be.requests, "get", fake_get)
    assert be.fetch_html() == "<html></html>" and len(calls) == 2


def test_fetch_gives_up_after_one_retry(monkeypatch, no_sleep):
    calls = []
    monkeypatch.setattr(be.requests, "get",
                        lambda url, headers, timeout: calls.append(1) or FakeResponse(503))
    with pytest.raises(be.SourceError, match="HTTP 503"):
        be.fetch_html()
    assert len(calls) == 2


def test_fetch_does_not_retry_a_404(monkeypatch, no_sleep):
    calls = []
    monkeypatch.setattr(be.requests, "get",
                        lambda url, headers, timeout: calls.append(1) or FakeResponse(404))
    with pytest.raises(be.SourceError, match="HTTP 404"):
        be.fetch_html()
    assert len(calls) == 1


# ---- determinism and file format ----------------------------------------
def test_same_input_gives_identical_files_except_generated_at(data_dir, tmp_path):
    rows = [row("A", "400001"), row("B", "400002", place="Banka,\nBihar"), row("C", "")]
    build(data_dir, rows)
    first = snapshot(data_dir)
    build(data_dir, rows, now=NOW.replace(hour=18, minute=5))  # same day, later
    second = snapshot(data_dir)
    assert first != second  # generated_at moved...

    def strip(raw):
        return raw.decode("utf-8").replace("10:30:00", "XX").replace("18:05:00", "XX")

    assert {k: strip(v) for k, v in first.items()} == {k: strip(v) for k, v in second.items()}
    # ...and a fresh folder gives the very same bytes again
    other = tmp_path / "other"
    other.mkdir()
    build(other, rows)
    assert snapshot(other) == first


def test_file_format_utf8_two_space_indent_stable_key_order(data_dir):
    build(data_dir, [row("Café – Open", "400001")])
    raw = (data_dir / "events.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and raw.endswith(b"}\n")
    text = raw.decode("utf-8")
    assert text.startswith('{\n  "schema_version": 2,\n  "generated_at": "2026-11-24T10:30:00+05:30",\n')
    assert "Café – Open" in text  # real characters, not \u escapes
    event = load_events(data_dir)[0]
    assert list(event) == list(be.EVENT_KEYS)
    assert "status" not in event
    assert list(json.loads((data_dir / "meta.json").read_text("utf-8"))) == [
        "generated_at", "scraped_count", "manual_count", "total", "suspect_dates_count",
        "missing_state_count", "gone_from_source_count"]


def test_meta_counts(data_dir):
    build(data_dir, [row("Ok", "400001", place="Pune"),
                     row("Odd place", "400002", place="Bilaspur"),
                     row("Bad date", "400003", start="x", end="y")])
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert meta["scraped_count"] == 3 and meta["total"] == 3
    assert meta["suspect_dates_count"] == 1 and meta["missing_state_count"] == 1
    assert meta["manual_count"] == 0 and meta["gone_from_source_count"] == 0


def test_report_counts_by_status(data_dir):
    report = build(data_dir, [row("Past", "400001", start="01-11-2026", end="02-11-2026"),
                              row("Now", "400002", start="23-11-2026", end="25-11-2026"),
                              row("Soon", "400003", start="01-12-2026", end="02-12-2026")])
    assert report["status_counts"] == {"past": 1, "ongoing": 1, "upcoming": 1}


# ---- command line -------------------------------------------------------
def test_main_success_and_failure_exit_codes(data_dir, tmp_path, capsys):
    page = tmp_path / "page.html"
    page.write_text(make_html(padding(150)), encoding="utf-8")
    assert be.main(["--html", str(page), "--data-dir", str(data_dir)]) == 0
    assert "Total events" in capsys.readouterr().out
    before = snapshot(data_dir)
    page.write_text(make_html(padding(3)), encoding="utf-8")
    assert be.main(["--html", str(page), "--data-dir", str(data_dir)]) == 2
    assert "left untouched" in capsys.readouterr().err
    assert snapshot(data_dir) == before
