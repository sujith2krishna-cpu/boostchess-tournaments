"""T13: two more state associations, Odisha (AOCA, odishachess.com) and Bihar (ABCA,
biharchess.org); Telangana (chesstelangana.com) was checked and not added (its terms forbid
crawling and scraping), and no date of birth is ever stored.

The fixtures are the pages saved on 28 Nov 2026, trimmed by hand (each says so inside it).
"""
import csv
import io
import json
import re
from datetime import date, datetime

import pytest
from bs4 import BeautifulSoup

import build_events as be
import dedup
import quality
from conftest import (ABCA, AOCA, NOW, ROOT, build, by_id, fx, load_events, make_html, row, run_all, serve_abca,
                      serve_aoca)
from eventlib import strip_birth_dates, strip_phones
from sources import abca, aoca, upcsa

TODAY = NOW.date()  # 24 Nov 2026
LATER = datetime(2026, 11, 25, 12, 0, tzinfo=be.IST)
AOCA_PAGE = "aoca_calendar_2026-11-28.html"
ABCA_NEW = "abca_calendar_2026-27_2026-11-28.html"
ABCA_OLD = "abca_calendar_2025-26_2026-11-28.html"
ONLY = {"aoca": {n: n == "aoca" for n in be.SOURCE_MODULES},
        "abca": {n: n == "abca" for n in be.SOURCE_MODULES}}
WITH_AICF = {name: {n: n in (name, "aicf") for n in be.SOURCE_MODULES} for name in ("aoca", "abca")}


def aoca_rows(html=None):
    return aoca.parse_calendar(html or fx(AOCA_PAGE), aoca.CALENDAR_URL)


def aoca_events(html=None, today=TODAY):
    return {e["id"]: e for e in (aoca.build_event(r, today) for r in aoca_rows(html) if aoca.keep(r, today))}


def abca_rows(html=None, season="2026-27"):
    return abca.parse_season(html or fx(ABCA_NEW), season, ABCA + f"calendar-{season}/")


def abca_line(name="Bihar State Open", city="Patna", dates="12-13 December", circular="", results=""):
    circular = f'<a href="{circular}">Circular</a>' if circular else ""
    results = f'<a href="{results}">Result &amp; Standing</a>' if results else ""
    return (f'<tr><td class="column-1">1</td><td class="column-2">{name}</td><td class="column-3">{city}</td>'
            f'<td class="column-4">{dates}</td><td class="column-5">{circular}</td><td class="column-6">{results}</td></tr>')


def abca_table(*lines):
    head = ("<tr><th>Sl. No.</th><th>Event</th><th>City</th><th>State Date</th><th>Circular</th>"
            "<th>Results &amp; Standing</th></tr>")
    return f"<html><body><table>{head}{''.join(lines)}</table></body></html>"


def one(line_html):
    return abca_rows(abca_table(line_html))[0]


# =====================================================================================
# Odisha (AOCA): odishachess.com/calendar/
# =====================================================================================
def test_aoca_reads_every_season_table_and_keeps_only_recent_and_upcoming_events():
    rows = aoca_rows()
    assert len(rows) == 21  # 16 numbered rows of 2026-27 (not "Tentative"), 3 of 2025-26, 2 of 2024-25
    assert sum(1 for r in rows if not r["scheduled"]) == 3  # "3rd National Team School", "Amature", "School"
    kept = aoca_events()
    # on 24 Nov 2026 only the two that ended in the last 60 days are kept; nothing is upcoming yet
    assert sorted(kept) == ["aoca-505918", "aoca-505919"]
    junior = kept["aoca-505919"]
    assert junior["name"] == "Odisha State Under 19 (Junior) Chess Championship"
    assert junior["codes"] == ["505919", "505920"]  # "505919/505920/OD(S)/2026"
    assert (junior["start"], junior["end"]) == ("2026-11-12", "2026-11-15")  # "12-Nov-26", "15-Nov-26"
    assert (junior["city"], junior["state"], junior["country"]) == ("Balasore", "Odisha", "IN")
    assert junior["place_text"] == "Balasore Station Club, Station Road, Balasore, Odisha"
    assert junior["organiser"] == "Balasore District Chess Association"
    assert junior["brochure_url"] == "https://odishachess.com/circular/2026/Odisha-State-Junior-U19-2026.pdf"
    assert junior["source"] == "aoca" and junior["source_url"] == aoca.CALENDAR_URL
    assert junior["flags"]["dates_suspect"] is False and junior["raw_dates"] is None
    assert junior["tags"]["age"] == ["U19"] and junior["tags"]["fide_rated"] is None  # nothing says FIDE
    women = kept["aoca-505918"]
    assert women["city"] is None  # "KIIT University" is a venue, not a town
    assert (women["start"], women["end"]) == ("2026-10-30", "2026-11-02")


