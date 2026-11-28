"""T12: Chess-Results rating row and brochure rule, the one-time refresh, coverage per state,
and the Goa QQChess pair."""
import csv
import json
from datetime import date

import pytest

import build_events as be
import quality
import refresh_chessresults as refresh
from conftest import NOW, ROOT, fx
from sources import chessresults_ind as cr

TODAY = NOW.date()
URL = "https://chess-results.com/tnr1600001.aspx?lan=1"


def page(rows, title="Some Open 2026"):
    """A details page in Chess-Results' layout: two-cell rows."""
    cells = "".join(f"<tr><td class=CR>{k}</td><td class=CR>{v}</td></tr>" for k, v in rows)
    return f"<html><body><h2>{title}</h2><table>{cells}</table></body></html>"


def details(rating=None, files=(), title="Some Open 2026", extra=()):
    rows = [("Organizer(s)", "Some Club"), ("Date", "2026/12/05 to 2026/12/06"),
            ("Number of rounds", "7"), *extra]
    if rating is not None:
        rows.append(("Rating calculation", rating))
    if files:
        rows.append(("Download Files", " ".join(f'<a href="UploadData.aspx?n={i}">{name}</a>'
                                                for i, name in enumerate(files))))
    return cr.parse_details(page(rows, title), URL)


def built(title="Some Open 2026", **kwargs):
    item = {"id": "1600001", "title": title, "url": URL}
    return cr.build_event(item, details(title=title, **kwargs), TODAY)


# ---- Part 1.1: the "Rating calculation" row -------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("Rating international", True),  # 13 of our stored pages
    ("Rating national, Rating international", True),  # 1 stored page
    ("Rating national", False),  # 1 stored page: national only
    ("-", None),  # what most stored pages show
    ("", None),
    (None, None),
    ("Elo FIDE", True),
    ("Elo national, Elo international", True),
    ("Rating internacional", True),
    ("Elo nacional", False),
    ("not rated", False),
    ("Swiss-Manager", None),
])
def test_rating_row_mapping(text, expected):
    assert cr.rating_from_row(text) is expected


def test_the_row_is_read_from_the_details_page():
    assert details("Rating international")["rating_row"] == "Rating international"
    assert details()["rating_row"] is None  # no row at all
    german = cr.parse_details(page([("Date", "2026/12/05"), ("Elorechnung", "Elo national, Elo FIDE")]), URL)
    assert german["rating_row"] == "Elo national, Elo FIDE"


def test_the_row_sets_fide_stated_when_the_name_says_nothing():
    e = built("National Open Chess Tournament for the Visually Challenged 2026", rating="Rating international")
    assert (e["tags"]["fide_rated"], e["tags"]["fide_how"]) == (True, "stated")
    e = built("Club Monthly Open", rating="Rating national")
    assert (e["tags"]["fide_rated"], e["tags"]["fide_how"]) == (False, "stated")
    e = built("Club Monthly Open", rating="-")
    assert (e["tags"]["fide_rated"], e["tags"]["fide_how"]) == (None, None)


def test_the_row_turns_an_inferred_yes_into_a_stated_one():
    e = built("Goa International Open 2026", rating="Rating international")
    assert (e["tags"]["fide_rated"], e["tags"]["fide_how"]) == (True, "stated")
    assert built("Goa International Open 2026")["tags"]["fide_how"] == "inferred"


def test_when_the_row_and_the_name_disagree_the_name_stays():
    e = built("Club FIDE Rated Rapid 2026", rating="Rating national")
    assert (e["tags"]["fide_rated"], e["tags"]["fide_how"]) == (True, "stated")
    e = built("Club Non-Rated Rapid 2026", rating="Rating international")
    assert (e["tags"]["fide_rated"], e["tags"]["fide_how"]) == (False, "stated")


def test_the_saved_fixture_pages_without_the_row_are_unchanged():
    for tnr in ("1528935", "1539989", "1549496", "1550001"):
        assert cr.parse_details(fx(f"chessresults_tnr{tnr}.html"), URL)["rating_row"] is None


