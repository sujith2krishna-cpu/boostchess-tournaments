"""T12, second round (decisions of 28 Nov 2026): ChessBase switched off and not published,
the Chess-Results "FIDE-Event-ID" as an AICF code, and the new pairs."""
import csv
import json
import re

import pytest

import build_events as be
import dedup
from conftest import (ALL_SOURCES_ON, CB, NOW, ROOT, fx, load_events, row, run_all, serve_aicf,
                      serve_chessbase)
from sources import chessbase_calendar as cb_source
from sources import chessresults_ind as cr_source
from test_t12 import TODAY, details

PAIRS_T12B = {("aicf-487790", "chessresults_ind-1493397"), ("aicf-505736", "upcsa-91"),
              ("aicf-496210", "upcsa-88"), ("aicf-505328", "upcsa-90")}


def published_events():
    return {e["id"]: e for e in json.loads((ROOT / "data" / "events.json").read_text("utf-8"))["events"]}


# ---- 1. ChessBase switched off and not published -----------------------------------
def test_publish_false_needs_enabled_false_and_is_read_from_the_file(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text('{"chessbase_calendar": {"enabled": true, "publish": false}}', encoding="utf-8")
    with pytest.raises(be.BuildError, match='must also have "enabled": false'):
        be.load_config(path)
    path.write_text('{"chessbase_calendar": {"enabled": false, "publish": "no"}}', encoding="utf-8")
    with pytest.raises(be.BuildError, match='"publish" must be true or false'):
        be.load_config(path)
    path.write_text('{"chessbase_calendar": {"enabled": false, "publish": false}, '
                    '"aicf": {"enabled": true}}', encoding="utf-8")
    assert be.unpublished_sources(path) == {"chessbase_calendar"}
    assert be.unpublished_sources() == {"chessbase_calendar"}  # the committed file


def test_an_unpublished_source_is_not_fetched_and_none_of_it_is_written(web, data_dir):
    serve_chessbase(web)
    for html in ("chessbase_calendar.html", "chessbase_calendar_2027.html"):
        for raw in cb_source.parse_events(fx(html)):
            web.add(CB + "chess-calendar/event/" + raw["slug"], fx("chessbase_event.html"))
    serve_aicf(web, [row("Plain AICF Open", "400001")])
    both = {n: n in ("aicf", "chessbase_calendar") for n in be.SOURCE_MODULES}
    run_all(data_dir, config=both)
    assert any(e["source"] == "chessbase_calendar" for e in load_events(data_dir))
    snapshot = data_dir / "sources" / "chessbase_calendar.json"
    kept = snapshot.read_bytes()
    web.calls.clear()
    off = {**ALL_SOURCES_ON, **{n: n == "aicf" for n in be.SOURCE_MODULES}}
    report = run_all(data_dir, config=off, unpublished=frozenset({"chessbase_calendar"}),
                     now=NOW.replace(day=25))
    assert not web.urls("chessbase")  # not contacted, not even robots.txt
    assert not [e for e in load_events(data_dir) if e["source"] == "chessbase_calendar"]
    assert not [e for e in load_events(data_dir)
                if any(x["source"] == "chessbase_calendar" for x in e["also_listed_on"])]
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))["sources"]["chessbase_calendar"]
    assert meta["status"] == "disabled" and meta["count"] == 0 and "publish" in meta["message"]
    assert snapshot.read_bytes() == kept  # never rewritten, so its history is not lost ...
    assert any("still in data/" in w for w in report["warnings"])  # ... but it must be moved
    snapshot.unlink()  # (moved to archive/)
    report = run_all(data_dir, config=off, unpublished=frozenset({"chessbase_calendar"}),
                     now=NOW.replace(day=26))
    assert not snapshot.exists() and not any("still in data/" in w for w in report["warnings"])


def test_the_chessbase_snapshot_is_kept_outside_the_published_folder():
    assert not (ROOT / "data" / "sources" / "chessbase_calendar.json").exists()
    kept = json.loads((ROOT / "archive" / "chessbase_calendar.json").read_text("utf-8"))
    assert kept["source"] == "chessbase_calendar" and len(kept["events"]) >= 30
    assert not [e for e in published_events().values() if e["source"] == "chessbase_calendar"
                or any(x["source"] == "chessbase_calendar" for x in e["also_listed_on"])]


def test_the_permission_e_mails_are_drafts_without_addresses():
    text = (ROOT / "docs" / "PERMISSION_EMAILS.md").read_text("utf-8")
    assert "not sent" in text and text.count("Vaiva Technologies") >= 3
    for who in ("ChessBase India", "All India Chess Federation", "FIDE"):
        assert who in text
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text)  # no e-mail addresses (public repo)


# ---- 3. Chess-Results "FIDE-Event-ID" as an AICF code ------------------------------
@pytest.mark.parametrize("text, expected", [
    ("487788", "487788"), (" 487788 ", "487788"), ("48778", None), ("4877880", None),
    ("487788/GA/2026", None), ("-", None), ("", None),
])
def test_fide_event_id_row(text, expected):
    assert details(extra=[("FIDE-Event-ID", text)])["fide_event_id"] == expected
    assert details()["fide_event_id"] is None


