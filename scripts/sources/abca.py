"""Source: All Bihar Chess Association (ABCA), biharchess.org, the state association of Bihar.

The site menu "Tournament Calendars" links one page per season ("Calendar 2026-27",
"Calendar 2025-26", ...). We read the home page for that menu, then the newest two season
pages it links to. Each season page has one table. Its columns, in the page's own words:

    Sl. No. | Event | City | State Date | Circular | Results & Standing

**The dates have no year** ("05 April", "28Apr-30 Apr", "31 Oct-04 Nov.", "12-13 December"):
the page is a season (2026-27), and a season is not a year. We never work a year out from
the season. A year is taken only from the event itself:

1. a year written in the date cell ("12-13 December 2026");
2. one year in the event's own name ("4th Mandar Fide Rapid Rating Chess Tournament, 2026";
   a season such as "2026-27" in a name is not a year);
3. a full date in the file name of the event's own circular that is the event's first or last
   day (`...-RAPID-RATING-03-05-2026.pdf` for "03 May").

All of them must agree, and an event that runs over New Year needs (1) or (3). Otherwise the
dates are unclear: the record keeps no dates, the page's text stays in `raw_dates`,
`dates_suspect` is set, and the review list (data/review.csv) asks a person to read the
circular and put the dates in overrides.csv. Nothing is guessed.

Kept: events with dates that are upcoming, ongoing or ended in the last RECENT_DAYS days; and,
from the newest season page only, events whose dates are unclear and that have no results link
yet (a "Results & Standing" link means the event has been played). The circular is a link only
(`brochure_url`, never downloaded); the results link is `results_url` (a Chess-Results page,
which also groups the record with the same Chess-Results record). The City column is often a
district town, so it never blocks a match with another town (dedup.DISTRICT_SOURCES).

Three requests per run (plus robots.txt). Facts and links only; every piece of text goes through
strip_phones(). The player registration lists on this site are never read.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from eventlib import (SourceError, canonical, check_dates, clean_name, clean_text, country_for,
                      derive_tags, short_hash, strip_phones, valid_url)

NAME = "abca"
SITE_URL = "https://biharchess.org/"
STATE = "Bihar"
RECENT_DAYS = 60
SEASON_PAGES = 2  # the newest two season pages the menu links to

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SEASON_LINK = re.compile(r"(?i)^\s*calendar\s+((?:19|20)\d{2})\s*[-–/]\s*(\d{2}|\d{4})\s*$")
_NEEDED = {"name": "event", "city": "city", "dates": "state date", "circular": "circular"}
_RESULTS_HEADER = re.compile(r"(?i)^results?\b")
_MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july", "august",
                "september", "october", "november", "december")
_MONTH = r"([A-Za-z]{3,9})\.?"
# "12-13 December", "28Apr-30 Apr", "31 Oct-04 Nov.", "05 April", optionally "... 2026"
_DATES = re.compile(rf"^(\d{{1,2}})\s*(?:{_MONTH})?\s*(?:(?:-|–|to)\s*(\d{{1,2}})\s*(?:{_MONTH})?)?"
                    r"\s*,?\s*((?:19|20)\d{2})?\.?$", re.I)
# A single year in a name; "2026-27" / "2025-2026" (a season) is not one.
_NAME_YEAR = re.compile(r"(?<![\d/])(?<!\d[-–/])((?:19|20)\d{2})(?!\s*[-–/]\s*\d{2})(?!\d)")
_FILE_DATE = re.compile(r"(?<!\d)(\d{1,2})[-_.](\d{1,2})[-_.]((?:19|20)\d{2})(?!\d)")
_CANCELLED = re.compile(r"(?i)\b(?:cancel|postpone)")


def _text(node, sep: str = " ") -> str:
    return clean_text(_CONTROL.sub(" ", node.get_text(sep) if node is not None else ""))


def _month(text: str | None) -> int | None:
    text = (text or "").lower()
    for number, month in enumerate(_MONTH_NAMES, start=1):
        if len(text) >= 3 and (month.startswith(text) or (text == "sept" and month == "september")):
            return number
    return None


# ---- the season menu -----------------------------------------------------------
def season_pages(html: str, page_url: str = SITE_URL) -> list[tuple[str, str]]:
    """[(season, url)] from the site's own "Calendar 2026-27" menu links, newest first."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        match = _SEASON_LINK.match(_text(a))
        url = valid_url(a["href"], page_url)
        if match and url and urlparse(url).hostname in ("biharchess.org", "www.biharchess.org"):
            found.setdefault(f"{match.group(1)}-{match.group(2)[-2:]}", url)
    if not found:
        raise SourceError("ABCA home page has no \"Calendar YYYY-YY\" links in its menu; layout changed?")
    return sorted(found.items(), reverse=True)


