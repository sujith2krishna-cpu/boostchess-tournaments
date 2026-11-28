"""T12: the UP Chess Sports Association tournaments page (upchess.org/tournament.php).

The fixture is the saved page of 28 Nov 2026, trimmed to the menu, the note and the table.
"""
import json
import re
from datetime import datetime

import build_events as be
import dedup
from conftest import NOW, UPCSA, by_id, fx, load_events, make_html, row, run_all, serve_upcsa
from sources import upcsa

ONLY_UPCSA = {n: n == "upcsa" for n in be.SOURCE_MODULES}
TODAY = NOW.date()  # 24 Nov 2026
PAGE = "upcsa_tournaments_2026-11-28.html"
LIST = UPCSA + "tournament.php"

# The real AICF record of an event UPCSA also lists (data/events.json, 28 Nov 2026).
AICF_KAPIL_DEV = {
    "id": "aicf-505328", "codes": ["505328"],
    "name": "KAPIL DEV KHARE MEMORIAL FIDE RATED OPEN CLASSICAL CHESS TOURNAMENT",
    "start": "2027-01-05", "end": "2027-01-10", "place_text": "Gola Gokaran Nath, Uttar Pradesh",
    "state": "Uttar Pradesh", "city": "Gola Gokaran Nath", "country": "IN", "source": "aicf",
    "source_url": "https://aicf.in/all-events/",
    "brochure_url": "https://aicf.in/wp-content/uploads/2026/11/Kapil-Dev-Khare-Memorial-Chess-Tournament-2027.pdf",
    "tags": {"formats": ["classical"], "fide_rated": True, "fide_how": "stated", "age": [],
             "open": True, "girls": None, "categories": []},
    "first_seen": "2026-11-10", "last_seen": "2026-11-28"}


def events_of(html=None):
    return {e["id"]: e for e in (upcsa.build_event(r, TODAY)
                                 for r in upcsa.parse_list(html or fx(PAGE), LIST))}


def table(*rows):
    """A small page in the site's layout (for cases the saved page does not show)."""
    head = ("<tr><th>S.No</th><th>Tournament_Name</th><th>Tournament_Level &amp; Type</th>"
            "<th>Tournament_Date</th><th>Entry_Apply_Dates</th><th>Entry_Apply_Dates with_Late_Fee</th>"
            "<th>District/City</th><th>Status</th><th>Brochure Result Link</th></tr>")
    return f'<html><body><table class="table" id="player_table">{head}{"".join(rows)}</table></body></html>'


def line(number="200", name="Some Open 2027", dates="<b>Start</b> : 09-Jan-2027<br><b>End</b> : 10-Jan-2027",
         entry="-", city="Varanasi", status="-",
         links='<a href="../uploads/prospectus/x.pdf">View Brochure</a>'
               '<button>Result Link Not Updated</button>',
         level="<b>Level</b> : State Level<br><b>Type</b> : For All"):
    return (f"<tr><td>1</td><td>{name}</td><td>{level}</td><td>{dates}</td><td>{entry}</td><td>-</td>"
            f'<td>{city}</td><td>{status}</td><td data-id="{number}"><center>{links}</center></td></tr>')


# ---- reading the page ------------------------------------------------------------
def test_every_row_of_the_saved_page_is_read():
    found = events_of()
    assert sorted(found) == sorted(f"upcsa-{n}" for n in (85, 86, 87, 88, 89, 90, 91, 96))
    women = found["upcsa-96"]
    assert women["name"] == "UP State Senior Women Chess Championship 2026-27"
    assert (women["start"], women["end"]) == ("2026-11-21", "2026-11-22")
    assert (women["city"], women["state"], women["country"]) == ("Jhansi", "Uttar Pradesh", "IN")
    assert women["place_text"] == "Jhansi, Uttar Pradesh"
    assert women["registration_deadline"] == "2026-11-18"  # the normal entry dates, not the late fee
    assert women["tags"]["categories"] == ["State Level"]
    assert women["brochure_url"] == ("https://upchess.org/uploads/prospectus/"
                                     "Prospectus%20Senior%20Women%20State%20Championship%202026%201.pdf")
    assert women["results_url"] is None  # "Result Link Not Updated" is a button, not a link
    assert women["source_url"] == LIST and women["source"] == "upcsa"
    assert women["flags"]["dates_suspect"] is False and women["cancelled"] is False


