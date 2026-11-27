"""Finding the same tournament on several sites, and grouping (never removing) them.

Every source record stays in events.json. Records that describe the same tournament
share a `group_id`; one of them is the group's primary, the others point at it with
`merged_into`. Nothing here deletes or hides an event.

Matching rules, in this order (see README, "Duplicates across sites"):
  1. different country                          -> different
  2. different state / city (both known)        -> different
  3. start dates more than 1 day apart          -> different (end dates are not used)
  4. name similarity on distinctive words       -> the score (a name with no distinctive
     words counts only when the whole name is the same word for word, in the same place)
  5. section guard (rating limit, age group, category letter, format) differs -> different
  6. strong proof (shared AICF code, same Chess-Results page) beats rules 2-5;
     the same brochure link beats rule 4 only (one brochure often covers several sections)
  7. score >= 0.80 same group; 0.50-0.80 flags.possible_duplicate_of; below: different
  8. data/manual/pairs.csv forces "same" or "not_same" for a pair of ids, beating all of this
     ("undecided" lines change nothing).

Everything is pure (no files, no network).
"""
from __future__ import annotations

import copy
import re
from collections import defaultdict
from datetime import date, timedelta

from eventlib import (STATES, VERIFIED_SOURCES, _CITY_BY_KEY, _STATE_BY_KEY, _key,
                      ages_from_text, clean_text, kerala_district, merge_tags, source_rank)

DATE_GAP_DAYS = 1  # start dates further apart than this: different tournaments
DATES_APART = "start dates more than 1 day apart"
SAME_AT = 0.80
POSSIBLE_AT = 0.50
NAME_WEIGHT, PLACE_WEIGHT, END_WEIGHT = 0.85, 0.10, 0.05
MIN_DISTINCT_WORDS = 2  # fewer distinctive words than this can never prove "same" by name alone

# Primary choice after "AICF with good dates": manual, kca, tnsca, ksca, chessfee, then the rest.
PRIMARY_ORDER = ("manual", "kca", "tnsca", "ksca", "chessfee", "chessresults_ind", "chessbase_calendar", "aicf")
# Sources whose "city" is a district (a town inside that district is not a different place).
DISTRICT_SOURCES = frozenset({"kca"})

FILLER = frozenset("""
chess tournament tournaments tmt international intl open fide rated rating ratings edition the of
and for in at a an
level championship championships player players only
prize prizes fund money lakh lakhs rs cash early bird till
""".split())
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
          r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_DATE_IN_TITLE = re.compile(
    rf"\b{_DAY}(?:\s*(?:-|to|&|and)\s*{_DAY})?\s*{_MONTH}\b|\b{_MONTH}\s*{_DAY}\b(?!\d)", re.I)
_MONTH_WORD = re.compile(rf"\b{_MONTH}\b", re.I)
_YEAR_RANGE = re.compile(r"\b(?:19|20)\d{2}\s*[-/]\s*\d{2,4}\b")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_ORDINAL = re.compile(r"\b(\d+)\s*(?:st|nd|rd|th)\b", re.I)
_POSSESSIVE = re.compile(r"[’'�`]s\b", re.I)
_LIMIT = re.compile(r"\b(below|under|upto|up\s+to|less\s+than|above|over|u|b)\s*(\d{4})\b", re.I)
_CATEGORY = re.compile(r"\b(?:category|cat|group|section)\s+([a-z])\b", re.I)
_FORMAT_WORDS = {"rapid": "rapid", "rapids": "rapid", "blitz": "blitz", "classical": "classical",
                 "classic": "classical", "standard": "classical"}
_AGE_TOKEN = re.compile(r"\b(?:under|u)\s*(\d{1,2})\b", re.I)
_STATE_WORDS = sorted({k for k in _STATE_BY_KEY} | {s.lower() for s in STATES}, key=len, reverse=True)
_STATE_PATTERN = re.compile(r"\b(?:" + "|".join(re.escape(s) for s in _STATE_WORDS) + r")\b")


def _flat(name: str) -> str:
    """Lowercase, possessives gone, punctuation as spaces."""
    text = _POSSESSIVE.sub("", clean_text(name).lower()).replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


