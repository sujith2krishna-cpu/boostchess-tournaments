# Telangana, Odisha and Bihar state associations (28 Nov 2026)

Each site was checked before anything was added: robots.txt, the site's terms, whether the
calendar needs a login, and whether it was updated in the last 6 months. Every request used our
User-Agent through `PoliteClient` (robots.txt first, 3 seconds apart).

## Summary

| State | Official site | Calendar page | robots.txt | Terms | Login | Updated | Decision |
|---|---|---|---|---|---|---|---|
| Telangana | Telangana State Chess Association, <https://www.chesstelangana.com/> | `/events/`, `/calendar/` | allows everything | **forbid it**: Terms of Service section 12 (i): you may not use the site "to spam, phish, pharm, pretext, spider, crawl, or scrape"; section 2: no copying of any part without written permission | No | – | **Not added** |
| Odisha | All Odisha Chess Association (AOCA), <https://odishachess.com/> | `/calendar/` (site menu "Calendar") | allows (only `/wp-admin/` and a few WordPress files are off limits) | none found: the footer's "Disclaimer" link answers 404, the privacy page is WordPress's default text; "Copyright 2026 © All rights reserved" only. We store facts and links, as for every source | No | yes: events up to 12-15 Nov 2026 marked completed; page modified 8 Aug 2026 | **Added** as `aoca` |
| Bihar | All Bihar Chess Association (ABCA), <https://biharchess.org/> | `/calendar-2026-27/` (site menu "Tournament Calendars") | allows (only `/wp-admin/`) | none found; "Copyright © 2026" only | No | yes: events up to 22-24 Nov 2026, circular for 12-13 Dec uploaded Nov 2026 | **Added** as `abca` |

## Telangana

The official site is found through AICF's news and the association's own posts. Its Terms of
Service (operated by Code Nukleus) forbid spidering, crawling and scraping, so the rule "terms
forbid automated reading: do not add" applies. Two listing pages (`/events/`, `/calendar/`) had
been fetched in the same first batch as the terms, before the terms were read. They were deleted
unread and never saved. Nothing from the site is stored, and the site is not in `config/sources.json`.
The site also lists "TSCA Registered Players" (players' details); that must never be read.

Telangana events still reach the data through AICF and Chess-Results (16 shown upcoming events in
Telangana on 28 Nov 2026). Adding the site would need the association's written permission.

## Odisha (`aoca`)

- One page, one request. A tab per season (2026-27 back to 2022-23), one table each. Only the
  left-hand columns (state events) are read; the right-hand columns of the current season list
  AICF's national championships in other states, which AICF's list already has.
- The current season's names are often a section only ("Under 19 (Junior)") plus AICF's code
  (`505919/505920/OD(S)/2026`). The codes go into `codes` and give the id, so the record groups
  with AICF's by its code.
- First real read (28 Nov 2026): 113 rows on the page, 3 of them planned but not scheduled yet.
  Kept: 2 (both ended in the last 60 days; nothing upcoming is listed yet).
  - `aoca-505918` Odisha State Women Chess Championship (30 Oct - 2 Nov): **grouped** with
    `aicf-505918` by the shared AICF code (AICF says 2-5 Nov; the group is past, so it is not on the
    "dates disagree" list).
  - `aoca-505919` Odisha State Under 19 (Junior) Chess Championship (12-15 Nov, Balasore): no other
    record has its codes or a close enough name and date, so it stands alone.

## Bihar (`abca`)

- The home page's menu links one page per season; we read the newest two (3 requests plus
  robots.txt). The 2025-26 page writes full dates ("13-16 Oct. 2025"); **the 2026-27 page does not**
  ("12-13 December"). The 2025-26 page also shows why a season is not a year: its Amateur
  championship was on 15-18 January 2026.
- A year is taken only from the event itself (see `scripts/sources/abca.py`): the date cell, one
  year in the name, or a full date in the circular's file name. In the 2026-27 table that gives
  dates to 2 of 23 rows (the Mandar Rapid, "..., 2026", 5 Apr; Kishanganj, `...-03-05-2026.pdf`,
  3 May), both past.
- First real read (28 Nov 2026): 35 rows on the two pages. Kept: 3, all from 2026-27, all **without
  dates** because the event itself gives no year: Bihar State Rapid (Jehanabad, "12-13 December"),
  Bihar State Blitz (Jehanabad, "13 December"), Bihar State Amateur (Motihari, no date yet). Each
  is on `data/review.csv` with a ready overrides.csv line; the circular for the Rapid and Blitz is
  linked (`brochure_url`). The other 2026-27 rows have results links (played) and are not kept.
  None matched an existing record (no shared code or Chess-Results page, and an event without a
  date is never matched by name alone).

## Dates of birth

No source stores one: there is no field for it, and `strip_phones()` (which every piece of page
text goes through) now also removes a labelled date of birth ("DOB: 12-03-2014", "Date of Birth
12 March 2014"). `tests/test_t13.py` checks the parsers and every committed data file.