def test_aoca_the_national_columns_are_not_read():
    text = json.dumps(list(aoca_events().values()))
    for national in ("Kolkata", "494716", "Miyapur", "496730"):
        assert national not in text  # AICF's own events in other states, in the right-hand columns


@pytest.mark.parametrize("text, expected", [
    ("12-Nov-26", date(2026, 11, 12)), ("14-April-2026", date(2026, 4, 14)),
    ("17-July-26", date(2026, 7, 17)), ("27 Mar 2025", date(2025, 3, 27)),
    ("27-Sep 2025", date(2025, 9, 27)), ("22-12-2024", date(2024, 12, 22)),
    ("8-June-2025", date(2025, 6, 8)), ("31-Sep-2024", None), ("Tentative", None), ("", None),
    ("12-Novx-26", None),
])
def test_aoca_dates_as_the_page_writes_them(text, expected):
    assert aoca.parse_date(text) == expected


@pytest.mark.parametrize("label, expected", [
    ("Under 19 (Junior)\n505919/505920/OD(S)/2026", "Odisha State Under 19 (Junior) Chess Championship"),
    ("66th State Senior\n487135/OD(S)/2026", "66th Odisha State Senior Chess Championship"),
    ("Women\n505918/OD(S)/2026", "Odisha State Women Chess Championship"),
    ("1st K.C.A. International FIDE rating Open Chess Tournament 2026",
     "1st K.C.A. International FIDE rating Open Chess Tournament 2026"),
])
def test_aoca_a_section_alone_gets_the_championships_words(label, expected):
    assert aoca.event_name(label) == expected


@pytest.mark.parametrize("place, city", [
    ("Puri Club, Puri", "Puri"), ("Mother's Public School, Pahal, BBSR", "Bhubaneswar"),
    ("KIIT University", None), ("Manoj The Non-Veg World", None),
    ("Vikash Residential School (LVRS), Bhawanipatna, Kalahandi, Odisha", "Kalahandi"),
    ("KT Global School, Khordha, Odisha -", "Khordha"), ("Takshashila Residential School, 761100", None),
    ("", None),
])
def test_aoca_city_is_the_last_part_only_when_it_reads_like_a_town(place, city):
    assert aoca.city_of(place) == city


def test_aoca_unclear_dates_are_kept_and_flagged_and_codes_shared_by_two_rows_prove_nothing():
    page = fx(AOCA_PAGE).replace("12-Nov-26", "31-Nov-26")
    junior = aoca_events(page)["aoca-505919"]
    assert junior["start"] is None and junior["flags"]["dates_suspect"] is True
    assert junior["raw_dates"] == {"start": "31-Nov-26", "end": "15-Nov-26"}  # kept, nothing fixed
    # two kept rows with the same first code: neither gets the code as its id
    twice = fx(AOCA_PAGE).replace("505918/OD(S)/2026", "505919/OD(S)/2026")
    rows = [r for r in aoca_rows(twice) if aoca.keep(r, TODAY)]
    events, _, _ = aoca.fetch(type("C", (), {"get": lambda self, url: twice})(), {}, TODAY)
    assert len(rows) == 2 and len({e["id"] for e in events}) == 2
    assert all(e["id"].startswith("aoca-505919-") for e in events)


def test_aoca_a_changed_layout_is_an_error_not_an_empty_list():
    with pytest.raises(be.SourceError, match="layout changed"):
        aoca.parse_calendar("<html><body>Under maintenance</body></html>")


def test_aoca_groups_with_aicf_by_its_code_even_when_the_dates_differ():
    # The real AICF record (data/events.json, 28 Nov 2026): AICF says 2-5 Nov, AOCA 30 Oct - 2 Nov.
    aicf = be.canonical({
        "id": "aicf-505918", "codes": ["505918"], "name": "Odisha State Women FIDE Rated Chess Championship 2026",
        "start": "2026-11-02", "end": "2026-11-05", "place_text": "Odisha", "state": "Odisha", "city": None,
        "country": "IN", "source": "aicf", "source_url": "https://aicf.in/all-events/",
        "tags": {"formats": [], "fide_rated": True, "fide_how": "stated", "age": [], "open": None,
                 "girls": None, "categories": []}, "first_seen": "2026-10-01", "last_seen": "2026-11-28"})
    women = aoca_events()["aoca-505918"]
    events = [aicf, women]
    dedup.group_events(events, [], [])
    assert women["merged_into"] == "aicf-505918" and aicf["merged_into"] is None
    assert [x["source"] for x in aicf["also_listed_on"]] == ["aoca"]


