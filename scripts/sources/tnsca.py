"""Source: Tamil Nadu State Chess Association (TNSCA), tamilchess.com.

The calendar page (`/tournament-registration/?y=YYYY`, the year menu the page itself offers,
2017 onwards) is plain server HTML with five tables: "All Events" and four subsets of it
("Tamilnadu State Championships", "Fide Rated Events", "International Level Event",
"National Championship"). Every row has the name (linked to the event's page), the TNSCA
event code (e.g. CO-212/CHE/25-26), the place, the start and the end (DD-Mon-YYYY).

Note: the page without `?y=` shows 2017 in its "All Events" table, so we always ask for a
year. We read this year's page; next year's page too when the page offers that year (events
are announced months ahead); last year's only in January and February, for events that
ended in the last 60 days. Upcoming events and those that ended in the last 60 days are kept.

One request per page, nothing else: no event pages, no brochures, no player lists.
Facts and links only; every piece of text goes through strip_phones().
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from eventlib import (SourceError, canonical, check_dates, clean_name, clean_text, country_for,
                      derive_tags, short_hash, strip_phones, valid_url)

NAME = "tnsca"
SITE_URL = "https://tamilchess.com/"
CALENDAR_URL = SITE_URL + "tournament-registration/"
RECENT_DAYS = 60
STATE = "Tamil Nadu"

_COLUMNS = ("name", "event code", "place", "start", "end")
_CODE = re.compile(r"^[A-Z]{1,5}-?\d{1,4}/[A-Z]{2,4}/\d{2}-\d{2}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_TABLE_KEYS = {"all events": "all", "fide rated events": "fide"}


def year_url(year: int) -> str:
    return f"{CALENDAR_URL}?y={year}"


def _text(node) -> str:
    return clean_text(_CONTROL.sub(" ", node.get_text(" ") if node is not None else ""))


def parse_date(text: str) -> date | None:
    """'01-Jan-2026' -> 2026-01-01; anything else -> None (kept as raw text, never guessed)."""
    try:
        return datetime.strptime(clean_text(text).title(), "%d-%b-%Y").date()
    except ValueError:
        return None


def _heading(table) -> str:
    heading = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
    return _text(heading).lower() if heading is not None else ""


def _rows(table, page_url: str) -> list[dict]:
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != 5:
            continue  # the header, or a month line ("January")
        link = cells[0].find("a", href=True)
        code = re.sub(r"\s+", "", _text(cells[1])).upper()
        row = {"name": _text(cells[0]), "raw_code": _text(cells[1]),
               "code": code if _CODE.match(code) else "",
               "place": _text(cells[2]), "start_text": _text(cells[3]), "end_text": _text(cells[4]),
               "detail_url": valid_url(link["href"], page_url) if link else None}
        if row["name"]:
            rows.append(row)
    return rows


def parse_calendar(html: str, page_url: str) -> dict:
    """{'all': [rows], 'fide': {row keys}, 'years': [years the page links to]}."""
    soup = BeautifulSoup(html, "html.parser")
    tables = {}
    for table in soup.find_all("table"):
        header = [_text(th).lower() for th in table.find("tr").find_all(["th", "td"])] if table.find("tr") else []
        key = _TABLE_KEYS.get(_heading(table))
        if key and tuple(header) == _COLUMNS and key not in tables:
            tables[key] = _rows(table, page_url)
    if "all" not in tables:
        raise SourceError("TNSCA calendar has no 'All Events' table with Name / Event code / Place / "
                          "Start / End; layout changed?")
    years = sorted({int(m.group(1)) for a in soup.find_all("a", href=True)
                    for m in [re.search(r"[?&]y=(\d{4})\b", a["href"])] if m})
    return {"all": tables["all"], "fide": {row_key(r) for r in tables.get("fide", [])},
            "years": years}


def row_key(row: dict) -> tuple:
    return (row["raw_code"], row["name"], row["start_text"])


def signature(row: dict, fide: bool) -> str:
    keys = ("raw_code", "name", "place", "start_text", "end_text", "detail_url")
    text = "|".join(row[k] or "" for k in keys) + f"|fide={fide}"
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def event_id(row: dict, shared_codes: frozenset = frozenset()) -> str:
    """tnsca-CO-212-CHE-25-26 from CO-212/CHE/25-26; a code two rows share gets a name hash."""
    if row["code"]:
        base = f"{NAME}-" + row["code"].replace("/", "-")
        if row["code"] in shared_codes:
            base += "-" + short_hash(clean_text(row["name"]).lower() + row["start_text"], 6)
        return base
    return f"{NAME}-" + short_hash(clean_text(row["name"]).lower() + row["start_text"])


def build_event(row: dict, fide: bool, today: date, shared_codes: frozenset = frozenset()) -> dict:
    name = clean_name(strip_phones(row["name"]))
    start, end = parse_date(row["start_text"]), parse_date(row["end_text"])
    suspect, raw_dates = check_dates(start, end, row["start_text"], row["end_text"], today)
    place = strip_phones(row["place"]).strip(" -–") or None
    tags = derive_tags(name)
    if fide:  # listed by the association under "Fide Rated Events"
        tags["fide_rated"], tags["fide_how"] = True, "stated"
    return canonical({
        "id": event_id(row, shared_codes),
        "codes": [row["code"]] if row["code"] else [],
        "name": name,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "place_text": ", ".join(p for p in (place, STATE) if p),
        "state": STATE,
        "city": place,
        "country": country_for(NAME),
        "source": NAME,
        "source_url": row["detail_url"] or CALENDAR_URL,
        "tags": tags,
        "flags": {"dates_suspect": suspect},
        "raw_dates": raw_dates,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def _keep(row: dict, today: date) -> bool:
    """Upcoming, ongoing, or ended in the last RECENT_DAYS days. Unreadable dates are kept."""
    start, end = parse_date(row["start_text"]), parse_date(row["end_text"])
    last = end or start
    return last is None or last >= today - timedelta(days=RECENT_DAYS)


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats). One request per calendar page read."""
    pages = [parse_calendar(client.get(year_url(today.year)), year_url(today.year))]
    offered = set(pages[0]["years"])
    extra = [today.year + 1]
    if (today - timedelta(days=RECENT_DAYS)).year < today.year:
        extra.append(today.year - 1)
    for year in extra:
        if year in offered:  # only a year the page itself links to
            pages.append(parse_calendar(client.get(year_url(year)), year_url(year)))

    rows, fide_keys = [], set()
    for page in pages:
        rows.extend(page["all"])
        fide_keys |= page["fide"]
    kept = [r for r in rows if _keep(r, today)]
    counts: dict[str, int] = {}
    for r in kept:
        if r["code"]:
            counts[r["code"]] = counts.get(r["code"], 0) + 1
    shared = frozenset(c for c, n in counts.items() if n > 1)

    old_events = {e["id"]: e for e in previous.get("events", [])}
    old_listing = previous.get("listing", {})
    events, listing, seen = [], {}, set()
    for r in kept:
        key = event_id(r, shared)
        if key in seen:
            continue  # the same row twice (it can sit on two year pages)
        seen.add(key)
        fide = row_key(r) in fide_keys
        sig = signature(r, fide)
        old = old_events.get(key)
        events.append(old if old is not None and old_listing.get(key) == sig
                      else build_event(r, fide, today, shared))
        listing[key] = sig
    stats = {"found": len(events), "listed_this_year": len(pages[0]["all"]),
             "pages_read": len(pages)}
    return events, listing, stats
