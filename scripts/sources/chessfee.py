"""Source: chessfee.com, the online registration portal (ongoing and upcoming tournaments).

We read the two listing pages (and their page links). Only new events, or events
whose listing card changed, get their details page read (for the full title and the
organiser's name). We store facts and links only: no posters, no descriptions, and
never the phone numbers on the page.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from eventlib import (RequestCapReached, SourceError, aicf_codes_in, canonical, check_dates,
                      clean_name, clean_text, country_for, derive_tags, locate_text, merge_tags,
                      strip_phones, valid_url)

NAME = "chessfee"
SITE_URL = "https://www.chessfee.com/"
LISTING_PAGES = ("tournament_ongoing.php", "upcoming_tournaments.php")
MAX_PAGES_PER_LISTING = 12

_ID = re.compile(r"tmt_details\.php\?id=(\d+)")
_LISTING_DATES = re.compile(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s+to\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})")


def _long_date(text: str) -> date | None:
    try:
        return datetime.strptime(clean_text(text), "%d %B %Y").date()
    except ValueError:
        return None


def _slash_date(text: str) -> date | None:
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text or "")
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def parse_listing(html: str, page_url: str) -> tuple[list[dict], list[str]]:
    """Event cards on one listing page, and the URLs of the other pages of the same list."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for card in soup.find_all("article"):
        link = card.find("a", href=_ID)
        if link is None:
            continue
        event_id = _ID.search(link["href"]).group(1)
        category = card.select_one(".catname")
        title = card.select_one(".caption")
        calendar = card.find("i", class_=re.compile("fa-calendar"))
        date_text = clean_text(calendar.parent.get_text(" ")) if calendar else ""
        venue = ""
        for item in card.select("ul.post-tools > li"):
            if item.find("a") or item.find("i", class_=re.compile("fa-calendar")):
                continue
            venue = clean_text(item.get_text(" "))
            break
        register = next((a["href"] for a in card.find_all("a", href=True)
                         if "treg.php" in a["href"]), None)
        brochure = next((a["href"] for a in card.find_all("a", href=True)
                         if "Brochure" in a["href"] or a["href"].lower().endswith(".pdf")), None)
        entries.append({
            "id": event_id,
            "category": clean_text(category.get_text(" ")) if category else "",
            "title": clean_text(title.get_text(" ")) if title else "",
            "date_text": date_text,
            "venue": venue,
            "detail_url": urljoin(page_url, f"tmt_details.php?id={event_id}"),
            "register_url": valid_url(register, page_url) if register else None,
            "brochure_url": valid_url(brochure, page_url) if brochure else None,
        })
    base_name = page_url.split("?")[0].rsplit("/", 1)[-1]
    pages = []
    for a in soup.find_all("a", href=True):
        if a["href"].startswith(base_name + "?page="):
            url = urljoin(page_url, a["href"])
            if url not in pages:
                pages.append(url)
    return entries, pages


def parse_detail(html: str) -> dict:
    """Full title, dates, venue and organiser's name from one details page."""
    soup = BeautifulSoup(html, "html.parser")
    caption = None
    for candidate in soup.select("div.caption"):
        if "Start Date" in candidate.get_text():
            caption = candidate
            break
    if caption is None:
        raise SourceError("chessfee details page has no 'Start Date' block; layout changed?")
    paragraphs = caption.find_all("p")
    text = [clean_text(p.get_text(" ")) for p in paragraphs]
    detail = {"title": text[0] if text else "", "start_text": "", "end_text": "", "venue": "",
              "organiser": None}
    for value in text:
        if value.startswith("Start Date"):
            detail["start_text"] = value
        elif value.startswith("Close Date"):
            detail["end_text"] = value
        elif value.startswith("Venue"):
            detail["venue"] = value.split(":", 1)[-1].strip()
    for p in paragraphs:
        if p.find("i", class_=re.compile("fa-user")):
            name = strip_phones(clean_text(p.get_text(" ")))
            if name and not re.search(r"\d|@", name):
                detail["organiser"] = name
            break
    return detail


def listing_signature(entry: dict) -> str:
    keys = ("category", "title", "date_text", "venue", "register_url", "brochure_url")
    return hashlib.sha1("|".join(entry[k] or "" for k in keys).encode("utf-8")).hexdigest()[:12]


def build_event(entry: dict, detail: dict | None, today: date) -> dict:
    title = clean_name(strip_phones((detail or {}).get("title") or entry["title"]))
    venue = strip_phones((detail or {}).get("venue") or entry["venue"])
    start = end = None
    raw_start = raw_end = ""
    if detail:
        raw_start, raw_end = detail["start_text"], detail["end_text"]
        start, end = _slash_date(raw_start), _slash_date(raw_end)
    else:
        match = _LISTING_DATES.search(entry["date_text"])
        if match:
            raw_start, raw_end = match.groups()
            start, end = _long_date(raw_start), _long_date(raw_end)
        else:
            raw_start = entry["date_text"]
    if end is None and start is not None and not raw_end:
        end = start
    suspect, raw_dates = check_dates(start, end, raw_start, raw_end, today)
    where = locate_text(venue, title)
    label = strip_phones(entry["category"])
    tags = merge_tags(derive_tags(title), derive_tags(label))
    tags["categories"] = [label] if label else []
    return canonical({
        "id": f"{NAME}-{entry['id']}",
        "codes": aicf_codes_in(title),
        "name": title,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "place_text": where["place_text"],
        "state": where["state"],
        "city": where["city"],
        "country": country_for(NAME),
        "brochure_url": entry["brochure_url"],
        "source": NAME,
        "source_url": entry["detail_url"],
        "register_url": entry["register_url"],
        "organiser": (detail or {}).get("organiser"),
        "tags": tags,
        "flags": {"dates_suspect": suspect},
        "raw_dates": raw_dates,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def _truncated(name: str) -> bool:
    return name.rstrip().endswith(("...", "…"))


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats). Details are read only when needed."""
    entries: dict[str, dict] = {}
    for page in LISTING_PAGES:
        queue = [urljoin(SITE_URL, page)]
        seen = set(queue)
        while queue and len(seen) <= MAX_PAGES_PER_LISTING:
            url = queue.pop(0)
            found, pages = parse_listing(client.get(url), url)
            for entry in found:
                entries.setdefault(entry["id"], entry)
            for other in pages:
                if other not in seen and len(seen) <= MAX_PAGES_PER_LISTING:
                    seen.add(other)
                    queue.append(other)
    old_events = {e["id"]: e for e in previous.get("events", [])}
    old_listing = previous.get("listing", {})
    events, listing = [], {}
    can_fetch, detail_requests = True, 0
    for entry in entries.values():
        event_id = f"{NAME}-{entry['id']}"
        signature = listing_signature(entry)
        old = old_events.get(event_id)
        unchanged = (old is not None and old_listing.get(entry["detail_url"]) == signature
                     and not _truncated(old["name"]))
        if unchanged:
            events.append(old)
            listing[entry["detail_url"]] = signature
            continue
        detail = None
        if can_fetch:
            try:
                detail = parse_detail(client.get(entry["detail_url"]))
                detail_requests += 1
            except RequestCapReached:
                can_fetch = False
            except SourceError:
                detail = None  # keep the listing's own (shorter) data; try again next run
        events.append(build_event(entry, detail, today))
        if detail is not None:
            listing[entry["detail_url"]] = signature
    return events, listing, {"found": len(entries), "detail_pages_read": detail_requests}
