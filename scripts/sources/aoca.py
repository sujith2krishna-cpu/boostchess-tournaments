"""Source: All Odisha Chess Association (AOCA), odishachess.com, the state association of Odisha.

The calendar page (`/calendar/`, "Calendar" in the site menu) is one WordPress page with a tab
per season ("2026-27", "2025-26", ...). Each tab holds one table. Its columns, in the page's
own words:

    Sl | Event (State) | ORGANISER | START | END | PLACE | BROUCHER | Status

The current season's table also has four more columns on the right about the *national*
championship each state event selects players for (Event (National) | State | Date |
National Circular). Those are AICF's own events, in other states; AICF's list already has
them, so they are not read here.

- The event cell is either a full name ("1st K.C.A. International FIDE rating Open Chess
  Tournament 2026") or, for the state championships, only the section ("Under 19 (Junior)",
  "Women", "66th State Senior") followed by the AICF event code(s) in the form
  `505919/505920/OD(S)/2026`. A section alone becomes "Odisha State Under 19 (Junior) Chess
  Championship" (or "66th Odisha State Senior Chess Championship"); the codes go into `codes`
  and give the id (`aoca-505919`), so the record groups with AICF's by its code.
- Dates: "12-Nov-26", "14-April-2026", "27 Mar 2025", "22-12-2024". A two-digit year is the
  page's way of writing 2026 (20YY), not a guess. Anything else is kept and flagged.
- PLACE is the venue line; the city is its last part when that looks like a place name
  ("Puri Club, Puri" -> Puri; "BBSR" is Bhubaneswar), else nothing. It is sometimes a district
  ("Kalahandi"), so it never blocks a match with a town (dedup.DISTRICT_SOURCES).
- A row with only a section and nothing else (no organiser, no dates, no place) is a planned
  championship that is not scheduled yet: not an event yet, so it is not stored.

Kept: upcoming and ongoing events, and those that ended in the last RECENT_DAYS days (as for
TNSCA and KCA). One request per run (plus robots.txt): no event pages, no brochure files (a
brochure is a link only). Facts and links only; every piece of text goes through strip_phones().
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from eventlib import (SourceError, canonical, check_dates, clean_name, clean_text, country_for,
                      derive_tags, short_hash, strip_phones, valid_url)

NAME = "aoca"
SITE_URL = "https://odishachess.com/"
CALENDAR_URL = SITE_URL + "calendar/"
STATE = "Odisha"
RECENT_DAYS = 60

# Header cells we need, in the page's words (any case). "Event (State)" in the current
# season's table, "EVENT NAME" in the older ones.
_NAME_HEADERS = ("event (state)", "event name")
_NEEDED = {"organiser": "organiser", "start": "start", "end": "end", "place": "place",
           "status": "status"}
_BROCHURE_HEADERS = ("broucher", "brochure", "circular")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# AICF event codes as the page writes them: "505919/505920/OD(S)/2026", "487135/OD(S)/2026".
_CODES = re.compile(r"(?<![\d/])(\d{6}(?:\s*/\s*\d{6})*)\s*/\s*O[DR]\s*(?:\(\s*[A-Za-z]\s*\))?\s*/\s*"
                    r"((?:19|20)\d{2})(?![\d/])")
# A name that is only a section of the state championships ("Under 9", "Women").
_FULL_NAME_WORDS = re.compile(r"(?i)\b(?:chess|championships?|tournaments?|tmt|open|festival|"
                              r"leagues?|legue|cup|trophy|memorial|odisha)\b")
_ORDINAL = re.compile(r"^(\d{1,3}(?:st|nd|rd|th))\s+(.*)$", re.I)
_DATE = re.compile(r"^(\d{1,2})[\s\-/.]+([A-Za-z]{3,9}|\d{1,2})\.?[\s\-/.,]+(\d{2}|\d{4})$")
_MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july", "august",
                "september", "october", "november", "december")
_CANCELLED = re.compile(r"(?i)\b(?:cancel|postpone)")
_FACILITY = re.compile(
    r"(?i)\b(?:road|rd|street|hall|school|college|university|complex|auditorium|stadium|club|"
    r"academy|centre|center|hotel|campus|building|institute|resort|mandap|bhawan|bhavan|theatre|"
    r"nagar|colony|world|global|residential|indoor|station|vihar)\b")
_TOWN_SHORT = {"bbsr": "Bhubaneswar", "ctc": "Cuttack"}


def _text(node, sep: str = " ") -> str:
    return clean_text(_CONTROL.sub(" ", node.get_text(sep) if node is not None else ""))


def _month(text: str) -> int | None:
    """'11' -> 11; 'Nov', 'November', 'Sept' -> 11 / 9; anything else -> None."""
    if text.isdigit():
        return int(text) if 1 <= int(text) <= 12 else None
    text = text.lower()
    for number, month in enumerate(_MONTH_NAMES, start=1):
        if len(text) >= 3 and (month.startswith(text) or (text == "sept" and month == "september")):
            return number
    return None


def parse_date(text: str | None) -> date | None:
    """'12-Nov-26', '14-April-2026', '27 Mar 2025', '22-12-2024' -> a date; else None."""
    match = _DATE.match(clean_text(text or ""))
    if not match:
        return None
    day, month_text, year_text = match.groups()
    month = _month(month_text)
    year = int(year_text) + (2000 if len(year_text) == 2 else 0)
    try:
        return date(year, month, int(day)) if month else None
    except ValueError:
        return None


def codes_in(text: str) -> list[str]:
    """['505919', '505920'] from '... 505919/505920/OD(S)/2026'."""
    found: list[str] = []
    for match in _CODES.finditer(text or ""):
        for code in re.findall(r"\d{6}", match.group(1)):
            if code not in found:
                found.append(code)
    return found


def event_name(label: str) -> str:
    """The page's name; a section alone ("Under 19 (Junior)") gets the championship's words."""
    label = clean_name(_CODES.sub(" ", label)).strip(" -–,")
    if not label or _FULL_NAME_WORDS.search(label):
        return label
    ordinal = _ORDINAL.match(label)
    lead, rest = (ordinal.group(1) + " ", ordinal.group(2)) if ordinal else ("", label)
    rest = re.sub(r"(?i)^state\s+", "", rest)
    return f"{lead}Odisha State {rest} Chess Championship"


def city_of(place: str) -> str | None:
    """The venue line's last part when it reads like a town ("..., Rourkela"), else None."""
    parts = [p.strip(" .-–") for p in re.split(r"[,\n]+", re.sub(r"\b\d{6}\b", "", place or ""))]
    parts = [p for p in parts if p and p.lower() not in ("odisha", "orissa", "india")]
    if len(parts) < 2 and not (parts and parts[0].lower() in _TOWN_SHORT):
        return None  # a single name is a venue ("KIIT University"), not a town
    last = parts[-1]
    if last.lower() in _TOWN_SHORT:
        return _TOWN_SHORT[last.lower()]
    if len(last.split()) > 2 or any(c.isdigit() for c in last) or _FACILITY.search(last) or "(" in last:
        return None
    return last.title() if last.isupper() else last


