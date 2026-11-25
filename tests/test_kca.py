"""T7: the Kerala Chess Association source (keralachessassociation.com), from saved pages only."""
import json
import re
from datetime import date, datetime, timedelta

import pytest

import build_events as be
import dedup
from conftest import KCA, NOW, ROOT, by_id, fx, load_events, run_all, serve_kca
from sources import kca

ONLY_KCA = {n: n == "kca" for n in be.SOURCE_MODULES}
LISTING = "kca_events_2026-11-25.html"
TODAY = NOW.date()  # 24 Nov 2026
REAL = {e["id"]: e for e in json.loads(
    (ROOT / "tests" / "fixtures" / "dedup_real_events.json").read_text("utf-8"))["events"]}


def entries():
    page = kca.parse_listing(fx(LISTING))
    return {e["code"]: e for e in page["upcoming"] + page["completed"]}


# ---- reading the pages -----------------------------------------------------------
def test_listing_has_both_tabs_and_the_year_menu():
    page = kca.parse_listing(fx(LISTING))
    assert len(page["upcoming"]) == 12 and len(page["completed"]) == 58
    assert page["years"][:2] == [2026, 2025] and page["years"][-1] == 2013
    assert page["year_form"] == (KCA + "events", {"tab": "completed"})
    first = page["upcoming"][0]
    assert (first["code"], first["label"], first["date_text"], first["district"], first["status"]) == (
        "736/CAK/2026", "FIDE", "Nov 29 - Nov 29, 2026", "Ernakulam", "Upcoming")
    assert first["detail_url"] == KCA + "events/736"
    assert first["brochure_url"].startswith(KCA + "storage/tournaments/") and first["brochure_url"].endswith(".pdf")


def test_dates_use_the_year_written_once_at_the_end():
    assert kca.parse_dates("Feb 13 - Feb 14, 2027") == (date(2027, 2, 13), date(2027, 2, 14))
    assert kca.parse_dates("Sept 3 - Sept 4, 2026") == (date(2026, 9, 3), date(2026, 9, 4))
    assert kca.parse_dates("soon") == (None, None)


def test_a_range_across_new_year_starts_in_the_year_before():
    entry = entries()["669/CAK/2025"]  # the site writes "Dec 29 - Jan 02, 2026"
    assert kca.parse_dates("Dec 29 - Jan 02, 2026") == (date(2025, 12, 29), date(2026, 1, 2))
    event = kca.build_event(entry, None, TODAY)
    assert (event["start"], event["end"]) == ("2025-12-29", "2026-01-02")
    assert event["flags"]["dates_suspect"] is False
    assert event["raw_dates"] == {"start": "Dec 29 - Jan 02, 2026", "end": "Dec 29 - Jan 02, 2026"}
    same_year = kca.build_event(entries()["736/CAK/2026"], None, TODAY)
    assert same_year["raw_dates"] is None  # only a crossing range keeps the page's text
    assert event["city"] is None  # the district column says "-"
    assert not kca._recent(entry, TODAY)  # it ended in January 2026


def test_detail_page_gives_venue_and_no_disabled_register_link():
    detail = kca.parse_detail(fx("kca_event_736.html"), KCA + "events/736")
    assert detail == {"venue": "Naipunya public school , kakkanad cochin, Ernakulam", "formats": [],
                      "register_url": None}  # "Register Now" is a disabled button pointing at "#"


def test_detail_page_register_link_and_time_control_when_shown():
    html = fx("kca_event_736.html").replace(
        '<a href="#" target="_blank" class="btn btn-success btn-lg px-5 rounded-pill shadow-sm disabled">',
        '<a href="https://example.org/entry/736" class="btn btn-success">').replace(
        "<small class=\"d-block text-uppercase fw-bold text-secondary\" style=\"font-size: 0.7rem; "
        "letter-spacing: 0.5px;\">Venue</small>",
        "<small>Time Control</small><span>Rapid 15 min + 10 sec</span></div><div>"
        "<small class=\"d-block\">Venue</small>")
    detail = kca.parse_detail(html, KCA + "events/736")
    assert detail["register_url"] == "https://example.org/entry/736"
    assert detail["formats"] == ["rapid"]


def test_a_changed_layout_is_an_error_not_an_empty_list():
    with pytest.raises(be.SourceError, match="layout changed"):
        kca.parse_listing("<html><body><p>Maintenance</p></body></html>")