def test_aoca_run_reads_one_page_politely_and_a_failed_fetch_keeps_the_events(web, data_dir):
    serve_aoca(web)
    report = run_all(data_dir, config=ONLY["aoca"])
    assert report["per_source"]["aoca"]["status"] == "ok"
    assert web.urls("odishachess.com") == [AOCA + "robots.txt", AOCA + "calendar/"]  # nothing else
    before = {e["id"]: e for e in load_events(data_dir) if e["source"] == "aoca"}
    assert sorted(before) == ["aoca-505918", "aoca-505919"]
    assert all(e["verified"] is True and e["listed_by"] == "aoca" for e in before.values())
    # the next day the site is down: AOCA failed, its events stay exactly as they were
    web.add(AOCA + "calendar/", "down", status=500)
    web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
    report = run_all(data_dir, config=WITH_AICF["aoca"], now=LATER)
    assert report["per_source"]["aoca"]["status"] == "failed"
    after = {e["id"]: e for e in load_events(data_dir) if e["source"] == "aoca"}
    assert after.keys() == before.keys()
    for key in before:
        assert {k: v for k, v in after[key].items() if k != "last_seen"} == \
               {k: v for k, v in before[key].items() if k != "last_seen"}
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))["sources"]["aoca"]
    assert meta["status"] == "failed" and meta["last_error"]["message"]


def test_aoca_a_page_with_far_fewer_rows_counts_as_failed(web, data_dir):
    serve_aoca(web)
    run_all(data_dir, config=ONLY["aoca"])
    soup = BeautifulSoup(fx(AOCA_PAGE), "html.parser")
    tables = soup.find_all("table")
    for table in tables[1:]:
        table.decompose()
    for tr in tables[0].find_all("tr")[5:]:
        tr.decompose()
    short = str(soup)
    assert 0 < len(aoca_rows(short)) < 21 / 2
    web.add(AOCA + "calendar/", short)
    web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
    report = run_all(data_dir, config=WITH_AICF["aoca"], now=LATER)
    assert report["per_source"]["aoca"]["status"] == "failed"
    assert "fewer than half" in report["per_source"]["aoca"]["message"]
    assert {e["id"] for e in load_events(data_dir) if e["source"] == "aoca"} == {"aoca-505918", "aoca-505919"}


def test_aoca_robots_txt_blocking_skips_the_source(web, data_dir):
    serve_aoca(web)
    web.add(AOCA + "robots.txt", "User-agent: *\nDisallow: /calendar/\n")
    web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
    report = run_all(data_dir, config=WITH_AICF["aoca"])
    assert report["per_source"]["aoca"]["status"] == "skipped"
    assert AOCA + "calendar/" not in web.urls()


# =====================================================================================
# Bihar (ABCA): biharchess.org, one calendar page per season, dates without a year
# =====================================================================================
def test_abca_seasons_come_from_the_sites_own_menu_newest_first():
    seasons = abca.season_pages(fx("abca_home_2026-11-28.html"))
    assert seasons[:2] == [("2026-27", ABCA + "calendar-2026-27/"), ("2025-26", ABCA + "calendar-2025-26/")]
    assert ("2023-24", ABCA + "tournament-calendar/") in seasons  # the link the menu gives, not a made-up one
    with pytest.raises(be.SourceError, match="layout changed"):
        abca.season_pages("<html><body><a href='/x/'>Calendar</a></body></html>")


def test_abca_a_year_is_taken_only_from_the_event_itself_never_from_the_season():
    rows = {r["name"]: r for r in abca_rows()}
    assert len(rows) == 23
    mandar = abca.work_out_dates(rows["4th Mandar Fide Rapid Rating Chess Tournament, 2026"])
    assert mandar == (date(2026, 4, 5), date(2026, 4, 5), "name")  # "05 April", the name says 2026
    kishanganj = abca.work_out_dates(rows["SARWATRA SHATRANJ KISHANGANJ FIDE RAPID RATING CHESS TOURNAMENT"])
    assert kishanganj == (date(2026, 5, 3), date(2026, 5, 3), "circular")  # "...-RAPID-RATING-03-05-2026.pdf"
    # "...Tournament-2026.pdfupdated.pdf" has a year but no date: not enough
    assert abca.work_out_dates(rows["SARWATRA SHATRANJ MADHEPURA FIDE RAPID RATING CHESS TOURNAMENT"])[0] is None
    # "Bihar-State-U-11-Circular-2026-27.pdf" is a season, the page "Calendar 2026-27" is a season
    assert abca.work_out_dates(rows["Bihar State Under -11 Open Chess Championship"])[0] is None
    rapid = abca.work_out_dates(rows["Bihar State Rapid Chess Championship"])
    assert rapid == (None, None, "no year on the page, in the name or in the circular")
    assert abca.work_out_dates(rows["Bihar State Amateur Chess Championship"]) == (None, None, "no dates on the page")


