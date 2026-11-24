# CLAUDE.md — boostchess-tournaments

Reads the AICF events page (https://aicf.in/all-events/) into `data/events.json`,
keeps history, accepts manual events and overrides. The JSON is shared by the
web site and the Android app, so changing its shape affects both.

## Rules (do not break these)

1. **Never delete events.** An event that vanishes from AICF stays, with
   `gone_from_source = true` and its old `last_seen`. Hiding is done with
   `overrides.csv` (`hide`), never by removing data.
2. **Never overwrite good data with a bad fetch.** Too few rows, a missing table,
   or mostly unreadable dates means stop with a clear error and write nothing.
   Any error in a manual file also means: stop, write nothing.
3. **Never guess dates.** A malformed date or end-before-start keeps the event,
   keeps the raw text in `raw_dates`, sets `flags.dates_suspect = true`, and does
   not "fix" anything. Tags and state are best effort: leave them `null`/empty
   when unsure.
4. **Keep the manual files human-friendly.** `data/manual/events.csv` and
   `overrides.csv` are edited by non-programmers on the GitHub website. Keep the
   columns simple, accept both `DD-MM-YYYY` and `YYYY-MM-DD`, and write error
   messages in plain words that name the file, the line number and the problem.
5. **Tests must pass before any commit:** `python -m pytest`.
6. **No secrets, no screenshots of desktop windows.** The repo is public; store
   no passwords or tokens.

## Layout

- `scripts/build_events.py` — the whole tool (`run()` is the entry point; `main()` the CLI).
- `tests/` — pytest, fully offline. `tests/fixtures/` holds a saved copy of the AICF table.
- `data/events.json`, `data/meta.json` — generated. `data/manual/*.csv` — hand-edited.

## How things work

- Only `requests` and `beautifulsoup4` (pinned in `requirements.txt`) plus the
  standard library. `pytest` is in `requirements-dev.txt`.
- One request per run, `BoostchessBot` User-Agent, 30 s timeout, one retry.
- Event id: `aicf-<first code>`; no code gives `aicf-<hash of name + start>`; two
  different events sharing a code get a name-hash suffix. Manual ids never start with `aicf-`.
- Precedence: override > manual > scraped. Overrides are re-applied from scratch each
  run; replaced values are remembered in `overridden` so removing a row restores them.
- No `status` is stored. `status(event, today)` computes ongoing/upcoming/past in
  Indian time (fixed UTC+05:30, no DST, so no `tzdata` needed).
- Schema version is `SCHEMA_VERSION` (now 2). Bump it, update the README and add a
  migration in `canonical()` whenever the shape of an event changes; old stored
  events (gone from the page) are read through `canonical()`.
- `tags.age` is a sorted list (`[]` when unknown). `country` comes from `country_for()`.
- `only_timestamps_changed()` tells a daily job whether anything except
  `generated_at`/`last_seen` changed (`--github-output` writes `real_changes=...`).
- Output is deterministic: UTF-8, LF, 2-space indent, fixed key order. Only
  `generated_at` (and `last_seen` for events on the page) change between runs.
- Do not hit the live site while developing. Use `--html tests/fixtures/...` or
  the test suite.

## Not done yet

- GitHub Action to run daily (task T2).
- `register_url` and `organiser` stay `null` for AICF events.