_LEAD = re.compile(r"^\s*([A-Za-z][A-Za-z .]{1,30}?)\s*[-–—:|]\s+(?=\S)")


def _strip_place_prefix(name: str, city: str | None = None) -> str:
    """'CHENNAI - Shree Rudhraa ...' -> 'Shree Rudhraa ...' (a known city, a state, or the event's city)."""
    match = _LEAD.match(name)
    if match:
        lead = _key(match.group(1))
        if lead in _CITY_BY_KEY or lead in _STATE_BY_KEY or (city and lead == _key(city)):
            return name[match.end():]
    return name


# Tails that Chess-Results (mostly) adds after the real name. Each is only removed at the very
# end of the name, and something must be left before it.
_SEP = r"[\s,;:|>\-–—]*"
_TAIL_ORGANISER = re.compile(rf"{_SEP}\borgani[sz]ed\s+by\b.*$", re.I)
_TAIL_PERSON = re.compile(rf"{_SEP}\(\s*(?:mr|mrs|ms|miss|dr|shri|sri|smt|prof)\b\.?[^()]*\)\s*$", re.I)
_RANGE = r"(?:-|–|—|to|till|&|and)"  # "2 to 6 Dec", "27-29 Nov"
_TAIL_DATE = re.compile(
    rf"{_SEP}(?:\b{_DAY}(?:\s*{_RANGE}\s*{_DAY})?\s*{_MONTH}\.?,?(?:\s*(?:19|20)\d{{2}})?"
    rf"|\b{_MONTH}\.?\s*{_DAY}(?:\s*{_RANGE}\s*{_DAY})?,?(?:\s*(?:19|20)\d{{2}})?"
    r"|\b\d{1,2}[./-]\d{1,2}[./-](?:19|20)?\d{2})\s*$", re.I)


def strip_name_tails(name: str, city: str | None = None) -> str:
    """Drop trailing 'Organised by ...', '(Mr. ...)', dates ('20th Dec 2026') and a place that
    equals the event's city, repeatedly: '... Tournament -> 27 Nov 2026 - 29 Nov 2026 - Coimbatore'
    becomes '... Tournament'."""
    text = clean_text(name or "")
    place = None
    if city and _flat(city):
        words = r"[\s.\-]+".join(re.escape(w) for w in _flat(city).split())
        place = re.compile(rf"{_SEP}\(?\b{words}\b\)?\.?\s*$", re.I)
    while True:
        before = text
        for pattern in (_TAIL_ORGANISER, _TAIL_PERSON, _TAIL_DATE, place):
            if pattern is None:
                continue
            match = pattern.search(text)
            if match and text[:match.start()].strip(" ,;:|>-–—"):
                text = text[:match.start()].rstrip()
        if text == before:
            return text


def name_words(name: str, city: str | None = None) -> frozenset[str]:
    """The distinctive words of a tournament name, as a set (order does not matter).

    Removed: name tails (strip_name_tails), punctuation, dates written in the title, years,
    Indian state names, filler words, and the section words (rating limits, age groups,
    category letters, formats), which the section guard compares on their own.
    """
    text = _POSSESSIVE.sub("", _strip_place_prefix(strip_name_tails(name, city), city).lower())
    text = _LIMIT.sub(" ", text)  # before the years: "below 2000" is a rating, not a year
    text = _YEAR_RANGE.sub(" ", text)
    text = _DATE_IN_TITLE.sub(" ", text)
    text = _YEAR.sub(" ", text)
    text = _ORDINAL.sub(r" no\1 ", text)  # "6th", "6 th" -> no6; other bare numbers are noise
    text = _flat(text)
    text = _LIMIT.sub(" ", text)
    text = _CATEGORY.sub(" ", text)
    text = _AGE_TOKEN.sub(" ", text)
    text = _MONTH_WORD.sub(" ", text)
    text = _STATE_PATTERN.sub(" ", text)
    words = set()
    for word in text.split():
        if word in FILLER or word in _FORMAT_WORDS or len(word) == 1 or word.isdigit():
            continue
        if len(word) > 4 and word.endswith("s"):
            word = word[:-1]  # championships -> championship
        words.add(word)
    return frozenset(words)


