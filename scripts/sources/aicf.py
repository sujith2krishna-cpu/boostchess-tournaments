"""Source: All India Chess Federation, https://aicf.in/all-events/ (one table, one request)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from bs4 import BeautifulSoup

from eventlib import *  # noqa: F401,F403
from eventlib import _iso

NAME = "aicf"
SITE_URL = "https://aicf.in/"
LISTING_URL = SOURCE_URL  # noqa: F405
MIN_ROWS = 100  # a page with fewer rows is treated as a broken fetch
MAX_SUSPECT_FRACTION = 0.5  # more bad dates than this means the layout changed

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
        "country": country_for("aicf"),
        "brochure_url": brochure,
        "source": "aicf",
        "source_url": SOURCE_URL,
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




def fetch(client, previous: dict, today: date, *, html: str | None = None,
          min_rows: int = MIN_ROWS):
    """One request for the whole table. Returns (events, listing state, stats).

    `html` lets tests and --html use a saved page instead of the network.
    """
    page = html if html is not None else client.get(LISTING_URL)
    rows, skipped = parse_html(page)
    events, duplicates = events_from_rows(rows, today)
    previous_count = sum(1 for e in previous.get("events", []) if not e.get("gone_from_source"))
    check_page_is_sane(len(rows), skipped, events, previous_count, min_rows)
    stats = {"found": len(rows), "rows_on_page": len(rows), "rows_skipped": skipped,
             "duplicate_rows_collapsed": duplicates}
    return events, {}, stats
