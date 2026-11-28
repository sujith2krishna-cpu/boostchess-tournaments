"""CR-29: brochure and registration links from KSCA's and TNSCA's own event pages.

Fixtures: ksca_event_2026-11-28.html and tnsca_event_2026-11-28.html are saved, trimmed pages
(contact details replaced with fake ones); event_page_links_made.html is made by hand."""
import json
from datetime import date

import build_events as be
from conftest import KSCA, TNSCA, by_id, fx, run_all, serve_ksca, serve_tnsca
from eventlib import RequestCapReached, SourceError
from sources import event_pages, ksca, tnsca
from sources.event_pages import EVENT_PAGES_KEY, MAX_EVENT_PAGES, page_links, read_event_pages

ONLY = lambda name: {n: n == name for n in be.SOURCE_MODULES}  # noqa: E731
KSCA_PDF = "https://karnatakachess.com/wp-content/uploads/2026/11/1003066513.pdf"
TNSCA_PDF = "https://tamilchess.com/wp-content/uploads/2026/11/CO-218.RAN_.26-27.pdf"
TODAY = date(2026, 11, 24)


# ---- reading one page -------------------------------------------------------------------
def test_ksca_page_gives_the_embedded_brochure_and_nothing_from_the_menu_or_contacts():
    links = page_links(fx("ksca_event_2026-11-28.html"), KSCA + "tournaments/x/",
                       ksca.EVENT_CONTAINER, (ksca.LIST_URL,))
    assert links == {"brochure_url": KSCA_PDF, "register_url": None}


def test_tnsca_page_gives_the_prospectus_and_never_the_theme_links_or_the_e_mail():
    links = page_links(fx("tnsca_event_2026-11-28.html"), TNSCA + "events/x/",
                       tnsca.EVENT_CONTAINER, (tnsca.CALENDAR_URL,))
    assert links == {"brochure_url": TNSCA_PDF, "register_url": None}


def test_labelled_registration_and_brochure_win_and_contacts_are_never_links():
    links = page_links(fx("event_page_links_made.html"), KSCA + "tournaments/x/",
                       ksca.EVENT_CONTAINER, (ksca.LIST_URL,))
    assert links == {"brochure_url": "https://karnatakachess.com/wp-content/uploads/2026/12/open-2026.pdf",
                     "register_url": "https://forms.example.org/chess-open-2026"}


def test_two_unlabelled_pdfs_give_no_brochure_and_a_page_without_the_text_gives_nothing():
    two = ('<div class="detail-text"><a href="/a.pdf">a</a> <a href="/b.pdf">b</a>'
           '<a href="/register-now/">Register</a></div>')
    assert page_links(two, TNSCA + "events/x/", ".detail-text") == {
        "brochure_url": None, "register_url": TNSCA + "register-now/"}
    assert page_links("<html><body><a href='/a.pdf'>a</a></body></html>", TNSCA, ".detail-text") is None


# ---- which pages are read, and what is kept --------------------------------------------
class Client:
    def __init__(self, pages=None, fail=(), cap_after=None):
        self.pages, self.fail, self.cap_after, self.urls = pages or {}, set(fail), cap_after, []

    def get(self, url):
        if self.cap_after is not None and len(self.urls) >= self.cap_after:
            raise RequestCapReached("cap")
        self.urls.append(url)
        if url in self.fail or url not in self.pages:
            raise SourceError("404")
        return self.pages[url]


def ev(n, start="2026-12-06", **extra):
    return {"id": f"tnsca-{n}", "start": start, "end": start, "source_url": f"{TNSCA}events/e{n}/",
            "brochure_url": None, "register_url": None, "cancelled": False, **extra}


PAGE = fx("tnsca_event_2026-11-28.html")
EMPTY = '<div class="detail-text"><p>Prospectus will follow</p></div>'


def read(events, client, old_state=None, sigs=None):
    listing = {e["id"]: (sigs or {}).get(e["id"], "s1") for e in events}
    return read_event_pages(client, events, listing, old_state or {}, TODAY, tnsca.EVENT_CONTAINER,
                            TNSCA + "events/", (tnsca.CALENDAR_URL,))


def test_only_listed_events_that_are_not_over_and_on_the_site_are_read_soonest_first():
    events = [ev(1, "2026-12-20"), ev(2, "2026-11-01"), ev(3, "2026-12-01"),
              ev(4, source_url="https://elsewhere.example.org/e4/")]
    client = Client({e["source_url"]: PAGE for e in events})
    out, state, stats = read(events, client)
    assert client.urls == [f"{TNSCA}events/e3/", f"{TNSCA}events/e1/"]  # e2 is over, e4 elsewhere
    assert [e["brochure_url"] for e in out] == [TNSCA_PDF, None, TNSCA_PDF, None]
    assert stats["event_pages_read"] == 2 and stats["brochure_links"] == 2


