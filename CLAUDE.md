# CLAUDE.md — boostchess-tournaments

Gathers chess tournaments (AICF, Kerala Chess Association, Tamil Nadu State Chess Association,
Karnataka State Chess Association, UP Chess Sports Association, All Odisha Chess Association,
All Bihar Chess Association, chessfee, Chess-Results India, ChessBase India calendar)
into `data/events.json`, keeps history, accepts manual events and overrides. The JSON is
shared by the web site and the Android app, so changing its shape affects both.

## Rules (do not break these)

1. **Never delete events.** An event that vanishes from a source stays, with
   `gone_from_source = true` and its old `last_seen`. Hiding is done with
   `overrides.csv` (`hide`), never by removing data.
2. **Never overwrite good data with a bad fetch.** A source that fails, is blocked by
   robots.txt, or returns less than half of last time keeps its previous events; the
   failure goes into `meta.json` and the other sources carry on. If *every* source fails,
   write nothing. Any error in a manual file also means: stop, write nothing.
3. **Never guess dates.** A malformed date or end-before-start keeps the event,
   keeps the raw text in `raw_dates`, sets `flags.dates_suspect = true`, and does
   not "fix" anything. Tags, state, city and country are best effort: leave them
   `null`/empty when unsure.
4. **Keep the manual files human-friendly.** `data/manual/events.csv` and
   `overrides.csv` are edited by non-programmers on the GitHub website. Keep the
   columns simple, accept both `DD-MM-YYYY` and `YYYY-MM-DD`, and write error
   messages in plain words that name the file, the line number and the problem.
5. **Tests must pass before any commit:** `python -m pytest`. Every pull request now shows a test
   check (`.github/workflows/tests.yml`, check `pytest`); never merge while it is red. That
   workflow only reads (`contents: read`, no secrets, no commit, no publishing, its own concurrency
   group); `tests/test_pr_checks.py` keeps it that way. The tests fail on any real network connection
   (`no_network` in `conftest.py`).
6. **No secrets, no screenshots of desktop windows.** The repo is public; store
   no passwords or tokens.

## Politeness (every source, no exceptions)

- **A new source: robots.txt and the terms first.** Before adding (or even trying) any new site,
  fetch only its `robots.txt` and its terms / terms of use / disclaimer pages. Find their addresses
  with a web search, not by opening the site's other pages. Fetch no other page of that site until
  both allow automated reading (no terms page at all counts as no ban; say so). If either forbids
  it, or the calendar needs a login, stop: do not add it, and write down why (as in
  `docs/STATE_SOURCES_T13.md`).
- Read `robots.txt` at the start of every run; if it disallows a path, skip that source
  and log it. Never work around it (for example: ChessBase's `/api/` and the data
  service its calendar page calls are off limits).
- User-Agent `BoostchessBot (+https://github.com/sujith2krishna-cpu/boostchess-tournaments)`.
- Each source at most once every 12 hours (`FETCH_INTERVAL_HOURS`, from its last success in
  meta.json; `--force` / the workflow's force box only for a deliberate manual refresh, never
  the schedule), >= 3 seconds between requests to one site, a timeout,
  one retry, at most 60 requests per site per run. All of this lives in `sources/polite.py`;
  use `PoliteClient` for every request, never `requests` directly.
- Fetch listing pages; fetch an event's details page only when the event is new or its listing
  line changed, and stay inside the cap.
- Use only links the pages themselves offer. Do not invent URL parameters.

## No-copy rules

- Store facts and links only: name, dates, place, state, city, country, organiser, format,
  source, source_url, register_url, brochure_url (a link only).
- Never copy descriptions, posters, images or brochure files.
- **Never store phone numbers** (or e-mail addresses): every piece of text taken from a page
  goes through `strip_phones()`. Fixtures in `tests/fixtures/` use fake numbers only.
- We only link to registration pages; `register_url` is set only when a page clearly labels
  it as registration.

## The daily workflow (`.github/workflows/daily.yml`)

- **Never make the workflow push anything except `data/` changes.** The commit step stages
  `data` only and refuses if anything else is staged. No force pushes, no other branches.
- **Never add secrets or personal tokens.** Use only the built-in `GITHUB_TOKEN`
  (`contents: write` for the data commit; `pages: write` / `id-token: write` only where
  Pages needs them). No `secrets.` anywhere in the workflow.
