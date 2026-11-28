"""Source: Chess-Results (chess-results.com), federation list for India (fed=IND).

The federation page has its own "Tournament selection" menu. We use the same menu the
page offers (it sends the page's own form back): running tournaments (up to 3 weeks)
and tournaments starting in the next 7 days or later. Finished tournaments and
long-running leagues are not read. Each list shows at most 50 tournaments (the page's
own limit). A tournament's details page gives dates, organiser and venue; it is read
only for new tournaments or when the title in the list changed.

From the details page we also read:

- the "Rating calculation" row. "Rating international" (also together with "Rating national")
  says the tournament is FIDE rated: `fide_rated` = true, "stated". "Rating national" alone
  (national only) or a row that says not rated: false, "stated". "-" (what most pages show) or
  anything else says nothing. When the row and the name disagree, the name's value stays;
- the brochure among the "Download Files": a file named brochure / prospectus / circular /
  invitation; otherwise the only PDF, when its name does not look like results, pairings, a
  starting rank, a players list, a ranking, prizes, rules or minutes. Several PDFs and none
  named like a brochure: no brochure. Only the link is kept; the file is never read.

"Number of rounds" is on the page too, but the schema has no place for it, so it is not kept.

We keep facts and links only. Phone numbers and player lists are never stored.
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

NAME = "chessresults_ind"
SITE_URL = "https://chess-results.com/"
FEDERATION_URL = "https://chess-results.com/fed.aspx?lan=1&fed=IND"  # the link on the home page
# (what the menu entry starts with in the page's own wording)
WANTED_SELECTIONS = (
    "Just running tournaments (duration <= 3 weeks)",
    "In the next 7 days starting",
    "In more than 7 days starting",
)

_TNR = re.compile(r"tnr(\d+)\.aspx", re.I)
_DATE = re.compile(r"(\d{4})/(\d{2})/(\d{2})")
_REGISTER_WORDS = re.compile(r"(?i)regist|enrol|enroll|sign\s*up|entry\s*form|apply")
_BROCHURE_FILE = re.compile(r"(?i)brochure|prospectus|circular|invitation")
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\")]+")
# The page is asked for in English (lan=1); the German and Spanish names of the row are
# accepted too, in case a page comes back in another language.
_RATING_ROW = re.compile(r"(?i)^(?:rating\s+calculation|elorechnung|elo-?berechnung|"
                         r"c[aá]lculo\s+de\s+(?:elo|rating))$")
_ROW_INTERNATIONAL = re.compile(r"(?i)\b(?:rating|elo)\s+(?:international|internacional|"
                                r"internazionale|fide)\b")
_ROW_NATIONAL = re.compile(r"(?i)\b(?:rating|elo)\s+(?:national|nacional|nazionale)\b")
_ROW_NOT_RATED = re.compile(r"(?i)\b(?:not\s+rated|unrated|non[\s-]*rated|no\s+rating)\b")
_SIX_DIGITS = re.compile(r"\d{6}")
# Where the snapshot's listing state keeps each tournament's "FIDE-Event-ID" ({event id: number}).
# It is not part of an event; build_events.add_fide_event_codes() turns it into an AICF code
# only when an AICF event has exactly that code.
FIDE_IDS_KEY = "fide_event_ids"
_PDF_NAME = re.compile(r"(?i)\.pdf\s*$")
# A file that is clearly not a brochure (names flattened: "_" "-" "." read as spaces).
_NOT_BROCHURE = re.compile(r"(?i)\b(?:results?|pairings?|starting\s*ranks?|start\s*list|players?|"
                           r"rankings?|ranks?|standings?|cross\s*tables?|tie\s*breaks?|prizes?|"
                           r"winners?|rules?|manual|laws?|minutes|meeting|appendix)\b")


def parse_form(html: str) -> dict:
    """The page's own selection menu: where to post, the hidden fields, option values."""
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select", id="combo_tur_sel")
    if select is None:
        raise SourceError("Chess-Results federation page has no tournament selection menu; "
                          "layout changed?")
    form = select.find_parent("form")
    target = re.search(r"__doPostBack\(['&#39;]*([\w$]+)", select.get("onchange", ""))
    options = {clean_text(o.get_text()): o.get("value", "") for o in select.find_all("option")}
    sort = soup.find("select", id="combo_sort")
    sort_value = ""
    if sort is not None:
        chosen = sort.find("option", selected=True) or sort.find("option")
        sort_value = chosen.get("value", "") if chosen else ""
    return {
        "action": urljoin(FEDERATION_URL, form.get("action", "")) if form else FEDERATION_URL,
        "hidden": {i["name"]: i.get("value", "") for i in form.find_all("input", type="hidden")
                   if i.get("name")} if form else {},
        "event_target": target.group(1) if target else "combo_sel",
        "options": options,
        "sort": sort_value,
    }