def test_facts_come_only_from_what_the_page_says():
    found = events_of()
    kapil = found["upcsa-90"]
    assert (kapil["start"], kapil["end"], kapil["city"]) == ("2027-01-05", "2027-01-10", "Lakhimpur Kheri")
    assert kapil["registration_deadline"] is None  # entry dates "-": nothing stated
    assert kapil["tags"]["fide_rated"] is True and kapil["tags"]["fide_how"] == "stated"  # the name says so
    assert kapil["tags"]["formats"] == ["classical"] and kapil["tags"]["categories"] == ["National Level"]
    assert found["upcsa-89"]["city"] == "Ghaziabad"  # "GHAZIABAD" on the page
    state_champs = found["upcsa-89"]
    assert state_champs["tags"]["fide_rated"] is None  # nothing on the page says FIDE
    # "International Chess Day" is the name of a day, not an international event
    day = found["upcsa-85"]
    assert "International Chess Day" in day["name"] and day["tags"]["fide_rated"] is None


def test_unclear_values_stay_empty():
    bad_dates = "<b>Start</b> : 31-Feb-2027<br><b>End</b> : 10-Jan-2027"
    late = "<b>Start</b> : 01-Jan-2027<br><b>End</b> : 12-Jan-2027"  # after the event: not a deadline
    page = table(line("201", dates=bad_dates), line("202", entry=late),
                 line("203", entry="<b>Start</b> : 01-Jan-2027<br><b>End</b> : 2027"))
    found = events_of(page)
    e = found["upcsa-201"]
    assert e["start"] is None and e["flags"]["dates_suspect"] is True
    assert "31-Feb-2027" in json.dumps(e["raw_dates"])  # the page's text is kept, nothing is fixed
    assert found["upcsa-202"]["registration_deadline"] is None
    assert found["upcsa-203"]["registration_deadline"] is None


def test_result_link_cancelled_status_and_school_type():
    links = ('<a href="../uploads/prospectus/y.pdf">View Brochure</a>'
             '<a href="https://chess-results.com/tnr1234567.aspx?lan=1">Result Link</a>')
    page = table(line("204", links=links, status="Cancelled",
                      level="<b>Level</b> : District Level<br><b>Type</b> : For Schools"),
                 line("", name="No Number Open"))
    found = events_of(page)
    e = found["upcsa-204"]
    assert e["results_url"] == "https://chess-results.com/tnr1234567.aspx?lan=1"
    assert e["brochure_url"] == "https://upchess.org/uploads/prospectus/y.pdf"
    assert e["cancelled"] is True
    assert e["tags"]["categories"] == ["District Level", "For Schools"]
    assert [k for k in found if k != "upcsa-204"][0].startswith("upcsa-")  # a hash id when no number


def test_a_changed_layout_is_an_error_not_an_empty_list():
    import pytest
    with pytest.raises(be.SourceError, match="layout changed"):
        upcsa.parse_list("<html><body>Under maintenance</body></html>", LIST)
    assert upcsa.parse_list(table(), LIST) == []


# ---- a run ---------------------------------------------------------------------
def test_run_reads_one_page_politely(web, data_dir):
    serve_upcsa(web)
    report = run_all(data_dir, config=ONLY_UPCSA)
    assert report["per_source"]["upcsa"]["status"] == "ok"
    assert web.urls("upchess.org") == [UPCSA + "robots.txt", LIST]  # nothing else
    mine = [e for e in load_events(data_dir) if e["source"] == "upcsa"]
    assert len(mine) == 8
    for e in mine:
        assert e["verified"] is True and e["listed_by"] == "upcsa" and e["country"] == "IN"


def test_robots_txt_blocking_skips_the_source(web, data_dir):
    serve_upcsa(web)
    web.add(UPCSA + "robots.txt", "User-agent: *\nDisallow: /tournament.php\n")
    web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
    report = run_all(data_dir, config={n: n in ("upcsa", "aicf") for n in be.SOURCE_MODULES})
    assert report["per_source"]["upcsa"]["status"] == "skipped"
    assert LIST not in web.urls()