- Tests run first; a failing test stops everything. The commit happens only when
  `real_changes == 'true'`. The heartbeat (`scripts/heartbeat.py`) fails the run when a source
  has had no successful fetch for 3 days, when the newest fetch of any source is over
  30 hours old (stale data), and when a source has been due for over 6 hours with no fetch
  attempt (missed fetch; it reads meta.json from before the build via `--before`/`--started`). The schedule is every 3 hours at minute 17; most runs fetch nothing. `tests/test_daily.py` checks these rules in the
  workflow file; keep them true when you edit it.
- Pages publishes only `data/`. `scripts/verify_published.py` checks the live files.
- The `alerts` job (needs build and deploy, `if: always()`, `contents: read` + `issues: write` only)
  runs `scripts/health.py alerts`: one "Data alert: ..." issue per problem (a source with
  `failures_in_a_row` >= 2 in meta.json, or the build / deploy job failing), closed after 2 runs
  without it (`<!-- ok-runs: N -->` in the issue body).
- `.github/workflows/weekly.yml` (Monday 01:30 UTC = 07:00 India time, and by hand): `contents: read`,
  `issues: write`, `actions: read` only; comments the report on the one "Weekly data health" issue.
  Neither writes data or publishes. GitHub calls go through `scripts/github_issues.py` (standard
  library, the built-in token), never through the source client. `tests/test_health.py` checks both.

## Layout

- `scripts/build_events.py` — the run (`run()`), manual files, meta, CLI.
- `scripts/dedup.py` — finding the same tournament across sources and grouping it (pure).
- `scripts/quality.py` — the quality report (`data/quality.json`) and the review list
  (`data/review.csv`), both pure; a change in either counts as a real change.
- `scripts/health.py` — the weekly data health report and the data alerts (pure planning, then
  GitHub issues via `scripts/github_issues.py`).
- `scripts/places.py` — India's districts and sub-districts (LGD copy in `config/lgd/`, Government Open Data
  License - India, via the planemad GitHub mirror) for filling an empty state (pure, no network).
- `scripts/eventlib.py` — pure helpers and the event record (`canonical()`, `status()`, places, tags,
  `country_for()`, `strip_phones()`, regions).
- `scripts/sources/` — one module per site (`aicf`, `kca`, `tnsca`, `ksca`, `upcsa`, `aoca`, `abca`, `chessfee`, `chessresults_ind`,
  `chessbase_calendar`) with `fetch(client, previous, today, **options)` returning
  `(events, listing_state, stats)`; `polite.py` is the shared client. Switch sources in
  `config/sources.json`; `"publish": false` (needs `"enabled": false`) also keeps a source's records out of
  every published file. **ChessBase is off and unpublished** (its terms forbid bulk scraping without
  permission; drafts in `docs/PERMISSION_EMAILS.md`); its snapshot is in `archive/`, outside `data/`.
- `data/sources/<name>.json` — per-source snapshots (history, what was already read).
- `tests/` — pytest, fully offline (a fake web in `conftest.py`). `tests/fixtures/` holds saved,
  trimmed, phone-free pages.

## How things work

- Only `requests` and `beautifulsoup4` (pinned in `requirements.txt`) plus the standard library.
  `pytest` is in `requirements-dev.txt`.
