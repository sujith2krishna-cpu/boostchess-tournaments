"""Source: ChessBase India calendar, https://chessbase.in/chess-calendar (India and abroad).

The calendar page ships its event list inside the page itself (the same data the page
shows), for the month that is open by default. We read that list for the current year
page and the other year pages the calendar links to. Switching months in the page
needs a separate data service that robots.txt asks robots to stay away from, so we do
not use it: a run therefore sees only the month (or first month) each page opens on.
Online-only events are left out ("Where = India" and "Abroad"). We store facts and links
only; the brochure is a link, never a copy.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from eventlib import (FORMAT_ORDER, IN_STATE_CODES, RequestCapReached, SourceError, aicf_codes_in,
                      canonical, check_dates, clean_name, clean_text, country_for, derive_tags,
                      merge_tags, region_for, strip_phones, valid_url)

NAME = "chessbase_calendar"
SITE_URL = "https://chessbase.in/"
CALENDAR_URL = "https://chessbase.in/chess-calendar"  # https://chessbase.in/calendar redirects here
MAX_YEAR_PAGES = 4

_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)
_EVENTS_KEY = re.compile(r'"events":\[')


def page_data(html: str) -> str:
    """The text of the page's embedded data (it is split into several script chunks)."""
    parts = []
    for chunk in _CHUNK.findall(html):
        try:
            parts.append(json.loads('"' + chunk + '"'))
        except ValueError:
            continue
    return "".join(parts)


def parse_events(html: str, required: bool = True) -> list[dict]:
    """The calendar's event list from one page.

    A page without the list is a layout change (SourceError) for the main page; a year page
    with no events at all simply has no list (required=False).
    """
    blob = page_data(html)
    decoder = json.JSONDecoder()
    for match in _EVENTS_KEY.finditer(blob):
        try:
            found, _ = decoder.raw_decode(blob[match.end() - 1:])
        except ValueError:
            continue
        if isinstance(found, list) and all(isinstance(e, dict) for e in found) \
                and all("slug" in e and "title" in e for e in found):
            return found
    if not required:
        return []
    raise SourceError("ChessBase calendar page has no event list; layout changed?")


def year_pages(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        if re.fullmatch(r"/chess-calendar/\d{4}", a["href"]):
            url = urljoin(page_url, a["href"])
            if url not in urls:
                urls.append(url)
    return urls


def parse_brochure(html: str, page_url: str) -> str | None:
    """The brochure link on an event page (a link only; we never copy the file)."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if "download brochure" in a.get_text(" ").lower() or a["href"].lower().endswith(".pdf"):
            return valid_url(a["href"], page_url)
    return None


def signature(raw: dict) -> str:
    keys = ("title", "startDate", "endDate", "formats", "fideRated", "mode", "location",
            "categories", "isCancelled", "hasBrochure")
    return hashlib.sha1(json.dumps([raw.get(k) for k in keys], sort_keys=True).encode()).hexdigest()[:12]


def _iso_date(text) -> date | None:
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


def build_event(raw: dict, brochure_url: str | None, today: date) -> dict:
    title = clean_name(strip_phones(raw.get("title")))
    location = raw.get("location") or {}
    country = country_for(NAME, location.get("country"))
    abroad = country is not None and country != "IN"
    region = clean_text(location.get("region"))
    if country == "IN":
        state = IN_STATE_CODES.get(clean_text(location.get("stateCode")).upper())
    else:
        state = (region_for(country, region) or region or None) if country else None
    city = clean_text(location.get("city")) or None
    place_parts = [p for p in (city, state if state != city else None, country if abroad else None) if p]
    start = _iso_date(raw.get("startDate"))
    end = _iso_date(raw.get("endDate")) or start
    suspect, raw_dates = check_dates(start, end, str(raw.get("startDate") or ""),
                                     str(raw.get("endDate") or ""), today)
    formats = [f for f in FORMAT_ORDER if f in (raw.get("formats") or [])]
    categories = [c for c in (raw.get("categories") or []) if isinstance(c, str)]
    if abroad:
        categories.append("abroad")
    tags = merge_tags(derive_tags(title), {
        "formats": formats, "categories": categories,
        "fide_rated": True if raw.get("fideRated") is True else None,
        "open": True if "open" in categories else None})
    return canonical({
        "id": f"{NAME}-{raw['id']}",
        "codes": aicf_codes_in(title),
        "name": title,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "place_text": ", ".join(place_parts) or None,
        "state": state,
        "city": city,
        "country": country,
        "brochure_url": brochure_url,
        "source": NAME,
        "source_url": f"{SITE_URL}chess-calendar/event/{raw['slug']}",
        "register_url": None,
        "tags": tags,
        "flags": {"dates_suspect": suspect},
        "raw_dates": raw_dates,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
        "cancelled": bool(raw.get("isCancelled")),
    })


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats)."""
    first_html = client.get(CALENDAR_URL)
    pages = [(CALENDAR_URL, first_html)]
    for url in year_pages(first_html, CALENDAR_URL):
        if len(pages) >= MAX_YEAR_PAGES:
            break
        if url.rstrip("/").endswith(f"/{today.year}"):
            continue  # the current year is the page we already read
        pages.append((url, client.get(url)))
    raws: dict[str, dict] = {}
    for index, (url, html) in enumerate(pages):
        for raw in parse_events(html, required=index == 0):
            if raw.get("mode") == "online" or not raw.get("id") or not raw.get("slug"):
                continue
            raws.setdefault(raw["id"], raw)
    old_events = {e["id"]: e for e in previous.get("events", [])}
    old_listing = previous.get("listing", {})
    events, listing = [], {}
    can_fetch = True
    for raw in raws.values():
        event_id = f"{NAME}-{raw['id']}"
        sig = signature(raw)
        url = f"{SITE_URL}chess-calendar/event/{raw['slug']}"
        old = old_events.get(event_id)
        if old is not None and old_listing.get(url) == sig:
            events.append(old)
            listing[url] = sig
            continue
        brochure, read_ok = None, True
        if raw.get("hasBrochure"):
            read_ok = False
            if can_fetch:
                try:
                    brochure = parse_brochure(client.get(url), url)
                    read_ok = True
                except RequestCapReached:
                    can_fetch = False
                except SourceError:
                    pass
        events.append(build_event(raw, brochure if read_ok else (old or {}).get("brochure_url"), today))
        if read_ok:
            listing[url] = sig
    return events, listing, {"found": len(raws), "pages_read": len(pages)}