@pytest.mark.parametrize("text, expected", [
    ("05 April", ((5, 4), (5, 4), None)), ("28Apr-30 Apr", ((28, 4), (30, 4), None)),
    ("30 Apr-02 May", ((30, 4), (2, 5), None)), ("15-17 May", ((15, 5), (17, 5), None)),
    ("31 Oct-04 Nov.", ((31, 10), (4, 11), None)), ("27-29 Sept", ((27, 9), (29, 9), None)),
    ("12-13 December 2026", ((12, 12), (13, 12), 2026)), ("13-16 Oct. 2025", ((13, 10), (16, 10), 2025)),
    ("08-11 Dec. 2025", ((8, 12), (11, 12), 2025)), ("Soon", None), ("12-13", None), ("5 Foo", None),
])
def test_abca_day_and_month_as_the_page_writes_them(text, expected):
    assert abca.day_months(text) == expected


@pytest.mark.parametrize("line_html, expected", [
    # the date cell has a year: that is the page's own statement
    (abca_line(dates="12-13 December 2026"), (date(2026, 12, 12), date(2026, 12, 13), "page")),
    # over New Year: the year written is the end's
    (abca_line(dates="30 Dec-02 Jan 2027"), (date(2026, 12, 30), date(2027, 1, 2), "page")),
    # over New Year with only a year in the name: which day is "2027"? unclear
    (abca_line(name="Bihar New Year Open 2027", dates="30 Dec-02 Jan"),
     (None, None, "no year: over New Year, and only the name has a year")),
    # the circular's file name gives the last day: the start is the year before
    (abca_line(dates="30 Dec-02 Jan", circular="/wp-content/uploads/2026/12/Open-02-01-2027.pdf"),
     (date(2026, 12, 30), date(2027, 1, 2), "circular")),
    # the name and the circular disagree: unclear, nothing chosen
    (abca_line(name="Bihar Open 2026", dates="03 May", circular="/x/Open-03-05-2027.pdf"),
     (None, None, "the event's own years disagree")),
    (abca_line(name="Bihar Open 2026 and 2027", dates="03 May"), (None, None, "two different years in the name")),
    # a season in the name is not a year
    (abca_line(name="Bihar State School Championship 2026-27", dates="22-24 November"),
     (None, None, "no year on the page, in the name or in the circular")),
    (abca_line(name="Bihar Open 2027", dates="30 Feb"), (None, None, "not a real date")),
])
def test_abca_working_out_dates(line_html, expected):
    assert abca.work_out_dates(one(line_html)) == expected


def test_abca_keeps_upcoming_and_unplayed_events_and_unclear_dates_are_never_guessed():
    events = {e["name"]: e for e in (abca.build_event(r, TODAY) for r in abca_rows() if abca.keep(r, TODAY, True))}
    assert sorted(events) == ["Bihar State Amateur Chess Championship", "Bihar State Blitz Chess Championship",
                              "Bihar State Rapid Chess Championship"]
    rapid = events["Bihar State Rapid Chess Championship"]
    assert rapid["start"] is None and rapid["end"] is None  # "12-13 December": no year, so no dates
    assert rapid["flags"]["dates_suspect"] is True
    assert rapid["raw_dates"] == {"start": "12-13 December", "end": "12-13 December"}
    assert (rapid["city"], rapid["state"], rapid["country"]) == ("Jehanabad", "Bihar", "IN")
    assert rapid["brochure_url"] == ABCA + "wp-content/uploads/2026/11/Bihar-State-Rapid-Blitz-Circular-26.pdf"
    assert rapid["tags"]["formats"] == ["rapid"] and rapid["source_url"] == ABCA + "calendar-2026-27/"
    assert rapid["id"] == abca.event_id({"season": "2026-27", "name": "Bihar State Rapid Chess Championship"})
    # played (it has a results link) but no year: not kept, not guessed
    schools = next(r for r in abca_rows() if r["name"] == "Bihar State Schools Chess Championship")
    assert schools["results_url"] and abca.keep(schools, TODAY, True) is False
    # an older season page: only events with real dates can be kept (they are all past here)
    old = abca_rows(fx(ABCA_OLD), "2025-26")
    assert len(old) == 12 and all(abca.work_out_dates(r)[2] == "page" for r in old)
    assert not [r for r in old if abca.keep(r, TODAY, False)]
    assert abca.keep(one(abca_line(dates="")), TODAY, False) is False  # undated, older season: left out


