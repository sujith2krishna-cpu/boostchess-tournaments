"""Shared building blocks: text cleaning, dates, places, tags, the event record.

Everything here is pure (no network, no files) so every source module and the
tests can use it. The sources live in scripts/sources/; the run itself is in
scripts/build_events.py.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

SOURCE_URL = "https://aicf.in/all-events/"
USER_AGENT = (
    "BoostchessBot (+https://github.com/sujith2krishna-cpu/boostchess-tournaments)"
)
REQUEST_TIMEOUT_SECONDS = 30
RETRY_WAIT_SECONDS = 5
MIN_FRACTION_OF_PREVIOUS = 0.5  # a source returning less than half of last time counts as failed
SCHEMA_VERSION = 5  # 5: group_id, merged_into, also_listed_on, dates_from; fide_rated may be false
#                     4: results_url
#                     3: sources[], source_url, listed_by, verified, flags.possible_duplicate_of
#                     2: tags.age is a list; every event has a country

# India has no daylight saving, so a fixed offset is exactly Asia/Kolkata and
# needs no extra package (zoneinfo needs tzdata on Windows).
IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

EVENTS_CSV_COLUMNS = (
    "id", "name", "start_date", "end_date", "place", "state", "country", "link",
    "brochure_url", "format", "age", "note", "results_url",
)
OVERRIDES_CSV_COLUMNS = (
    "key", "start_date", "end_date", "place", "state", "hide", "cancelled", "note",
    "register_url", "results_url",
)
PAIRS_CSV_COLUMNS = ("id_a", "id_b", "decision", "note")
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


class SourceSkipped(BuildError):
    """A source was not read on purpose (robots.txt, request cap, switched off)."""

    exit_code = 2


class RobotsDisallowed(SourceSkipped):
    """The site's robots.txt does not allow this path."""


class RequestCapReached(SourceSkipped):
    """The per-site request cap for this run is used up."""


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


def valid_url(href, base: str = SOURCE_URL) -> str | None:
    """An absolute http(s) URL with a real-looking host, else None."""
    href = clean_text(href).replace(" ", "%20")
    if not href or href.startswith("#"):
        return None
    absolute = urljoin(base, href)
    parsed = urlparse(absolute)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or "." not in host:
        return None
    if host.replace(".", "").isdigit():
        return None
    return absolute


_AGE = re.compile(r"(?<![A-Za-z])(?:under|u)[\s\-\u2013\u2014.]*(\d{1,2})(?!\d)", re.I)
# "Under 12 & 18", "U-9, 11, 13", "U11/U13": more ages joined to one already found
# (but not a date like "Under 13, 14 Oct").
_AGE_MORE = re.compile(
    r"\s*(?:&|and|,|/)\s*(?:under|u)?[\s\-\u2013]*(\d{1,2})(?!\d)"
    r"(?!\s*(?:st|nd|rd|th)?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))", re.I)


def ages_from_text(text: str) -> list[str]:
    """Age groups as a list: 'Under 12 & 18' -> ['U12', 'U18']; nothing found -> []."""
    found = set()
    for match in _AGE.finditer(text):
        values = [int(match.group(1))]
        position = match.end()
        while True:
            more = _AGE_MORE.match(text, position)
            if not more:
                break
            values.append(int(more.group(1)))
            position = more.end()
        found.update(v for v in values if 4 <= v <= 25)
    return [f"U{v}" for v in sorted(found)]


# Formats: the words a name uses for each one. "Standard" is FIDE's word for classical.
_FORMAT_WORDS = {
    "classical": r"classical|standard",
    "rapid": r"rapid|rapids|rapidplay|rapid[\s-]play",
    "blitz": r"blitz",
}
_NON_RATED = re.compile(r"(?i)\b(?:non|un)[\s-]?(?:fide[\s-]?)?rated\b|\bnon[\s-]?fide\b|\bunrated\b"
                        r"|\bnot\s+(?:fide\s+)?rated\b")
_RATED = re.compile(r"(?i)\b(?:rated|rating|ratings)\b")
_FIDE_WITH = re.compile(r"(?i)\bfide\b[\s-]*(?:rapid|blitz|standard|classical|below|above|under\b|u[\s-]*\d)"
                        r"|\b(?:rapid|blitz|standard|classical)[\s-]+fide\b")


