#!/usr/bin/env python3
"""Build data/events.json and data/meta.json from the AICF "All Events" page.

Run from the repository root:

    python scripts/build_events.py

What it does, in short:
  1. reads the manual files (data/manual/events.csv and overrides.csv) and stops
     with a plain-words message if a row has a mistake;
  2. fetches https://aicf.in/all-events/ once (single retry) and parses the table;
  3. refuses to continue if the page looks wrong (too few rows), leaving the
     existing data untouched;
  4. merges with the previous data/events.json so events are never deleted;
  5. applies overrides and writes events.json + meta.json.

Only `requests` and `beautifulsoup4` are used besides the standard library.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://aicf.in/all-events/"
USER_AGENT = (
    "BoostchessBot (+https://github.com/sujith2krishna-cpu/boostchess-tournaments)"
)
REQUEST_TIMEOUT_SECONDS = 30
RETRY_WAIT_SECONDS = 5
MIN_ROWS = 100  # a page with fewer rows is treated as a broken fetch
MIN_FRACTION_OF_PREVIOUS = 0.5  # ... and so is one with under half of last time
MAX_SUSPECT_FRACTION = 0.5  # more bad dates than this means the layout changed
SCHEMA_VERSION = 1

# India has no daylight saving, so a fixed offset is exactly Asia/Kolkata and
# needs no extra package (zoneinfo needs tzdata on Windows).
IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

EVENTS_CSV_COLUMNS = (
    "id", "name", "start_date", "end_date", "place", "state", "link",
    "brochure_url", "format", "age", "note",
)
OVERRIDES_CSV_COLUMNS = (
    "key", "start_date", "end_date", "place", "state", "hide", "cancelled", "note",
)
FORMAT_ORDER = ("classical", "rapid", "blitz")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class BuildError(Exception):
    """Something went wrong; nothing has been written."""

    exit_code = 1


class SourceError(BuildError):
    """The AICF page could not be fetched or looks wrong."""

    exit_code = 2


class DataFileError(BuildError):
    """A mistake in one of the hand-edited files in data/manual/."""

    exit_code = 3


# --------------------------------------------------------------------------
# Small text helpers
# --------------------------------------------------------------------------
def clean_text(text) -> str:
    text = (text or "").replace("\xa0", " ").replace("​", "")
    return re.sub(r"\s+", " ", text).strip()


def clean_name(text) -> str:
    text = clean_text(text)
    # A lone replacement character between spaces is a broken dash on the page.
    return re.sub(r"(?<= )�(?= )", "–", text)


def normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def short_hash(text: str, length: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def today_in_india(now: datetime | None = None) -> date:
    now = now or datetime.now(IST)
    return now.astimezone(IST).date()


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------
_DMY = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")
_YMD = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


def parse_date(text, allow_iso: bool = False) -> date | None:
    """DD-MM-YYYY (and YYYY-MM-DD when allowed). None if it is not a real date."""
    text = clean_text(text)
    match = _DMY.match(text)
    if match:
        day, month, year = (int(g) for g in match.groups())
    elif allow_iso and (match := _YMD.match(text)):
        year, month, day = (int(g) for g in match.groups())
    else:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _from_iso(text) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def status(event: dict, today: date) -> str:
    """'upcoming', 'ongoing' or 'past' for an event, judged on `today` (India).

    A missing or unusable end date counts as a one-day event (end = start).
    Returns 'unknown' when there is no usable date at all.
    """
    start = _from_iso(event.get("start"))
    end = _from_iso(event.get("end"))
    if start is None:
        # Only an end date is known: we can say "past", but not more.
        if end is not None and today > end:
            return "past"
        return "unknown"
    if end is None or end < start:
        end = start
    if today < start:
        return "upcoming"
    if today <= end:
        return "ongoing"
    return "past"


# --------------------------------------------------------------------------
# States, cities, places
# --------------------------------------------------------------------------
STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # union territories
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
)


def _key(text: str) -> str:
    text = text.lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", text)).strip()


_STATE_BY_KEY = {_key(s): s for s in STATES}
_STATE_BY_KEY.update({
    "mp": "Madhya Pradesh", "up": "Uttar Pradesh", "wb": "West Bengal",
    "tn": "Tamil Nadu", "ap": "Andhra Pradesh", "hp": "Himachal Pradesh",
    "tamilnadu": "Tamil Nadu", "orissa": "Odisha", "pondicherry": "Puducherry",
    "chattisgarh": "Chhattisgarh", "chhatisgarh": "Chhattisgarh",
    "uttaranchal": "Uttarakhand", "new delhi": "Delhi", "nct of delhi": "Delhi",
    "jammu": "Jammu and Kashmir", "kashmir": "Jammu and Kashmir",
    "jammu kashmir": "Jammu and Kashmir", "j and k": "Jammu and Kashmir",
    "jk": "Jammu and Kashmir", "andaman and nicobar": "Andaman and Nicobar Islands",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
})

# Only cities that sit in exactly one state. Anything doubtful (Bilaspur,
# Aurangabad, Udaipur, ...) is left out so the state stays null.
_CITY_TO_STATE = {
    "Tamil Nadu": "chennai, coimbatore, madurai, tiruchirappalli, trichy, salem, "
                  "tirunelveli, vellore, erode, tiruppur, tirupur, thanjavur, nagercoil, "
                  "kanyakumari, cuddalore, chengalpattu, thiruvarur",
    "Maharashtra": "mumbai, navi mumbai, pune, nagpur, nashik, thane",
    "Karnataka": "bengaluru, bangalore, mysuru, mysore, mangalore, mangaluru, belagavi",
    "Telangana": "hyderabad, secunderabad",
    "West Bengal": "kolkata, siliguri",
    "Gujarat": "ahmedabad, surat, vadodara",
    "Madhya Pradesh": "bhopal, indore, jabalpur, burhanpur",
    "Chhattisgarh": "raipur",
    "Andhra Pradesh": "visakhapatnam, vijayawada",
    "Uttarakhand": "dehradun",
    "Uttar Pradesh": "lucknow",
    "Rajasthan": "jaipur",
    "Bihar": "patna",
    "Kerala": "kochi, thiruvananthapuram",
    "Odisha": "bhubaneswar",
    "Jharkhand": "ranchi",
    "Assam": "guwahati",
}
_CITY_BY_KEY = {
    _key(city): state
    for state, cities in _CITY_TO_STATE.items()
    for city in cities.split(",")
}


def lookup_state(text: str) -> str | None:
    return _STATE_BY_KEY.get(_key(text))


def parse_place(raw) -> dict:
    """Split a raw place into place_text, city and state (best effort, else null)."""
    parts = [p for p in (clean_text(x).strip(" .") for x in re.split(r"[\n,]+", raw or "")) if p]
    place_text = ", ".join(parts) or None
    state = None
    state_index = None
    for index in range(len(parts) - 1, -1, -1):
        found = lookup_state(parts[index])
        if found:
            state, state_index = found, index
            break
    if state is None:
        for part in reversed(parts):
            found = _CITY_BY_KEY.get(_key(part))
            if found:
                state = found
                break
    city_parts = [p for i, p in enumerate(parts) if i != state_index]
    return {"place_text": place_text, "city": city_parts[0] if city_parts else None,
            "state": state}


# --------------------------------------------------------------------------
# Event codes, brochure links, tags
# --------------------------------------------------------------------------
def parse_codes(text) -> tuple[list[str], dict]:
    """6-digit codes from the code cell. '472175/76' means 472175 and 472176."""
    codes: list[str] = []
    expanded = unclear = False
    for token in re.findall(r"\d+", text or ""):
        if len(token) == 6:
            code = token
        elif len(token) < 6 and codes:
            code = codes[0][: 6 - len(token)] + token
            expanded = True
        else:
            unclear = True
            continue
        if code not in codes:
            codes.append(code)
    return codes, {"code_expanded": expanded, "code_unclear": unclear}


def valid_url(href) -> str | None:
    """An absolute http(s) URL with a real-looking host, else None."""
    href = clean_text(href).replace(" ", "%20")
    if not href or href.startswith("#"):
        return None
    absolute = urljoin(SOURCE_URL, href)
    parsed = urlparse(absolute)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or "." not in host:
        return None
    if host.replace(".", "").isdigit():
        return None
    return absolute


_AGE = re.compile(r"(?<![A-Za-z])(?:under|u)[\s\-–—.]*(\d{1,2})(?!\d)", re.I)
_AGE_MORE = re.compile(r"\s*(?:&|and|,|/)\s*(?:under|u)?[\s\-–]*\d{1,2}(?!\d)", re.I)


def age_from_text(text: str) -> str | None:
    """'U11' from 'Under-11' / 'U-11' / 'U11' / 'Under 11'; None if absent or mixed."""
    ages = set()
    for match in _AGE.finditer(text):
        value = int(match.group(1))
        if not 4 <= value <= 25:
            continue
        if _AGE_MORE.match(text, match.end()):
            return None  # "Under 12 & 18": several age groups, so we do not pick one
        ages.add(f"U{value}")
    return ages.pop() if len(ages) == 1 else None


def derive_tags(name: str) -> dict:
    """Conservative tags from the name. Anything unsure stays empty."""
    formats = [f for f in FORMAT_ORDER if re.search(rf"\b{f}\b", name, re.I)]
    fide = bool(re.search(r"\bfide\b", name, re.I)) and bool(
        re.search(r"\b(?:rated|rating|ratings)\b", name, re.I)
    ) and not re.search(r"\b(?:un|non)[\s-]?rated\b", name, re.I)
    return {
        "formats": formats,
        "fide_rated": True if fide else None,
        "age": age_from_text(name),
        "open": True if re.search(r"\bopen\b", name, re.I) else None,
        "girls": True if re.search(r"\bgirls?\b", name, re.I) else None,
    }


# --------------------------------------------------------------------------
# Event records
# --------------------------------------------------------------------------
EVENT_KEYS = (
    "id", "codes", "name", "start", "end", "place_text", "state", "city",
    "brochure_url", "source", "register_url", "organiser", "tags", "flags",
    "raw_dates", "first_seen", "last_seen", "gone_from_source", "cancelled",
    "hidden", "note", "overridden",
)
TAG_DEFAULTS = (("formats", []), ("fide_rated", None), ("age", None),
                ("open", None), ("girls", None))
FLAG_DEFAULTS = (("dates_suspect", False), ("code_expanded", False),
                 ("code_unclear", False))
EVENT_DEFAULTS = {
    "codes": [], "start": None, "end": None, "place_text": None, "state": None,
    "city": None, "brochure_url": None, "register_url": None, "organiser": None,
    "raw_dates": None, "gone_from_source": False, "cancelled": False,
    "hidden": False, "note": None, "overridden": None,
}
OVERRIDABLE_FIELDS = ("start", "end", "place_text", "state", "city")


def canonical(event: dict) -> dict:
    """The event with keys in the one fixed order (and defaults filled in)."""
    tags_in = event.get("tags") or {}
    flags_in = event.get("flags") or {}
    out = {}
    for key in EVENT_KEYS:
        if key == "tags":
            out[key] = {k: copy.deepcopy(tags_in.get(k, d)) for k, d in TAG_DEFAULTS}
        elif key == "flags":
            out[key] = {k: bool(flags_in.get(k, d)) for k, d in FLAG_DEFAULTS}
        elif key in event:
            out[key] = copy.deepcopy(event[key])
        else:
            out[key] = copy.deepcopy(EVENT_DEFAULTS[key])
    return out


def sort_key(event: dict):
    start = event.get("start") or event.get("end") or "9999-12-31"
    return (start, event.get("end") or start, event["id"])


# --------------------------------------------------------------------------
# Fetching and parsing the AICF page
# --------------------------------------------------------------------------
def fetch_html(url: str = SOURCE_URL) -> str:
    """One polite request, one retry on a network error or a 5xx answer."""
    last_problem = "unknown problem"
    for attempt in (1, 2):
        try:
            response = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            last_problem = f"network problem: {exc}"
        else:
            if response.status_code == 200:
                return response.content.decode("utf-8", errors="replace")
            last_problem = f"the server answered HTTP {response.status_code}"
            if response.status_code < 500:
                break  # a 4xx will not get better by asking again
        if attempt == 1:
            time.sleep(RETRY_WAIT_SECONDS)
    raise SourceError(f"Could not fetch {url}: {last_problem}.")


EXPECTED_HEADERS = ("name of tournament", "event code", "start date", "end date",
                    "place", "brochure")


def parse_html(html: str) -> tuple[list[dict], int]:
    """Raw rows from the events table, plus the number of rows we had to skip."""
    soup = BeautifulSoup(html, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        first = candidate.find("tr")
        if first and [clean_text(c.get_text()).lower()
                      for c in first.find_all(["th", "td"])][:6] == list(EXPECTED_HEADERS):
            table = candidate
            break
    if table is None:
        raise SourceError(
            "The events table was not found on the AICF page (expected the columns "
            + ", ".join(EXPECTED_HEADERS) + "). The page layout may have changed."
        )
    rows, skipped = [], 0
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if cells and all(c.name == "th" for c in cells):
            continue  # header row
        if not any(clean_text(c.get_text()) for c in cells):
            continue  # blank row
        if len(cells) < len(EXPECTED_HEADERS):
            skipped += 1
            continue
        name = clean_name(cells[0].get_text(" "))
        if not name:
            skipped += 1
            continue
        rows.append({
            "name": name,
            "code": cells[1].get_text(" "),
            "start": cells[2].get_text(" "),
            "end": cells[3].get_text(" "),
            "place": cells[4].get_text("\n"),
            "hrefs": [a.get("href", "") for a in cells[5].find_all("a")],
        })
    return rows, skipped


def event_from_row(row: dict, today: date) -> dict:
    """Turn one raw AICF row into a normalised event. Bad dates are kept, flagged."""
    name = row["name"]
    codes, code_flags = parse_codes(row["code"])
    raw_start, raw_end = clean_text(row["start"]), clean_text(row["end"])
    start, end = parse_date(raw_start), parse_date(raw_end)
    suspect = start is None or end is None or end < start
    for value in (start, end):
        if value is not None and not today.year - 2 <= value.year <= today.year + 3:
            suspect = True  # a valid date, but a year that is surely a typo
    if codes:
        event_id = f"aicf-{codes[0]}"
    else:
        event_id = "aicf-" + short_hash(f"{normalise_name(name)}|{_iso(start) or raw_start}")
    place = parse_place(row["place"])
    brochure = next((u for u in (valid_url(h) for h in row["hrefs"]) if u), None)
    return canonical({
        "id": event_id,
        "codes": codes,
        "name": name,
        "start": _iso(start),
        "end": _iso(end),
        "place_text": place["place_text"],
        "state": place["state"],
        "city": place["city"],
        "brochure_url": brochure,
        "source": "aicf",
        "tags": derive_tags(name),
        "flags": {"dates_suspect": suspect, **code_flags},
        "raw_dates": {"start": raw_start, "end": raw_end} if suspect else None,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def events_from_rows(rows: list[dict], today: date) -> tuple[list[dict], int]:
    """Normalise rows, collapse exact duplicate rows and give every event a unique id."""
    events = [event_from_row(r, today) for r in rows]
    kept: dict[tuple, dict] = {}
    duplicates = 0
    for event in events:
        signature = (event["id"], normalise_name(event["name"]), event["start"], event["end"],
                     (event["raw_dates"] or {}).get("start"), (event["raw_dates"] or {}).get("end"),
                     event["place_text"])
        if signature in kept:
            duplicates += 1
            if not kept[signature]["brochure_url"]:
                kept[signature]["brochure_url"] = event["brochure_url"]
        else:
            kept[signature] = event
    unique = list(kept.values())
    # Different events that share a code (it happens): the first, by date, keeps
    # the plain id; the others get a short suffix made from their name.
    groups = defaultdict(list)
    for event in unique:
        groups[event["id"]].append(event)
    used = {i for i, group in groups.items() if len(group) == 1}
    for event_id, group in groups.items():
        if len(group) == 1:
            continue
        group.sort(key=lambda e: (e["start"] or "9999", normalise_name(e["name"]), e["end"] or ""))
        used.add(event_id)
        for event in group[1:]:
            number = 0
            candidate = f"{event_id}-{short_hash(normalise_name(event['name']), 6)}"
            while candidate in used:
                number += 1
                candidate = f"{event_id}-{short_hash(normalise_name(event['name']) + str(number), 6)}"
            event["id"] = candidate
            used.add(candidate)
    return unique, duplicates


def check_page_is_sane(row_count: int, skipped: int, events: list[dict],
                       previous_count: int, min_rows: int) -> None:
    """Never trust the layout silently: stop before anything is written."""
    if row_count < min_rows:
        raise SourceError(
            f"The AICF page gave only {row_count} event rows (at least {min_rows} expected). "
            "The page may be broken or its layout changed. Existing data left untouched."
        )
    if previous_count and row_count < previous_count * MIN_FRACTION_OF_PREVIOUS:
        raise SourceError(
            f"The AICF page gave {row_count} event rows, fewer than half of the "
            f"{previous_count} from the previous run. Existing data left untouched."
        )
    if skipped > max(5, row_count * 0.05):
        raise SourceError(
            f"{skipped} rows of the AICF page could not be read (only {row_count} were). "
            "The page layout may have changed. Existing data left untouched."
        )
    suspect = sum(1 for e in events if e["flags"]["dates_suspect"])
    if len(events) >= 20 and suspect > len(events) * MAX_SUSPECT_FRACTION:
        raise SourceError(
            f"{suspect} of {len(events)} rows have unreadable dates, so the date format "
            "probably changed. Existing data left untouched."
        )


# --------------------------------------------------------------------------
# History: previous events.json
# --------------------------------------------------------------------------
def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError(
            f"{path.name} exists but cannot be read ({exc}). Not overwriting it; "
            "fix or restore the file first."
        )


def restore_base(event: dict) -> dict:
    """Undo overrides on a stored event, giving the values AICF itself reported."""
    event = canonical(event)
    for field, original in (event["overridden"] or {}).items():
        if field in OVERRIDABLE_FIELDS:
            event[field] = original
    event["hidden"] = False
    event["cancelled"] = False
    event["note"] = None
    event["flags"]["dates_suspect"] = event["raw_dates"] is not None
    event["overridden"] = None
    return event


def merge_history(scraped: list[dict], previous: list[dict], today: date) -> list[dict]:
    """Keep every AICF event ever seen. New AICF values win; vanished ones are kept."""
    previous_aicf = {e["id"]: e for e in previous if e.get("source") == "aicf"}
    merged = []
    seen_ids = set()
    for event in scraped:
        old = previous_aicf.get(event["id"])
        if old and old.get("first_seen"):
            event["first_seen"] = old["first_seen"]
        event["last_seen"] = today.isoformat()
        event["gone_from_source"] = False
        seen_ids.add(event["id"])
        merged.append(event)
    for event_id, old in previous_aicf.items():
        if event_id not in seen_ids:
            kept = restore_base(old)
            kept["gone_from_source"] = True  # last_seen stays as it was
            merged.append(kept)
    return merged


# --------------------------------------------------------------------------
# Manual CSV files
# --------------------------------------------------------------------------
def read_csv_file(path: Path, rel: str, allowed: tuple, required: tuple,
                  errors: list[str], warnings: list[str]) -> list[tuple[int, dict]]:
    """Rows as (line number, {column: text}). Problems are appended to `errors`."""
    if not path.exists():
        warnings.append(f"{rel} not found; treated as empty.")
        return []
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        errors.append(f"{rel} line 1: the file is not UTF-8 text. In Excel use "
                      "'Save as' > 'CSV UTF-8'; on GitHub just edit it in the browser.")
        return []
    reader = csv.reader(io.StringIO(text, newline=""))
    header = None
    rows: list[tuple[int, dict]] = []
    while True:
        start_line = reader.line_num + 1
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            errors.append(f"{rel} line {start_line}: the row cannot be read ({exc}). "
                          "Check for a missing closing quote.")
            break
        if header is None:
            header = [re.sub(r"\s+", "_", c.strip().lower()) for c in cells]
            bad = [h for h in header if h not in allowed]
            missing = [c for c in required if c not in header]
            if bad:
                errors.append(f"{rel} line {start_line}: unknown column name(s): "
                              f"{', '.join(repr(h) for h in bad)}. Allowed: {', '.join(allowed)}.")
            if missing:
                errors.append(f"{rel} line {start_line}: the header row is missing the "
                              f"column(s): {', '.join(missing)}.")
            if bad or missing:
                return []
            continue
        if not any(c.strip() for c in cells):
            continue
        if len(cells) > len(header) and any(c.strip() for c in cells[len(header):]):
            errors.append(f"{rel} line {start_line}: the row has more values than the header "
                          f"has columns ({len(cells)} vs {len(header)}). If a value contains "
                          "a comma, put the value in double quotes.")
            continue
        row = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(header)}
        rows.append((start_line, row))
    if header is None:
        errors.append(f"{rel} line 1: the file is empty; it needs the header row "
                      f"({','.join(allowed)}).")
    return rows


def _date_problem(text: str, what: str) -> str:
    return (f"{what} '{text}' is not a date. Write it as DD-MM-YYYY (like 25-12-2026) "
            "or YYYY-MM-DD.")


def event_from_manual_row(line: int, row: dict, rel: str, today: date,
                          errors: list[str]) -> dict | None:
    problems: list[str] = []
    name = clean_name(row.get("name", ""))
    if not name:
        problems.append("the name is empty.")
    start = end = None
    if not row.get("start_date"):
        problems.append("start_date is empty.")
    else:
        start = parse_date(row["start_date"], allow_iso=True)
        if start is None:
            problems.append(_date_problem(row["start_date"], "start_date"))
    if row.get("end_date"):
        end = parse_date(row["end_date"], allow_iso=True)
        if end is None:
            problems.append(_date_problem(row["end_date"], "end_date"))
    elif start is not None:
        end = start  # no end date means a one-day event
    if start and end and end < start:
        problems.append(f"end_date {end.isoformat()} is before start_date {start.isoformat()}.")
    event_id = row.get("id", "").strip()
    if event_id:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", event_id):
            problems.append(f"id '{event_id}' may only use letters, digits, dash, "
                            "underscore and dot, without spaces.")
        elif event_id.lower().startswith("aicf-"):
            problems.append(f"id '{event_id}' starts with 'aicf-', which is reserved for AICF events.")
    elif name and start:
        event_id = "manual-" + short_hash(f"{normalise_name(name)}|{start.isoformat()}")
    state = None
    place = parse_place(row.get("place", ""))
    if row.get("state"):
        state = lookup_state(row["state"])
        if state is None:
            problems.append(f"state '{row['state']}' is not an Indian state or union territory I "
                            "know. Check the spelling (for example 'Tamil Nadu').")
    else:
        state = place["state"]
    tags = derive_tags(name)
    if row.get("format"):
        wanted = [t for t in re.split(r"[\s/,;&+]+", row["format"].lower()) if t]
        unknown = [t for t in wanted if t not in FORMAT_ORDER]
        if unknown:
            problems.append(f"format '{row['format']}' is not understood. Use rapid, blitz "
                            "and/or classical.")
        tags["formats"] = [f for f in FORMAT_ORDER if f in wanted or f in tags["formats"]]
    if row.get("age"):
        age = age_from_text(row["age"]) if not re.fullmatch(r"\d+", row["age"]) else None
        if age is None:
            problems.append(f"age '{row['age']}' is not understood. Write it like U11 or Under-11.")
        else:
            tags["age"] = age
    urls = {}
    for column, field in (("link", "register_url"), ("brochure_url", "brochure_url")):
        if row.get(column):
            url = valid_url(row[column])
            if url is None or not re.match(r"https?://", row[column].strip(), re.I):
                problems.append(f"{column} '{row[column]}' is not a full web address "
                                "(it must start with http:// or https://).")
            else:
                urls[field] = url
    if problems:
        errors.extend(f"{rel} line {line}: {p}" for p in problems)
        return None
    return canonical({
        "id": event_id,
        "codes": [],
        "name": name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "place_text": place["place_text"],
        "state": state,
        "city": place["city"],
        "brochure_url": urls.get("brochure_url"),
        "source": "manual",
        "register_url": urls.get("register_url"),
        "tags": tags,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
        "note": row.get("note") or None,
    })


def load_manual_events(data_dir: Path, today: date, errors: list[str],
                       warnings: list[str]) -> list[dict]:
    rel = "data/manual/events.csv"
    rows = read_csv_file(data_dir / "manual" / "events.csv", rel, EVENTS_CSV_COLUMNS,
                         ("name", "start_date"), errors, warnings)
    events, line_of = [], {}
    for line, row in rows:
        event = event_from_manual_row(line, row, rel, today, errors)
        if event is None:
            continue
        if event["id"] in line_of:
            errors.append(f"{rel} line {line}: id '{event['id']}' is already used on line "
                          f"{line_of[event['id']]}. Every event needs its own id.")
            continue
        line_of[event["id"]] = line
        events.append(event)
    return events


def _yes(value: str, column: str, line: int, rel: str, errors: list[str]) -> bool:
    value = value.strip().lower()
    if value in ("", "no", "n", "false", "0"):
        return False
    if value in ("yes", "y", "true", "1"):
        return True
    errors.append(f"{rel} line {line}: {column} must be 'yes' or empty, not '{value}'.")
    return False


def load_overrides(data_dir: Path, errors: list[str], warnings: list[str]) -> list[dict]:
    rel = "data/manual/overrides.csv"
    rows = read_csv_file(data_dir / "manual" / "overrides.csv", rel, OVERRIDES_CSV_COLUMNS,
                         ("key",), errors, warnings)
    overrides = []
    for line, row in rows:
        item = {"line": line, "key": row.get("key", "").strip()}
        if not item["key"]:
            errors.append(f"{rel} line {line}: key is empty. Put the event id or the 6-digit "
                          "AICF code there.")
            continue
        for column in ("start_date", "end_date"):
            item[column] = None
            if row.get(column):
                item[column] = parse_date(row[column], allow_iso=True)
                if item[column] is None:
                    errors.append(f"{rel} line {line}: " + _date_problem(row[column], column))
        item["place"] = row.get("place") or None
        item["state"] = None
        if row.get("state"):
            item["state"] = lookup_state(row["state"])
            if item["state"] is None:
                errors.append(f"{rel} line {line}: state '{row['state']}' is not an Indian state "
                              "or union territory I know. Check the spelling.")
        item["hide"] = _yes(row.get("hide", ""), "hide", line, rel, errors)
        item["cancelled"] = _yes(row.get("cancelled", ""), "cancelled", line, rel, errors)
        item["note"] = row.get("note") or None
        overrides.append(item)
    return overrides


def apply_overrides(events: list[dict], overrides: list[dict], errors: list[str],
                    warnings: list[str]) -> None:
    """Override > manual > scraped. Changes `events` in place."""
    rel = "data/manual/overrides.csv"
    by_id = {e["id"]: e for e in events}
    by_code = defaultdict(list)
    for event in events:
        for code in event["codes"]:
            by_code[code].append(event)

    def change(event: dict, field: str, value) -> None:
        if event[field] != value:
            if event["overridden"] is None:
                event["overridden"] = {}
            event["overridden"].setdefault(field, event[field])
            event[field] = value

    for item in overrides:
        key = item["key"]
        targets = [by_id[key]] if key in by_id else list(by_code.get(key, []))
        if not targets:
            warnings.append(f"{rel} line {item['line']}: no event has the id or code '{key}'; "
                            "this row was ignored.")
            continue
        if len(targets) > 1:
            warnings.append(f"{rel} line {item['line']}: the code '{key}' belongs to "
                            f"{len(targets)} events, so the row was applied to all of them. "
                            "Use the event id to pick one.")
        for event in targets:
            if item["start_date"] or item["end_date"]:
                new_start = item["start_date"].isoformat() if item["start_date"] else event["start"]
                new_end = item["end_date"].isoformat() if item["end_date"] else event["end"]
                if new_start and new_end and new_end < new_start:
                    errors.append(f"{rel} line {item['line']}: these dates would put the end "
                                  f"({new_end}) before the start ({new_start}) for event "
                                  f"'{event['id']}'.")
                    continue
                change(event, "start", new_start)
                change(event, "end", new_end)
                event["flags"]["dates_suspect"] = not (
                    event["start"] and event["end"] and event["end"] >= event["start"]
                )
            if item["place"]:
                place = parse_place(item["place"])
                change(event, "place_text", place["place_text"])
                change(event, "city", place["city"])
                change(event, "state", item["state"] or place["state"])
            elif item["state"]:
                change(event, "state", item["state"])
            if item["hide"]:
                event["hidden"] = True
            if item["cancelled"]:
                event["cancelled"] = True
            if item["note"]:
                event["note"] = item["note"]


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def dump_json(obj) -> bytes:
    """Same data always gives the same bytes: fixed key order, 2 spaces, UTF-8, LF."""
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_files(data_dir: Path, payloads: dict[str, bytes]) -> None:
    """Write every file to a temporary name first, then swap them in."""
    data_dir.mkdir(parents=True, exist_ok=True)
    temporary = {}
    try:
        for name, payload in payloads.items():
            tmp = data_dir / f".{name}.tmp"
            tmp.write_bytes(payload)
            temporary[name] = tmp
        for name, tmp in temporary.items():
            os.replace(tmp, data_dir / name)
    finally:
        for tmp in temporary.values():
            if tmp.exists():
                tmp.unlink()


# --------------------------------------------------------------------------
# The whole run
# --------------------------------------------------------------------------
def run(data_dir=DATA_DIR, *, html: str | None = None, fetch=fetch_html,
        now: datetime | None = None, min_rows: int = MIN_ROWS) -> dict:
    """Do a full build. Returns a report; raises BuildError (and writes nothing) on trouble."""
    data_dir = Path(data_dir)
    now = (now or datetime.now(IST)).astimezone(IST).replace(microsecond=0)
    today = now.date()
    warnings: list[str] = []

    previous_doc = load_json(data_dir / "events.json") or {}
    previous_meta = load_json(data_dir / "meta.json") or {}
    previous_events = previous_doc.get("events", [])
    previous_count = previous_meta.get("scraped_count")
    if previous_count is None:
        previous_count = sum(1 for e in previous_events
                             if e.get("source") == "aicf" and not e.get("gone_from_source"))

    # Hand-edited files first: a typo there should stop us before we fetch anything.
    errors: list[str] = []
    manual_events = load_manual_events(data_dir, today, errors, warnings)
    overrides = load_overrides(data_dir, errors, warnings)
    if errors:
        raise DataFileError("Nothing was written. Please fix:\n  " + "\n  ".join(errors))

    page = html if html is not None else fetch()
    rows, skipped = parse_html(page)
    scraped, duplicates = events_from_rows(rows, today)
    check_page_is_sane(len(rows), skipped, scraped, previous_count, min_rows)

    events = merge_history(scraped, previous_events, today)
    previous_manual = {e["id"]: e for e in previous_events if e.get("source") == "manual"}
    for event in manual_events:
        old = previous_manual.get(event["id"])
        if old and old.get("first_seen"):
            event["first_seen"] = old["first_seen"]
    events.extend(manual_events)

    apply_overrides(events, overrides, errors, warnings)
    if errors:
        raise DataFileError("Nothing was written. Please fix:\n  " + "\n  ".join(errors))

    events = sorted((canonical(e) for e in events), key=sort_key)
    generated_at = now.isoformat()
    meta = {
        "generated_at": generated_at,
        "scraped_count": sum(1 for e in events if e["source"] == "aicf" and not e["gone_from_source"]),
        "manual_count": sum(1 for e in events if e["source"] == "manual"),
        "total": len(events),
        "suspect_dates_count": sum(1 for e in events if e["flags"]["dates_suspect"]),
        "missing_state_count": sum(1 for e in events if e["state"] is None),
        "gone_from_source_count": sum(1 for e in events if e["gone_from_source"]),
    }
    document = {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "events": events}
    write_files(data_dir, {"events.json": dump_json(document), "meta.json": dump_json(meta)})

    visible = [e for e in events if not e["hidden"]]
    return {
        "meta": meta,
        "today": today.isoformat(),
        "rows_on_page": len(rows),
        "rows_skipped": skipped,
        "duplicate_rows_collapsed": duplicates,
        "new_events": sum(1 for e in events if e["first_seen"] == today.isoformat()
                          and e["source"] == "aicf"),
        "status_counts": dict(Counter(status(e, today) for e in visible)),
        "hidden_count": len(events) - len(visible),
        "cancelled_count": sum(1 for e in events if e["cancelled"]),
        "missing_brochure_count": sum(1 for e in events if e["brochure_url"] is None),
        "warnings": warnings,
        "events": events,
    }


def print_summary(report: dict) -> None:
    meta = report["meta"]
    counts = report["status_counts"]
    print(f"Done. Today in India: {report['today']}")
    print(f"  Rows on the AICF page : {report['rows_on_page']} "
          f"({report['duplicate_rows_collapsed']} exact duplicate rows collapsed, "
          f"{report['rows_skipped']} unreadable rows skipped)")
    print(f"  New events this run   : {report['new_events']}")
    print(f"  Total events          : {meta['total']} "
          f"(AICF {meta['scraped_count']}, manual {meta['manual_count']}, "
          f"gone from source {meta['gone_from_source_count']})")
    print(f"  Suspect dates         : {meta['suspect_dates_count']}")
    print(f"  Missing state         : {meta['missing_state_count']}")
    print(f"  Missing brochure      : {report['missing_brochure_count']}")
    print(f"  Hidden / cancelled    : {report['hidden_count']} / {report['cancelled_count']}")
    print("  By status (not hidden): "
          + ", ".join(f"{name} {counts.get(name, 0)}"
                      for name in ("ongoing", "upcoming", "past", "unknown")))
    for warning in report["warnings"]:
        print(f"  WARNING: {warning}")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Build data/events.json from the AICF events page.")
    parser.add_argument("--html", help="read this saved HTML file instead of fetching the live page")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="where data/ lives")
    args = parser.parse_args(argv)
    try:
        html = Path(args.html).read_text(encoding="utf-8") if args.html else None
        report = run(args.data_dir, html=html)
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if not isinstance(exc, DataFileError):
            print("Existing data was left untouched.", file=sys.stderr)
        return exc.exit_code
    print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
