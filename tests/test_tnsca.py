"""T8: the Tamil Nadu State Chess Association calendar (tamilchess.com), from saved pages only."""
import json
import re
from datetime import datetime

import pytest

import build_events as be
import dedup
from conftest import NOW, ROOT, TNSCA, by_id, fx, load_events, make_html, row, run_all, serve_tnsca
from sources import tnsca

ONLY_TNSCA = {n: n == "tnsca" for n in be.SOURCE_MODULES}
TODAY = NOW.date()  # 24 Nov 2026
Y2026, Y2027 = "tnsca_calendar_2026.html", "tnsca_calendar_2027.html"
CAL = TNSCA + "tournament-registration/"
REAL = {e["id"]: e for e in json.loads(
    (ROOT / "tests" / "fixtures" / "dedup_real_events.json").read_text("utf-8"))["events"]}

HEADER = "<tr><th> Name</th><th> Event code</th><th>Place</th><th> Start</th><th> End</th></tr>"


def page(rows="", years=(2026, 2027), tables=("All Events", "Fide Rated Events")):
    """A small calendar page in the site's layout (for cases the saved pages do not show)."""
    menu = "".join(f'<a href="?y={y}">{y}</a>' for y in years)
    body = "".join(f"<h3>{t}</h3><table>{HEADER}{rows if t == 'All Events' else ''}</table>" for t in tables)
    return f"<html><body>{menu}{body}</body></html>"


def tr(name, code, place, start, end, slug="x"):
    return (f'<tr><td><a href="https://tamilchess.com/events/{slug}/">{name}</a></td><td>{code}</td>'
            f"<td>{place}</td><td>{start}</td><td>{end}</td></tr>")


def rows_of(name=Y2026):
    return {r["code"]: r for r in tnsca.parse_calendar(fx(name), CAL)["all"]}


# ---- reading the page ------------------------------------------------------------
def test_calendar_page_tables_and_year_menu():
    parsed = tnsca.parse_calendar(fx(Y2026), CAL + "?y=2026")
    assert len(parsed["all"]) == 135 and len(parsed["fide"]) == 37
    assert parsed["years"] == list(range(2017, 2030))
    row = rows_of()["RR-24/CBE/26-27"]
    assert row == {"name": "2nd Manchester City Below 1800 International Fide Rated Tournament",
                   "raw_code": "RR-24/CBE/26-27", "code": "RR-24/CBE/26-27", "place": "Coimbatore",
                   "start_text": "27-Nov-2026", "end_text": "29-Nov-2026",
                   "detail_url": TNSCA + "events/2nd-manchester-city-below-1800-international-fide-rated-tournament/"}
    assert len(tnsca.parse_calendar(fx(Y2027), CAL)["all"]) == 25


def test_dates_are_read_never_guessed():
    assert tnsca.parse_date("01-Jan-2027").isoformat() == "2027-01-01"
    assert tnsca.parse_date("29-nov-2026").isoformat() == "2026-11-29"
    for bad in ("", "31-Feb-2027", "2027-01-01", "Jan 1"):
        assert tnsca.parse_date(bad) is None


def test_month_lines_are_skipped_and_a_changed_layout_is_an_error():
    html = page('<tr><td colspan="5">December</td></tr>'
                + tr("Salem Open", "CO-1/SLM/26-27", "Salem", "06-Dec-2026", "06-Dec-2026"))
    assert [r["name"] for r in tnsca.parse_calendar(html, CAL)["all"]] == ["Salem Open"]
    with pytest.raises(be.SourceError, match="layout changed"):
        tnsca.parse_calendar("<html><body><h3>Events</h3><table><tr><td>x</td></tr></table></body></html>", CAL)
    # an empty year (tables with headers only) is fine
    assert tnsca.parse_calendar(page(), CAL)["all"] == []


# ---- one record ------------------------------------------------------------------
def test_fields_of_a_record():
    row = rows_of()["RR-24/CBE/26-27"]
    event = tnsca.build_event(row, True, TODAY)
    assert event["id"] == "tnsca-RR-24-CBE-26-27" and event["codes"] == ["RR-24/CBE/26-27"]
    assert (event["start"], event["end"]) == ("2026-11-27", "2026-11-29")
    assert (event["city"], event["state"], event["country"]) == ("Coimbatore", "Tamil Nadu", "IN")
    assert event["place_text"] == "Coimbatore, Tamil Nadu"
    assert event["source"] == "tnsca" and event["source_url"] == row["detail_url"]
    assert event["register_url"] is None and event["brochure_url"] is None  # we only link the page
    assert (event["tags"]["fide_rated"], event["tags"]["fide_how"]) == (True, "stated")
    assert event["flags"]["dates_suspect"] is False and event["raw_dates"] is None


