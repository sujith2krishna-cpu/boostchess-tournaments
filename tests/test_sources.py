"""The three web sources (chessfee, Chess-Results India, ChessBase calendar) and the AICF one,
all run against saved pages: parsing, robots, caps, isolation, merging, privacy."""
import json
import re
from datetime import timedelta

import pytest

import build_events as be
from conftest import (ALL_SOURCES_ON, CB, CF, CR, CR_FED, EVENTS_HEADER, NOW, build, by_id, fx,
                      load_doc, load_events, row, run_all, serve_aicf, serve_chessbase,
                      serve_chessfee, serve_chessresults, write_manual)
from sources import chessbase_calendar as cb_source
from sources import chessfee as cf_source

NEXT_DAY = NOW + timedelta(days=1)
ONLY = lambda *names: {n: (n in names) for n in be.SOURCE_MODULES}  # noqa: E731


def live_sources(folder, source):
    return [e for e in load_events(folder) if e["source"] == source]


def count(web, host, part=""):
    return sum(1 for u in web.urls(host) if part in u)


# ---- chessfee -----------------------------------------------------------
def test_chessfee_parses_listing_and_details(web, data_dir):
    serve_chessfee(web)
    report = run_all(data_dir, config=ONLY("chessfee"))
    events = by_id(data_dir)
    assert report["per_source"]["chessfee"]["found"] == 6 == len(events)  # the repeated card is joined
    e = events["chessfee-1860"]
    assert e["name"].endswith("AICF Event Code: 473001") and "..." not in e["name"]  # full title
    assert (e["start"], e["end"]) == ("2026-11-27", "2026-11-27")
    assert e["source_url"] == CF + "tmt_details.php?id=1860"
    assert e["register_url"] == CF + "treg.php?id=1860"
    assert e["sources"] == [{"source": "chessfee", "source_url": CF + "tmt_details.php?id=1860",
                             "register_url": CF + "treg.php?id=1860"}]
    assert e["brochure_url"].startswith(CF + "admin/Brochure/")  # a link, nothing copied
    assert e["tags"]["categories"] == ["INTER-DISTRICT"] and e["tags"]["formats"] == ["rapid"]
    assert (e["country"], e["listed_by"], e["verified"], e["organiser"]) == ("IN", "chessfee", False, "Indian Chess Consortium (ICC)")
    assert e["codes"] == ["473001"]


def test_chessfee_without_a_details_page_keeps_the_listing_data(web, data_dir):
    serve_chessfee(web, details=())  # every details page answers 404
    run_all(data_dir, config=ONLY("chessfee"))
    e = by_id(data_dir)["chessfee-1727"]
    assert e["name"].endswith("...") or e["name"].endswith("…") or "..." in e["name"]
    assert e["start"] and e["register_url"] and e["organiser"] is None


def test_chessfee_city_and_state_come_only_from_text(web, data_dir):
    serve_chessfee(web, details=())
    web.add(CF + "tmt_details.php?id=1727", fx("chessfee_detail_1872.html"))
    run_all(data_dir, config=ONLY("chessfee"))
    e = by_id(data_dir)["chessfee-1727"]
    assert (e["city"], e["state"]) == ("Coimbatore", "Tamil Nadu")
    unsure = by_id(data_dir)["chessfee-1860"]  # "Vidvath PU College, Guruvayankere": nothing to go on
    assert (unsure["city"], unsure["state"]) == (None, None)


def test_chessfee_reads_details_only_for_new_or_changed_events(web, data_dir):
    serve_chessfee(web)
    for event_id in ("1727", "1857", "1800", "1817", "1824"):
        web.add(CF + f"tmt_details.php?id={event_id}", fx("chessfee_detail_1872.html"))
    run_all(data_dir, config=ONLY("chessfee"))
    assert count(web, "chessfee", "tmt_details") == 6  # all six were new
    web.calls.clear()
    run_all(data_dir, now=NEXT_DAY, config=ONLY("chessfee"))
    assert count(web, "chessfee", "tmt_details") == 0  # nothing changed: no details pages
    # one card changes (new venue): only that one is read again
    page = fx("chessfee_ongoing_p1.html").replace("Vidvath PU College, Guruvayankere", "Another Hall, Pune")
    web.add(CF + "tournament_ongoing.php", page)
    web.calls.clear()
    run_all(data_dir, now=NEXT_DAY + timedelta(days=1), config=ONLY("chessfee"))
    assert [u for u in web.urls("chessfee") if "tmt_details" in u] == [CF + "tmt_details.php?id=1860"]