# ---- a season page ---------------------------------------------------------------
def parse_season(html: str, season: str, page_url: str) -> list[dict]:
    """Every row of the season's table, as plain text and links."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        first = table.find("tr")
        header = [_text(c).lower().rstrip(".") for c in first.find_all(["th", "td"])] if first else []
        if all(h in header for h in _NEEDED.values()):
            break
    else:
        raise SourceError(f"ABCA calendar {season} has no table with Event / City / State Date / "
                          "Circular columns; layout changed?")
    col = {key: header.index(h) for key, h in _NEEDED.items()}
    results_col = next((i for i, h in enumerate(header) if _RESULTS_HEADER.match(h)), None)
    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td", recursive=False)
        if len(cells) <= max(col.values()):
            continue
        name = _text(cells[col["name"]])
        if not name:
            continue
        circular = cells[col["circular"]].find("a", href=True)
        results = cells[results_col].find("a", href=True) if results_col is not None and \
            results_col < len(cells) else None
        rows.append({
            "season": season,
            "number": _text(cells[0]),
            "name": name,
            "city": _text(cells[col["city"]]),
            "dates": _text(cells[col["dates"]]),
            "circular_url": valid_url(circular["href"], page_url) if circular else None,
            "results_url": valid_url(results["href"], page_url) if results else None,
            "page_url": page_url,
        })
    return rows


# ---- dates -------------------------------------------------------------------------
def day_months(text: str) -> tuple[tuple[int, int], tuple[int, int], int | None] | None:
    """'31 Oct-04 Nov.' -> ((31, 10), (4, 11), None); '12-13 December 2026' -> (..., 2026)."""
    match = _DATES.match(clean_text(text).replace("–", "-"))
    if not match:
        return None
    d1, m1, d2, m2, year = match.groups()
    m2 = _month(m2) if m2 else None
    m1 = _month(m1) if m1 else m2
    if m1 is None or (match.group(4) and m2 is None):
        return None  # no month, or a month word we do not know
    end = (int(d2), m2 or m1) if d2 else (int(d1), m1)
    return (int(d1), m1), end, int(year) if year else None


def year_evidence(row: dict, start: tuple[int, int], end: tuple[int, int]) -> dict[str, int]:
    """{"name": 2026, "circular": 2026}: years the event itself states (see the module notes).

    "circular" is the start's year when the file name's date is the first day, else (the last
    day) the end's year, so it is returned as ("circular_start" | "circular_end")."""
    found: dict[str, int] = {}
    years = set(_NAME_YEAR.findall(row["name"]))
    if len(years) == 1:
        found["name"] = int(years.pop())
    elif len(years) > 1:
        found["name"] = -1  # two different years in one name: unclear
    file = unquote(urlparse(row["circular_url"] or "").path.rsplit("/", 1)[-1])
    for d, m, y in _FILE_DATE.findall(file):
        if (int(d), int(m)) == start:
            found.setdefault("circular_start", int(y))
        elif (int(d), int(m)) == end:
            found.setdefault("circular_end", int(y))
    return found