def _header(table) -> list[str]:
    first = table.find("tr")
    return [_text(c).lower() for c in first.find_all(["th", "td"], recursive=False)] if first else []


def parse_calendar(html: str, page_url: str = CALENDAR_URL) -> list[dict]:
    """Every state-event row of every season table, as plain text and links."""
    soup = BeautifulSoup(html, "html.parser")
    rows, tables = [], 0
    for table in soup.find_all("table"):
        header = _header(table)
        name_col = next((header.index(h) for h in _NAME_HEADERS if h in header), None)
        if name_col is None or not all(h in header for h in _NEEDED.values()):
            continue
        tables += 1
        col = {key: header.index(h) for key, h in _NEEDED.items()}
        brochure_col = next((header.index(h) for h in _BROCHURE_HEADERS if h in header), None)
        width = max(col.values()) + 1
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td", recursive=False)
            if len(cells) < width or not _text(cells[0]).isdigit():
                continue  # no row number: a "Tentative" line or an empty spacer
            label = _text(cells[name_col], "\n")
            brochure = None
            if brochure_col is not None:
                link = cells[brochure_col].find("a", href=True)
                brochure = valid_url(link["href"], page_url) if link else None
            row = {"number": _text(cells[0]), "label": label,
                   **{key: _text(cells[i]) for key, i in col.items()}, "brochure_url": brochure}
            row["scheduled"] = any(row[k] for k in ("organiser", "start", "end", "place"))
            if label:
                rows.append(row)
    if not tables:
        raise SourceError("AOCA calendar page has no table with Event / ORGANISER / START / END / "
                          "PLACE columns; layout changed?")
    return rows


