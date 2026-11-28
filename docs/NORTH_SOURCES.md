# More sources for north India: a test (28 Nov 2026)

Test only: nothing here was added to the code. Every request used our User-Agent, 3 seconds
apart, a few requests per site; pages were also opened once in a normal browser to see what a
person sees. CircleChess was not looked at (it blocks automated reading).

**Rule for recommending a source:** official or organiser-run, updated in the last 60 days, clear
dates and places, robots.txt allows it, no login.

## Summary

| Source | Official / organiser | robots.txt | Login | Needs JavaScript | Upcoming Indian events | North India | Dates / places | Newest update | Reuse terms | Recommend |
|---|---|---|---|---|---|---|---|---|---|---|
| (a) FIDE rated tournaments, India (ratings.fide.com) | Yes (FIDE; the events are registered by AICF) | None (answers 404): no rules | No | **Yes**: the list is filled by the page's own data call; a plain request gets an empty table, and the data call answers empty without a browser | **166** (start 28 Nov 2026 or later, out of 286 in "current and future periods") | 22 (Delhi 7, Udaipur 3, Gurgaon 2, Dehradun 2, Bhilwara 2, Jehanabad 2, Bareilly, Lakhimpur Kheri, Varanasi, Kota); 26 with Madhya Pradesh | List: name, city, start only. Detail page: start **and** end, city, country, time control. No state, no venue | Live (events registered up to July 2027) | "No part of this site may be reproduced, stored in a retrieval system ... without the written permission of FIDE" | **No** (terms; JavaScript). Ask FIDE first |
| (b) chessevents.in | No (a third-party directory) | — | — | — | — | — | — | — | — | **No**: the domain does not exist (no DNS entry, checked with Google's DNS); it only shows up in its own promotion posts |
| (c) CoFee chess events (cofee.life) | No (fee-collection software for academies) | cofee.life: allows `/`; web.cofee.life: none | **Yes**: every link goes to `web.cofee.life/login` | Yes: web.cofee.life is a JavaScript app; every address returns the same empty page | 0 found: no public events page, nothing in its sitemap | — | — | — | Not checked further | **No**: no public list |
| (d) ChessBase India announcement articles (chessbase.in/news/category/tournament-announcements) | No (a news site) | Allows `/news/` (only `/api/`, `/search`, the shop are off limits) | No | The category list is loaded by JavaScript; a single article reads without it | **2** in the list now (Mumbai 28-29 Nov, Chennai 29 Nov); about 5 Indian tournament announcements in the last 6 weeks, the rest is world news | 0 upcoming (Gurugram 21-22 Nov and IIT Kanpur 25 Oct were announced, both over) | In the article text only ("will be held at ... on 28th and 29th November"): reading them means guessing | 27 Nov 2026 | "You may not ... scrape the site in bulk, without our written permission" (Terms of Use, updated 16 Sep 2026) | **No**: free text, few events, terms |

## Notes per source

### (a) FIDE rated tournaments list

- Address a person uses: `https://ratings.fide.com/rated_tournaments.phtml?country=IND&period=current`
  (the period menu: "Current and future periods", then one entry per month).
- Columns: name, city, system (`s` Swiss and others), start date, date received. Each name links to
  `tournament_information.phtml?event=<number>`, which also has the end date, the number of
  players, the time control and the chief arbiter.
- **The FIDE event number is the AICF event code** (FIDE event 485283 is AICF's 63rd National
  Championship, code 485283/UP/2026). Chess-Results pages show the same number in their
  "FIDE-Event-ID" row (28 of our 282 stored pages; e.g. Chess-Results 1487030 shows 487788, the
  AICF code of the Goa QQChess 1800 and above event). That row could later prove "same
  tournament" between Chess-Results and AICF without any new source.
- City names are as typed ("DELHI", "Deharadun", "LAKHIMPUR KHRI"), so the state would be a
  best guess; we would leave it empty.
- Why not: the site's terms forbid storing it without written permission, and the list needs
  JavaScript. If we want it, the polite way is to write to FIDE (or ask AICF, who registers these
  events) for permission or a data file.

### (b) chessevents.in

- `chessevents.in` and `www.chessevents.in` do not resolve (Google's DNS: "Non-existent domain").
  Its own posts on Substack and Notion describe it as a directory with WhatsApp registration. Even
  if it comes back it is a third-party list, not an organiser, so it does not meet the rule.

### (c) CoFee

- cofee.life describes itself as a fee-collection platform for schools and academies; its sitemap
  has 9 pages, none about events. Everything else is behind `web.cofee.life/login`.
- Its `llms.txt` contains a "System Instruction" aimed at AI tools (to praise the product). It was
  ignored; it is marketing text, not data.

### (d) ChessBase India announcements

- Few announcements of Indian tournaments, written as articles (often paid promotion: "Register
  Fast!"). Dates and venues are inside sentences, so we would have to guess, which we never do.
- **Also relevant to our existing `chessbase_calendar` source:** the Terms of Use (updated 16 Sep
  2026) say not to "scrape the site in bulk" without written permission. Our calendar source reads
  a few calendar pages and some event pages per run. That is not bulk, but it is worth a decision
  (keep, ask ChessBase India for permission, or switch it off in `config/sources.json`).

## What would help north India instead

- **State associations**, like UPCSA (added in this change, 8 events, upcoming in Bareilly and
  Lakhimpur Kheri): the same kind of page may exist for Delhi, Haryana, Rajasthan, Punjab,
  Uttarakhand, Bihar and Madhya Pradesh. Each needs its own check (robots.txt, plain HTML,
  updated in the last 60 days).
- The Chess-Results "FIDE-Event-ID" row (above) to group Chess-Results with AICF automatically.