def formats_in(text: str) -> list[str]:
    """Formats a piece of text names, in FORMAT_ORDER ([] when it names none)."""
    return [f for f in FORMAT_ORDER if re.search(rf"(?i)\b(?:{_FORMAT_WORDS[f]})\b", text or "")]


# Words that do not say "FIDE rated" but only occur on FIDE-rated events: a grandmaster event,
# a norm event, an "International" open / tournament (the AICF lists these only when rated).
_INFERRED_RATED = (
    re.compile(r"(?i)\b(?:grand[\s-]*masters?|gm)\b[\s\-–—:('‘]*"
               r"(?:open|tournaments?|chess|category)\b"),
    re.compile(r"(?i)\b(?:im|gm)[\s-]*norms?\b|\bnorms?[\s-]+tournaments?\b"),
)
_INTERNATIONAL = re.compile(r"(?i)\binternational\b")
_SCHOOL = re.compile(r"(?i)\bschools?\b")  # "St. Xavier International ... School": a school's name
_INTERNATIONAL_WITH = re.compile(r"(?i)\b(?:open|tournaments?|chess|rating)\b")


def fide_evidence(text: str) -> tuple[bool | None, str | None]:
    """(fide_rated, fide_how) from a piece of text.

    (False, "stated") when it says non-rated / unrated / not rated;
    (True, "stated") when it says FIDE rated ("FIDE Rated", "Rapid Rating", "FIDE RAPID");
    (True, "inferred") for grandmaster / norm / "International ... Open|Tournament|Chess" names;
    (None, None) when it says nothing.
    """
    text = clean_text(text)
    if _NON_RATED.search(text):
        return False, "stated"
    if _RATED.search(text) or _FIDE_WITH.search(text):
        return True, "stated"
    if any(p.search(text) for p in _INFERRED_RATED) or (
            _INTERNATIONAL.search(text) and _INTERNATIONAL_WITH.search(text) and not _SCHOOL.search(text)):
        return True, "inferred"
    return None, None


def fide_rated_in(text: str) -> bool | None:
    """Only the "stated" part of fide_evidence(): True / False when the text says so, else None."""
    value, how = fide_evidence(text)
    return value if how == "stated" else None


def derive_tags(name: str) -> dict:
    """Conservative tags from the name. Anything unsure stays empty."""
    fide_rated, fide_how = fide_evidence(name)
    return {
        "formats": formats_in(name),
        "fide_rated": fide_rated,
        "fide_how": fide_how,
        "age": ages_from_text(name),
        "open": True if re.search(r"\bopen\b", name, re.I) else None,
        "girls": True if re.search(r"\bgirls?\b", name, re.I) else None,
        "categories": [],
    }


# --------------------------------------------------------------------------
# Event records
# --------------------------------------------------------------------------
EVENT_KEYS = (
    "id", "codes", "name", "start", "end", "place_text", "state", "city", "country",
    "brochure_url", "source", "source_url", "sources", "listed_by", "verified",
    "group_id", "merged_into", "also_listed_on",
    "register_url", "results_url", "organiser", "tags", "flags",
    "raw_dates", "dates_from", "first_seen", "last_seen", "gone_from_source", "cancelled",
    "hidden", "note", "overridden",
)
TAG_DEFAULTS = (("formats", []), ("fide_rated", None), ("fide_how", None), ("age", []),
                ("open", None), ("girls", None), ("categories", []))
FLAG_DEFAULTS = (("dates_suspect", False), ("code_expanded", False),
                 ("code_unclear", False))
EVENT_DEFAULTS = {
    "source_url": None, "sources": None, "listed_by": None, "verified": None, "results_url": None,
    "codes": [], "start": None, "end": None, "place_text": None, "state": None,
    "city": None, "country": None, "brochure_url": None, "register_url": None, "organiser": None,
    "raw_dates": None, "gone_from_source": False, "cancelled": False,
    "hidden": False, "note": None, "overridden": None,
    "merged_into": None, "also_listed_on": [], "dates_from": None,
}
OVERRIDABLE_FIELDS = ("start", "end", "place_text", "state", "city", "register_url", "results_url")

