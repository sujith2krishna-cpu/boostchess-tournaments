"""Brochure and registration links from a state association's own event pages (KSCA, TNSCA).

The list pages give each event's own page. We read that page only for events we already list
that are not over, only when the event is new or its listing line changed since we last read
its page, and at most MAX_EVENT_PAGES pages per run (the soonest events first; the rest wait
for a later run). Inside the page we look only at the event's own text (the caller names the
container), never at menus, sidebars or footers.

- brochure: a link labelled brochure / prospectus / circular / flyer / invitation, else the
  only PDF in the text (more than one unlabelled PDF: none, we do not pick one);
- register: a link clearly labelled as registration ("Register", "Registration link").

Only links: no text, no files, and never an e-mail address or phone number (mailto:, tel:,
WhatsApp and anything with an "@" are skipped). What a page gave is kept in the listing state
under EVENT_PAGES_KEY. A page that cannot be read changes nothing, and a link once found is
never removed: a later read can only replace it with another link.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString

from eventlib import RequestCapReached, SourceError, SourceSkipped, status, valid_url

MAX_EVENT_PAGES = 45  # with the list pages and robots.txt this stays under the 60-request cap
EVENT_PAGES_KEY = "event_pages"
LINK_FIELDS = ("brochure_url", "register_url")

_BROCHURE_WORDS = re.compile(r"(?i)\b(?:brochure|broucher|prospectus|circular|flyer|invitation)s?\b")
_REGISTER_WORDS = re.compile(r"(?i)\bregist(?:er|ration)\b")
_SKIP_HOSTS = ("wa.me", "whatsapp.com", "maps.google.", "google.com", "outlook.", "facebook.com",
               "twitter.com", "x.com", "instagram.com", "youtube.com", "linkedin.com")
_BLOCKS = ("p", "li", "td", "th", "div", "h1", "h2", "h3", "h4", "h5", "h6")


def _label_before(link, block) -> str:
    """The text just before the link inside its paragraph ("Download prospectus :")."""
    parts = []
    for node in block.descendants:
        if node is link:
            break
        if isinstance(node, NavigableString):
            parts.append(str(node))
    return " ".join("".join(parts).split())[-60:]


def page_links(html: str, page_url: str, container: str, not_links: tuple = ()) -> dict | None:
    """{'brochure_url', 'register_url'} from the event text in `container` (a CSS selector);
    None when the page has no such container (layout changed: keep what we have). Links that
    start with one of `not_links` (the site's own calendar pages) are never taken."""
    box = BeautifulSoup(html, "html.parser").select_one(container)
    if box is None:
        return None
    labelled, pdfs, register = None, [], None
    for a in box.find_all("a", href=True):
        href = a["href"].strip()
        if "@" in href or href.lower().startswith(("mailto:", "tel:", "webcal:", "javascript:")):
            continue
        url = valid_url(href, page_url)
        if not url or url.startswith(tuple(not_links) or ("\0",)) \
                or any(h in (urlparse(url).hostname or "") for h in _SKIP_HOSTS):
            continue
        block = a.find_parent(_BLOCKS) or box
        text = a.get_text(" ", strip=True)
        label = f"{text} {_label_before(a, block)}"
        is_pdf = urlparse(url).path.lower().endswith(".pdf") or "pdfemb-viewer" in (a.get("class") or [])
        if not is_pdf and (_REGISTER_WORDS.search(text) or _REGISTER_WORDS.search(label)):
            register = register or url
            continue
        if _BROCHURE_WORDS.search(label) and labelled is None:
            labelled = url
        if is_pdf and url not in pdfs:
            pdfs.append(url)
    return {"brochure_url": labelled or (pdfs[0] if len(pdfs) == 1 else None), "register_url": register}


def read_event_pages(client, events: list[dict], listing: dict, old_state: dict, today: date,
                     container: str, site_url: str, not_links: tuple = ()) -> tuple[list[dict], dict, dict]:
    """Reads the event pages that are due and puts the links on the events.

    `listing` is the source's new {event id: listing signature}; `old_state` is what the last
    runs found ({event id: {'sig', 'brochure_url', 'register_url'}}). Returns (events with the
    links, the new state, stats)."""
    state = {key: dict(old_state[key]) for key in listing if key in old_state}
    due = [e for e in events
           if e["id"] in listing and (e.get("source_url") or "").startswith(site_url)
           and status(e, today) != "past"
           and state.get(e["id"], {}).get("sig") != listing[e["id"]]]
    due.sort(key=lambda e: (e.get("start") or "9999", e["id"]))
    read = failed = 0
    for event in due[:MAX_EVENT_PAGES]:
        try:
            found = page_links(client.get(event["source_url"]), event["source_url"], container, not_links)
        except RequestCapReached:
            break
        except (SourceError, SourceSkipped):
            found = None
        if found is None:
            failed += 1  # keep what we had; tried again next run
            continue
        read += 1
        old = state.get(event["id"], {})
        state[event["id"]] = {"sig": listing[event["id"]],
                              **{f: found[f] or old.get(f) for f in LINK_FIELDS}}
    out = []
    for event in events:
        known = state.get(event["id"])
        if known and any(known.get(f) and not event.get(f) for f in LINK_FIELDS):
            event = dict(event)
            for f in LINK_FIELDS:
                event[f] = event.get(f) or known.get(f)
        out.append(event)
    stats = {"event_pages_read": read, "event_pages_failed": failed,
             "event_pages_waiting": max(0, len(due) - MAX_EVENT_PAGES),
             "brochure_links": sum(1 for v in state.values() if v.get("brochure_url")),
             "register_links": sum(1 for v in state.values() if v.get("register_url"))}
    return out, dict(sorted(state.items())), stats