# ---- one run --------------------------------------------------------------------
def test_run_reads_upcoming_and_the_last_60_days(web, data_dir):
    serve_kca(web)
    report = run_all(data_dir, config=ONLY_KCA)
    events = {e["id"]: e for e in load_events(data_dir)}
    assert report["per_source"]["kca"]["status"] == "ok"
    assert set(events) == {e["id"] for e in load_events(data_dir) if e["source"] == "kca"}
    kca_codes = {e["codes"][0] for e in events.values()}
    assert len(events) == 22  # 12 upcoming + 10 that ended since 25 Sep 2026
    assert "722/CAK/2026" in kca_codes  # 27 Sep: inside the window
    assert "731/CAK/2026" not in kca_codes and "674/CAK/2026" not in kca_codes  # older: skipped
    e = events["kca-736-CAK-2026"]
    assert e["codes"] == ["736/CAK/2026"]
    assert e["name"] == "Chessind Academy's 2nd International FIDE Rated Open Rapid Chess Tournament"
    assert (e["start"], e["end"], e["city"], e["state"], e["country"]) == (
        "2026-11-29", "2026-11-29", "Ernakulam", "Kerala", "IN")
    assert e["place_text"] == "Naipunya public school, kakkanad cochin, Ernakulam, Kerala"
    assert kca.join_place("De Paul Auditorium, Angamaly, Ernakulam, Kerala, Ernakulam", "Ernakulam",
                          "Kerala") == "De Paul Auditorium, Angamaly, Ernakulam, Kerala"
    assert kca.join_place("Hall , puzhakkal, Thrissur, Thrissur", "Thrissur", "Kerala") == (
        "Hall, puzhakkal, Thrissur, Kerala")
    assert (e["source"], e["listed_by"], e["verified"]) == ("kca", "kca", True)
    assert e["source_url"] == KCA + "events/736" and e["register_url"] is None
    assert (e["tags"]["fide_rated"], e["tags"]["fide_how"], e["tags"]["formats"]) == (True, "stated", ["rapid"])
    assert e["organiser"] is None and e["results_url"] is None


def test_type_labels(web, data_dir):
    serve_kca(web)
    run_all(data_dir, config=ONLY_KCA)
    events = by_id(data_dir)
    fide, state = events["kca-730-CAK-2026"], events["kca-745-CAK-2026"]
    plain = kca.build_event(entries()["669/CAK/2025"], None, TODAY)  # an "EVENT" row (too old to be read)
    assert (fide["tags"]["fide_rated"], fide["tags"]["fide_how"], fide["tags"]["categories"]) == (True, "stated", [])
    assert (state["tags"]["fide_rated"], state["tags"]["categories"]) == (None, ["KCA state rated"])
    assert plain["tags"]["categories"] == [] and plain["tags"]["fide_rated"] is None


def test_a_state_event_never_gets_fide_from_its_name(web, data_dir):
    page = fx(LISTING).replace("ALL KERALA OPEN CHESS TOURNAMENT  ( BELOW - 1700 )",
                               "Grandmaster International Open")
    web.add(KCA + "events", page)
    run_all(data_dir, config=ONLY_KCA)
    e = by_id(data_dir)["kca-745-CAK-2026"]
    assert e["name"] == "Grandmaster International Open"
    assert (e["tags"]["fide_rated"], e["tags"]["fide_how"]) == (None, None)


def test_details_only_for_upcoming_events_that_are_new_or_changed(web, data_dir):
    serve_kca(web)
    numbers = set(re.findall(r'href="https://www\.keralachessassociation\.com/events/(\d+)"', fx(LISTING)))
    for number in numbers:
        web.add(KCA + f"events/{number}", fx("kca_event_736.html"))
    report = run_all(data_dir, config=ONLY_KCA)
    detail_calls = [u for u in web.urls("keralachess") if re.search(r"/events/\d+$", u)]
    assert len(detail_calls) == 12  # the upcoming ones; never the completed ones
    assert report["per_source"]["kca"]["requests"] == 1 + 1 + 12  # robots, list, details
    assert len(web.sleeps) >= 13  # a polite pause before every request after the first
    web.calls.clear()
    run_all(data_dir, config=ONLY_KCA, now=NOW + timedelta(days=1))
    assert [u for u in web.urls() if re.search(r"/events/\d+$", u)] == []  # nothing changed
    web.add(KCA + "events", fx(LISTING).replace("MET ALL KERALA CHESS TOURNAMENT", "MET ALL KERALA OPEN"))
    web.calls.clear()
    run_all(data_dir, config=ONLY_KCA, now=NOW + timedelta(days=2))
    assert [u for u in web.urls() if re.search(r"/events/\d+$", u)] == [KCA + "events/741"]