def test_abca_a_dated_upcoming_event_groups_with_its_chess_results_page():
    page = abca_table(abca_line(name="Bihar State Rapid Chess Championship", city="Jehanabad",
                                dates="12-13 December 2026",
                                results="https://s2.chess-results.com/tnr1560001.aspx?lan=1&SNode=S0"))
    mine = abca.build_event(abca_rows(page)[0], TODAY)
    assert (mine["start"], mine["end"], mine["flags"]["dates_suspect"]) == ("2026-12-12", "2026-12-13", False)
    other = be.canonical({"id": "chessresults_ind-1560001", "name": "BIHAR STATE RAPID 2026", "start": "2026-12-12",
                          "end": "2026-12-13", "state": "Bihar", "city": "Jehanabad", "country": "IN",
                          "source": "chessresults_ind", "source_url": "https://chess-results.com/tnr1560001.aspx?lan=1",
                          "first_seen": "2026-11-20", "last_seen": "2026-11-24"})
    events = [other, mine]
    dedup.group_events(events, [], [])
    assert other["merged_into"] == mine["id"] and mine["merged_into"] is None  # the association is primary


def test_abca_pairs_csv_still_decides():
    mine = abca.build_event(abca_rows(abca_table(abca_line(name="Bihar State Open Championship",
                                                           dates="12-13 December 2026")))[0], TODAY)
    look_alike = be.canonical({"id": "chessresults_ind-1", "name": "Bihar State Open Championship",
                               "start": "2026-12-12", "end": "2026-12-13", "state": "Bihar", "city": "Patna",
                               "country": "IN", "source": "chessresults_ind",
                               "source_url": "https://chess-results.com/tnr1.aspx", "first_seen": "2026-11-20",
                               "last_seen": "2026-11-24"})
    events = [look_alike, mine]
    dedup.group_events(events, [{"line": 2, "a": mine["id"], "b": "chessresults_ind-1", "decision": "not_same",
                                 "note": None}], [])
    assert look_alike["merged_into"] is None and mine["merged_into"] is None
    events = [be.canonical(dict(look_alike)), be.canonical(dict(mine))]
    dedup.group_events(events, [{"line": 2, "a": mine["id"], "b": "chessresults_ind-1", "decision": "undecided",
                                 "note": None}], [])
    assert events[0]["merged_into"] == mine["id"]  # "undecided" changes nothing: the rules decide


def test_abca_run_reads_the_menu_and_two_seasons_and_unclear_dates_go_to_review(web, data_dir):
    serve_abca(web)
    report = run_all(data_dir, config=ONLY["abca"])
    assert report["per_source"]["abca"]["status"] == "ok"
    assert web.urls("biharchess.org") == [ABCA + "robots.txt", ABCA, ABCA + "calendar-2026-27/",
                                          ABCA + "calendar-2025-26/"]
    mine = [e for e in load_events(data_dir) if e["source"] == "abca"]
    assert len(mine) == 3 and all(e["start"] is None for e in mine)
    assert all(e["verified"] is True and e["listed_by"] == "abca" for e in mine)
    review = list(csv.DictReader(io.StringIO((data_dir / "review.csv").read_text("utf-8"))))
    lines = {r["id"]: r for r in review if r["id"].startswith("abca-")}
    assert len(lines) == 3 and all(r["kind"] == "missing" for r in lines.values())
    rapid = next(r for r in lines.values() if r["name"] == "Bihar State Rapid Chess Championship")
    assert "the page says '12-13 December'" in rapid["missing"] and rapid["missing"].startswith("fide, dates")
    assert rapid["add_to_file"] == "data/manual/overrides.csv"
    assert rapid["line_to_add"].startswith(rapid["id"] + ",?,?,")  # start_date and end_date to fill in
    amateur = next(r for r in lines.values() if r["name"] == "Bihar State Amateur Chess Championship")
    assert "the page says nothing" in amateur["missing"]
    report_q = json.loads((data_dir / "quality.json").read_text("utf-8"))
    assert report_q["review"]["missing"] == sum(1 for r in review if r["kind"] == "missing")