def test_a_broken_page_keeps_the_events_from_before_and_vanished_ones_stay(web, data_dir):
    serve_upcsa(web)
    run_all(data_dir, config=ONLY_UPCSA)
    before = {e["id"] for e in load_events(data_dir) if e["source"] == "upcsa"}
    web.add(LIST, "<html><body>Under maintenance</body></html>")
    web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
    later = datetime(2026, 11, 25, 12, 0, tzinfo=be.IST)
    report = run_all(data_dir, config={n: n in ("upcsa", "aicf") for n in be.SOURCE_MODULES}, now=later)
    assert report["per_source"]["upcsa"]["status"] == "failed"
    assert {e["id"] for e in load_events(data_dir) if e["source"] == "upcsa"} == before
    without = re.sub(r"<tr>(?:(?!</tr>)[\s\S])*data-id=\"96\"[\s\S]*?</tr>", "", fx(PAGE))
    assert 'data-id="96"' not in without
    web.add(LIST, without)
    run_all(data_dir, config=ONLY_UPCSA, now=datetime(2026, 11, 26, 12, 0, tzinfo=be.IST))
    gone = by_id(data_dir)["upcsa-96"]
    assert gone["gone_from_source"] is True and gone["last_seen"] == "2026-11-24"


def test_no_phone_numbers_fees_or_e_mails_are_stored(web, data_dir):
    serve_upcsa(web)
    run_all(data_dir, config=ONLY_UPCSA)
    text = json.dumps([e for e in load_events(data_dir) if e["source"] == "upcsa"], ensure_ascii=False)
    assert not re.search(r"(?<![\d/-])\d{10}(?!\d)|\+91|[\w.+-]+@[\w-]+\.|Fee|Rs\.", text)


# ---- with the other sources ------------------------------------------------------
def test_importance_and_trust():
    assert be.SOURCE_PRIORITY.index("upcsa") == be.SOURCE_PRIORITY.index("ksca") + 1
    assert dedup.PRIMARY_ORDER.index("upcsa") == dedup.PRIMARY_ORDER.index("ksca") + 1
    assert "upcsa" in be.VERIFIED_SOURCES and be.LISTED_BY["upcsa"] == "upcsa"
    assert be.SOURCE_LABELS["upcsa"] == "UP Chess Sports Association"
    assert be.country_for("upcsa") == "IN"


def test_a_district_never_blocks_a_town_and_the_aicf_record_stays_primary():
    aicf = be.canonical(dict(AICF_KAPIL_DEV))
    mine = events_of()["upcsa-90"]  # "Lakhimpur Kheri", the district Gola Gokaran Nath is in
    result = dedup.compare(dedup.Features(aicf), dedup.Features(mine))
    assert result["reason"] != "different city" and result["hard"] is False
    # "1st" in UPCSA's name keeps the score just under "same": flagged for review, not guessed
    assert result["decision"] == "possible"
    events = [be.canonical(dict(AICF_KAPIL_DEV)), dict(mine)]
    dedup.group_events(events, [], [])
    assert events[1]["merged_into"] is None and events[1]["flags"]["possible_duplicate_of"] == "aicf-505328"
    # once a person says so in pairs.csv they are one tournament, AICF shown
    events = [aicf, mine]
    dedup.group_events(events, [{"line": 2, "a": "aicf-505328", "b": "upcsa-90", "decision": "same",
                                 "note": None}], [])
    assert mine["merged_into"] == "aicf-505328" and aicf["merged_into"] is None
    assert aicf["city"] == "Gola Gokaran Nath"  # the town is kept, not replaced by the district
    assert [x["source"] for x in aicf["also_listed_on"]] == ["upcsa"]
    # two different UP places on non-district sources are still different
    assert dedup._same_city({"source": "aicf", "city": "Agra"}, {"source": "chessfee", "city": "Lucknow"}) is False


def test_the_deadline_fills_the_primarys_gap():
    shown = be.canonical({**AICF_KAPIL_DEV, "id": "aicf-1", "start": "2026-11-21", "end": "2026-11-22",
                          "name": "UP State Senior Women Chess Championship 2026-27", "city": "Jhansi",
                          "codes": []})
    mine = events_of()["upcsa-96"]
    events = [shown, mine]
    dedup.group_events(events, [], [])
    assert mine["merged_into"] == "aicf-1" and shown["registration_deadline"] == "2026-11-18"