def parse_list(html: str) -> list[dict]:
    """(tournament id, title, link) for every tournament in the list on the page."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="CRs2")
    if table is None:
        raise SourceError("Chess-Results tournament list not found; layout changed?")
    found = []
    for row in table.find_all("tr"):
        link = row.find("a", href=_TNR)
        if link is None:
            continue
        found.append({"id": _TNR.search(link["href"]).group(1),
                      "title": clean_text(link.get_text(" ")),
                      "url": f"https://chess-results.com/tnr{_TNR.search(link['href']).group(1)}.aspx?lan=1"})
    return found


def parse_details(html: str, page_url: str) -> dict:
    """Dates, organiser, venue and links from a tournament's details page."""
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h2")
    rows = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if len(cells) == 2:
            key = clean_text(cells[0].get_text(" "))
            if key and key not in rows and len(key) < 45:
                rows[key] = cells[1]
    if "Date" not in rows and "Organizer(s)" not in rows:
        raise SourceError("Chess-Results details page has no Date/Organizer rows; layout changed?")
    dates = _DATE.findall(rows["Date"].get_text(" ")) if "Date" in rows else []
    parsed = []
    for y, m, d in dates:
        try:
            parsed.append(date(int(y), int(m), int(d)))
        except ValueError:
            parsed.append(None)
    format_row = next((k for k in rows if k.lower().startswith("time control")), "")
    kind = re.search(r"\(([^)]*)\)", format_row)
    links = rows.get("Links")
    downloads = rows.get("Download Files")
    rating_key = next((k for k in rows if _RATING_ROW.match(k)), None)
    return {
        "title": clean_text(heading.get_text(" ")) if heading else "",
        "date_text": clean_text(rows["Date"].get_text(" ")) if "Date" in rows else "",
        "dates": parsed,
        "organiser": clean_text(rows["Organizer(s)"].get_text(" ")) if "Organizer(s)" in rows else None,
        "location": clean_text(rows["Location"].get_text(" ")) if "Location" in rows else "",
        "time_control": kind.group(1).strip().lower() if kind else None,
        "links": [(clean_text(a.get_text(" ")), a["href"]) for a in links.find_all("a", href=True)]
                 if links else [],
        "files": [(clean_text(a.get_text(" ")), urljoin(page_url, a["href"]))
                  for a in downloads.find_all("a", href=True)] if downloads else [],
        "rating_row": clean_text(rows[rating_key].get_text(" ")) if rating_key else None,
        "fide_event_id": fide_event_id(rows["FIDE-Event-ID"].get_text(" ")) if "FIDE-Event-ID" in rows
                         else None,
    }


def fide_event_id(text) -> str | None:
    """The "FIDE-Event-ID" row when it is exactly a 6-digit number (FIDE uses AICF's event code
    for Indian events), else None."""
    text = clean_text(text or "")
    return text if _SIX_DIGITS.fullmatch(text) else None


def rating_from_row(text) -> bool | None:
    """What the "Rating calculation" row says: True (FIDE), False (national only / not rated),
    None ("-", empty, or anything else)."""
    text = clean_text(text or "")
    if _ROW_INTERNATIONAL.search(text):
        return True
    if _ROW_NOT_RATED.search(text):
        return False
    if _ROW_NATIONAL.search(text) and not _ROW_NATIONAL.sub("", text).strip(" ,;/-"):
        return False  # only the national rating, nothing else
    return None


def brochure_link(files: list[tuple[str, str]]) -> str | None:
    """A brochure-named file; else the only PDF, unless its name says it is something else."""
    named = next((url for name, url in files if _BROCHURE_FILE.search(name)), None)
    if named:
        return named
    pdfs = [(name, url) for name, url in files if _PDF_NAME.search(name)]
    if len(pdfs) == 1 and not _NOT_BROCHURE.search(re.sub(r"[_\-.]+", " ", pdfs[0][0])):
        return pdfs[0][1]
    return None