# Where an event comes from, how much we trust it, and who wins when two sources
# describe the same event. (Override > manual > aicf > the rest.)
SOURCE_PRIORITY = ("manual", "aicf", "chessfee", "chessresults_ind", "chessbase_calendar")
AUTOMATIC_SOURCES = SOURCE_PRIORITY[1:]
LISTED_BY = {"manual": "manual", "aicf": "aicf", "chessfee": "chessfee",
             "chessresults_ind": "chess-results", "chessbase_calendar": "chessbase"}
VERIFIED_SOURCES = frozenset({"aicf", "manual"})


def source_rank(source: str | None) -> int:
    return SOURCE_PRIORITY.index(source) if source in SOURCE_PRIORITY else len(SOURCE_PRIORITY)


# Country codes (ISO 3166-1 alpha-2). The AICF-style sources are all Indian events; a
# calendar that lists events from many countries must supply its own code per event.
COUNTRY_BY_SOURCE = {"aicf": "IN", "manual": "IN", "chessfee": "IN", "chessresults_ind": "IN"}
ISO_COUNTRIES = frozenset("""
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS
BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE
EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM
HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC
LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA
NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW
SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO
TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
""".split())


def country_for(source: str | None, country: str | None = None) -> str | None:
    """'IN' for the Indian sources; for chessbase_calendar the event's own ISO code or None."""
    if source in COUNTRY_BY_SOURCE:
        return COUNTRY_BY_SOURCE[source]
    if source == "chessbase_calendar":
        code = (country or "").strip().upper()
        return code if code in ISO_COUNTRIES else None
    return None


def canonical(event: dict) -> dict:
    """The event with keys in the one fixed order (and defaults filled in)."""
    tags_in = event.get("tags") or {}
    flags_in = event.get("flags") or {}
    out = {}
    for key in EVENT_KEYS:
        if key == "tags":
            out[key] = {k: copy.deepcopy(tags_in.get(k, d)) for k, d in TAG_DEFAULTS}
            age = out[key]["age"]  # schema 1 stored one string (or null); schema 2 a list
            out[key]["age"] = [] if age is None else [age] if isinstance(age, str) else age
            if "fide_how" not in tags_in:  # before fide_how, only what a name or site said was stored
                out[key]["fide_how"] = "stated" if out[key]["fide_rated"] is not None else None
        elif key == "country":
            out[key] = event["country"] if "country" in event else country_for(event.get("source"))
        elif key == "flags":
            out[key] = {k: bool(flags_in.get(k, d)) for k, d in FLAG_DEFAULTS}
            out[key]["possible_duplicate_of"] = flags_in.get("possible_duplicate_of")
        elif key == "results_url":
            # schema 3 and older had no results_url: a Chess-Results page is the results page
            out[key] = event["results_url"] if "results_url" in event else (
                event.get("source_url") if event.get("source") == "chessresults_ind" else None)
        elif key == "listed_by":
            out[key] = event["listed_by"] if event.get("listed_by") else LISTED_BY.get(event.get("source"))
        elif key == "verified":
            out[key] = bool(event["verified"]) if event.get("verified") is not None \
                else event.get("source") in VERIFIED_SOURCES
        elif key == "group_id":  # schema 4 and older: every event was its own group
            out[key] = event.get("group_id") or event.get("id")
        elif key == "sources":
            out[key] = copy.deepcopy(event["sources"]) if event.get("sources") else [
                {"source": event.get("source"), "source_url": event.get("source_url"),
                 "register_url": event.get("register_url")}]
        elif key in event:
            out[key] = copy.deepcopy(event[key])
        else:
            out[key] = copy.deepcopy(EVENT_DEFAULTS[key])
    return out


def _comparable(doc: dict, meta: dict) -> tuple:
    """Everything in the output except the timestamps (generated_at, every last_seen)."""
    events = [{k: v for k, v in canonical(e).items() if k != "last_seen"}
              for e in (doc or {}).get("events", [])]
    stable = {k: v for k, v in (meta or {}).items() if k not in ("generated_at", "last_run_at")}
    if isinstance(stable.get("sources"), dict):  # per-source times are timestamps too
        stable["sources"] = {
            name: {k: ({a: b for a, b in v.items() if a != "at"} if k == "last_error" and isinstance(v, dict)
                       else v) for k, v in info.items() if k not in ("last_success", "next_due")}
            for name, info in stable["sources"].items()}
    return (doc or {}).get("schema_version"), events, stable


