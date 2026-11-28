"""Source: UP Chess Sports Association (UPCSA), upchess.org, the state association of Uttar Pradesh.

The tournaments page (`/tournament.php`, "All Tournament/Events" in the site menu) is plain
server HTML with one table. Its columns, in the page's own words:

    S.No | Tournament_Name | Tournament_Level & Type | Tournament_Date | Entry_Apply_Dates |
    Entry_Apply_Dates with_Late_Fee | District/City | Status | Brochure Result Link

- the level and type cell: "Level : State Level / Type : For All";
- the dates: "Start : 21-Nov-2026 / End : 22-Nov-2026" (DD-Mon-YYYY);
- the entry dates: "Start : 12-Nov-2026 / End : 18-Nov-2026" plus the fees (never stored), or "-";
- the last cell carries the row's number (`data-id="96"`, which gives our id `upcsa-96`), a
  "View Brochure" link and either a result link or a "Result Link Not Updated" button.

One request per run (plus robots.txt), no event pages, no brochure files (a brochure is a
link only). Facts and links only; every piece of text goes through strip_phones().

What we store: name, dates, district/city (as `city`; it is often a district such as
"Kanpur Nagar", so it never blocks a match with a town), state Uttar Pradesh, the level in
`tags.categories` ("State Level", "National Level"), the end of the normal entry dates as
`registration_deadline` (the later late-fee dates are not used), the brochure and result links.
Nothing here says FIDE rated or not; only the name can (as for every source).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from eventlib import (SourceError, canonical, check_dates, clean_name, clean_text, country_for,
                      derive_tags, short_hash, strip_phones, valid_url)

NAME = "upcsa"
SITE_URL = "https://upchess.org/"
LIST_URL = SITE_URL + "tournament.php"
STATE = "Uttar Pradesh"

# The header cells we need, in the page's words (underscores read as spaces, any case).
_NEEDED = {"name": "tournament name", "level": "tournament level & type",
           "dates": "tournament date", "entry": "entry apply dates", "city": "district/city",
           "status": "status", "links": "brochure result link"}
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_START = re.compile(r"\bStart\s*:\s*([^\s|]+)", re.I)
_END = re.compile(r"\bEnd\s*:\s*([^\s|]+)", re.I)
_LEVEL = re.compile(r"\bLevel\s*:\s*(.+?)\s*(?:\bType\s*:|$)", re.I)
_TYPE = re.compile(r"\bType\s*:\s*(.+?)\s*$", re.I)
_BROCHURE = re.compile(r"(?i)brochure|prospectus|circular")
_RESULT = re.compile(r"(?i)\bresult")
_NOT_UPDATED = re.compile(r"(?i)not\s+updated")
_CANCELLED = re.compile(r"(?i)\bcancel")


def _text(node, sep: str = " ") -> str:
    return clean_text(_CONTROL.sub(" ", node.get_text(sep) if node is not None else ""))


def _header_key(text: str) -> str:
    return clean_text(text.replace("_", " ")).lower()


def parse_date(text: str | None) -> date | None:
    """'21-Nov-2026' -> 2026-11-21; anything else -> None (kept as raw text, never guessed)."""
    try:
        return datetime.strptime(clean_text(text or "").title(), "%d-%b-%Y").date()
    except ValueError:
        return None


def _labelled(regex, text: str) -> str:
    match = regex.search(text)
    return clean_text(match.group(1)) if match else ""


def parse_list(html: str, page_url: str = LIST_URL) -> list[dict]:
    """Every row of the tournaments table, as plain text and links."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        first = table.find("tr")
        header = [_header_key(_text(c)) for c in first.find_all(["th", "td"])] if first else []
        if all(name in header for name in _NEEDED.values()):
            break
    else:
        raise SourceError("UPCSA tournaments page has no table with Tournament_Name / "
                          "Tournament_Date / District/City columns; layout changed?")
    col = {key: header.index(name) for key, name in _NEEDED.items()}
    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td", recursive=False)
        if len(cells) < len(header):
            continue
        name = _text(cells[col["name"]])
        if not name:
            continue
        dates = _text(cells[col["dates"]])
        entry = _text(cells[col["entry"]])
        level = _text(cells[col["level"]])
        links_cell = cells[col["links"]]
        brochure = result = None
        for a in links_cell.find_all("a", href=True):
            label = _text(a)
            if brochure is None and _BROCHURE.search(label):
                brochure = valid_url(a["href"], page_url)
            elif result is None and _RESULT.search(label) and not _NOT_UPDATED.search(label):
                result = valid_url(a["href"], page_url)
        number = (links_cell.get("data-id") or "").strip()
        rows.append({
            "number": number if number.isdigit() else "",
            "name": name,
            "level": _labelled(_LEVEL, level),
            "type": _labelled(_TYPE, level),
            "start_text": _labelled(_START, dates),
            "end_text": _labelled(_END, dates),
            "entry_end_text": _labelled(_END, entry),
            "city": _text(cells[col["city"]]).strip(" -–"),
            "status": _text(cells[col["status"]]).strip(" -–"),
            "brochure_url": brochure,
            "results_url": result,
        })
    return rows


def event_id(row: dict) -> str:
    if row["number"]:
        return f"{NAME}-{row['number']}"
    return f"{NAME}-" + short_hash(clean_text(row["name"]).lower() + row["start_text"])


def signature(row: dict) -> str:
    text = "|".join(str(row[k] or "") for k in sorted(row))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _city(text: str) -> str | None:
    text = strip_phones(text).strip(" -–,")
    if not text:
        return None
    return text.title() if text.isupper() else text  # "GHAZIABAD" -> "Ghaziabad"


def build_event(row: dict, today: date) -> dict:
    name = clean_name(strip_phones(row["name"]))
    start, end = parse_date(row["start_text"]), parse_date(row["end_text"])
    suspect, raw_dates = check_dates(start, end, row["start_text"], row["end_text"], today)
    # The last day of the normal entry dates; only a readable day that is not after the event.
    deadline = parse_date(row["entry_end_text"])
    if deadline is not None and (start is None or deadline > (end or start)):
        deadline = None
    city = _city(row["city"])
    tags = derive_tags(name)
    level = strip_phones(row["level"])
    kind = strip_phones(row["type"])
    tags["categories"] = [x for x in (level, kind if kind.lower() != "for all" else "") if x]
    return canonical({
        "id": event_id(row),
        "codes": [],
        "name": name,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "place_text": ", ".join(p for p in (city, STATE) if p),
        "state": STATE,
        "city": city,
        "country": country_for(NAME),
        "brochure_url": row["brochure_url"],
        "source": NAME,
        "source_url": LIST_URL,  # the events have no pages of their own
        "results_url": row["results_url"],
        "registration_deadline": deadline.isoformat() if deadline else None,
        "tags": tags,
        "flags": {"dates_suspect": suspect},
        "raw_dates": raw_dates,
        "cancelled": bool(_CANCELLED.search(row["status"])),
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats). One request: the tournaments page."""
    rows = parse_list(client.get(LIST_URL), LIST_URL)
    events, listing = [], {}
    for row in rows:
        key = event_id(row)
        if key in listing:
            continue  # the same row twice
        listing[key] = signature(row)
        events.append(build_event(row, today))
    return events, listing, {"found": len(events), "rows_on_page": len(rows)}