def _register_url(title: str, links: list[tuple[str, str]]) -> str | None:
    """A registration link, only when it is clearly one."""
    for text, href in links:
        if _REGISTER_WORDS.search(text) and valid_url(href, SITE_URL):
            return valid_url(href, SITE_URL)
    for match in _URL_IN_TEXT.finditer(title):  # a link written in the title itself
        if _REGISTER_WORDS.search(title[max(0, match.start() - 40):match.start()]):
            return valid_url(match.group().rstrip(".,;)"), SITE_URL)
    return None


def build_event(item: dict, details: dict | None, today: date) -> dict:
    title = clean_name(strip_phones((details or {}).get("title") or item["title"]))
    if details:
        start = details["dates"][0] if details["dates"] else None
        end = details["dates"][1] if len(details["dates"]) > 1 else start
        raw_start, raw_end = details["date_text"], details["date_text"]
        suspect, raw_dates = check_dates(start, end, raw_start, raw_end, today)
    else:
        start = end = None
        suspect, raw_dates = True, {"start": "", "end": ""}
    venue = strip_phones(details["location"]) if details else ""
    where = locate_text(venue, title)
    tags = derive_tags(title)
    kind = (details or {}).get("time_control")
    mapped = {"blitz": "blitz", "rapid": "rapid", "standard": "classical", "classical": "classical"}
    if kind in mapped:
        tags = merge_tags(tags, {"formats": [mapped[kind]]})
    row_says = rating_from_row((details or {}).get("rating_row"))
    if row_says is not None and tags["fide_rated"] in (None, row_says):
        tags["fide_rated"], tags["fide_how"] = row_says, "stated"  # the site's own setting
    brochure = brochure_link((details or {}).get("files", []))
    organiser = strip_phones((details or {}).get("organiser") or "") or None
    return canonical({
        "id": f"{NAME}-{item['id']}",
        "codes": aicf_codes_in(title),
        "name": title,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "place_text": where["place_text"],
        "state": where["state"],
        "city": where["city"],
        "country": country_for(NAME),
        "brochure_url": brochure,
        "source": NAME,
        "source_url": item["url"],
        "register_url": _register_url(item["title"], (details or {}).get("links", [])),
        "results_url": item["url"],  # the tournament page is where the results appear
        "organiser": organiser,
        "tags": tags,
        "flags": {"dates_suspect": suspect},
        "raw_dates": raw_dates,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
    })


def fetch(client, previous: dict, today: date, **_options):
    """Returns (events, listing state, stats)."""
    form_html = client.get(FEDERATION_URL)
    form = parse_form(form_html)
    items: dict[str, dict] = {}
    for wanted in WANTED_SELECTIONS:
        value = next((v for text, v in form["options"].items() if text.startswith(wanted)), None)
        if value is None:
            raise SourceError(f"Chess-Results menu has no entry '{wanted}'; layout changed?")
        data = dict(form["hidden"])
        data.update({"__EVENTTARGET": form["event_target"], "__EVENTARGUMENT": "",
                     "combo_tur_sel": value, "combo_sort": form["sort"]})
        for item in parse_list(client.post(form["action"], data)):
            items.setdefault(item["id"], item)
    old_events = {e["id"]: e for e in previous.get("events", [])}
    old_listing = previous.get("listing", {})
    events, listing = [], {}
    fide_ids = dict(old_listing.get(FIDE_IDS_KEY) or {})  # kept for every event ever read
    can_fetch = True
    for item in items.values():
        event_id = f"{NAME}-{item['id']}"
        signature = hashlib.sha1(item["title"].encode("utf-8")).hexdigest()[:12]
        old = old_events.get(event_id)
        if old is not None and old_listing.get(item["url"]) == signature and old.get("start"):
            old = dict(old)
            old["results_url"] = old.get("results_url") or item["url"]
            events.append(old)
            listing[item["url"]] = signature
            continue
        details = None
        if can_fetch:
            try:
                details = parse_details(client.get(item["url"] + "&turdet=YES"), item["url"])
            except RequestCapReached:
                can_fetch = False
            except SourceError:
                details = None
        if details is None:
            if old is not None:
                events.append(old)  # keep what we know; the details are tried again next run
            continue  # a tournament we know nothing about yet waits for a later run
        events.append(build_event(item, details, today))
        listing[item["url"]] = signature
        if details.get("fide_event_id"):
            fide_ids[event_id] = details["fide_event_id"]
        else:
            fide_ids.pop(event_id, None)  # the page no longer says it
    if fide_ids:
        listing[FIDE_IDS_KEY] = dict(sorted(fide_ids.items()))
    return events, listing, {"found": len(items), "events_with_details": len(events)}
