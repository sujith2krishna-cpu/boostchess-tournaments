"""T10: the Karnataka State Chess Association tournaments list (karnatakachess.com).

Page 1 is a saved, trimmed page (26 Nov 2026); page 2 is made by hand from its markup.
"""
import json
import re
from datetime import date, datetime

import pytest

import build_events as be
import dedup
from conftest import KSCA, NOW, by_id, fx, load_events, make_html, row, run_all, serve_ksca
from sources import ksca

ONLY_KSCA = {n: n == "ksca" for n in be.SOURCE_MODULES}
TODAY = NOW.date()  # 24 Nov 2026
P1, P2 = "ksca_tournaments_2026-11-26.html", "ksca_tournaments_page2_made.html"
LIST, PAGE2 = KSCA + "tournaments/", KSCA + "tournaments/list/page/2/"

# The real AICF records of two events KSCA also lists (data/events.json, 26 Nov 2026).
AICF_INVENTIVE = {
    "id": "aicf-503301", "codes": ["503301"], "name": "INVENTIVE 2.0 FIDE-rated Rapid Chess Tournament",
    "start": "2026-12-05", "end": "2026-12-05", "place_text": "Bangalore, Karnataka",
    "state": "Karnataka", "city": "Bangalore", "country": "IN", "source": "aicf",
    "source_url": "https://aicf.in/all-events/",
    "brochure_url": "https://aicf.in/wp-content/uploads/2026/10/INVENTIVE-2.0-FIDE-Rapid-Rated-Chess-Tournament-Dec-5th-2026._compressed.pdf",
    "tags": {"formats": ["rapid"], "fide_rated": True, "fide_how": "stated", "age": [], "open": None,
             "girls": None, "categories": []},
    "first_seen": "2026-11-01", "last_seen": "2026-11-26"}
AICF_CHADURANGOTSAVA = {
    "id": "aicf-511064", "codes": ["511064"],
    "name": "Chadurangotsava All India Open Rapid Rated Tournament 2026",
    "start": "2026-12-06", "end": "2026-12-06", "place_text": "Karnataka", "state": "Karnataka",
    "city": None, "country": "IN", "source": "aicf", "source_url": "https://aicf.in/all-events/",
    "brochure_url": "https://aicf.in/wp-content/uploads/2026/11/Chadurangotsava-rapid-rating.pdf",
    "tags": {"formats": ["rapid"], "fide_rated": True, "fide_how": "stated", "age": [], "open": True,
             "girls": None, "categories": []},
    "first_seen": "2026-11-20", "last_seen": "2026-11-26"}


def rows_of(name=P1, url=LIST):
    return {r["post"]: r for r in ksca.parse_list(fx(name), url)["rows"]}


def event(post, name=P1, url=LIST):
    return ksca.build_event(rows_of(name, url)[post], TODAY)


def view(articles="", nav=""):
    """A small list page in the site's layout (for cases the saved page does not show)."""
    return (f'<html><body><div class="tribe-events tribe-events-view tribe-events-view--list">'
            f"{articles}{nav}</div></body></html>")


def article(post="9001", start_attr="2026-12-20", start="December 20 @ 9:00 am", end="",
            cats=("monthly-tournaments",), title="Some Open 2026"):
    classes = " ".join(f"tribe_events_cat-{c}" for c in cats)
    end_span = f' - <span class="tribe-event-date-end">{end}</span>' if end else ""
    return (f'<article class="tribe-events-calendar-list__event post-{post} {classes}">'
            f'<h4 class="tribe-events-calendar-list__event-title"><a href="{KSCA}tournaments/x-{post}/">'
            f'{title}</a></h4><time class="tribe-events-calendar-list__event-datetime" '
            f'datetime="{start_attr}"><span class="tribe-event-date-start">{start}</span>{end_span}</time>'
            f"</article>")