def _cr(number, name, start="2026-11-27"):
    return be.canonical({"id": f"chessresults_ind-{number}", "name": name, "start": start, "end": start,
                         "source": "chessresults_ind", "country": "IN", "first_seen": "x",
                         "last_seen": "x",
                         "source_url": f"https://chess-results.com/tnr{number}.aspx?lan=1"})


def _aicf(code, name, start="2026-11-27"):
    return be.canonical({"id": f"aicf-{code}", "codes": [code], "name": name, "start": start,
                         "end": start, "source": "aicf", "country": "IN", "state": "Goa",
                         "first_seen": "x", "last_seen": "x"})


def test_a_fide_event_id_becomes_a_code_only_when_an_aicf_event_has_it():
    events = [_aicf("487790", "International FIDE Rated Below 1800 Open Chess Tournament 2026"),
              _cr("1493397", "QQCHESS INTERNATIONAL BELOW 1800 FIDE RATING CHESS TOURNAMENT 2026"),
              _cr("1500000", "Some Open"), _cr("1500001", "Other Open")]
    ids = {"chessresults_ind-1493397": "487790", "chessresults_ind-1500000": "999999",
           "chessresults_ind-1500001": "48779"}
    assert be.add_fide_event_codes(events, ids) == 1
    assert events[1]["codes"] == ["487790"]
    assert events[2]["codes"] == [] and events[3]["codes"] == []  # no such AICF event / not 6 digits
    assert be.add_fide_event_codes(events, ids) == 0  # never added twice
    dedup.group_events(events, [], [])
    assert events[1]["merged_into"] == "aicf-487790"  # the shared code proves it


def test_a_two_code_aicf_row_or_a_shared_code_is_not_used():
    junior = _aicf("494716", "National U19 (Junior) Chess Championship 2026")
    junior["codes"] = ["494716", "494717"]  # open and girls in one AICF row
    first_move, khannur = _aicf("494719", "First Move Open"), _aicf("501318", "Khannur Rapid")
    first_move["codes"] = ["494719", "501318"]  # the code is on two AICF events
    girls = _cr("1548779", "40th National Junior Girls Championship")
    open_ = _cr("1548787", "55th National Junior Championship")
    rapid = _cr("1502344", "Khannur Fide Rapid Rating Chess Tournament 2026")
    events = [junior, first_move, khannur, girls, open_, rapid]
    ids = {"chessresults_ind-1548779": "494717", "chessresults_ind-1548787": "494716",
           "chessresults_ind-1502344": "501318"}
    assert be.add_fide_event_codes(events, ids) == 0
    assert girls["codes"] == open_["codes"] == rapid["codes"] == []


def test_khannur_is_with_its_own_aicf_event_not_first_move():
    published = published_events()
    assert published["chessresults_ind-1502344"]["merged_into"] == "aicf-501318"


def test_fetch_keeps_the_fide_event_ids_of_events_it_did_not_read_again():
    state = {"listing": {cr_source.FIDE_IDS_KEY: {"chessresults_ind-1": "400001"}}, "events": []}

    class Client:
        def get(self, url):
            return fx("chessresults_fed_ind.html")

        def post(self, url, data):
            return "<html><body><table class=CRs2></table></body></html>"  # empty lists

    _events, listing, _stats = cr_source.fetch(Client(), state, TODAY)
    assert listing[cr_source.FIDE_IDS_KEY] == {"chessresults_ind-1": "400001"}


def test_the_stored_fide_event_ids_group_the_goa_events():
    snapshot = json.loads((ROOT / "data" / "sources" / "chessresults_ind.json").read_text("utf-8"))
    ids = snapshot["listing"][cr_source.FIDE_IDS_KEY]
    assert ids["chessresults_ind-1487030"] == "487788" and ids["chessresults_ind-1493397"] == "487790"
    assert all(re.fullmatch(r"\d{6}", v) for v in ids.values())
    published = published_events()
    assert "487790" in published["chessresults_ind-1493397"]["codes"]
    assert published["chessresults_ind-1493397"]["merged_into"] == "aicf-487790"


# ---- 4, 5, 6. pairs.csv --------------------------------------------------------------
def test_the_goa_below_1800_and_upcsa_pairs_are_same():
    with open(ROOT / "data" / "manual" / "pairs.csv", encoding="utf-8", newline="") as handle:
        rows = {tuple(sorted((r["id_a"], r["id_b"]))): r for r in csv.DictReader(handle)}
    for pair in PAIRS_T12B:
        line = rows[tuple(sorted(pair))]
        assert line["decision"] == "same" and line["note"], pair
    assert rows[("chessresults_ind-1547750", "tnsca-CO-213-CHE-26-27")]["decision"] == "same"  # kept
    published = published_events()
    for aicf_id, other in [("aicf-505736", "upcsa-91"), ("aicf-496210", "upcsa-88"),
                           ("aicf-505328", "upcsa-90")]:
        assert published[other]["merged_into"] == aicf_id and published[other]["verified"] is True