def sections(name: str) -> dict:
    """What tells two sections of one festival apart: rating limits, ages, category, format."""
    flat = _flat(_ORDINAL.sub(r"\1", clean_text(name)))
    limits = set()
    for word, number in _LIMIT.findall(flat):
        limits.add(("above" if word.lower() in ("above", "over") else "below", int(number)))
    formats = {_FORMAT_WORDS[w] for w in flat.split() if w in _FORMAT_WORDS}
    return {"limits": frozenset(limits), "ages": frozenset(ages_from_text(clean_text(name))),
            "categories": frozenset(c.lower() for c in _CATEGORY.findall(flat)),
            "formats": frozenset(formats)}


def section_difference(a: dict, b: dict) -> str | None:
    for key, label in (("limits", "rating limit"), ("ages", "age group"), ("categories", "category")):
        if a[key] != b[key]:
            return label
    if a["formats"] and b["formats"] and a["formats"] != b["formats"]:
        return "format"
    return None


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _day(text) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _same_text(a, b) -> bool | None:
    if not a or not b:
        return None
    return _flat(a) == _flat(b)


# Renamed towns: the old and the new name are one place ("Bangalore" on AICF, "Bengaluru" on
# KSCA). Only official renames, so two different towns can never be made the same.
TOWN_RENAMES = {
    "bangalore": "bengaluru", "mysore": "mysuru", "mangalore": "mangaluru",
    "belgaum": "belagavi", "hubli": "hubballi", "gulbarga": "kalaburagi", "bellary": "ballari",
    "bijapur": "vijayapura", "shimoga": "shivamogga", "tumkur": "tumakuru",
    "bombay": "mumbai", "poona": "pune", "madras": "chennai", "trichy": "tiruchirappalli",
    "calcutta": "kolkata", "baroda": "vadodara", "gurgaon": "gurugram",
    "pondicherry": "puducherry", "trivandrum": "thiruvananthapuram", "cochin": "kochi",
    "calicut": "kozhikode",
    # spellings of one town (not renames): TNSCA writes "Pudukottai", "Tirupattur DT"
    "pudukottai": "pudukkottai", "tirupattur dt": "tirupattur",
}
# Never add a district as one of its towns here (Chengalpattu district is not Chennai):
# a different town must stay a different town.


