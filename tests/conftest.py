"""Shared helpers for the offline tests."""
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_events as be  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "aicf_all_events_2026-11-24.html"
NOW = datetime(2026, 11, 24, 10, 30, tzinfo=be.IST)

EVENTS_HEADER = ",".join(be.EVENTS_CSV_COLUMNS) + "\n"
OVERRIDES_HEADER = ",".join(be.OVERRIDES_CSV_COLUMNS) + "\n"


def make_html(rows):
    """A tiny AICF-style page. Each row is (name, code, start, end, place_html, brochure_html)."""
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in r) + "</tr>" for r in rows
    )
    return (
        "<html><body><table><tbody><tr><th>Name of Tournament</th><th>Event Code</th>"
        "<th>Start Date</th><th>End Date</th><th>Place</th><th>Brochure</th></tr>"
        f"{body}</tbody></table></body></html>"
    )


def row(name="Test Open 2026", code="400001", start="10-12-2026", end="12-12-2026",
        place="Chennai", brochure=""):
    return (name, code, start, end, place, brochure)


def padding(n, first=500000):
    """Filler rows so a page passes the 100-row check (when a test uses the real minimum)."""
    return [row(f"Filler {i}", str(first + i), start="01-12-2026", end="02-12-2026")
            for i in range(n)]


@pytest.fixture
def data_dir(tmp_path):
    folder = tmp_path / "data"
    (folder / "manual").mkdir(parents=True)
    (folder / "manual" / "events.csv").write_text(EVENTS_HEADER, encoding="utf-8")
    (folder / "manual" / "overrides.csv").write_text(OVERRIDES_HEADER, encoding="utf-8")
    return folder


def build(folder, rows, now=NOW, min_rows=1, **kwargs):
    return be.run(folder, html=make_html(rows), now=now, min_rows=min_rows, **kwargs)


def load_doc(folder):
    return json.loads((folder / "events.json").read_text(encoding="utf-8"))


def load_events(folder):
    return load_doc(folder)["events"]


def by_id(folder):
    return {e["id"]: e for e in load_events(folder)}


def write_manual(folder, text, name="events.csv"):
    (folder / "manual" / name).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# A pretend internet for the source tests: nothing here touches the network.
# ---------------------------------------------------------------------------
SOURCE_FIXTURES = ROOT / "tests" / "fixtures" / "sources"
ALL_SOURCES_ON = {name: True for name in be.SOURCE_MODULES}


def fx(name):
    return (SOURCE_FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, status_code, body, url):
        self.status_code = status_code
        self.content = body.encode("utf-8") if isinstance(body, str) else body
        self.url = url


class FakeWeb:
    """Stands in for requests.get / requests.post and records every call."""

    def __init__(self):
        self.routes = {}
        self.calls = []

    def add(self, url, body, status=200, method="GET"):
        self.routes[(method, url)] = (status, body)

    def _answer(self, method, url, data=None, headers=None):
        self.calls.append({"method": method, "url": url, "data": data, "headers": headers})
        status, body = self.routes.get((method, url), (404, "not found"))
        if callable(body):
            body = body(data)
        return FakeResponse(status, body, url)

    def get(self, url, headers=None, timeout=None):
        assert timeout, "every request needs a timeout"
        return self._answer("GET", url, headers=headers)

    def post(self, url, data=None, headers=None, timeout=None):
        assert timeout, "every request needs a timeout"
        return self._answer("POST", url, data=data, headers=headers)

    def urls(self, host=None):
        return [c["url"] for c in self.calls if host is None or host in c["url"]]


@pytest.fixture
def web(monkeypatch):
    fake = FakeWeb()
    fake.sleeps = []
    monkeypatch.setattr(be.requests, "get", fake.get)
    monkeypatch.setattr(be.requests, "post", fake.post)
    monkeypatch.setattr(be.time, "sleep", lambda seconds: fake.sleeps.append(seconds))
    for host in ("aicf.in", "www.keralachessassociation.com", "tamilchess.com", "karnatakachess.com",
                 "upchess.org", "www.chessfee.com",
                 "chess-results.com", "chessbase.in"):
        fake.add(f"https://{host}/robots.txt", "User-agent: *\nAllow: /\n")
    return fake


CF = "https://www.chessfee.com/"
CR = "https://chess-results.com/"
CB = "https://chessbase.in/"
KCA = "https://www.keralachessassociation.com/"
TNSCA = "https://tamilchess.com/"
KSCA = "https://karnatakachess.com/"
UPCSA = "https://upchess.org/"
CR_FED = CR + "fed.aspx?lan=1&fed=IND"


def serve_chessfee(web, details=("1860",)):
    web.add(CF + "tournament_ongoing.php", fx("chessfee_ongoing_p1.html"))
    web.add(CF + "tournament_ongoing.php?page=2", fx("chessfee_ongoing_p2.html"))
    web.add(CF + "tournament_ongoing.php?page=3", fx("chessfee_ongoing_p2.html"))
    web.add(CF + "upcoming_tournaments.php", fx("chessfee_upcoming.html"))
    for event_id in details:
        web.add(CF + f"tmt_details.php?id={event_id}", fx(f"chessfee_detail_{event_id}.html"))


def serve_chessresults(web):
    option_pages = {"1": "chessresults_list_running.html", "2": "chessresults_list_next7.html",
                    "3": "chessresults_list_later.html"}
    web.add(CR_FED, fx("chessresults_fed_ind.html"))
    web.add(CR_FED, lambda data: fx(option_pages.get(data["combo_tur_sel"], "chessresults_fed_ind.html")),
            method="POST")
    for tnr in ("1528935", "1539989", "1549496", "1550001"):
        web.add(CR + f"tnr{tnr}.aspx?lan=1&turdet=YES", fx(f"chessresults_tnr{tnr}.html"))


def serve_chessbase(web):
    web.add(CB + "chess-calendar", fx("chessbase_calendar.html"))
    web.add(CB + "chess-calendar/2027", fx("chessbase_calendar_2027.html"))
    web.add(CB + "chess-calendar/2028", fx("chessbase_calendar_2028.html"))


def serve_kca(web, details=("736",)):
    """The saved events page (25 Nov 2026) and the saved details page(s)."""
    web.add(KCA + "events", fx("kca_events_2026-11-25.html"))
    for number in details:
        web.add(KCA + f"events/{number}", fx(f"kca_event_{number}.html"))


def serve_tnsca(web, years=(2026, 2027)):
    """The saved calendar pages (26 Nov 2026): this year (from 10 Sep) and next year."""
    for year in years:
        web.add(TNSCA + f"tournament-registration/?y={year}", fx(f"tnsca_calendar_{year}.html"))


def serve_ksca(web, page2=True):
    """The saved tournaments page (26 Nov 2026) and a hand-made page 2 (the last page)."""
    web.add(KSCA + "tournaments/", fx("ksca_tournaments_2026-11-26.html"))
    if page2:
        web.add(KSCA + "tournaments/list/page/2/", fx("ksca_tournaments_page2_made.html"))


def serve_upcsa(web):
    """The saved, trimmed tournaments page (28 Nov 2026)."""
    web.add(UPCSA + "tournament.php", fx("upcsa_tournaments_2026-11-28.html"))


def serve_aicf(web, rows):
    web.add("https://aicf.in/all-events/", make_html(rows))


def run_all(folder, now=NOW, config=None, **kwargs):
    return be.run(folder, config=config or ALL_SOURCES_ON, now=now, min_rows=1, **kwargs)