# ---- reading the page ------------------------------------------------------------
def test_saved_page_rows_and_the_next_link():
    parsed = ksca.parse_list(fx(P1), LIST)
    assert len(parsed["rows"]) == 12 and parsed["next"] == PAGE2
    assert parsed["rows"][0] == {
        "post": "7128", "name": "South Open FIDE Rapid Chess Tournament 2026",
        "detail_url": KSCA + "tournaments/south-open-fide-rapid-chess-tournament-2026/",
        "start_attr": "2026-11-28", "start_text": "November 28 @ 8:00 am", "end_text": "",
        "venue": "Sri Sai Palace",
        "address": "Near Vishwa Vokkaligara Maha Samsthana, NICE Road, Junction, SH17, Kengeri, "
                   "Bengaluru, Karnataka, India",
        "categories": ["fide-rating-events"]}
    last = ksca.parse_list(fx(P2), PAGE2)
    assert len(last["rows"]) == 5 and last["next"] is None  # the last page: "Next" is a button


def test_days_are_read_never_guessed():
    assert ksca.parse_day("December 28 @ 6:00 pm", 2026) == date(2026, 12, 28)
    assert ksca.parse_day("January 2, 2027 @ 9:00 am", 2026) == date(2027, 1, 2)
    assert ksca.parse_day("Dec 28", 2026) == date(2026, 12, 28)
    assert ksca.parse_day("December 28", None) is None  # no year anywhere: not guessed
    for bad in ("", "To be announced", "February 30 @ 9:00 am", "28 December"):
        assert ksca.parse_day(bad, 2026) is None


def test_one_day_event_from_the_saved_page():
    e = event("7128")
    assert (e["id"], e["start"], e["end"]) == ("ksca-7128", "2026-11-28", "2026-11-28")
    assert (e["city"], e["state"], e["country"]) == ("Bengaluru", "Karnataka", "IN")
    assert e["place_text"].startswith("Sri Sai Palace, Near Vishwa") and e["place_text"].endswith("India")
    assert e["source"] == "ksca" and e["source_url"].endswith("/south-open-fide-rapid-chess-tournament-2026/")
    assert e["flags"]["dates_suspect"] is False and e["raw_dates"] is None
    assert e["codes"] == [] and e["register_url"] is None and e["brochure_url"] is None


def test_fide_category_is_stated_other_categories_add_nothing():
    fide, monthly = event("7128"), event("7183")
    assert fide["tags"]["fide_rated"] is True and fide["tags"]["fide_how"] == "stated"
    assert fide["tags"]["categories"] == ["FIDE Rating Events"]
    assert monthly["tags"]["fide_rated"] is None and monthly["tags"]["categories"] == ["Monthly Tournaments"]
    assert "blitz" in monthly["tags"]["formats"]  # "5th Sajjan Academy Open Blitz ..."
    assert event("7404", P2, PAGE2)["tags"]["categories"] == ["National Events"]


def test_double_commas_in_the_address_are_tidied():
    e = event("6939")  # "Ramamurthy Nagar,, Bengaluru"
    assert ",," not in e["place_text"] and e["city"] == "Bengaluru"


def test_events_over_several_days_and_a_year_change():
    selection = event("7400", P2, PAGE2)
    assert (selection["start"], selection["end"]) == ("2026-12-19", "2026-12-21")
    assert selection["tags"]["categories"] == ["State Selection Tournaments"]
    year_end = event("7401", P2, PAGE2)  # "December 30 @ 9:00 am - January 3, 2027 @ 6:00 pm"
    assert (year_end["start"], year_end["end"]) == ("2026-12-30", "2027-01-03")
    assert year_end["flags"]["dates_suspect"] is False and year_end["city"] == "Mysuru"
    all_day = event("7402", P2, PAGE2)  # no venue at all
    assert (all_day["start"], all_day["end"]) == ("2027-01-09", "2027-01-10")
    assert all_day["place_text"] is None and all_day["state"] is None and all_day["city"] is None


def test_an_unreadable_end_is_kept_and_flagged():
    e = event("7403", P2, PAGE2)
    assert e["start"] == "2027-01-10" and e["end"] is None
    assert e["flags"]["dates_suspect"] is True
    assert e["raw_dates"] == {"start": "January 10, 2027 @ 9:00 am", "end": "To be announced"}


def test_an_end_without_a_year_before_the_start_is_flagged_not_fixed():
    html = view(article(start_attr="2026-12-30", start="December 30 @ 9:00 am", end="January 2 @ 6:00 pm"))
    e = ksca.build_event(ksca.parse_list(html, LIST)["rows"][0], TODAY)
    assert (e["start"], e["end"]) == ("2026-12-30", "2026-01-02")
    assert e["flags"]["dates_suspect"] is True and e["raw_dates"]["end"] == "January 2 @ 6:00 pm"