def test_in_january_the_previous_year_comes_from_the_page_s_own_menu(web, data_dir):
    january = re.sub(r'(<div class="tab-pane fade " id="completed".*?</form>\s*</div>).*?(</main>)',
                     r"\1</div></div></div>\2", fx(LISTING), flags=re.S)
    january = january.replace('<option value="2026" selected>2026</option>',
                               '<option value="2027" selected>2027</option>\n<option value="2026" >2026</option>')
    web.add(KCA + "events", january)
    web.add(KCA + "events?tab=completed&year=2026", fx(LISTING))
    run_all(data_dir, config=ONLY_KCA, now=datetime(2027, 1, 10, 9, 0, tzinfo=be.IST))
    assert KCA + "events?tab=completed&year=2026" in web.urls()
    assert KCA + "events?tab=completed&year=2025" not in web.urls()
    ids = set(by_id(data_dir))
    assert {"kca-742-CAK-2026", "kca-739-CAK-2026"} <= ids  # 15 and 22 Nov 2026: within 60 days
    assert "kca-734-CAK-2026" not in ids  # 1 Nov 2026: too old


def test_no_phone_numbers_or_people_are_stored(web, data_dir):
    serve_kca(web)
    run_all(data_dir, config=ONLY_KCA)
    text = (data_dir / "events.json").read_text("utf-8") + (data_dir / "sources" / "kca.json").read_text("utf-8")
    assert "90000" not in text and "Organiser Name" not in text and "Arbiter Name" not in text


def test_a_vanished_event_is_kept(web, data_dir):
    serve_kca(web)
    run_all(data_dir, config=ONLY_KCA)
    page = re.sub(r'<tr class="status-strip-upcoming">(?:(?!</tr>).)*745/CAK/2026.*?</tr>', "",
                  fx(LISTING), count=1, flags=re.S)
    web.add(KCA + "events", page)
    run_all(data_dir, config=ONLY_KCA, now=NOW + timedelta(days=1))
    e = by_id(data_dir)["kca-745-CAK-2026"]
    assert e["gone_from_source"] is True and e["last_seen"] == TODAY.isoformat()


# ---- importance order and grouping ---------------------------------------------------
def test_importance_order():
    assert be.SOURCE_PRIORITY[:3] == ("manual", "aicf", "kca")
    assert dedup.PRIMARY_ORDER[:2] == ("manual", "kca")
    assert "kca" in be.VERIFIED_SOURCES and be.SOURCE_LABELS["kca"] == "Kerala Chess Association"


def _kca(code, district="Ernakulam", **changes):
    return be.canonical({"id": f"kca-{code}", "name": "Some Cup", "start": "2026-12-06", "end": "2026-12-06",
                         "source": "kca", "state": "Kerala", "city": district, "first_seen": "2026-11-25",
                         "last_seen": "2026-11-25", **changes})


def test_a_kca_district_matches_the_towns_inside_it():
    other = lambda city: be.canonical({"id": "chessfee-1", "name": "Some Cup", "start": "2026-12-06",
                                       "end": "2026-12-06", "source": "chessfee", "state": "Kerala",
                                       "city": city, "first_seen": "x", "last_seen": "x"})
    assert dedup._same_city(_kca("1"), other("Kochi")) is True
    assert dedup._same_city(_kca("1"), other("Aluva")) is True
    assert dedup._same_city(_kca("1"), other("Thrissur")) is False
    assert dedup._same_city(_kca("1"), other("Somewhere")) is None  # unknown town: never "different"
    plain = be.canonical({"id": "aicf-1", "name": "x", "source": "aicf", "city": "Aluva",
                          "first_seen": "x", "last_seen": "x"})
    assert dedup._same_city(plain, other("Kochi")) is False  # other sources: unchanged rule


def test_chessind_rapid_groups_with_the_aicf_record_not_twice(web, data_dir):
    serve_kca(web)
    report = run_all(data_dir, config=ONLY_KCA)
    mine = by_id(data_dir)["kca-736-CAK-2026"]
    events = [be.canonical(REAL[i]) for i in ("aicf-502180", "chessfee-1800", "chessresults_ind-1532678")]
    events.append(be.canonical(mine))
    dedup.group_events(events, [], [])
    by = {e["id"]: e for e in events}
    assert {e["group_id"] for e in events} == {"aicf-502180"}
    assert by["kca-736-CAK-2026"]["merged_into"] == "aicf-502180"
    assert by["aicf-502180"]["merged_into"] is None
    assert [x["source"] for x in by["aicf-502180"]["also_listed_on"]] == ["kca", "chessfee", "chessresults_ind"]
    assert by["aicf-502180"]["city"] == "Kochi"  # chessfee's town beats KCA's district
    assert report["per_source"]["kca"]["found"] == 22


def test_kca_is_primary_over_chessfee_when_aicf_has_no_record():
    fee = be.canonical({**REAL["chessfee-1800"]})
    mine = _kca("736-CAK-2026", name="Chessind Academy's 2nd International FIDE Rated Open Rapid Chess "
                "Tournament", start="2026-11-29", end="2026-11-29", codes=["736/CAK/2026"])
    events = [fee, mine]
    dedup.group_events(events, [], [])
    assert fee["merged_into"] == "kca-736-CAK-2026" and mine["verified"] is True