def test_a_row_outside_the_fide_table_gets_fide_only_from_its_name():
    row = rows_of()["CO-109/CHE/26-27"]  # 3rd Harshana Chess Academy ... Children's Chess Tournament
    assert tnsca.build_event(row, False, TODAY)["tags"]["fide_rated"] is None


def test_a_missing_or_broken_date_is_kept_flagged_with_the_raw_text():
    row = tnsca.parse_calendar(page(tr("RIT Cup", "CO-9/TLR/26-27", "Tiruvallur", "13-Dec-2026", "")), CAL)["all"][0]
    event = tnsca.build_event(row, False, TODAY)
    assert event["start"] == "2026-12-13" and event["end"] is None
    assert event["flags"]["dates_suspect"] is True
    assert event["raw_dates"] == {"start": "13-Dec-2026", "end": ""}


def test_two_rows_sharing_a_code_get_different_ids():
    html = page(tr("Cup Category A", "RR-9/MDU/26-27", "Madurai", "06-Dec-2026", "07-Dec-2026")
                + tr("Cup Category B", "RR-9/MDU/26-27", "Madurai", "06-Dec-2026", "07-Dec-2026"))
    rows = tnsca.parse_calendar(html, CAL)["all"]
    shared = frozenset({"RR-9/MDU/26-27"})
    ids = {tnsca.event_id(r, shared) for r in rows}
    assert len(ids) == 2 and all(i.startswith("tnsca-RR-9-MDU-26-27-") for i in ids)


# ---- a run -----------------------------------------------------------------------
def test_run_reads_this_year_and_next_year_one_request_each(web, data_dir):
    serve_tnsca(web)
    report = run_all(data_dir, config=ONLY_TNSCA)
    assert web.urls("tamilchess.com") == [TNSCA + "robots.txt", CAL + "?y=2026", CAL + "?y=2027"]
    assert all(c["headers"]["User-Agent"].startswith("BoostchessBot") for c in web.calls)
    assert all(s >= 2.9 for s in web.sleeps)  # polite spacing between the pages
    events = [e for e in load_events(data_dir) if e["source"] == "tnsca"]
    assert len(events) == 151 == report["per_source"]["tnsca"]["found"]
    # upcoming, ongoing, or ended in the last 60 days (from 25 Sep 2026); older rows are not kept
    assert min(e["end"] for e in events) >= "2026-09-25"
    assert "tnsca-CO-109-CHE-26-27" in {e["id"] for e in events}  # ended 26 Sep: kept
    assert all(e["state"] == "Tamil Nadu" and e["verified"] for e in events)
    assert sum(1 for e in events if e["tags"]["fide_rated"] and e["tags"]["fide_how"] == "stated") >= 45


def test_a_year_the_page_does_not_offer_is_not_read(web, data_dir):
    web.add(CAL + "?y=2026", fx(Y2026).replace('<li><a href="?y=2027">2027</a></li>', ""))
    run_all(data_dir, config=ONLY_TNSCA)
    assert web.urls("tamilchess.com") == [TNSCA + "robots.txt", CAL + "?y=2026"]


def test_in_january_last_year_is_read_for_recent_events(web, data_dir):
    serve_tnsca(web)
    web.add(CAL + "?y=2028", page(years=range(2017, 2030)))  # an empty year, as offered
    january = datetime(2027, 1, 15, 10, 0, tzinfo=be.IST)
    run_all(data_dir, config=ONLY_TNSCA, now=january)
    assert web.urls("tamilchess.com")[1:] == [CAL + "?y=2027", CAL + "?y=2028", CAL + "?y=2026"]
    events = by_id(data_dir)
    assert "tnsca-RR-24-CBE-26-27" in events  # ended 29 Nov 2026, inside the 60 days


def test_robots_txt_can_switch_the_source_off(web, data_dir):
    serve_tnsca(web)
    web.add(TNSCA + "robots.txt", "User-agent: *\nDisallow: /tournament-registration/\n")
    with pytest.raises(be.SourceError, match="robots.txt of https://tamilchess.com does not allow"):
        run_all(data_dir, config=ONLY_TNSCA)  # the only source switched on: nothing is written
    assert web.urls("tamilchess.com") == [TNSCA + "robots.txt"]
    assert not (data_dir / "events.json").exists()


