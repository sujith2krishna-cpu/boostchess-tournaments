"""Source: Karnataka State Chess Association (KSCA), karnatakachess.com.

The tournaments page (`/tournaments/`) is a WordPress "The Events Calendar" list of upcoming
and ongoing events, about twelve per page, oldest first. Every event is an <article> with:

- the WordPress post number in its classes (`post-7128`), which gives our id `ksca-7128`;
- the category in its classes (`tribe_events_cat-fide-rating-events`); the association files
  events under "FIDE Rating Events", "National Events", "State Selection Tournaments" and
  "Monthly Tournaments";
- the title, linked to the event's page;
- the start date as `<time datetime="2026-11-28">`, and the text "November 28 @ 8:00 am -
  5:00 pm" (one day) or "December 26 @ 9:00 am - December 28 @ 6:00 pm" (several days);
- the venue name and its address ("Shanti Colony, Hubli, Karnataka, India").

We read page 1 and then follow the page's own "Next Events" link, at most MAX_PAGES pages.
Then, for events that are not over, the event's own page (the title's link), only when the
event is new or its list line changed (sources/event_pages.py, at most 45 a run): its text
(`.tribe-events-single-event-description`) gives the brochure (the embedded PDF) and a
registration link when one is labelled. The page's organiser phone and e-mail are never read.

Dates: the start comes from the `datetime` attribute. The end is read from the end text; when
that text has no year, it is the start's year (the calendar writes the year only when it is
not the current one). Anything unreadable, or an end before the start, is kept and flagged
(`dates_suspect`, raw text in `raw_dates`), never fixed.

An event in the category "FIDE Rating Events" gets `fide_rated` = true ("stated").
Facts and links only; every piece of text goes through strip_phones().
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from eventlib import (SourceError, canonical, check_dates, clean_name, clean_text, country_for,
                      derive_tags, locate_text, strip_phones, valid_url)
from sources.event_pages import EVENT_PAGES_KEY, read_event_pages

NAME = "ksca"
SITE_URL = "https://karnatakachess.com/"
LIST_URL = SITE_URL + "tournaments/"
MAX_PAGES = 8  # 8 pages of ~12 events: months ahead; well inside the per-site request cap
# The event's own text on its page (The Events Calendar); menus and sidebars are not read.
EVENT_CONTAINER = ".tribe-events-single-event-description"

# The association's own category names (the home page's "See all ..." links).
CATEGORY_LABELS = {
    "fide-rating-events": "FIDE Rating Events",
    "national-events": "National Events",
    "state-selection-tournaments": "State Selection Tournaments",
    "monthly-tournaments": "Monthly Tournaments",
}
FIDE_CATEGORY = "fide-rating-events"

_POST = re.compile(r"^post-(\d+)$")
_CATEGORY = re.compile(r"^tribe_events_cat-([a-z0-9-]+)$")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# "December 28 @ 6:00 pm", "January 2, 2027 @ 9:00 am", "December 28", "December 28, 2026"
_DAY_TEXT = re.compile(r"^([A-Za-z]+)\s+(\d{1,2})(?:,\s*(\d{4}))?(?:\s*@.*)?$")


def _text(node) -> str:
    return clean_text(_CONTROL.sub(" ", node.get_text(" ") if node is not None else ""))


def parse_day(text: str, default_year: int | None) -> date | None:
    """'December 28 @ 6:00 pm' -> that day in default_year; 'January 2, 2027' -> 2027-01-02.

    No year in the text and no default year, or anything else: None (never guessed).
    """
    match = _DAY_TEXT.match(clean_text(text))
    if not match:
        return None
    month, day, year = match.groups()
    year = int(year) if year else default_year
    if year is None:
        return None
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{month.title()} {day} {year}", fmt).date()
        except ValueError:
            continue
    return None


def _iso_day(text) -> date | None:
    try:
        return date.fromisoformat((text or "").strip()[:10])
    except ValueError:
        return None


def _article(article, page_url: str) -> dict | None:
    classes = article.get("class") or []
    post = next((m.group(1) for c in classes for m in [_POST.match(c)] if m), None)
    link = article.select_one(".tribe-events-calendar-list__event-title a[href]")
    if post is None or link is None:
        return None
    when = article.select_one("time.tribe-events-calendar-list__event-datetime")
    start_span = when.select_one(".tribe-event-date-start") if when else None
    end_span = when.select_one(".tribe-event-date-end") if when else None
    return {
        "post": post,
        "name": _text(link),
        "detail_url": valid_url(link["href"], page_url),
        "start_attr": (when.get("datetime") or "") if when else "",
        "start_text": _text(start_span) if start_span else _text(when),
        "end_text": _text(end_span) if end_span else "",
        "venue": _text(article.select_one(".tribe-events-calendar-list__event-venue-title")),
        "address": _text(article.select_one(".tribe-events-calendar-list__event-venue-address")),
        "categories": sorted({m.group(1) for c in classes for m in [_CATEGORY.match(c)] if m}),
    }


def parse_list(html: str, page_url: str) -> dict:
    """{'rows': [...], 'next': URL of the page's own "Next Events" link or None}."""
    soup = BeautifulSoup(html, "html.parser")
    view = soup.select_one(".tribe-events-view--list")
    if view is None:
        raise SourceError("KSCA tournaments page has no event list (The Events Calendar 'list' "
                          "view); layout changed?")
    rows = [r for r in (_article(a, page_url)
                        for a in view.select("article.tribe-events-calendar-list__event")) if r]
    if not rows and not view.select_one(".tribe-events-c-messages"):
        raise SourceError("KSCA tournaments page shows neither events nor a 'no events' notice; "
                          "layout changed?")
    nxt = view.select_one("a.tribe-events-c-nav__next[href]")
    next_url = valid_url(nxt["href"], page_url) if nxt else None
    if next_url and not next_url.startswith(LIST_URL):
        next_url = None  # only the list's own pages
    return {"rows": rows, "next": next_url}


def signature(row: dict) -> str:
    keys = ("name", "detail_url", "start_attr", "start_text", "end_text", "venue", "address")
    text = "|".join(row[k] or "" for k in keys) + "|" + ",".join(row["categories"])
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def event_id(row: dict) -> str:
    return f"{NAME}-{row['post']}"


def build_event(row: dict, today: date) -> dict:
    name = clean_name(strip_phones(row["name"]))
    start = _iso_day(row["start_attr"])
    shown = parse_day(row["start_text"], start.year if start else None)
    if start is None:
        start = shown  # no machine date: only a text that carries its own year
    end = parse_day(row["end_text"], start.year if start else None) if row["end_text"] else start
    raw_start = row["start_text"] or row["start_attr"]
    suspect, raw_dates = check_dates(start, end, raw_start, row["end_text"], today)
    if not suspect and shown is not None and shown != start:
        # the text and the machine date disagree: keep both, flag, fix nothing
        suspect, raw_dates = True, {"start": f"{row['start_attr']} ({row['start_text']})",
                                    "end": row["end_text"]}
    venue = strip_phones(row["venue"])
    address = strip_phones(row["address"])
    place = re.sub(r"\s*,(?:\s*,)+\s*", ", ", ", ".join(p for p in (venue, address) if p))  # "Nagar,, Bengaluru"
    where = locate_text(place, name)
    tags = derive_tags(name)
    if FIDE_CATEGORY in row["categories"]:  # filed by the association under "FIDE Rating Events"
        tags["fide_rated"], tags["fide_how"] = True, "stated"
    tags["categories"] = [CATEGORY_LABELS.get(c, c.replace("-", " ").title())
                          for c in row["categories"]]
    return canonical({
        "id": event_id(row),
        "codes": [],
        "name": name,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "place_text": where["place_text"],
        "state": where["state"],
        "city": where["city"],
        "country": country_for(NAME),
        "source": NAME,
        "source_url": row["detail_url"] or LIST_URL,
        "tags": tags,
        "flags": {"dates_suspect": suspect},
        "raw_dates": raw_dates,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats). One request per list page read."""
    rows, url, pages, seen_urls = [], LIST_URL, 0, set()
    more = False
    while url and url not in seen_urls:
        if pages == MAX_PAGES:
            more = True
            break
        seen_urls.add(url)
        page = parse_list(client.get(url), url)
        pages += 1
        rows.extend(page["rows"])
        url = page["next"]

    old_events = {e["id"]: e for e in previous.get("events", [])}
    old_listing = previous.get("listing", {})
    events, listing = [], {}
    for r in rows:
        key = event_id(r)
        if key in listing:
            continue  # the same event on two pages (the list moved while we read it)
        sig = signature(r)
        old = old_events.get(key)
        events.append(old if old is not None and old_listing.get(key) == sig
                      else build_event(r, today))
        listing[key] = sig
    events, pages_state, page_stats = read_event_pages(
        client, events, listing, old_listing.get(EVENT_PAGES_KEY) or {}, today,
        EVENT_CONTAINER, LIST_URL, not_links=(LIST_URL,))
    stats = {"found": len(events), "pages_read": len(seen_urls), "more_pages_not_read": more,
             **page_stats}
    if pages_state:
        listing[EVENT_PAGES_KEY] = pages_state
    return events, listing, stats