def test_abca_an_override_with_the_dates_from_the_circular_fills_them_in(web, data_dir):
    serve_abca(web)
    run_all(data_dir, config=ONLY["abca"])
    rapid = next(e for e in load_events(data_dir) if e["name"] == "Bihar State Rapid Chess Championship")
    (data_dir / "manual" / "overrides.csv").write_text(
        ",".join(be.OVERRIDES_CSV_COLUMNS) + "\n" + rapid["id"] + ",12-12-2026,13-12-2026" +
        "," * (len(be.OVERRIDES_CSV_COLUMNS) - 3) + "\n", encoding="utf-8")
    run_all(data_dir, config=ONLY["abca"], now=LATER)
    fixed = by_id(data_dir)[rapid["id"]]
    assert (fixed["start"], fixed["end"], fixed["flags"]["dates_suspect"]) == ("2026-12-12", "2026-12-13", False)
    assert fixed["raw_dates"] == {"start": "12-13 December", "end": "12-13 December"}  # the page's text stays
    review = (data_dir / "review.csv").read_text("utf-8")
    assert "the page says '12-13 December'" not in review


def test_abca_a_failed_fetch_keeps_the_events_from_before(web, data_dir):
    serve_abca(web)
    run_all(data_dir, config=ONLY["abca"])
    before = {e["id"]: e for e in load_events(data_dir) if e["source"] == "abca"}
    for failure in ("home page down", "season page changed"):
        if failure == "home page down":
            web.add(ABCA, "down", status=500)
        else:
            serve_abca(web)
            web.add(ABCA + "calendar-2026-27/", "<html><body>Under maintenance</body></html>")
        web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
        report = run_all(data_dir, config=WITH_AICF["abca"], now=LATER)
        assert report["per_source"]["abca"]["status"] == "failed", failure
        after = {e["id"]: e for e in load_events(data_dir) if e["source"] == "abca"}
        assert after.keys() == before.keys()
        assert all(after[k]["name"] == before[k]["name"] and after[k]["gone_from_source"] is False for k in before)


def test_abca_an_event_that_leaves_the_page_stays_as_gone(web, data_dir):
    serve_abca(web)
    run_all(data_dir, config=ONLY["abca"])
    without = re.sub(r"<tr class=\"row-24\">[\s\S]*?</tr>", "", fx(ABCA_NEW))
    assert "Amateur" not in without
    web.add(ABCA + "calendar-2026-27/", without)
    run_all(data_dir, config=ONLY["abca"], now=LATER)
    amateur = next(e for e in load_events(data_dir) if e["name"] == "Bihar State Amateur Chess Championship")
    assert amateur["gone_from_source"] is True and amateur["last_seen"] == "2026-11-24"


# =====================================================================================
# Both, and Telangana
# =====================================================================================
def test_importance_trust_and_districts():
    order = be.SOURCE_PRIORITY
    assert order.index("upcsa") < order.index("aoca") < order.index("abca") < order.index("chessfee")
    assert dedup.PRIMARY_ORDER.index("aoca") == dedup.PRIMARY_ORDER.index("upcsa") + 1
    assert dedup.PRIMARY_ORDER.index("abca") == dedup.PRIMARY_ORDER.index("aoca") + 1
    for name, label in (("aoca", "All Odisha Chess Association"), ("abca", "All Bihar Chess Association")):
        assert name in be.VERIFIED_SOURCES and be.LISTED_BY[name] == name
        assert be.SOURCE_LABELS[name] == label and be.country_for(name) == "IN"
        assert name in dedup.DISTRICT_SOURCES  # a district town never blocks a match with a town


def test_config_has_both_with_enabled_and_publish_and_no_telangana():
    raw = json.loads((ROOT / "config" / "sources.json").read_text("utf-8"))
    for name in ("aoca", "abca"):
        assert raw[name] == {"enabled": True, "publish": True}
    assert not [n for n in list(raw) + list(be.SOURCE_MODULES) if re.search(r"(?i)telangana|tsca|chesstelangana", n)]


def test_quality_json_counts_telangana_odisha_and_bihar(web, data_dir):
    serve_aoca(web)
    serve_abca(web)
    run_all(data_dir, config={n: n in ("aoca", "abca") for n in be.SOURCE_MODULES})
    states = json.loads((data_dir / "quality.json").read_text("utf-8"))["states"]
    for state in ("Telangana", "Odisha", "Bihar"):
        assert state in states["by_state"]  # 0 included: a state with none is shown as 0
    events = [be.canonical(dict(e)) for e in load_events(data_dir)]
    upcoming = [e for e in events if quality.is_shown(e) and quality.in_window(e, "upcoming", TODAY)]
    assert states["by_state"]["Odisha"] == sum(1 for e in upcoming if e["state"] == "Odisha")
    assert states["by_state"]["Bihar"] == 0  # its three events have no dates yet, so none is "upcoming"