def test_a_page_is_read_again_only_when_the_listing_line_changed():
    events = [ev(1)]
    _, state, _ = read(events, Client({events[0]["source_url"]: PAGE}))
    client = Client({events[0]["source_url"]: PAGE})
    out, again, _ = read(events, client, state)
    assert client.urls == [] and again == state and out[0]["brochure_url"] == TNSCA_PDF
    client = Client({events[0]["source_url"]: PAGE})
    read(events, client, state, sigs={"tnsca-1": "s2"})
    assert client.urls == [events[0]["source_url"]]


def test_a_failed_page_keeps_what_we_had_and_a_link_is_never_removed():
    events = [ev(1)]
    _, state, _ = read(events, Client({events[0]["source_url"]: PAGE}))
    # the line changed, the page fails: the old link stays, and it is tried again next run
    out, kept, stats = read(events, Client(fail={events[0]["source_url"]}), state, sigs={"tnsca-1": "s2"})
    assert out[0]["brochure_url"] == TNSCA_PDF and kept == state and stats["event_pages_failed"] == 1
    # the page no longer shows the PDF: the link is still kept
    out, later, _ = read(events, Client({events[0]["source_url"]: EMPTY}), state, sigs={"tnsca-1": "s3"})
    assert out[0]["brochure_url"] == TNSCA_PDF and later["tnsca-1"]["sig"] == "s3"
    # an event's own brochure (from the list) is never replaced
    own = [ev(1, brochure_url="https://tamilchess.com/own.pdf")]
    out, _, _ = read(own, Client({own[0]["source_url"]: PAGE}))
    assert out[0]["brochure_url"] == "https://tamilchess.com/own.pdf"


def test_at_most_max_event_pages_a_run_and_the_request_cap_stops_reading():
    events = [ev(n, f"2026-12-{1 + n % 28:02d}") for n in range(MAX_EVENT_PAGES + 7)]
    client = Client({e["source_url"]: PAGE for e in events})
    _, state, stats = read(events, client)
    assert len(client.urls) == MAX_EVENT_PAGES and stats["event_pages_waiting"] == 7
    client = Client({e["source_url"]: PAGE for e in events}, cap_after=3)
    _, state, stats = read(events, client)
    assert len(state) == 3 and stats["event_pages_read"] == 3


def test_ksca_and_tnsca_stay_under_the_request_cap_with_their_list_pages():
    assert ksca.MAX_PAGES + 1 + MAX_EVENT_PAGES < 60
    assert 3 + 1 + MAX_EVENT_PAGES < 60  # TNSCA: at most three year pages
    assert event_pages.MAX_EVENT_PAGES == 45


# ---- the whole run ----------------------------------------------------------------------
def first_event_page(web, data_dir, serve, name, host):
    serve(web)
    run_all(data_dir, config=ONLY(name))
    lists = {KSCA + "robots.txt", TNSCA + "robots.txt"}
    pages = [u for u in web.urls(host) if u not in lists and "/tournaments/list/" not in u
             and u != KSCA + "tournaments/" and "tournament-registration" not in u]
    return pages[0]


def test_ksca_run_puts_the_brochure_on_the_event_and_keeps_it_when_the_page_later_fails(web, data_dir):
    url = first_event_page(web, data_dir, serve_ksca, "ksca", "karnatakachess.com")
    web.add(url, fx("ksca_event_2026-11-28.html"))
    report = run_all(data_dir, config=ONLY("ksca"))
    event = next(e for e in by_id(data_dir).values() if e["source_url"] == url)
    assert event["brochure_url"] == KSCA_PDF and report["per_source"]["ksca"]["status"] == "ok"
    snapshot = json.loads((data_dir / "sources" / "ksca.json").read_text("utf-8"))
    assert snapshot["listing"][EVENT_PAGES_KEY][event["id"]]["brochure_url"] == KSCA_PDF
    # the page is not read again while its list line is the same
    before = len(web.urls(url))
    run_all(data_dir, config=ONLY("ksca"))
    assert len(web.urls(url)) == before
    # the page goes away: the link stays
    web.add(url, "gone", status=404)
    run_all(data_dir, config=ONLY("ksca"))
    assert next(e for e in by_id(data_dir).values() if e["source_url"] == url)["brochure_url"] == KSCA_PDF


def test_tnsca_run_reads_event_pages_and_stores_no_contact_details(web, data_dir):
    url = first_event_page(web, data_dir, serve_tnsca, "tnsca", "tamilchess.com")
    assert url.startswith(TNSCA + "events/")
    web.add(url, fx("tnsca_event_2026-11-28.html"))
    run_all(data_dir, config=ONLY("tnsca"))
    event = next(e for e in by_id(data_dir).values() if e["source_url"] == url)
    assert event["brochure_url"] == TNSCA_PDF
    for name in ("events.json", "sources/tnsca.json"):
        text = (data_dir / name).read_text("utf-8")
        assert "90000" not in text and "organiser@example.com" not in text and "A Sample" not in text