def test_a_broken_page_keeps_the_events_from_before(web, data_dir):
    serve_tnsca(web)
    run_all(data_dir, config=ONLY_TNSCA)
    before = {e["id"] for e in load_events(data_dir) if e["source"] == "tnsca"}
    web.add(CAL + "?y=2026", "<html><body>Under maintenance</body></html>")
    later = datetime(2026, 11, 25, 12, 0, tzinfo=be.IST)
    with pytest.raises(be.SourceError, match="layout changed"):
        run_all(data_dir, config=ONLY_TNSCA, now=later)  # the only source: nothing is written
    assert {e["id"] for e in load_events(data_dir) if e["source"] == "tnsca"} == before
    # with another source working, the run goes on and TNSCA keeps its events from before
    web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
    both = {n: n in ("tnsca", "aicf") for n in be.SOURCE_MODULES}
    report = run_all(data_dir, config=both, now=later)
    assert report["per_source"]["tnsca"]["status"] == "failed"
    assert {e["id"] for e in load_events(data_dir) if e["source"] == "tnsca"} == before


def test_a_second_run_changes_nothing_and_a_vanished_event_is_kept(web, data_dir):
    serve_tnsca(web)
    run_all(data_dir, config=ONLY_TNSCA)
    later = datetime(2026, 11, 25, 12, 0, tzinfo=be.IST)
    again = run_all(data_dir, config=ONLY_TNSCA, now=later)
    assert again["changes"] == {"new": 0, "changed": 0, "gone": 0}
    without = re.sub(r"<tr[^>]*>\s*<td[^>]*>\s*<a[^>]*2nd-manchester-city[\s\S]*?</tr>", "", fx(Y2026))
    assert "2nd-manchester-city" not in without
    web.add(CAL + "?y=2026", without)
    run_all(data_dir, config=ONLY_TNSCA, now=datetime(2026, 11, 26, 12, 0, tzinfo=be.IST))
    gone = by_id(data_dir)["tnsca-RR-24-CBE-26-27"]
    assert gone["gone_from_source"] is True and gone["name"].startswith("2nd Manchester City")


def test_no_phone_numbers_or_e_mails_are_stored(web, data_dir):
    serve_tnsca(web)
    run_all(data_dir, config=ONLY_TNSCA)
    text = json.dumps([e for e in load_events(data_dir) if e["source"] == "tnsca"], ensure_ascii=False)
    assert not re.search(r"(?<![\d/-])\d{10}(?!\d)|\+91|@", text)


# ---- with the other sources ------------------------------------------------------
def test_importance_and_trust():
    assert be.SOURCE_PRIORITY.index("tnsca") == be.SOURCE_PRIORITY.index("kca") + 1
    assert dedup.PRIMARY_ORDER.index("tnsca") == dedup.PRIMARY_ORDER.index("kca") + 1
    assert "tnsca" in be.VERIFIED_SOURCES and be.LISTED_BY["tnsca"] == "tnsca"
    assert be.SOURCE_LABELS["tnsca"] == "Tamil Nadu State Chess Association"
    assert be.country_for("tnsca") == "IN"


def test_the_same_tournament_groups_with_aicf_and_chessfee_and_aicf_stays_primary():
    record = tnsca.build_event(rows_of()["RR-24/CBE/26-27"], True, TODAY)
    events = [be.canonical(REAL["aicf-486240"]), be.canonical(REAL["chessfee-1727"]), record]
    dedup.group_events(events, [], [])
    by = {e["id"]: e for e in events}
    assert by["tnsca-RR-24-CBE-26-27"]["merged_into"] == "aicf-486240"
    assert by["chessfee-1727"]["merged_into"] == "aicf-486240"
    assert "tnsca" in {x["source"] for x in by["aicf-486240"]["also_listed_on"]}


def test_tnsca_is_primary_over_chessfee_when_aicf_has_no_record():
    record = tnsca.build_event(rows_of()["RR-24/CBE/26-27"], True, TODAY)
    events = [be.canonical(REAL["chessfee-1727"]), record]
    dedup.group_events(events, [], [])
    assert events[0]["merged_into"] == "tnsca-RR-24-CBE-26-27" and events[1]["merged_into"] is None