def test_machine_date_and_text_disagreeing_is_flagged():
    html = view(article(start_attr="2026-12-20", start="December 21 @ 9:00 am"))
    e = ksca.build_event(ksca.parse_list(html, LIST)["rows"][0], TODAY)
    assert e["start"] == "2026-12-20" and e["flags"]["dates_suspect"] is True
    assert e["raw_dates"]["start"] == "2026-12-20 (December 21 @ 9:00 am)"


def test_no_machine_date_uses_only_a_text_with_its_own_year():
    with_year = view(article(start_attr="", start="January 9, 2027 @ 9:00 am"))
    without = view(article(start_attr="", start="January 9 @ 9:00 am"))
    assert ksca.build_event(ksca.parse_list(with_year, LIST)["rows"][0], TODAY)["start"] == "2027-01-09"
    e = ksca.build_event(ksca.parse_list(without, LIST)["rows"][0], TODAY)
    assert e["start"] is None and e["flags"]["dates_suspect"] is True


def test_an_event_outside_karnataka_gets_its_own_state():
    e = event("7404", P2, PAGE2)
    assert (e["city"], e["state"]) == ("Panaji", "Goa")


def test_a_changed_layout_is_an_error_but_no_events_is_fine():
    with pytest.raises(be.SourceError, match="layout changed"):
        ksca.parse_list("<html><body>Under maintenance</body></html>", LIST)
    with pytest.raises(be.SourceError, match="layout changed"):
        ksca.parse_list(view(), LIST)
    empty = view('<div class="tribe-events-c-messages">There are no upcoming events.</div>')
    assert ksca.parse_list(empty, LIST) == {"rows": [], "next": None}


def test_only_the_lists_own_next_link_is_followed():
    elsewhere = view(article(), '<a class="tribe-events-c-nav__next" href="https://example.com/more/">Next</a>')
    assert ksca.parse_list(elsewhere, LIST)["next"] is None


# ---- a run ---------------------------------------------------------------------
def test_run_reads_both_pages_politely(web, data_dir):
    serve_ksca(web)
    report = run_all(data_dir, config=ONLY_KSCA)
    assert report["per_source"]["ksca"]["status"] == "ok"
    assert web.urls("karnatakachess.com") == [KSCA + "robots.txt", LIST, PAGE2]  # nothing else
    mine = [e for e in load_events(data_dir) if e["source"] == "ksca"]
    assert len(mine) == 17 and len({e["id"] for e in mine}) == 17
    for e in mine:
        assert e["verified"] is True and e["listed_by"] == "ksca" and e["country"] == "IN"


def test_page_cap_stops_a_list_that_never_ends(web):
    class Client:
        def __init__(self):
            self.urls = []

        def get(self, url):
            self.urls.append(url)
            n = len(self.urls)
            nav = f'<a class="tribe-events-c-nav__next" href="{LIST}list/page/{n + 1}/">Next</a>'
            return view(article(post=str(9000 + n)), nav)

    client = Client()
    events, _listing, stats = ksca.fetch(client, {}, TODAY)
    assert len(client.urls) == ksca.MAX_PAGES == len(events)
    assert stats["more_pages_not_read"] is True and stats["pages_read"] == ksca.MAX_PAGES


def test_robots_txt_blocking_skips_the_source(web, data_dir):
    serve_ksca(web)
    web.add(KSCA + "robots.txt", "User-agent: *\nDisallow: /tournaments/\n")
    web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
    report = run_all(data_dir, config={n: n in ("ksca", "aicf") for n in be.SOURCE_MODULES})
    assert report["per_source"]["ksca"]["status"] == "skipped"
    assert LIST not in web.urls()


def test_a_broken_page_keeps_the_events_from_before(web, data_dir):
    serve_ksca(web)
    run_all(data_dir, config=ONLY_KSCA)
    before = {e["id"] for e in load_events(data_dir) if e["source"] == "ksca"}
    web.add(LIST, "<html><body>Under maintenance</body></html>")
    web.add("https://aicf.in/all-events/", make_html([row("Plain AICF Open", "400001")]))
    later = datetime(2026, 11, 25, 12, 0, tzinfo=be.IST)
    report = run_all(data_dir, config={n: n in ("ksca", "aicf") for n in be.SOURCE_MODULES}, now=later)
    assert report["per_source"]["ksca"]["status"] == "failed"
    assert {e["id"] for e in load_events(data_dir) if e["source"] == "ksca"} == before