def only_timestamps_changed(previous_doc, previous_meta, new_doc, new_meta) -> bool:
    """True when the new files differ from the old only in generated_at / last_seen.

    A daily job can use this to skip a pointless commit. With no previous data
    there is always something real to commit, so this is False.
    """
    if not previous_doc or not previous_doc.get("events"):
        return False
    return _comparable(previous_doc, previous_meta) == _comparable(new_doc, new_meta)


def count_changes(previous_events, new_events) -> dict:
    """How many events are new / changed (not counting last_seen) / newly no longer listed."""
    old = {e["id"]: canonical(e) for e in previous_events or []}
    new = changed = gone = 0
    for event in new_events:
        before = old.get(event["id"])
        if before is None:
            new += 1
            continue
        if {k: v for k, v in before.items() if k != "last_seen"} != \
                {k: v for k, v in event.items() if k != "last_seen"}:
            changed += 1
            if event["gone_from_source"] and not before["gone_from_source"]:
                gone += 1
    return {"new": new, "changed": changed, "gone": gone}


def sort_key(event: dict):
    start = event.get("start") or event.get("end") or "9999-12-31"
    return (start, event.get("end") or start, event["id"])




# --------------------------------------------------------------------------
# Privacy: never keep phone numbers or e-mail addresses
# --------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RUN = re.compile(r"(?<![\w/])\+?\(?\d[\d\s().\-]{6,}\d(?![\w/])")
_PHONE_LABEL = re.compile(
    r"(?i)(?:\b(?:ph(?:one)?|mob(?:ile)?|cell|tel(?:ephone)?|whats\s*app|contact(?:\s+no)?|call)\b"
    r"\.?\s*(?:no\.?|number)?\s*[:\-]?\s*)$")
_DATE_LIKE = re.compile(r"^\d{1,4}[-/. ]\d{1,2}[-/. ]\d{1,4}$")


def strip_phones(text) -> str:
    """Remove phone numbers (and e-mail addresses) from a piece of text.

    Anything with 9 or more digits counts, including +91 and spacing like
    98422 05003. Dates are left alone. A label right before a number
    ("Ph:", "Mob", "Contact:") goes too. We only store facts, never contact details.
    """
    original = str(text or "")
    text = _EMAIL.sub(" ", original)
    pieces, last = [], 0
    for match in _PHONE_RUN.finditer(text):
        digits = sum(c.isdigit() for c in match.group())
        if digits < 9 or _DATE_LIKE.match(match.group().strip()):
            continue
        before = text[last:match.start()]
        pieces.append(_PHONE_LABEL.sub("", before))
        last = match.end()
    pieces.append(text[last:])
    cleaned = "".join(pieces)
    if cleaned == original:
        return clean_text(original)  # nothing removed: leave the text exactly as it was
    cleaned = re.sub(r"\(\s*\)", " ", cleaned)
    cleaned = re.sub(r"\s*[,;&/|-]\s*(?=[,;&/|-]|$)", " ", cleaned)
    return clean_text(cleaned).strip(" ,;:-/|&")


# --------------------------------------------------------------------------
# AICF codes inside other sources' titles, similar names
# --------------------------------------------------------------------------
_AICF_CODE = re.compile(r"(?i)\bAICF\b[^0-9]{0,25}?(\d{6}(?:\s*/\s*\d{2,6}(?![\d/a-z]))*)")


def aicf_codes_in(text) -> list[str]:
    """6-digit AICF codes written next to the word AICF ("AICF Event Code: 502180/KL")."""
    found: list[str] = []
    for match in _AICF_CODE.finditer(text or ""):
        for code in parse_codes(match.group(1))[0]:
            if code not in found:
                found.append(code)
    return found


def similar_names(a: str, b: str, threshold: float = 0.85) -> bool:
    a, b = normalise_name(a), normalise_name(b)
    return bool(a and b) and difflib.SequenceMatcher(None, a, b).ratio() >= threshold