- Event id: `aicf-<first code>`; no code gives `aicf-<hash of name + start>`; two different events
  sharing a code get a name-hash suffix. Other sources: `<source>-<their id>` (KCA: `kca-736-CAK-2026` from code
  `736/CAK/2026`, which also goes into `codes`; TNSCA: `tnsca-RR-24-CBE-26-27` from `RR-24/CBE/26-27`, the same way; KSCA: `ksca-7128` from the WordPress post number; UPCSA: `upcsa-96` from the row's `data-id`; AOCA: `aoca-505919` from the first AICF code in the row; ABCA: `abca-<hash of season + name>`). Manual ids never
  start with `aicf-`.
- Duplicates (`scripts/dedup.py`): records are **grouped, never removed or hidden**. Every event
  has `group_id`; non-primary members get `merged_into`; the primary gets `also_listed_on` and fills
  only its gaps. Rules in order: country, state/city (only when both known), start within ±1 day,
  name word-set score, section guard (rating limit / age / category letter / format), strong proof
  (shared AICF code or Chess-Results page beats 2–5; same brochure beats the name only), score
  ≥0.80 same, 0.50–0.80 `flags.possible_duplicate_of`, except when both names name their own, different
  academy / club / foundation / association (`organisers()`: "Vetrious" vs "Dragon"; Vetri = Veteri) and
  neither the venue nor the organiser field matches: then different (not hard). Same-source records are never grouped by the
  algorithm; `data/manual/pairs.csv` (same / not_same) beats everything. Primary: AICF with good
  dates, else manual > kca > tnsca > ksca > upcsa > aoca > abca > chessfee > chessresults_ind > chessbase_calendar. A KCA `city` is a
  district: it matches the towns inside it (`kerala_district()`), unknown towns never block. A UPCSA `city`
  is often a district too (`DISTRICT_SOURCES`, also AOCA and ABCA), so it never blocks either. Renamed towns are one place (`TOWN_RENAMES`: Bangalore = Bengaluru; official renames and two TNSCA spellings,
  Pudukottai, Tirupattur DT; never a district as its town). If two AICF events share a
  code, that code proves nothing. A pairs.csv "same" across a date gap lets the other copies with
  either date join (`dates_vouched()`). Equal scores: lower ids first (`id_order()`), so rebuilds
  never flip. Every same/possible pair goes to `data/review/dedup_review.csv`.
- AICF codes in other sites' names: next to "AICF", or AICF's full form `499268/KA(R)/2026` anywhere
  (`aicf_codes_in()`). `fill_codes_and_state()` (each run, also for stored events) adds them to
  chessfee / Chess-Results / ChessBase `codes` and fills an empty Indian state from: chessfee's
  "TAMILNADU STATE LEVEL" label, the code's state letters, exactly one known town in the venue
  (`town_state_in()`; two towns or none: null), or the name (`name_state_in()`: its towns, state
  names and capital letters in brackets "(TN)" all give one state, and no venue town says otherwise;
  a short form like "UP" outside brackets never counts; two states or none: null), and last
  `places.state_from_places()` over the name, venue and organiser: LGD districts and sub-districts;
  exactly one state; a place in two states never counts alone; a place followed by a venue word
  ("Indore Stadium") is weak, set aside only when two other places agree; `NOT_PLACES` are words, not places. A set state is never changed.
- `quality.json` `states`: shown upcoming events per Indian state / UT (all 36 listed, 0 included), `no_state`,
  `abroad`; they add up to `overall.upcoming.events`, which `verify_published.py` checks.
- review.csv kinds: `missing`, `dates_disagree` (a not-past group whose start dates are >1 day apart),
  `possible_duplicate`; `quality.json` `review` counts all three and `verify_published.py` checks them.
- Tags (format, `fide_rated`) need evidence (name, category label, time control, group member);
  `fide_rated` is true / false (says non-rated) / null, with `fide_how` "stated" / "inferred"
  (grandmaster, norm or "International ... Open" names, but not "International Chess Day" and other day names, an AICF-listed National / State / Asian /
  Zonal championship, or a rated sibling section) / null. "FIDE" next to Open / Chess / Tournament /
  TMT turns an inferred true into "stated" (`fide_named()`); it never creates or flips a value. Only a
  true is ever shared (sections, groups); a false never is.
- Overrides are re-applied from scratch each run; replaced values are remembered in `overridden`
  (tags as `tags.formats` etc.). `fide_rated` / `format` / `age` / `registration_deadline` from
  overrides.csv set `fide_how` "manual" and are re-applied after grouping (also on the group's
  primary), so they win over everything. A cell that is just `?` is "not filled in" (a warning).
- No `status` is stored. `status(event, today)` computes ongoing/upcoming/past in Indian time
  (fixed UTC+05:30, no DST, so no `tzdata` needed).
- Schema version is `SCHEMA_VERSION` (now 6). Bump it, update the README and add a migration in
  `canonical()` whenever the shape of an event changes; stored events are read through `canonical()`.
- `only_timestamps_changed()` tells a daily job whether anything except `generated_at`/`last_seen`
  /per-source times changed (`--github-output` writes `real_changes=...`).
- Output is deterministic: UTF-8, LF, 2-space indent, fixed key order.
- KCA writes the year once (the end's): a start month later than the end month means the
  start is in the year before. Dates set, not suspect, the text kept in `raw_dates` (reading the
  page's format, not guessing; any other end-before-start is still flagged).
- TNSCA (`tamilchess.com`): always ask for a year (`?y=YYYY`, the page's own menu); without it the
  *All Events* table shows 2017. One request per year page, then event pages (below).
- KSCA (`karnatakachess.com/tournaments/`, The Events Calendar): list pages, following the
  page's own *Next Events* link (`MAX_PAGES` 8), then event pages (below). Start from the `<time datetime>`; an end without a
  year is in the start's year, else flagged. Category *FIDE Rating Events* = `fide_rated` "stated".
  `tests/fixtures/sources/ksca_tournaments_page2_made.html` is made by hand (said so inside it).
- KSCA and TNSCA event pages (`sources/event_pages.py`, allowed by both sites' robots.txt and terms,
  checked 28 Nov 2026): only the own page of an event we list that is not over, only when it is new
  or its list line changed, at most `MAX_EVENT_PAGES` (45) a run, soonest first. Only the event's
  text is read (KSCA `.tribe-events-single-event-description`, TNSCA `.detail-text`; TNSCA's theme
  has a block of unrelated advertising links). brochure = a labelled link or the only PDF;
  register = a link labelled registration. Never mailto/tel/WhatsApp/"@" (the pages show the
  organiser's phone and e-mail). Found links live in the listing under `event_pages`; a failed page
  changes nothing and a found link is never removed.
- Chess-Results details: the *Rating calculation* row gives `fide_rated` "stated" (international: true; national
  only / not rated: false; "-": nothing; disagrees with the name: the name stays). Brochure: a brochure-named file,
  else the only PDF unless it looks like results / pairings / ranks / players / prizes / rules / minutes.
  *Number of rounds* is not stored (no schema field). *FIDE-Event-ID* (6 digits) is kept in the snapshot's
  `listing.fide_event_ids` and becomes an AICF code (`add_fide_event_codes()`) only when exactly one AICF event has
  that code and no other code. `scripts/refresh_chessresults.py` re-reads the stored pages
  once, by hand (fetch into a folder outside the repo, max 400 pages, then apply offline); never from the workflow.
- UPCSA (`upchess.org/tournament.php`): one request, the table only. `registration_deadline` = the end of the
  normal entry dates (not the late-fee dates), only when it is a real date not after the event.
- AOCA (`odishachess.com/calendar/`): one request; every season tab, the state-event columns only (the national
  columns are AICF's own events). Codes `505919/505920/OD(S)/2026` go into `codes`; a section-only name gets
  "Odisha State ... Chess Championship". Kept: upcoming, ongoing, ended in the last 60 days; unscheduled rows
  (a name and nothing else) are not events. `found` = all rows on the page (the half-rule watches the page, not age).
- ABCA (`biharchess.org`): the home page's *Tournament Calendars* menu, then the newest two season pages. The
  2026-27 page has **no years** in its dates. A year only from the event itself (date cell, one year in the name,
  a full date in the circular's file name = first or last day), all agreeing; never from the season. Unclear:
  no dates, `dates_suspect`, text in `raw_dates`, and review.csv lists it (shown, not past, no start date). Undated
  rows are kept only from the newest page and only without a results link (played = has results).
- Telangana (`chesstelangana.com`) is **not** a source: its Terms of Service forbid spidering, crawling and
  scraping (section 12) and copying without permission (section 2). Its "TSCA Registered Players" list has
  players' details; never read it. `strip_phones()` also removes a labelled date of birth ("DOB: 12-03-2014");
  no record field ever holds one (`tests/test_t13.py`).
- Do not hit live sites while developing. Use `--html tests/fixtures/...` or the test suite.

## Not done yet

- ChessBase calendar: only the default month of each year page is readable without its data service.
- Bihar 2026-27: events whose year the event itself does not give wait on review.csv for dates from
  their circular (overrides.csv). Telangana: only with the association's written permission
  (`docs/STATE_SOURCES_T13.md`).
- Website / app (data is ready, not built yet): show "not stated" labels for an unknown format,
  FIDE status or state, show `registration_deadline`, and a review/admin page built from
  `data/review.csv` and `data/quality.json`. Both must accept schema 6.