def test_chessfee_event_that_leaves_the_listing_is_kept(web, data_dir):
    serve_chessfee(web)
    run_all(data_dir, config=ONLY("chessfee"))
    web.add(CF + "tournament_ongoing.php", fx("chessfee_ongoing_p1.html"))  # page 2 events vanish
    web.add(CF + "tournament_ongoing.php?page=2", fx("chessfee_upcoming.html"))
    web.add(CF + "tournament_ongoing.php?page=3", fx("chessfee_upcoming.html"))
    run_all(data_dir, now=NEXT_DAY, config=ONLY("chessfee"))
    events = by_id(data_dir)
    assert len(events) == 6 and events["chessfee-1824"]["gone_from_source"] is True
    assert events["chessfee-1824"]["last_seen"] == "2026-11-24"


# ---- chess-results ------------------------------------------------------
def test_chessresults_uses_the_pages_own_menu_and_reads_three_lists(web, data_dir):
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("chessresults_ind"))
    posts = [c["data"] for c in web.calls if c["method"] == "POST"]
    assert [p["combo_tur_sel"] for p in posts] == ["1", "2", "3"]  # not "all", not "> 3 weeks"
    assert all(p["__EVENTTARGET"] == "combo_sel" and p["__VIEWSTATE"] for p in posts)
    assert len(by_id(data_dir)) == 4  # one tournament shows up in two lists


def test_chessresults_event_details(web, data_dir):
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("chessresults_ind"))
    events = by_id(data_dir)
    e = events["chessresults_ind-1528935"]
    assert e["source_url"] == CR + "tnr1528935.aspx?lan=1"
    assert (e["start"], e["end"]) == ("2026-11-28", "2026-11-28")
    assert e["register_url"] == "https://circlechess.com/registration?id=61557"  # clearly a registration link
    assert e["organiser"] == "Sajjan Academy" and e["tags"]["formats"] == ["blitz"]
    assert e["brochure_url"].startswith(CR + "UploadData.aspx")
    assert (e["country"], e["listed_by"], e["verified"]) == ("IN", "chess-results", False)
    multi = events["chessresults_ind-1539989"]
    assert (multi["start"], multi["end"]) == ("2026-11-22", "2026-11-24")
    assert multi["register_url"] is None  # no registration link on the page: never invented
    assert multi["tags"]["age"] == ["U13"]


def test_chessresults_keeps_a_registration_link_written_in_the_title_only_when_clear(web, data_dir):
    from sources import chessresults_ind as cr
    assert cr._register_url("Cup. Register at https://example.org/enter now", []) == "https://example.org/enter"
    assert cr._register_url("Cup. See https://example.org/info", []) is None
    assert cr._register_url("Cup", [("Instagram", "https://instagram.com/x")]) is None


def test_chessresults_reads_details_once(web, data_dir):
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("chessresults_ind"))
    first = count(web, "chess-results", "turdet=YES")
    assert first == 4
    web.calls.clear()
    run_all(data_dir, now=NEXT_DAY, config=ONLY("chessresults_ind"))
    assert count(web, "chess-results", "turdet=YES") == 0


# ---- chessbase ----------------------------------------------------------
def serve_chessbase_with_events(web):
    serve_chessbase(web)
    for html in ("chessbase_calendar.html", "chessbase_calendar_2027.html"):
        for raw in cb_source.parse_events(fx(html)):
            web.add(CB + f"chess-calendar/event/{raw['slug']}", fx("chessbase_event.html"))