# --------------------------------------------------------------------------
# Regions for countries other than India (used for manual events and ChessBase)
# --------------------------------------------------------------------------
IN_STATE_CODES = {
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar",
    "CG": "Chhattisgarh", "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana",
    "HP": "Himachal Pradesh", "JH": "Jharkhand", "KA": "Karnataka", "KL": "Kerala",
    "MP": "Madhya Pradesh", "MH": "Maharashtra", "MN": "Manipur", "ML": "Meghalaya",
    "MZ": "Mizoram", "NL": "Nagaland", "OD": "Odisha", "OR": "Odisha", "PB": "Punjab",
    "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu", "TS": "Telangana",
    "TG": "Telangana", "TR": "Tripura", "UP": "Uttar Pradesh", "UK": "Uttarakhand",
    "UT": "Uttarakhand", "WB": "West Bengal", "AN": "Andaman and Nicobar Islands",
    "CH": "Chandigarh", "DD": "Dadra and Nagar Haveli and Daman and Diu",
    "DH": "Dadra and Nagar Haveli and Daman and Diu", "DL": "Delhi", "JK": "Jammu and Kashmir",
    "LA": "Ladakh", "LD": "Lakshadweep", "PY": "Puducherry",
}

REGIONS = {
    "US": "Alabama AL|Alaska AK|Arizona AZ|Arkansas AR|California CA|Colorado CO|Connecticut CT|"
          "Delaware DE|District of Columbia DC|Florida FL|Georgia GA|Hawaii HI|Idaho ID|Illinois IL|"
          "Indiana IN|Iowa IA|Kansas KS|Kentucky KY|Louisiana LA|Maine ME|Maryland MD|"
          "Massachusetts MA|Michigan MI|Minnesota MN|Mississippi MS|Missouri MO|Montana MT|"
          "Nebraska NE|Nevada NV|New Hampshire NH|New Jersey NJ|New Mexico NM|New York NY|"
          "North Carolina NC|North Dakota ND|Ohio OH|Oklahoma OK|Oregon OR|Pennsylvania PA|"
          "Rhode Island RI|South Carolina SC|South Dakota SD|Tennessee TN|Texas TX|Utah UT|"
          "Vermont VT|Virginia VA|Washington WA|West Virginia WV|Wisconsin WI|Wyoming WY",
    "GB": "England|Scotland|Wales|Northern Ireland",
    "CA": "Alberta AB|British Columbia BC|Manitoba MB|New Brunswick NB|"
          "Newfoundland and Labrador NL|Nova Scotia NS|Ontario ON|Prince Edward Island PE|"
          "Quebec QC|Saskatchewan SK|Northwest Territories NT|Nunavut NU|Yukon YT",
    "AU": "New South Wales NSW|Victoria VIC|Queensland QLD|Western Australia WA|"
          "South Australia SA|Tasmania TAS|Australian Capital Territory ACT|Northern Territory NT",
}


def _region_table(country: str) -> dict[str, str]:
    table = {}
    for entry in REGIONS[country].split("|"):
        words = entry.split()
        if country != "GB" and len(words) > 1 and words[-1].isupper() and len(words[-1]) <= 3 \
                and not (len(words) > 2 and words[-1] == "DC" and False):
            name, code = " ".join(words[:-1]), words[-1]
            table[_key(code)] = name
        else:
            name = entry
        table[_key(name)] = name
    return table


_REGION_TABLES = {c: _region_table(c) for c in REGIONS}


def region_for(country: str | None, text) -> str | None:
    """Canonical state/region name for a country we keep a list for, else None.

    India uses the state list above; US, GB, CA and AU use built-in lists.
    """
    text = clean_text(text)
    if not text:
        return None
    if country == "IN":
        return lookup_state(text) or IN_STATE_CODES.get(text.upper())
    if country in _REGION_TABLES:
        return _REGION_TABLES[country].get(_key(text))
    return None


def has_region_list(country: str | None) -> bool:
    return country == "IN" or country in _REGION_TABLES


# --------------------------------------------------------------------------
# Helpers for the web sources
# --------------------------------------------------------------------------
def check_dates(start: date | None, end: date | None, raw_start: str, raw_end: str,
                today: date) -> tuple[bool, dict | None]:
    """(dates_suspect, raw_dates). Bad dates are kept and flagged, never fixed."""
    suspect = start is None or end is None or end < start
    for value in (start, end):
        if value is not None and not today.year - 2 <= value.year <= today.year + 3:
            suspect = True
    return suspect, ({"start": raw_start, "end": raw_end} if suspect else None)


_FACILITY_WORDS = re.compile(
    r"(?i)\b(?:road|rd|street|st|hall|school|college|university|complex|auditorium|stadium|club|"
    r"academy|centre|center|hotel|campus|plaza|mandapam|building|floor|main|cross|lane|avenue|park|"
    r"layout|nagar|colony|sector|opp|opposite|near|behind|institute|convention|palace|resort)\b")


