# CLAUDE.md — boostchess-tournaments

Gathers chess tournaments (AICF, Kerala Chess Association, chessfee, Chess-Results India,
ChessBase India calendar)
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
5. **Tests must pass before any commit:** `python -m pytest`.
6. **No secrets, no screenshots of desktop windows.** The repo is public; store
   no passwords or tokens.

## Politeness (every source, no exceptions)

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
  has had no successful fetch for 3 days, and when the newest fetch of any source is over
  30 hours old (stale data). The schedule is every 3 hours at minute 17; most runs fetch nothing. `tests/test_daily.py` checks these rules in the
  workflow file; keep them true when you edit it.
- Pages publishes only `data/`. `scripts/verify_published.py` checks the live files.

## Layout

- `scripts/build_events.py` — the run (`run()`), manual files, meta, CLI.
- `scripts/dedup.py` — finding the same tournament across sources and grouping it (pure).
- `scripts/eventlib.py` — pure helpers and the event record (`canonical()`, `status()`, places, tags,
  `country_for()`, `strip_phones()`, regions).
- `scripts/sources/` — one module per site (`aicf`, `kca`, `chessfee`, `chessresults_ind`,
  `chessbase_calendar`) with `fetch(client, previous, today, **options)` returning
  `(events, listing_state, stats)`; `polite.py` is the shared client. Switch sources in
  `config/sources.json`.
- `data/sources/<name>.json` — per-source snapshots (history, what was already read).
- `tests/` — pytest, fully offline (a fake web in `conftest.py`). `tests/fixtures/` holds saved,
  trimmed, phone-free pages.

## How things work

- Only `requests` and `beautifulsoup4` (pinned in `requirements.txt`) plus the standard library.
  `pytest` is in `requirements-dev.txt`.
- Event id: `aicf-<first code>`; no code gives `aicf-<hash of name + start>`; two different events
  sharing a code get a name-hash suffix. Other sources: `<source>-<their id>` (KCA: `kca-736-CAK-2026` from code
  `736/CAK/2026`, which also goes into `codes`). Manual ids never
  start with `aicf-`.
- Duplicates (`scripts/dedup.py`): records are **grouped, never removed or hidden**. Every event
  has `group_id`; non-primary members get `merged_into`; the primary gets `also_listed_on` and fills
  only its gaps. Rules in order: country, state/city (only when both known), start within ±1 day,
  name word-set score, section guard (rating limit / age / category letter / format), strong proof
  (shared AICF code or Chess-Results page beats 2–5; same brochure beats the name only), score
  ≥0.80 same, 0.50–0.80 `flags.possible_duplicate_of`. Same-source records are never grouped by the
  algorithm; `data/manual/pairs.csv` (same / not_same) beats everything. Primary: AICF with good
  dates, else manual > kca > chessfee > chessresults_ind > chessbase_calendar. A KCA `city` is a
  district: it matches the towns inside it (`kerala_district()`), unknown towns never block. If two AICF events share a
  code, that code proves nothing. Every same/possible pair goes to `data/review/dedup_review.csv`.
- Tags (format, `fide_rated`) need evidence (name, category label, time control, group member);
  `fide_rated` is true / false (says non-rated) / null, with `fide_how` "stated" / "inferred"
  (grandmaster, norm or "International ... Open" names, or a rated sibling section) / null. Only a
  true is ever shared (sections, groups); a false never is.
- Overrides are re-applied from scratch each run; replaced values are remembered in `overridden`.
- No `status` is stored. `status(event, today)` computes ongoing/upcoming/past in Indian time
  (fixed UTC+05:30, no DST, so no `tzdata` needed).
- Schema version is `SCHEMA_VERSION` (now 5). Bump it, update the README and add a migration in
  `canonical()` whenever the shape of an event changes; stored events are read through `canonical()`.
- `only_timestamps_changed()` tells a daily job whether anything except `generated_at`/`last_seen`
  /per-source times changed (`--github-output` writes `real_changes=...`).
- Output is deterministic: UTF-8, LF, 2-space indent, fixed key order.
- KCA writes the year once (the end's): a start month later than the end month means the
  start is in the year before. Dates set, not suspect, the text kept in `raw_dates` (reading the
  page's format, not guessing; any other end-before-start is still flagged).
- Do not hit live sites while developing. Use `--html tests/fixtures/...` or the test suite.

## Not done yet

- ChessBase calendar: only the default month of each year page is readable without its data service.