def work_out_dates(row: dict) -> tuple[date | None, date | None, str]:
    """(start, end, how): how is "page", "name", "circular", or why the dates are unclear."""
    if not row["dates"]:
        return None, None, "no dates on the page"
    parsed = day_months(row["dates"])
    if parsed is None:
        return None, None, "dates not readable"
    start_dm, end_dm, cell_year = parsed
    crosses = (end_dm[1], end_dm[0]) < (start_dm[1], start_dm[0])
    evidence = year_evidence(row, start_dm, end_dm)
    if evidence.get("name") == -1:
        return None, None, "two different years in the name"
    # Every piece of evidence, as the start's year.
    starts: dict[str, int] = {}
    if cell_year:
        starts["page"] = cell_year - 1 if crosses else cell_year  # the year written is the end's
    if "name" in evidence and not crosses:
        starts["name"] = evidence["name"]
    if "circular_start" in evidence:
        starts["circular"] = evidence["circular_start"]
    if "circular_end" in evidence:
        starts.setdefault("circular", evidence["circular_end"] - (1 if crosses else 0))
    if not starts:
        return None, None, ("no year: over New Year, and only the name has a year" if crosses and
                            "name" in evidence else "no year on the page, in the name or in the circular")
    if len(set(starts.values())) > 1:
        return None, None, "the event's own years disagree"
    year = next(iter(starts.values()))
    try:
        start = date(year, start_dm[1], start_dm[0])
        end = date(year + (1 if crosses else 0), end_dm[1], end_dm[0])
    except ValueError:
        return None, None, "not a real date"
    return start, end, next(iter(starts))


# ---- records ------------------------------------------------------------------------
def event_id(row: dict) -> str:
    """abca-<hash of season + name>: stays the same when the page adds or moves dates."""
    return f"{NAME}-" + short_hash(row["season"] + "|" + clean_text(row["name"]).lower())


def signature(row: dict) -> str:
    text = "|".join(str(row[k] or "") for k in sorted(row))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _city(text: str) -> str | None:
    text = strip_phones(text).strip(" -–,.")
    if not text:
        return None
    return text.title() if text.isupper() else text


def build_event(row: dict, today: date) -> dict:
    name = clean_name(strip_phones(row["name"]))
    start, end, _how = work_out_dates(row)
    suspect, _ = check_dates(start, end, row["dates"], row["dates"], today)
    city = _city(row["city"])
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
        "brochure_url": row["circular_url"],
        "source": NAME,
        "source_url": row["page_url"],  # the events have no pages of their own
        "results_url": row["results_url"],
        "tags": derive_tags(name),
        "flags": {"dates_suspect": suspect},
        # The page's text always stays: the year came from elsewhere, or there is none.
        "raw_dates": {"start": row["dates"], "end": row["dates"]},
        "cancelled": bool(_CANCELLED.search(row["name"])),
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def keep(row: dict, today: date, newest: bool) -> bool:
    start, end, _ = work_out_dates(row)
    if start is None:
        return newest and row["results_url"] is None  # not played yet, as far as the page shows
    return (end or start) >= today - timedelta(days=RECENT_DAYS)


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats). The home page, then the newest season pages.

    `found` is every row on the season pages read, so a page that suddenly shows far fewer
    rows counts as a failed fetch, while events simply getting old does not.
    """
    seasons = season_pages(client.get(SITE_URL), SITE_URL)[:SEASON_PAGES]
    rows, kept = [], []
    for index, (season, url) in enumerate(seasons):
        page_rows = parse_season(client.get(url), season, url)
        rows.extend(page_rows)
        kept.extend(r for r in page_rows if keep(r, today, newest=index == 0))
    events, listing = [], {}
    for r in kept:
        key = event_id(r)
        if key in listing:
            continue  # the same row twice
        listing[key] = signature(r)
        events.append(build_event(r, today))
    stats = {"found": len(rows), "kept": len(events), "seasons": [s for s, _ in seasons],
             "dates_unclear": sum(1 for e in events if e["start"] is None)}
    return events, listing, stats