def locate_text(venue, title: str = "") -> dict:
    """Best-effort place_text / city / state from a venue line and a "CITY - name" title.

    Only text on the page is used; anything doubtful stays None.
    """
    venue = clean_text(venue)
    stripped = re.sub(r"[\s,\-\u2013\u2014]*\b\d{6}\b", "", venue)  # drop PIN codes
    parts = [p for p in (x.strip(" .-\u2013\u2014") for x in re.split(r"[,\n]+", stripped)) if p]
    state = city = None
    state_index = None
    for index in range(len(parts) - 1, -1, -1):
        found = lookup_state(parts[index])
        if found:
            state, state_index = found, index
            break
    if state_index:
        candidate = parts[state_index - 1]
        if not lookup_state(candidate):
            city = candidate
    if state is None:
        for part in reversed(parts):
            found = _CITY_BY_KEY.get(_key(part))
            if found:
                state, city = found, part
                break
    lead = re.match(r"\s*([A-Za-z][A-Za-z .]*?)\s+[-\u2013\u2014:]\s+\S", title or "")
    if lead:
        token = lead.group(1)
        token_state = lookup_state(token)
        token_city_state = _CITY_BY_KEY.get(_key(token))
        if state is None and token_state:
            state = token_state
        elif token_city_state and (state is None or state == token_city_state):
            state = token_city_state
            city = city or token.title()
    if city and (len(city.split()) > 3 or any(c.isdigit() for c in city) or _FACILITY_WORDS.search(city)):
        city = None
    return {"place_text": venue or None, "city": city, "state": state}


def merge_tags(primary: dict, other: dict) -> dict:
    """Primary's tags, with gaps filled from the other (lists are joined)."""
    out = copy.deepcopy(primary)
    for key in ("formats", "categories"):
        out[key] = list(out.get(key) or []) + [x for x in (other.get(key) or [])
                                              if x not in (out.get(key) or [])]
    out["formats"] = [f for f in FORMAT_ORDER if f in out["formats"]]
    out["age"] = sorted(set(out.get("age") or []) | set(other.get("age") or []),
                        key=lambda a: int(a[1:]))
    for key in ("open", "girls"):
        out[key] = out.get(key) or other.get(key) or None
    if out.get("fide_rated") is None and other.get("fide_rated") is not None:
        # True / False from the primary win; a gap is filled (a site's own flag counts as stated)
        out["fide_rated"] = other["fide_rated"]
        out["fide_how"] = other.get("fide_how") or "stated"
    elif out.get("fide_rated") is True and other.get("fide_rated") is True \
            and out.get("fide_how") == "inferred" and (other.get("fide_how") or "stated") == "stated":
        out["fide_how"] = "stated"  # a site saying so beats our inference
    if out.get("fide_rated") is None:
        out["fide_how"] = None
    return out


def parse_place_abroad(country: str, raw) -> dict:
    """place_text / city / state for a place outside India (state only for countries with a list)."""
    parts = [p for p in (clean_text(x).strip(" .") for x in re.split(r"[\n,]+", raw or "")) if p]
    state = None
    state_index = None
    if has_region_list(country):
        for index in range(len(parts) - 1, -1, -1):
            found = region_for(country, parts[index])
            if found:
                state, state_index = found, index
                break
    city_parts = [p for i, p in enumerate(parts) if i != state_index]
    return {"place_text": ", ".join(parts) or None,
            "city": city_parts[0] if city_parts else None, "state": state}


_REGION_EXAMPLE = {"IN": "Tamil Nadu", "US": "North Carolina", "GB": "Scotland",
                   "CA": "Ontario", "AU": "Victoria"}


def resolve_state(country: str, text) -> tuple[str | None, str | None]:
    """(state, problem). India, US, GB, CA and AU are checked against a list; others are free text."""
    text = clean_text(text)
    if not has_region_list(country):
        return (text or None), None
    found = region_for(country, text)
    if found:
        return found, None
    if country == "IN":
        return None, (f"state '{text}' is not an Indian state or union territory I know. "
                      "Check the spelling (for example 'Tamil Nadu').")
    return None, (f"state '{text}' is not a known state or region of {country}. Check the "
                  f"spelling (for example '{_REGION_EXAMPLE[country]}').")
