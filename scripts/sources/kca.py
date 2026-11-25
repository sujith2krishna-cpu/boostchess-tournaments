"""Source: Kerala Chess Association (Chess Association Kerala, CAK), keralachessassociation.com.

The events page is plain server HTML with two tabs that are both in the page:
"Upcoming & Ongoing" and "Completed Events". The completed tab shows one year (the
current one by default); other years come from the page's own year menu (a GET form,
`?tab=completed&year=YYYY`). We read the upcoming list and, for results links later on,
the completed events of the last 60 days (the previous year's list only in the first
two months of a year). Older years are not read.

Each row has the KCA event code (e.g. 736/CAK/2026), a type label (FIDE, STATE, EVENT, ...),
the name, the dates, the district and links (details page, brochure). The details page
is read only for upcoming events that are new or whose row changed, for the venue, a
time-control/format line and a registration link when the page offers a working one.

Facts and links only: no organiser phone numbers, no player lists, no brochure files.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from eventlib import (RequestCapReached, SourceError, canonical, check_dates, clean_name,
                      clean_text, country_for, derive_tags, formats_in, merge_tags, strip_phones,
                      valid_url)

NAME = "kca"
SITE_URL = "https://www.keralachessassociation.com/"
EVENTS_URL = SITE_URL + "events"
RECENT_DAYS = 60
STATE_CATEGORY = "KCA state rated"

_CODE = re.compile(r"^\s*(\d{1,5})\s*/\s*([A-Za-z]+)\s*/\s*(\d{4})\s*$")
_DETAIL = re.compile(r"/events/(\d+)/?$")
# "Nov 29 - Nov 29, 2026" (the year is written once, at the end)
_DATES = re.compile(r"([A-Za-z]{3,9})\s+(\d{1,2})\s*[-–]\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})")
_SPACED_POSSESSIVE = re.compile(r"\s+['’]\s+s\b")
_REGISTER_WORDS = re.compile(r"(?i)\bregist|\benrol")
_FORMAT_LABEL = re.compile(r"(?i)time\s*control|format|category|type\s+of")


def _month_day(month: str, day: str, year: str) -> date | None:
    try:
        return datetime.strptime(f"{month[:3].title()} {day} {year}", "%b %d %Y").date()
    except ValueError:
        return None


def parse_dates(text: str) -> tuple[date | None, date | None]:
    """Both dates in the year written at the end. A range that crosses into a new year comes
    out with the end before the start, and is then flagged, not fixed (no guessing)."""
    match = _DATES.search(text or "")
    if not match:
        return None, None
    m1, d1, m2, d2, year = match.groups()
    return _month_day(m1, d1, year), _month_day(m2, d2, year)


def _rows(pane, page_url: str, tab: str) -> list[dict]:
    entries = []
    for tr in pane.find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 5:
            continue
        badge = cells[0].select_one(".type-badge-text")
        code = clean_text(cells[1].get_text(" "))
        name_cell = cells[2]
        title = name_cell.find(["a", "span"])
        status = name_cell.find("div", class_=re.compile(r"status-text-"))
        links = [a for a in tr.find_all("a", href=True)]
        detail = next((a["href"] for a in links if _DETAIL.search(a["href"])), None)
        brochure = next((a["href"] for a in links
                         if "btn-pdf" in (a.get("class") or [])
                         or "brochure" in (a.get("title") or "").lower()
                         or a["href"].lower().endswith(".pdf")), None)
        entry = {
            "tab": tab,
            "label": clean_text(badge.get_text(" ")).upper() if badge else "",
            "code": code if _CODE.match(code) else "",
            "raw_code": code,
            "title": clean_text(title.get_text(" ")) if title else "",
            "status": clean_text(status.get_text(" ")) if status else "",
            "date_text": clean_text(cells[3].get_text(" ")),
            "district": clean_text(cells[4].get_text(" ")),
            "detail_url": valid_url(detail, page_url) if detail else None,
            "brochure_url": valid_url(brochure, page_url) if brochure else None,
        }
        if entry["title"] and (entry["code"] or entry["detail_url"]):
            entries.append(entry)
    return entries


def parse_listing(html: str, page_url: str = EVENTS_URL) -> dict:
    """{'upcoming': [...], 'completed': [...], 'years': [int], 'year_form': (action, fields) | None}."""
    soup = BeautifulSoup(html, "html.parser")
    upcoming = soup.find(id="upcoming")
    completed = soup.find(id="completed")
    if upcoming is None or completed is None:
        raise SourceError("KCA events page has no Upcoming/Completed tabs; layout changed?")
    years, year_form = [], None
    select = completed.find("select", attrs={"name": "year"})
    if select is not None:
        years = [int(o["value"]) for o in select.find_all("option")
                 if re.fullmatch(r"\d{4}", o.get("value", ""))]
        form = select.find_parent("form")
        if form is not None and (form.get("method") or "get").lower() == "get":
            fields = {i["name"]: i.get("value", "") for i in form.find_all("input", type="hidden")
                      if i.get("name")}
            year_form = (urljoin(page_url, form.get("action") or page_url), fields)
    return {"upcoming": _rows(upcoming, page_url, "upcoming"),
            "completed": _rows(completed, page_url, "completed"),
            "years": years, "year_form": year_form}


def parse_detail(html: str, page_url: str) -> dict:
    """Venue, a format line and a working registration link from an event's page."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    labels = {}
    for small in main.find_all("small"):
        key = clean_text(small.get_text(" "))
        value = small.find_next_sibling(["span", "div", "p"])
        if key and value is not None and len(key) < 40 and key not in labels:
            extra = value.find_next_sibling("small")
            text = clean_text(value.get_text(" "))
            if extra is not None:
                text = f"{text}, {clean_text(extra.get_text(' '))}" if text else clean_text(extra.get_text(" "))
            labels[key] = text
    if "Venue" not in labels and "Date" not in labels:
        raise SourceError("KCA event page has no Date/Venue block; layout changed?")
    register = None
    for a in main.find_all("a", href=True):
        if not _REGISTER_WORDS.search(a.get_text(" ")):
            continue
        if "disabled" in (a.get("class") or []) or a.get("aria-disabled") == "true":
            continue
        url = valid_url(a["href"], page_url)
        if url:
            register = url
            break
    format_text = " ".join(v for k, v in labels.items() if _FORMAT_LABEL.search(k))
    return {"venue": strip_phones(labels.get("Venue", "")),
            "formats": formats_in(strip_phones(format_text)),
            "register_url": register}