# ---- Part 1.2: the brochure link -------------------------------------------------
@pytest.mark.parametrize("files, expected", [
    (["MahaGames 2026.pdf"], 0),  # the only PDF
    (["3rd Speed Chess Festival_compressed.pdf"], 0),
    (["Bihar-State-School-26-Circular.pdf"], 0),  # named like a brochure
    (["Kai. Ramchandra Kabnurkar Chashak 2026 Open Kolhapur_Crosstable_Tiebreaks.pdf"], None),
    (["Prize List.pdf"], None),
    (["MINUTES - MANAGERS MEETING.pdf"], None),
    (["Final_Results.pdf"], None), (["Pairings Round 3.pdf"], None), (["Starting rank.pdf"], None),
    (["Players List.pdf"], None), (["Ranking after round 5.pdf"], None),
    (["PRIZE STRUCTURE.xlsx"], None),  # not a PDF
    (["SARJI RENUKA OPEN (2).pdf", "Appendix A Rapid Rules.pdf"], None),  # two PDFs, no brochure name
    (["20230101Laws-of-Chess.pdf", "Arbiters_Manual_2025.pdf", "ARTICLE 12.9.docx",
      "qqchess-1800-and-above.pdf"], None),
    (["Arbiter-Manual-2026_compressed.pdf", "Manchester City Below 1800 Fide Prospectus_compressed.pdf"], 1),
    (["Results.pdf", "Event Invitation.pdf"], 1),
    (["Rules.docx", "Open 2026.pdf"], 1),  # one PDF among other files
])
def test_brochure_rule(files, expected):
    e = built(files=files)
    want = None if expected is None else f"https://chess-results.com/UploadData.aspx?n={expected}"
    assert e["brochure_url"] == want


def test_the_brochure_file_is_never_read():
    e = built(files=["Open 2026.pdf"])
    assert e["brochure_url"].startswith("https://chess-results.com/UploadData.aspx")  # a link only


# ---- Part 1.3: number of rounds --------------------------------------------------
def test_rounds_are_not_stored_the_schema_has_no_place_for_them():
    e = built()
    assert "rounds" not in e and "number_of_rounds" not in e and list(e) == list(be.EVENT_KEYS)
    assert be.SCHEMA_VERSION == 6


# ---- Part 1.4: the one-time refresh ---------------------------------------------
def _snapshot(tmp_path, events):
    path = tmp_path / "chessresults_ind.json"
    path.write_text(json.dumps({"source": "chessresults_ind", "found": len(events), "listing": {},
                                "events": events}), encoding="utf-8")
    return path


def _old(number, **values):
    return be.canonical({
        "id": f"chessresults_ind-{number}", "name": "Some Open 2026", "start": "2026-12-05",
        "end": "2026-12-06", "source": "chessresults_ind", "country": "IN",
        "source_url": f"https://chess-results.com/tnr{number}.aspx?lan=1",
        "register_url": "https://example.org/register",
        "first_seen": "2026-11-20", "last_seen": "2026-11-25", "gone_from_source": True, **values})