def test_telangana_is_never_fetched(web, data_dir):
    from test_sources import serve_everything
    serve_everything(web)
    serve_aoca(web)
    serve_abca(web)
    run_all(data_dir)
    assert not [u for u in web.urls() if "chesstelangana" in u]


# ---- no date of birth, ever ------------------------------------------------------------
@pytest.mark.parametrize("text, kept", [
    ("A. Player (DOB: 12-03-2014)", "A. Player"),
    ("D.O.B 2014-03-12, Hyderabad", "Hyderabad"),
    ("Date of Birth: 12 March 2014", ""),
    ("born on 12/03/2014 in Patna", "in Patna"),
    ("Birth date - March 12, 2014", ""),
    ("Telangana State Under-11 Chess Championship 2026", "Telangana State Under-11 Chess Championship 2026"),
    ("Celebrating the Birthday of Mr. X", "Celebrating the Birthday of Mr. X"),
])
def test_a_date_of_birth_is_removed_from_every_piece_of_text(text, kept):
    cleaned = strip_phones(text)
    assert not re.search(r"2014|12-03|03-12|12/03|March 12|12 March", cleaned)
    assert re.sub(r"[\s(),]+", " ", cleaned).strip() == kept
    assert strip_birth_dates(text) == text or "2014" not in strip_birth_dates(text)


def test_no_date_of_birth_reaches_a_record_from_the_new_or_old_parsers():
    # made-up rows (fake names, fake dates) as a careless page might write them
    label = "Under 11 (Telangana-style list: Fake Kid DOB: 01-02-2015)\n483174/OD(S)/2026"
    page = fx(AOCA_PAGE).replace("Under 11<br/>\n483174/483175/OD(S)/ 2026", label.replace("\n", "<br/>"))
    page = page.replace("Manoj The Non-Veg World", "Hall, Date of Birth 01 Feb 2015, Puri")
    page = page.replace("18-Jun-26", "18-Nov-26").replace("21-Jun-2026", "21-Nov-2026")
    under11 = aoca_events(page)["aoca-483174"]
    bihar = abca.build_event(one(abca_line(name="Bihar Open (DOB 2015-02-01)", city="Patna D.O.B. 01/02/2015")),
                             TODAY)
    upcsa_row = upcsa.parse_list(fx("upcsa_tournaments_2026-11-28.html"))[0]
    upcsa_row = dict(upcsa_row, name=upcsa_row["name"] + " born on 01-02-2015", city="Jhansi DOB: 01-02-2015")
    for record in (under11, bihar, upcsa.build_event(upcsa_row, TODAY)):
        text = json.dumps(record, ensure_ascii=False)
        assert not re.search(r"2015|01-02|01/02|01 Feb", text), record["id"]
        assert not re.search(r"(?i)\bd\.?o\.?b\b|date of birth|born", text), record["id"]


def test_the_committed_files_hold_no_date_of_birth():
    files = [ROOT / "data" / n for n in ("events.json", "meta.json", "quality.json", "review.csv")]
    files += sorted((ROOT / "data" / "sources").glob("*.json"))
    for path in files:
        text = path.read_text("utf-8")
        assert not re.search(r'(?i)"[a-z_]*(?:dob|birth)[a-z_]*"\s*:', text), path.name  # no such field
        assert not re.search(r"(?i)\b(?:d\.?o\.?b\b|date\s+of\s+birth|birth\s*date|born\s+on)", text), path.name


# ---- an event with no start date that is not over is hidden, kept, and on review.csv ----------
def review_lines(data_dir):
    return list(csv.DictReader(io.StringIO((data_dir / "review.csv").read_text("utf-8"))))


def test_undated_events_that_are_not_over_are_hidden_but_kept_and_on_review(web, data_dir):
    serve_abca(web)
    run_all(data_dir, config=ONLY["abca"])
    mine = [e for e in load_events(data_dir) if e["source"] == "abca"]
    assert len(mine) == 3 and all(e["start"] is None and e["hidden"] is True for e in mine)
    assert all(e["overridden"] is None for e in mine)  # hidden by the tool, not by a person
    lines = [r for r in review_lines(data_dir) if r["id"].startswith("abca-")]
    assert len(lines) == 3 and all("hidden from players" in r["missing"] for r in lines)
    report = json.loads((data_dir / "quality.json").read_text("utf-8"))
    assert report["overall"]["upcoming"]["events"] == 0  # nothing of it is shown