def id_order(event_id: str):
    """Sort key for ids, numbers compared as numbers: chessfee-999 before chessfee-1832."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", event_id or "")]


def _town(name: str) -> str:
    flat = _flat(name)
    return TOWN_RENAMES.get(flat, flat)


def _same_town(a, b) -> bool | None:
    if not a or not b:
        return None
    return _town(a) == _town(b)


def _same_city(ea: dict, eb: dict) -> bool | None:
    """Same town (renamed towns count as one), and a KCA district matches the towns inside it.

    Both places known Kerala districts or towns: same district or not. A district against a
    town we do not know: unknown (None), never "different".
    """
    if ea.get("source") not in DISTRICT_SOURCES and eb.get("source") not in DISTRICT_SOURCES:
        return _same_town(ea.get("city"), eb.get("city"))
    if not ea.get("city") or not eb.get("city"):
        return None
    if _town(ea["city"]) == _town(eb["city"]):
        return True
    da, db = kerala_district(ea["city"]), kerala_district(eb["city"])
    if da and db:
        return da == db
    return None


def _chess_results_page(event: dict) -> str | None:
    for url in (event.get("source_url"), event.get("results_url")):
        match = re.search(r"chess-results\.com/(?:\w+\.aspx\?)?tnr(\d+)", url or "", re.I)
        if match:
            return match.group(1)
    return None


class Features:
    """What we compare, worked out once per event."""

    def __init__(self, event: dict):
        self.event = event
        self.id = event["id"]
        self.source = event["source"]
        self.words = name_words(event["name"] or "", event.get("city"))
        # the whole name, only lower-cased and without punctuation or tails ("Organised by ...")
        self.full = _flat(strip_name_tails(event["name"] or "", event.get("city"))) or None
        self.sections = sections(strip_name_tails(event["name"] or "", event.get("city")))
        self.start = _day(event.get("start"))
        self.end = _day(event.get("end"))
        self.codes = frozenset(event.get("codes") or [])
        self.cr_page = _chess_results_page(event)
        self.brochure = (event.get("brochure_url") or "").strip().lower() or None


def compare(a: Features, b: Features, ambiguous_codes: frozenset = frozenset()) -> dict:
    """{'score', 'decision' ('same'|'possible'|'different'), 'reason', 'hard'}.

    `hard` is True when a rule (not just a low name score) says they are different;
    a group never takes in two events with a hard difference.
    """
    ea, eb = a.event, b.event

    def out(score, decision, reason, hard=False):
        return {"score": round(score, 3), "decision": decision, "reason": reason, "hard": hard}

    if ea.get("country") and eb.get("country") and ea["country"] != eb["country"]:
        return out(0, "different", "different country", hard=True)
    shared = (a.codes & b.codes) - ambiguous_codes
    if shared:
        return out(1.0, "same", f"same AICF code {min(shared)}")
    if a.cr_page and a.cr_page == b.cr_page:
        return out(1.0, "same", "same Chess-Results page")
    if _same_text(ea.get("state"), eb.get("state")) is False:
        return out(0, "different", "different state", hard=True)
    if _same_city(ea, eb) is False:
        return out(0, "different", "different city", hard=True)
    if a.start is None or b.start is None:
        return out(0, "different", "start date unknown")
    if abs((a.start - b.start).days) > DATE_GAP_DAYS:
        return out(0, "different", DATES_APART, hard=True)
    city = _same_city(ea, eb)
    state = _same_text(ea.get("state"), eb.get("state"))
    section = section_difference(a.sections, b.sections)
    if section:
        return out(0, "different", f"different {section}", hard=True)
    words_a, words_b = a.words, b.words
    name = jaccard(words_a, words_b)
    reason = f"names {name:.2f}"
    if min(len(words_a), len(words_b)) < MIN_DISTINCT_WORDS:
        if a.full and a.full == b.full and (city or state):
            # "International FIDE Rated Above 1800 Open Chess Tournament 2026" on both sites, same
            # state: no distinctive words, but the whole name is the same word for word.
            name, reason = 1.0, "identical names (no distinctive words, same place)"
        else:
            name = min(name, 0.6)
            reason += " (too few distinctive words)"
    if a.brochure and a.brochure == b.brochure:
        name, reason = 1.0, "same brochure link"
    place = 1.0 if city else 0.5 if state else 0.0
    end = 1.0 if a.end and a.end == b.end else 0.0
    score = NAME_WEIGHT * name + PLACE_WEIGHT * place + END_WEIGHT * end
    if score >= SAME_AT:
        return out(score, "same", reason)
    if score >= POSSIBLE_AT:
        return out(score, "possible", reason)
    return out(score, "different", reason)


# --------------------------------------------------------------------------
# Grouping
# --------------------------------------------------------------------------
def _candidates(features: list[Features]):
    """Pairs worth comparing: from different sources, starting within a day, or sharing proof."""
    by_day = defaultdict(list)
    by_key = defaultdict(list)
    for index, f in enumerate(features):
        if f.start:
            by_day[f.start].append(index)
        for code in f.codes:
            by_key[("code", code)].append(index)
        if f.cr_page:
            by_key[("cr", f.cr_page)].append(index)
    pairs = set()
    for day, indexes in by_day.items():
        for other_day in (day, day + timedelta(days=1)):
            for i in indexes:
                for j in by_day.get(other_day, ()):
                    if i != j:
                        pairs.add((min(i, j), max(i, j)))
    for indexes in by_key.values():
        for i in indexes:
            for j in indexes:
                if i < j:
                    pairs.add((i, j))
    return sorted((i, j) for i, j in pairs if features[i].source != features[j].source)


def _primary_key(event: dict):
    suspect = bool(event["flags"]["dates_suspect"])
    good_aicf = event["source"] == "aicf" and not suspect
    rank = PRIMARY_ORDER.index(event["source"]) if event["source"] in PRIMARY_ORDER else len(PRIMARY_ORDER)
    return (bool(event["hidden"]), not good_aicf, rank, event["id"])


def _link(event: dict) -> dict:
    return {"source": event["source"], "source_url": event["source_url"],
            "register_url": event["register_url"], "results_url": event["results_url"],
            "brochure_url": event["brochure_url"]}


def _inherit_tags(members: list[dict]) -> None:
    """A format or FIDE flag one member knows is given to the others, if no member disagrees."""
    formats = {tuple(m["tags"]["formats"]) for m in members if m["tags"]["formats"]}
    if len(formats) == 1:
        known = list(next(iter(formats)))
        for m in members:
            if not m["tags"]["formats"]:
                m["tags"]["formats"] = known
    # A "true" on any record of the tournament fills the gaps; "false" is never passed on.
    rated = [m for m in members if m["tags"]["fide_rated"] is True]
    if rated:
        how = "stated" if any(m["tags"]["fide_how"] == "stated" for m in rated) else "inferred"
        for m in members:
            if m["tags"]["fide_rated"] is None:
                m["tags"]["fide_rated"], m["tags"]["fide_how"] = True, how


def _finish_group(members: list[dict]) -> None:
    members.sort(key=_primary_key)
    primary = members[0]
    _inherit_tags(members)
    for m in members:
        m["group_id"] = primary["id"]
        m["merged_into"] = None if m is primary else primary["id"]
        m["also_listed_on"] = []
    if len(members) == 1:
        return
    others = sorted(members[1:], key=lambda e: (source_rank(e["source"]), e["id"]))
    primary["also_listed_on"] = [_link(m) for m in others]
    links = [{"source": m["source"], "source_url": m["source_url"], "register_url": m["register_url"]}
             for m in [primary] + others]
    primary["sources"] = [l for i, l in enumerate(links) if l not in links[:i]]
    known = (primary["tags"]["formats"], primary["tags"]["fide_rated"],
             primary["tags"]["fide_how"])  # settled by _inherit_tags
    if primary["city"] is None:
        # A town (Kochi) says more than a district (Ernakulam): districts fill the gap last.
        town = next((m["city"] for m in others
                     if m["city"] and m["source"] not in DISTRICT_SOURCES), None)
        primary["city"] = town
    for other in others:
        for field in ("register_url", "results_url", "brochure_url", "city", "state", "place_text",
                      "organiser", "registration_deadline"):
            if primary[field] is None and other[field] is not None:
                primary[field] = other[field]
        primary["tags"] = merge_tags(primary["tags"], other["tags"])
        primary["codes"] = primary["codes"] + [c for c in other["codes"] if c not in primary["codes"]]
        seen = [x for x in (primary["first_seen"], other["first_seen"]) if x]
        primary["first_seen"] = min(seen) if seen else None
    primary["tags"]["formats"], primary["tags"]["fide_rated"], primary["tags"]["fide_how"] = known
    primary["gone_from_source"] = all(m["gone_from_source"] for m in members)
    primary["verified"] = any(m["source"] in VERIFIED_SOURCES for m in members)
    if primary["flags"]["dates_suspect"]:
        good = next((m for m in others if not m["flags"]["dates_suspect"] and m["start"]), None)
        if good is not None:
            primary["start"], primary["end"] = good["start"], good["end"]
            primary["dates_from"] = good["id"]
            primary["flags"]["dates_suspect"] = False  # raw_dates still holds what the source said


def share_fide_with_sections(events: list[dict]) -> int:
    """Sections of one festival share a true fide_rated (never a false one).

    Siblings: the same brochure link, or the same name once the section words (category letter,
    rating limit, age group, format) are removed, with the same start date and city.
    A record that gets its flag this way has fide_how "inferred". Returns how many were filled.
    """
    parent = list(range(len(events)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first: dict[tuple, int] = {}
    for index, event in enumerate(events):
        keys = []
        if event.get("brochure_url"):
            keys.append(("brochure", event["brochure_url"].strip().lower()))
        words = name_words(event["name"] or "", event.get("city"))
        if len(words) >= MIN_DISTINCT_WORDS and event.get("start") and event.get("city"):
            keys.append(("name", words, event["start"], _flat(event["city"])))
        for key in keys:
            if key in first:
                parent[find(index)] = find(first[key])
            else:
                first[key] = index
    clusters = defaultdict(list)
    for index, event in enumerate(events):
        clusters[find(index)].append(event)
    filled = 0
    for members in clusters.values():
        if len(members) > 1 and any(m["tags"]["fide_rated"] is True for m in members):
            for m in members:
                if m["tags"]["fide_rated"] is None:
                    m["tags"]["fide_rated"], m["tags"]["fide_how"] = True, "inferred"
                    filled += 1
    return filled


def group_events(events: list[dict], pairs: list[dict], warnings: list[str]) -> dict:
    """Give every event group_id / merged_into / also_listed_on; flag possible duplicates.

    `pairs` are the rows of data/manual/pairs.csv: {"line", "a", "b", "decision", "note"}.
    Changes `events` in place, never removes one. Returns {"review": [...rows], "groups": n,
    "merged": n, "possible": n}.
    """
    for e in events:
        e["group_id"], e["merged_into"], e["also_listed_on"], e["dates_from"] = e["id"], None, [], None
        e["flags"]["possible_duplicate_of"] = None
    share_fide_with_sections(events)
    features = [Features(e) for e in events]
    index_of = {f.id: i for i, f in enumerate(features)}
    aicf_by_code = defaultdict(list)
    for f in features:
        if f.source == "aicf":
            for code in f.codes:
                aicf_by_code[code].append(f.id)
    ambiguous = frozenset(c for c, ids in aicf_by_code.items() if len(ids) > 1)
    for code in sorted(ambiguous):
        if any(code in f.codes and f.source != "aicf" for f in features):
            warnings.append(f"Several AICF events share one code ({', '.join(aicf_by_code[code])}); "
                            "entries with that code were not grouped by the code.")

    forced: dict[tuple[int, int], dict] = {}
    for row in pairs:
        missing = [x for x in (row["a"], row["b"]) if x not in index_of]
        if missing:
            warnings.append(f"data/manual/pairs.csv line {row['line']}: no event has the id "
                            f"{' or '.join(repr(m) for m in missing)}; this row was ignored.")
            continue
        if row["decision"] == "undecided":
            continue  # still to be checked by a person: the rules below decide for now
        i, j = sorted((index_of[row["a"]], index_of[row["b"]]))
        forced[(i, j)] = row

    results = {}
    for i, j in _candidates(features):
        results[(i, j)] = compare(features[i], features[j], ambiguous)
    for key, row in forced.items():
        base = results.get(key) or compare(features[key[0]], features[key[1]], ambiguous)
        results[key] = {**base, "decision": row["decision"], "reason": "pairs.csv"
                        + (f": {row['note']}" if row.get("note") else ""), "forced": True}

    # Union-find; a merge is refused when it would put a hard difference inside one group.
    parent = list(range(len(events)))
    members = {i: [i] for i in range(len(events))}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # pairs.csv "same" partners: a person has said these records are one tournament, also when
    # their start dates are days apart (ChessBase 21 Nov, AICF 27 Nov).
    vouched = defaultdict(set)
    for (i, j), row in forced.items():
        if row["decision"] == "same":
            vouched[i].add(j)
            vouched[j].add(i)

    def dates_vouched(x, y, together) -> bool:
        """x and y start days apart, but a pairs.csv "same" partner of one of them (in the same
        group) starts within a day of the other: the person already said both dates are this
        tournament, so the gap is not a reason to keep y out."""
        for a, b in ((x, y), (y, x)):
            for w in vouched[a]:
                if w in together and features[w].start and features[b].start \
                        and abs((features[w].start - features[b].start).days) <= DATE_GAP_DAYS:
                    return True
        return False

    def blocked(ri, rj) -> str | None:
        together = set(members[ri]) | set(members[rj])
        for x in members[ri]:
            for y in members[rj]:
                key = (min(x, y), max(x, y))
                result = results.get(key)
                if result and result.get("forced"):
                    if result["decision"] == "not_same":
                        return f"pairs.csv says {features[x].id} and {features[y].id} are not the same"
                    continue
                if features[x].source == features[y].source:
                    return f"{features[x].id} and {features[y].id} come from the same source"
                result = result or compare(features[x], features[y], ambiguous)
                if result["hard"]:
                    if result["reason"] == DATES_APART and dates_vouched(x, y, together):
                        continue
                    return f"{features[x].id} vs {features[y].id}: {result['reason']}"
        return None

    def union(i, j) -> str | None:
        ri, rj = find(i), find(j)
        if ri == rj:
            return None
        why = blocked(ri, rj)
        if why:
            return why
        parent[rj] = ri
        members[ri].extend(members.pop(rj))
        return None

    # Best score first; on a tie the pair with the lower ids goes first, so the result never
    # depends on the order the records were read in (chessfee lists Eight Square twice).
    order = sorted(results.items(), key=lambda kv: (
        not kv[1].get("forced"), -kv[1]["score"],
        sorted((id_order(features[kv[0][0]].id), id_order(features[kv[0][1]].id)))))
    for (i, j), result in order:
        if result["decision"] == "same":
            if result.get("forced"):
                ri, rj = find(i), find(j)
                why = None
                if ri != rj:
                    # a forced pair only yields to a forced "not_same"
                    for x in members[ri]:
                        for y in members[rj]:
                            r = results.get((min(x, y), max(x, y)))
                            if r and r.get("forced") and r["decision"] == "not_same":
                                why = f"pairs.csv also says {features[x].id} and {features[y].id} are not the same"
                    if why is None:
                        parent[rj] = ri
                        members[ri].extend(members.pop(rj))
                if why:
                    warnings.append(f"data/manual/pairs.csv: {features[i].id} and {features[j].id} were "
                                    f"not grouped because {why}.")
                    result["decision"], result["reason"] = "possible", result["reason"] + f" (blocked: {why})"
            else:
                why = union(i, j)
                if why:
                    result["decision"] = "possible"
                    result["reason"] += f" (not grouped: {why})"

    groups = defaultdict(list)
    for i in range(len(events)):
        groups[find(i)].append(events[i])
    for group in groups.values():
        _finish_group(group)

    # Possible duplicates: point the lower-ranked event at the better one (best score first).
    # When both already sit in a group with other records, they have found their twins: no flag.
    for (i, j), result in order:
        if result["decision"] != "possible" or find(i) == find(j):
            continue
        if len(members[find(i)]) > 1 and len(members[find(j)]) > 1:
            result["reason"] += " (both already grouped with others; not flagged)"
            continue
        a, b = sorted((events[i], events[j]), key=lambda e: (source_rank(e["source"]), e["id"]))
        if b["flags"]["possible_duplicate_of"] is None:
            b["flags"]["possible_duplicate_of"] = a["id"]

    review = []
    for (i, j), result in sorted(results.items(), key=lambda kv: (kv[1]["score"], kv[0])):
        if result["decision"] == "different" and not result.get("forced"):
            continue
        a, b = sorted((events[i], events[j]), key=lambda e: (source_rank(e["source"]), e["id"]))
        decision = result["decision"]
        if decision == "same" and find(i) != find(j):
            decision = "possible"
        review.append({"score": f"{result['score']:.3f}", "decision": decision,
                       "reason": result["reason"],
                       **{f"{k}_{s}": v for s, e in (("a", a), ("b", b)) for k, v in (
                           ("id", e["id"]), ("source", e["source"]), ("name", e["name"]),
                           ("start", e["start"] or ""), ("end", e["end"] or ""),
                           ("place", ", ".join(x for x in (e["city"], e["state"]) if x)
                            or (e["place_text"] or "")))},
                       "group_id": events[i]["group_id"] if find(i) == find(j) else ""})
    review.sort(key=lambda r: (float(r["score"]), r["id_a"], r["id_b"]))  # lowest score first
    multi = [g for g in groups.values() if len(g) > 1]
    return {"review": review, "groups": len(groups), "multi_groups": len(multi),
            "merged": sum(len(g) - 1 for g in multi),
            "possible": sum(1 for e in events if e["flags"]["possible_duplicate_of"])}


REVIEW_COLUMNS = ("score", "decision", "reason", "id_a", "source_a", "name_a", "start_a", "end_a",
                  "place_a", "id_b", "source_b", "name_b", "start_b", "end_b", "place_b", "group_id")