def test_a_second_run_changes_nothing_and_a_vanished_event_is_kept(web, data_dir):
    serve_ksca(web)
    run_all(data_dir, config=ONLY_KSCA)
    again = run_all(data_dir, config=ONLY_KSCA, now=datetime(2026, 11, 25, 12, 0, tzinfo=be.IST))
    assert again["changes"] == {"new": 0, "changed": 0, "gone": 0}
    without = re.sub(r"<article[^>]*post-7128[\s\S]*?</article>", "", fx(P1))
    assert not re.search(r"<article[^>]*post-7128", without)
    web.add(LIST, without)
    run_all(data_dir, config=ONLY_KSCA, now=datetime(2026, 11, 26, 12, 0, tzinfo=be.IST))
    gone = by_id(data_dir)["ksca-7128"]
    assert gone["gone_from_source"] is True and gone["name"] == "South Open FIDE Rapid Chess Tournament 2026"


def test_no_phone_numbers_or_e_mails_are_stored(web, data_dir):
    serve_ksca(web)
    run_all(data_dir, config=ONLY_KSCA)
    text = json.dumps([e for e in load_events(data_dir) if e["source"] == "ksca"], ensure_ascii=False)
    assert not re.search(r"(?<![\d/-])\d{10}(?!\d)|\+91|[\w.+-]+@[\w-]+\.", text)


# ---- with the other sources ------------------------------------------------------
def test_importance_and_trust():
    assert be.SOURCE_PRIORITY.index("ksca") == be.SOURCE_PRIORITY.index("tnsca") + 1
    assert dedup.PRIMARY_ORDER.index("ksca") == dedup.PRIMARY_ORDER.index("tnsca") + 1
    assert "ksca" in be.VERIFIED_SOURCES and be.LISTED_BY["ksca"] == "ksca"
    assert be.SOURCE_LABELS["ksca"] == "Karnataka State Chess Association"
    assert be.country_for("ksca") == "IN"


def test_renamed_towns_are_one_place():
    assert dedup._same_town("Bangalore", "Bengaluru") is True
    assert dedup._same_town("Belgaum", "Belagavi") is True and dedup._same_town("Hubli", "Hubballi") is True
    assert dedup._same_town("Hubli", "Dharwad") is False and dedup._same_town("Mysuru", None) is None


def test_bengaluru_on_ksca_is_not_a_different_city_from_bangalore_on_aicf(monkeypatch):
    aicf, mine = dedup.Features(be.canonical(dict(AICF_INVENTIVE))), dedup.Features(event("6967"))
    result = dedup.compare(aicf, mine)
    assert result["reason"] != "different city" and result["hard"] is False
    # AICF's name has one distinctive word ("inventive"), too few to prove "same": not grouped
    assert result["decision"] == "different" and "too few distinctive words" in result["reason"]
    monkeypatch.setattr(dedup, "TOWN_RENAMES", {})
    assert dedup.compare(aicf, mine)["reason"] == "different city"  # what it was before


def test_ksca_is_primary_over_chess_results():
    chess_results = be.canonical({
        "id": "chessresults_ind-1528935", "name": "5th Sajjan Academy Open Blitz Chess Tournament 2026",
        "start": "2026-11-28", "end": "2026-11-28", "source": "chessresults_ind", "country": "IN",
        "source_url": "https://chess-results.com/tnr1528935.aspx?lan=1",
        "first_seen": "2026-11-20", "last_seen": "2026-11-26"})
    events = [chess_results, event("7183")]
    dedup.group_events(events, [], [])
    assert events[0]["merged_into"] == "ksca-7183" and events[1]["merged_into"] is None


def test_aicf_without_a_city_groups_with_ksca():
    events = [be.canonical(dict(AICF_CHADURANGOTSAVA)), event("7309")]
    dedup.group_events(events, [], [])
    assert events[1]["merged_into"] == "aicf-511064"
    assert events[0]["city"] == "Bengaluru"  # the primary fills its gap from KSCA's town