def test_refresh_rebuilds_from_the_saved_pages_and_keeps_history(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    rows = [("Organizer(s)", "Some Club"), ("Date", "2026/12/05 to 2026/12/06"),
            ("Rating calculation", "Rating international"),
            ("Download Files", '<a href="UploadData.aspx?n=0">Open 2026.pdf</a>')]
    (cache / "1600001.html").write_text(page(rows), encoding="utf-8")
    (cache / "1600003.html").write_text(page([("Organizer(s)", "Club"), ("Date", "soon")]), encoding="utf-8")
    snapshot = _snapshot(tmp_path, [_old("1600001"), _old("1600002"), _old("1600003")])
    assert refresh.apply(cache, date(2026, 11, 28), snapshot) == 0
    events = {e["id"]: e for e in json.loads(snapshot.read_text("utf-8"))["events"]}
    new = events["chessresults_ind-1600001"]
    assert (new["tags"]["fide_rated"], new["tags"]["fide_how"]) == (True, "stated")
    assert new["brochure_url"] == "https://chess-results.com/UploadData.aspx?n=0"
    assert (new["first_seen"], new["last_seen"], new["gone_from_source"]) == ("2026-11-20", "2026-11-25", True)
    assert new["register_url"] == "https://example.org/register"  # kept: it came from the list line
    assert events["chessresults_ind-1600002"] == _old("1600002")  # no saved page: unchanged
    assert events["chessresults_ind-1600003"] == _old("1600003")  # unreadable dates: unchanged


def test_refresh_fetch_stops_before_any_request_above_the_limit(tmp_path, monkeypatch, capsys):
    snapshot = _snapshot(tmp_path, [_old(str(1600000 + i)) for i in range(3)])
    monkeypatch.setattr(refresh, "MAX_PAGES", 2)

    class NoClient:
        def load_robots(self):
            raise AssertionError("no request may be made")

    assert refresh.fetch(tmp_path / "cache", snapshot, client=NoClient()) == 2
    assert "3 pages would be needed, more than 2" in capsys.readouterr().out


def test_refresh_fetch_reads_robots_first_and_each_page_once(tmp_path):
    snapshot = _snapshot(tmp_path, [_old("1600001"), _old("1600002")])

    class Client:
        def __init__(self):
            self.calls = []
            self.requests_made = 0

        def load_robots(self):
            self.calls.append("robots.txt")

        def get(self, url):
            self.calls.append(url)
            self.requests_made += 1
            return page([("Date", "2026/12/05")])

    client = Client()
    cache = tmp_path / "cache"
    assert refresh.fetch(cache, snapshot, client=client) == 0
    assert client.calls == ["robots.txt", "https://chess-results.com/tnr1600001.aspx?lan=1&turdet=YES",
                            "https://chess-results.com/tnr1600002.aspx?lan=1&turdet=YES"]
    assert refresh.fetch(cache, snapshot, client=Client()) == 0  # already saved: nothing again
    assert sorted(p.name for p in cache.iterdir()) == ["1600001.html", "1600002.html"]


# ---- Part 3: upcoming events per state -------------------------------------------
def _shown(eid, state, start="2026-12-01", country="IN", **values):
    return be.canonical({"id": eid, "name": eid, "start": start, "end": start, "state": state,
                         "country": country, "source": "aicf", "first_seen": "x", "last_seen": "x",
                         **values})


def test_states_counts_every_state_no_state_and_abroad():
    events = [_shown("a", "Kerala"), _shown("b", "Kerala"), _shown("c", "Uttar Pradesh"),
              _shown("d", None), _shown("e", "Texas", country="US"), _shown("f", None, country=None),
              _shown("past", "Goa", start="2026-11-01"),
              _shown("merged", "Goa", merged_into="a"), _shown("hidden", "Goa", hidden=True)]
    report = quality.quality_report(events, TODAY, "t")
    states = report["states"]
    assert states["window"] == "upcoming" and states["events"] == 6
    assert states["by_state"]["Kerala"] == 2 and states["by_state"]["Uttar Pradesh"] == 1
    assert states["by_state"]["Goa"] == 0  # every state is listed, so a thin one shows
    assert set(states["by_state"]) == set(be.STATES) and list(states["by_state"]) == sorted(be.STATES)
    assert (states["no_state"], states["abroad"]) == (2, 1)
    total = sum(states["by_state"].values()) + states["no_state"] + states["abroad"]
    assert total == report["overall"]["upcoming"]["events"]


def test_a_change_in_the_state_counts_is_a_real_change_and_shows_in_the_summary():
    a = quality.quality_report([_shown("a", "Kerala")], TODAY, "t1")
    b = quality.quality_report([_shown("a", "Goa")], TODAY, "t2")
    assert quality.comparable(a) != quality.comparable(b)
    text = quality.summary_markdown(b)
    assert "**Upcoming by state:** Goa 1; no state 0; abroad 0." in text and "None yet: Andaman" in text


def test_the_build_writes_the_states(data_dir):
    from conftest import build, row
    build(data_dir, [row("Kochi Open", "400001", start="10-12-2026", place="Kochi, Kerala")])
    written = json.loads((data_dir / "quality.json").read_text("utf-8"))
    assert written["states"]["by_state"]["Kerala"] == 1 and written["states"]["events"] == 1


# ---- Part 5: the Goa QQChess pair ------------------------------------------------
def test_the_goa_qqchess_pair_is_in_pairs_csv():
    with open(ROOT / "data" / "manual" / "pairs.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    match = [r for r in rows if {r["id_a"], r["id_b"]} == {"aicf-487788", "chessresults_ind-1487030"}]
    assert len(match) == 1 and match[0]["decision"] == "same"
    errors, warnings = [], []
    be.load_pairs(ROOT / "data", errors, warnings)
    assert errors == []