def test_chessbase_events_abroad_tag_and_country(web, data_dir):
    serve_chessbase_with_events(web)
    run_all(data_dir, config=ONLY("chessbase_calendar"))
    events = load_events(data_dir)
    assert all(e["id"].startswith("chessbase_calendar-") for e in events)
    assert len(events) == 10  # 7 in the month + 3 in 2027; the online-only event is left out
    abroad = [e for e in events if e["country"] != "IN"]
    assert {e["country"] for e in abroad} == {"ID", "CA"}
    assert all("abroad" in e["tags"]["categories"] for e in abroad)
    assert all("abroad" not in e["tags"]["categories"] for e in events if e["country"] == "IN")
    india = next(e for e in events if e["country"] == "IN" and e["state"])
    assert re.fullmatch(r"https://chessbase\.in/chess-calendar/event/[\w-]+", india["source_url"])
    assert india["listed_by"] == "chessbase" and india["verified"] is False


def test_chessbase_country_unsure_is_null_and_not_abroad():
    raw = {"id": "x1", "slug": "x1", "title": "Some Open", "formats": ["rapid"], "fideRated": True,
           "startDate": "2026-12-01", "endDate": "2026-12-02", "mode": "in_person",
           "location": {"country": "UK", "region": "", "city": "London"}, "categories": ["open"],
           "isCancelled": True, "hasBrochure": False}
    e = cb_source.build_event(raw, None, NOW.date())
    assert e["country"] is None and "abroad" not in e["tags"]["categories"]
    assert e["cancelled"] is True and e["tags"]["open"] is True and e["tags"]["fide_rated"] is True
    raw["location"]["country"] = "de"
    german = cb_source.build_event(raw, None, NOW.date())
    assert german["country"] == "DE" and "abroad" in german["tags"]["categories"]
    assert german["place_text"] == "London, DE"


def test_chessbase_reads_only_the_pages_it_links_to_and_never_the_data_service(web, data_dir):
    serve_chessbase_with_events(web)
    run_all(data_dir, config=ONLY("chessbase_calendar"))
    pages = [u for u in web.urls("chessbase") if "/event/" not in u]
    assert pages == [CB + "robots.txt", CB + "chess-calendar", CB + "chess-calendar/2027",
                     CB + "chess-calendar/2028"]
    assert not [u for u in web.urls() if "/api/" in u or "cbin-api" in u or "?month=" in u]


def test_chessbase_year_page_without_events_is_empty_but_the_main_page_must_have_a_list(web, data_dir):
    serve_chessbase_with_events(web)
    run_all(data_dir, config=ONLY("chessbase_calendar"))  # the 2028 fixture has no event list at all
    assert len(load_events(data_dir)) == 10
    web.add(CB + "chess-calendar", "<html><body>redesigned</body></html>")
    with pytest.raises(be.SourceError, match="No source could be read"):
        run_all(data_dir, now=NEXT_DAY, config=ONLY("chessbase_calendar"))


# ---- robots.txt, caps, isolation ---------------------------------------
def serve_everything(web, aicf_rows=None):
    serve_aicf(web, aicf_rows or [row("Plain AICF Open", "400001", place="Pune")])
    serve_chessfee(web)
    serve_chessresults(web)
    serve_chessbase_with_events(web)


def test_robots_disallow_skips_that_source_and_logs_it(web, data_dir):
    serve_everything(web)
    web.add(CF + "robots.txt", "User-agent: *\nDisallow: /tournament_ongoing.php\n")
    report = run_all(data_dir)
    assert report["per_source"]["chessfee"]["status"] == "skipped"
    assert "robots.txt" in report["per_source"]["chessfee"]["message"]
    assert not [u for u in web.urls("chessfee") if "tournament_ongoing" in u]
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert meta["sources"]["chessfee"]["status"] == "skipped"
    assert "does not allow" in meta["sources"]["chessfee"]["last_error"]["message"]
    assert report["per_source"]["chessresults_ind"]["status"] == "ok"  # the rest carried on