def event_id(row: dict, shared: frozenset = frozenset()) -> str:
    codes = codes_in(row["label"])
    if codes and codes[0] not in shared:
        return f"{NAME}-{codes[0]}"
    base = clean_text(_CODES.sub(" ", row["label"])).lower() + "|" + row["start"]
    return f"{NAME}-" + (f"{codes[0]}-" if codes else "") + short_hash(base)


def signature(row: dict) -> str:
    text = "|".join(str(row[k] or "") for k in sorted(row))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def build_event(row: dict, today: date, shared: frozenset = frozenset()) -> dict:
    name = event_name(strip_phones(row["label"]))
    start, end = parse_date(row["start"]), parse_date(row["end"])
    suspect, raw_dates = check_dates(start, end, row["start"], row["end"], today)
    place = strip_phones(row["place"]) or None
    city = city_of(place or "")
    return canonical({
        "id": event_id(row, shared),
        "codes": codes_in(row["label"]),
        "name": name,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "place_text": ", ".join(p for p in (place, STATE) if p),
        "state": STATE,
        "city": city,
        "country": country_for(NAME),
        "brochure_url": row["brochure_url"],
        "organiser": strip_phones(row["organiser"]) or None,
        "source": NAME,
        "source_url": CALENDAR_URL,  # the events have no pages of their own
        "tags": derive_tags(name),
        "flags": {"dates_suspect": suspect},
        "raw_dates": raw_dates,
        "cancelled": bool(_CANCELLED.search(row["status"])),
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def keep(row: dict, today: date) -> bool:
    """Upcoming, ongoing, or ended in the last RECENT_DAYS days. A row whose dates cannot be read
    is kept unless the page says it is completed (it is then flagged, never fixed)."""
    if not row["scheduled"]:
        return False
    start, end = parse_date(row["start"]), parse_date(row["end"])
    last = max((d for d in (start, end) if d), default=None)
    if last is None:
        return "complete" not in row["status"].lower()
    return last >= today - timedelta(days=RECENT_DAYS)


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats). One request: the calendar page.

    `found` is every state-event row on the page (all seasons), so a page that suddenly shows
    far fewer rows counts as a failed fetch, while events simply getting old does not.
    """
    rows = parse_calendar(client.get(CALENDAR_URL), CALENDAR_URL)
    kept = [r for r in rows if keep(r, today)]
    counts: dict[str, int] = {}
    for r in kept:
        for code in codes_in(r["label"])[:1]:
            counts[code] = counts.get(code, 0) + 1
    shared = frozenset(c for c, n in counts.items() if n > 1)
    events, listing = [], {}
    for r in kept:
        key = event_id(r, shared)
        if key in listing:
            continue  # the same row twice
        listing[key] = signature(r)
        events.append(build_event(r, today, shared))
    stats = {"found": len(rows), "kept": len(events),
             "not_scheduled": sum(1 for r in rows if not r["scheduled"])}
    return events, listing, stats