def join_place(*pieces) -> str | None:
    """Comma-separated parts, each once: the details page repeats the district (and often
    "Kerala") under the venue, so "Hall, Angamaly, Ernakulam, Kerala" + "Ernakulam" stays as is."""
    parts, seen = [], set()
    for piece in pieces:
        for part in re.split(r"\s*,\s*", clean_text(piece or "")):
            key = re.sub(r"[^a-z0-9]+", " ", part.lower()).strip()
            if key and key not in seen:
                seen.add(key)
                parts.append(part.strip(" ."))
    return ", ".join(parts) or None


def signature(entry: dict) -> str:
    keys = ("label", "raw_code", "title", "date_text", "district", "brochure_url")
    return hashlib.sha1("|".join(entry[k] or "" for k in keys).encode("utf-8")).hexdigest()[:12]


def event_id(entry: dict) -> str:
    if entry["code"]:
        return f"{NAME}-" + re.sub(r"\s+", "", entry["code"]).replace("/", "-")
    return f"{NAME}-page-{_DETAIL.search(entry['detail_url']).group(1)}"


def build_event(entry: dict, detail: dict | None, today: date) -> dict:
    title = clean_name(strip_phones(_SPACED_POSSESSIVE.sub("'s", entry["title"])))
    start, end = parse_dates(entry["date_text"])
    suspect, raw_dates = check_dates(start, end, entry["date_text"], entry["date_text"], today)
    district = strip_phones(entry["district"]).strip(" -–") or None  # "-" means none given
    place_text = join_place((detail or {}).get("venue"), district, "Kerala")
    tags = derive_tags(title)
    label = entry["label"]
    if label == "FIDE":
        tags["fide_rated"], tags["fide_how"] = True, "stated"
    elif label == "STATE":
        tags["fide_rated"], tags["fide_how"] = None, None
        tags["categories"] = [STATE_CATEGORY]
    if detail and detail.get("formats"):
        tags = merge_tags(tags, {"formats": detail["formats"]})
    return canonical({
        "id": event_id(entry),
        "codes": [re.sub(r"\s+", "", entry["code"])] if entry["code"] else [],
        "name": title,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "place_text": place_text,
        "state": "Kerala",
        "city": district,
        "country": country_for(NAME),
        "brochure_url": entry["brochure_url"],
        "source": NAME,
        "source_url": entry["detail_url"] or EVENTS_URL,
        "register_url": (detail or {}).get("register_url"),
        "tags": tags,
        "flags": {"dates_suspect": suspect},
        "raw_dates": raw_dates,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def _recent(entry: dict, today: date) -> bool:
    """Ended in the last RECENT_DAYS days. The end date carries the year the site wrote, so it
    is the one to trust ("Dec 29 - Jan 02, 2026" ended in January 2026)."""
    start, end = parse_dates(entry["date_text"])
    last = end or start
    return last is not None and last >= today - timedelta(days=RECENT_DAYS)


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats). Details pages only for upcoming events."""
    page = parse_listing(client.get(EVENTS_URL), EVENTS_URL)
    completed = list(page["completed"])
    window_start = today - timedelta(days=RECENT_DAYS)
    shown_years = {parse_dates(e["date_text"])[0].year for e in completed
                   if parse_dates(e["date_text"])[0]} or {today.year}
    for year in sorted(range(window_start.year, today.year + 1), reverse=True):
        # The page shows the current year; an earlier year inside the window (January,
        # February) comes from the page's own year menu.
        if year in shown_years or year not in page["years"] or page["year_form"] is None:
            continue
        action, fields = page["year_form"]
        url = f"{action}?{urlencode({**fields, 'year': str(year)})}"
        completed.extend(parse_listing(client.get(url), url)["completed"])

    entries: dict[str, dict] = {}
    for entry in page["upcoming"]:
        entries.setdefault(event_id(entry), entry)
    recent = 0
    for entry in completed:
        if _recent(entry, today) and event_id(entry) not in entries:
            entries[event_id(entry)] = entry
            recent += 1

    old_events = {e["id"]: e for e in previous.get("events", [])}
    old_listing = previous.get("listing", {})
    events, listing = [], {}
    can_fetch, detail_requests = True, 0
    for key, entry in entries.items():
        sig = signature(entry)
        old = old_events.get(key)
        if old is not None and old_listing.get(key) == sig:
            events.append(old)
            listing[key] = sig
            continue
        detail = None
        if entry["tab"] == "upcoming" and entry["detail_url"] and can_fetch:
            try:
                detail = parse_detail(client.get(entry["detail_url"]), entry["detail_url"])
                detail_requests += 1
            except RequestCapReached:
                can_fetch = False
            except SourceError:
                detail = None  # the row's own data is enough; the page is tried again next run
        event = build_event(entry, detail, today)
        if detail is None and old is not None and old["city"] == event["city"]:
            # A row that changed but whose page was not read keeps the venue and link read before.
            event["place_text"] = old["place_text"] or event["place_text"]
            event["register_url"] = old["register_url"]
        events.append(event)
        if detail is not None or entry["tab"] == "completed" or not entry["detail_url"]:
            listing[key] = sig
    stats = {"found": len(entries), "upcoming": len(page["upcoming"]), "recent_past": recent,
             "detail_pages_read": detail_requests}
    return events, listing, stats