def test_robots_is_checked_at_the_start_for_every_site(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    for host, robots in (("aicf.in", "https://aicf.in/robots.txt"), ("chessfee", CF + "robots.txt"),
                         ("chess-results", CR + "robots.txt"), ("chessbase", CB + "robots.txt")):
        assert web.urls(host)[0] == robots


def test_request_cap_per_site_is_respected(web, data_dir, monkeypatch):
    serve_chessfee(web)
    for event_id in ("1727", "1857", "1800", "1817", "1824"):
        web.add(CF + f"tmt_details.php?id={event_id}", fx("chessfee_detail_1872.html"))
    monkeypatch.setattr(be, "PoliteClient", lambda url: _capped(url, 7))
    report = run_all(data_dir, config=ONLY("chessfee"))
    assert count(web, "chessfee") <= 7 and report["per_source"]["chessfee"]["requests"] == 7
    assert report["per_source"]["chessfee"]["status"] == "ok"
    assert report["per_source"]["chessfee"]["found"] == 6  # every event is listed, details come later
    assert 0 < count(web, "chessfee", "tmt_details") < 6


def _capped(url, cap):
    from sources.polite import PoliteClient
    return PoliteClient(url, max_requests=cap)


def test_one_failing_source_does_not_stop_the_others(web, data_dir):
    serve_everything(web)
    web.add(CF + "tournament_ongoing.php", "boom", status=500)
    report = run_all(data_dir)
    assert report["per_source"]["chessfee"]["status"] == "failed"
    assert "HTTP 500" in report["per_source"]["chessfee"]["message"]
    for good in ("aicf", "chessresults_ind", "chessbase_calendar"):
        assert report["per_source"][good]["status"] == "ok"
    sources = {e["source"] for e in load_events(data_dir)}
    assert sources == {"aicf", "chessresults_ind", "chessbase_calendar"}
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert meta["sources"]["chessfee"]["last_error"]["message"].startswith("Could not fetch")
    assert meta["sources"]["chessfee"]["last_success"] is None
    assert meta["sources"]["aicf"]["last_success"] == NOW.isoformat()


def test_a_broken_parser_is_isolated_too(web, data_dir, monkeypatch):
    serve_everything(web)
    monkeypatch.setattr(cb_source, "parse_events", lambda html, required=True: 1 / 0)
    report = run_all(data_dir)
    assert report["per_source"]["chessbase_calendar"]["status"] == "failed"
    assert "ZeroDivisionError" in report["per_source"]["chessbase_calendar"]["message"]
    assert report["per_source"]["chessfee"]["status"] == "ok"


def test_failed_source_keeps_its_previous_events_and_the_error_is_recorded(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    before = [e for e in load_events(data_dir) if e["source"] == "chessfee"]
    assert len(before) == 6
    web.add(CF + "tournament_ongoing.php", "down", status=503)
    report = run_all(data_dir, now=NEXT_DAY)
    after = [e for e in load_events(data_dir) if e["source"] == "chessfee"]
    assert [e["id"] for e in after] == [e["id"] for e in before]
    assert not any(e["gone_from_source"] for e in after)  # a failure is not "gone"
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert meta["sources"]["chessfee"]["status"] == "failed"
    assert meta["sources"]["chessfee"]["last_success"] == NOW.isoformat()  # the earlier success
    assert meta["sources"]["chessfee"]["count"] == 6
    assert report["only_timestamps_changed"] is False  # the failure is a real change in meta.json


def test_a_shrunken_result_keeps_the_previous_data(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    # chessfee suddenly lists only 2 of its 6 events
    page = fx("chessfee_ongoing_p1.html")
    articles = page.split("</article>")
    web.add(CF + "tournament_ongoing.php", "</article>".join(articles[:2]) + "</article></div></body></html>")
    report = run_all(data_dir, now=NEXT_DAY)
    info = report["per_source"]["chessfee"]
    assert info["status"] == "failed" and "fewer than half" in info["message"]
    assert len([e for e in load_events(data_dir) if e["source"] == "chessfee"]) == 6


def test_all_sources_failing_writes_nothing(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    snapshot = {p.name: p.read_bytes() for p in data_dir.iterdir() if p.is_file()}
    for host in ("https://aicf.in/all-events/", CF + "tournament_ongoing.php", CR_FED,
                 CB + "chess-calendar"):
        web.add(host, "down", status=500)
    with pytest.raises(be.SourceError, match="No source could be read"):
        run_all(data_dir, now=NEXT_DAY)
    assert {p.name: p.read_bytes() for p in data_dir.iterdir() if p.is_file()} == snapshot


def test_switching_a_source_off_stops_fetching_it_but_keeps_its_events(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    web.calls.clear()
    config = {**ALL_SOURCES_ON, "chessfee": False}
    report = run_all(data_dir, now=NEXT_DAY, config=config)
    assert not web.urls("chessfee")
    assert report["per_source"]["chessfee"]["status"] == "disabled"
    assert len([e for e in load_events(data_dir) if e["source"] == "chessfee"]) == 6


def test_a_source_fetched_less_than_12_hours_ago_is_not_fetched_again(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    web.calls.clear()
    report = run_all(data_dir, min_hours_between_fetches=12, now=NOW + timedelta(hours=11, minutes=59))
    assert web.calls == [] and report["fetched_any"] is False
    assert all(i["due"] is False and i["status"] == "ok" for i in report["per_source"].values())
    web.calls.clear()
    run_all(data_dir, min_hours_between_fetches=12, now=NOW + timedelta(hours=12))
    assert web.calls  # 12 hours later: due again


def test_config_file_is_validated(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text('{"chessfee": {"enabled": false}}', encoding="utf-8")
    config = be.load_config(path)
    assert config["chessfee"] is False and config["aicf"] is True
    path.write_text('{"nonsense": {"enabled": true}}', encoding="utf-8")
    with pytest.raises(be.BuildError, match="unknown source 'nonsense'"):
        be.load_config(path)
    path.write_text('{"aicf": true}', encoding="utf-8")
    with pytest.raises(be.BuildError, match='"aicf" needs'):
        be.load_config(path)
    real = be.load_config()  # the committed config/sources.json
    assert set(real) == set(be.SOURCE_MODULES) and all(real.values())


# ---- merging ------------------------------------------------------------
def test_entries_sharing_an_aicf_code_become_one_event(web, data_dir):
    serve_aicf(web, [row("AICF Rapid Cup 2026", "473001", start="30-11-2026", end="01-12-2026",
                         place="Kochi, Kerala", brochure='<a href="https://aicf.in/b.pdf">Download</a>')])
    serve_chessfee(web)
    serve_chessresults(web)
    report = run_all(data_dir, config=ONLY("aicf", "chessfee", "chessresults_ind"))
    events = by_id(data_dir)
    merged = events["aicf-473001"]
    assert [s["source"] for s in merged["sources"]] == ["aicf", "chessfee", "chessresults_ind"]
    assert merged["sources"][1] == {"source": "chessfee", "source_url": CF + "tmt_details.php?id=1860",
                                    "register_url": CF + "treg.php?id=1860"}
    assert merged["sources"][2]["source_url"] == CR + "tnr1550001.aspx?lan=1"
    # AICF wins for the facts it has; the gaps are filled from the others
    assert merged["name"] == "AICF Rapid Cup 2026" and merged["start"] == "2026-11-30"
    assert merged["brochure_url"] == "https://aicf.in/b.pdf"
    assert merged["register_url"] == CF + "treg.php?id=1860"
    assert merged["organiser"] == "Indian Chess Consortium (ICC)"
    assert merged["source"] == "aicf" and merged["listed_by"] == "aicf" and merged["verified"] is True
    assert "chessfee-1860" not in events and "chessresults_ind-1550001" not in events
    assert report["per_source"]["chessfee"]["joined"] == 1
    assert report["per_source"]["chessresults_ind"]["joined"] == 1 and report["per_source"]["aicf"]["joined"] == 1


def test_entries_sharing_a_code_join_even_without_an_aicf_listing(web, data_dir):
    serve_chessfee(web)
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("chessfee", "chessresults_ind"))
    events = load_events(data_dir)
    joined = [e for e in events if len(e["sources"]) == 2]
    assert len(joined) == 1 and joined[0]["id"] == "chessfee-1860"  # chessfee outranks chess-results
    assert joined[0]["verified"] is False and joined[0]["listed_by"] == "chessfee"


def test_no_code_means_no_merge_but_look_alikes_are_flagged(web, data_dir):
    similar = "5th Sajjan Academy Open Blitz Chess Tournament 2026 PRIZE FUND - 50,000/- Early Bird Rs 500/- till 10th Nov 2026"
    serve_aicf(web, [row(similar, "400001", start="28-11-2026",
                         end="28-11-2026", place="Bengaluru"),
                     row("Totally Different Cup", "400002", start="28-11-2026", end="28-11-2026",
                         place="Bengaluru")])
    serve_chessresults(web)  # 5th Sajjan Academy Open Blitz Chess Tournament 2026 ... starts 2026-11-28
    web.add(CR + "tnr1528935.aspx?lan=1&turdet=YES", fx("chessresults_tnr1528935.html").replace(
        "Sri Sai Palace Convention Centre, NICE Road, Junction, SH17, Kengeri, BNG-60", "Bengaluru, Karnataka"))
    report = run_all(data_dir, config=ONLY("aicf", "chessresults_ind"))
    events = by_id(data_dir)
    assert "aicf-400001" in events and "chessresults_ind-1528935" in events  # both kept
    assert len(events["aicf-400001"]["sources"]) == 1
    twin = events["chessresults_ind-1528935"]
    assert twin["flags"]["possible_duplicate_of"] == "aicf-400001"
    assert events["aicf-400001"]["flags"]["possible_duplicate_of"] is None  # AICF outranks
    assert events["aicf-400002"]["flags"]["possible_duplicate_of"] is None
    assert report["possible_duplicates"] == 1


def test_look_alike_needs_same_date_same_city_and_a_different_source(web, data_dir):
    similar = "5th Sajjan Academy Open Blitz Chess Tournament 2026 PRIZE FUND - 50,000/- Early Bird Rs 500/- till 10th Nov 2026"
    serve_aicf(web, [row(similar, "400001", start="29-11-2026",
                         end="29-11-2026", place="Bengaluru"),   # other day
                     row(similar, "400002", start="28-11-2026",
                         end="28-11-2026", place="Mysuru")])     # other city
    serve_chessresults(web)
    web.add(CR + "tnr1528935.aspx?lan=1&turdet=YES", fx("chessresults_tnr1528935.html").replace(
        "Sri Sai Palace Convention Centre, NICE Road, Junction, SH17, Kengeri, BNG-60", "Bengaluru, Karnataka"))
    run_all(data_dir, config=ONLY("aicf", "chessresults_ind"))
    assert all(e["flags"]["possible_duplicate_of"] is None for e in load_events(data_dir))


def test_two_aicf_events_with_one_code_are_never_joined_to_a_third_entry(web, data_dir):
    serve_aicf(web, [row("Cup A", "473001", start="01-12-2026", end="02-12-2026"),
                     row("Cup B", "473001", start="05-12-2026", end="06-12-2026")])
    serve_chessfee(web)
    report = run_all(data_dir, config=ONLY("aicf", "chessfee"))
    ids = {e["id"] for e in load_events(data_dir)}
    assert "chessfee-1860" in ids and len(ids) == 8
    assert any("share one code" in w for w in report["warnings"])


def test_overrides_still_win_over_every_source(web, data_dir):
    serve_aicf(web, [row("AICF Rapid Cup 2026", "473001", start="30-11-2026", end="01-12-2026")])
    serve_chessfee(web)
    write_manual(data_dir, "key,start_date,end_date,place,state,hide,cancelled,note\n"
                           "473001,02-12-2026,03-12-2026,,,,yes,Moved and cancelled\n", "overrides.csv")
    run_all(data_dir, config=ONLY("aicf", "chessfee"))
    e = by_id(data_dir)["aicf-473001"]
    assert (e["start"], e["cancelled"], e["note"]) == ("2026-12-02", True, "Moved and cancelled")
    assert len(e["sources"]) == 2


# ---- privacy ------------------------------------------------------------
PHONE = re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)")


def test_phone_numbers_are_never_stored_anywhere(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    for path in sorted(data_dir.rglob("*.json")):
        text = path.read_text("utf-8")
        assert "98765" not in text, path
        assert not PHONE.search(text), (path, PHONE.search(text).group())


@pytest.mark.parametrize("text, clean", [
    ("Contact: 98765 43210 & 98765 43211 Entry 500/-", "Entry 500"),
    ("Chessind Academy, Ph: +91 98765 43210", "Chessind Academy"),
    ("Hall A, call 044-24331234 now", "Hall A, now"),
    ("Cup AICF Event Code 473001 on 28-11-2026 prize Rs. 11,50,000/-",
     "Cup AICF Event Code 473001 on 28-11-2026 prize Rs. 11,50,000/-"),
    ("FIDE ID 25054309 player", "FIDE ID 25054309 player"),
    ("mail me a.b@example.org Venue Hall", "mail me Venue Hall"),
])
def test_strip_phones(text, clean):
    assert be.strip_phones(text) == clean


def test_chessfee_organiser_is_dropped_if_it_looks_like_a_number(web, data_dir):
    serve_chessfee(web)
    page = fx("chessfee_detail_1860.html").replace("Indian Chess Consortium (ICC)", "98765 43210")
    web.add(CF + "tmt_details.php?id=1860", page)
    run_all(data_dir, config=ONLY("chessfee"))
    assert by_id(data_dir)["chessfee-1860"]["organiser"] is None


# ---- determinism --------------------------------------------------------
def snapshot(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def test_same_input_gives_identical_files(web, data_dir, tmp_path):
    serve_everything(web)
    run_all(data_dir)
    first = snapshot(data_dir)
    other = tmp_path / "other"
    (other / "manual").mkdir(parents=True)
    for name in ("events.csv", "overrides.csv"):
        (other / "manual" / name).write_bytes((data_dir / "manual" / name).read_bytes())
    run_all(other)
    assert snapshot(other) == first
    assert set(first) >= {"events.json", "meta.json", "sources/aicf.json", "sources/chessfee.json",
                          "sources/chessresults_ind.json", "sources/chessbase_calendar.json"}


def test_next_day_with_the_same_pages_changes_only_timestamps(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    report = run_all(data_dir, now=NEXT_DAY)
    assert report["only_timestamps_changed"] is True


def test_events_json_has_the_new_fields_in_a_fixed_order(web, data_dir):
    serve_everything(web)
    run_all(data_dir)
    doc = load_doc(data_dir)
    assert doc["schema_version"] == 4
    keys = list(be.EVENT_KEYS)
    assert all(list(e) == keys for e in doc["events"])
    for key in ("source_url", "sources", "listed_by", "verified"):
        assert key in keys
    assert keys.index("sources") == keys.index("source_url") + 1
    assert all(e["flags"]["possible_duplicate_of"] is None or isinstance(e["flags"]["possible_duplicate_of"], str)
               for e in doc["events"])
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert set(meta["sources"]) == set(be.SOURCE_MODULES)
    assert set(meta["sources"]["aicf"]) == {"enabled", "status", "message", "count", "last_success",
                                            "last_error", "next_due"}


def test_trust_labels(web, data_dir):
    serve_everything(web)
    write_manual(data_dir, EVENTS_HEADER + "mine,My Cup,10-01-2027,,Goa,,,,,,,\n")
    run_all(data_dir)
    for e in load_events(data_dir):
        if e["source"] in ("aicf", "manual"):
            assert e["verified"] is True and e["listed_by"] == e["source"]
        else:
            assert e["verified"] is False and e["listed_by"] != "aicf"