def test_an_aicf_event_without_dates_is_hidden_and_one_that_is_over_is_not(data_dir):
    build(data_dir, [row("No Dates Open", "471848", start="", end=""),
                     row("Ended Open", "400002", start="", end="01-11-2026"),
                     row("Dated Open", "400003")])
    events = by_id(data_dir)
    assert events["aicf-471848"]["hidden"] is True and events["aicf-471848"]["start"] is None
    assert events["aicf-400002"]["hidden"] is False  # no start, but its end is past: over, not hidden
    assert events["aicf-400003"]["hidden"] is False
    ids = [r["id"] for r in review_lines(data_dir) if r["kind"] == "missing"]
    assert "aicf-471848" in ids and "aicf-400002" not in ids


def test_dates_from_overrides_show_the_event_again_and_take_it_off_review(web, data_dir):
    serve_abca(web)
    run_all(data_dir, config=ONLY["abca"])
    rapid = next(e for e in load_events(data_dir) if e["name"] == "Bihar State Rapid Chess Championship")
    amateur = next(e for e in load_events(data_dir) if e["name"] == "Bihar State Amateur Chess Championship")
    columns = be.OVERRIDES_CSV_COLUMNS
    line = dict.fromkeys(columns, "")
    line.update(key=rapid["id"], start_date="12-12-2026", end_date="13-12-2026", fide_rated="yes",
                note="from the circular")
    hide = dict.fromkeys(columns, "")
    hide.update(key=amateur["id"], hide="yes")
    (data_dir / "manual" / "overrides.csv").write_text(
        ",".join(columns) + "\n" + ",".join(line[c] for c in columns) + "\n"
        + ",".join(hide[c] for c in columns) + "\n", encoding="utf-8")
    run_all(data_dir, config=ONLY["abca"], now=LATER)
    events = by_id(data_dir)
    assert events[rapid["id"]]["hidden"] is False and events[rapid["id"]]["start"] == "2026-12-12"
    assert events[amateur["id"]]["hidden"] is True  # hidden by a person: off the review list too
    ids = {r["id"] for r in review_lines(data_dir)}
    assert rapid["id"] not in ids and amateur["id"] not in ids
    assert len([i for i in ids if i.startswith("abca-")]) == 1  # only the Blitz is still to do


def test_a_year_given_later_by_the_page_shows_the_event_again(web, data_dir):
    serve_abca(web)
    run_all(data_dir, config=ONLY["abca"])
    web.add(ABCA + "calendar-2026-27/", fx(ABCA_NEW).replace(">12-13 December<", ">12-13 December 2026<"))
    run_all(data_dir, config=ONLY["abca"], now=LATER)
    rapid = next(e for e in load_events(data_dir) if e["name"] == "Bihar State Rapid Chess Championship")
    assert rapid["start"] == "2026-12-12" and rapid["hidden"] is False


def test_the_committed_bihar_overrides_name_their_source():
    lines = list(csv.DictReader(io.StringIO((ROOT / "data" / "manual" / "overrides.csv").read_text("utf-8"))))
    bihar = {r["key"]: r for r in lines if r["key"].startswith("abca-")}
    assert set(bihar) == {"abca-d1fd24b5", "abca-19fb180e"}  # State Rapid and State Blitz
    for line in bihar.values():
        assert "Bihar-State-Rapid-Blitz-Circular-26.pdf" in line["note"] and "2026" in line["note"]
        assert line["registration_deadline"] == "10-12-2026" and line["fide_rated"] == "yes"
    assert (bihar["abca-d1fd24b5"]["start_date"], bihar["abca-d1fd24b5"]["end_date"]) == ("12-12-2026", "13-12-2026")
    assert (bihar["abca-19fb180e"]["start_date"], bihar["abca-19fb180e"]["end_date"]) == ("13-12-2026", "13-12-2026")
    doc = json.loads((ROOT / "data" / "events.json").read_text("utf-8"))
    built = doc["generated_at"][:10]  # the day the committed data was built (India)
    events = {e["id"]: e for e in doc["events"]}
    for key in bihar:
        assert events[key]["hidden"] is False and events[key]["start"]
    for key, event in events.items():  # nothing undated and not over is shown
        if not event["start"] and not (event["end"] and event["end"] < built):
            assert event["hidden"] is True, key
