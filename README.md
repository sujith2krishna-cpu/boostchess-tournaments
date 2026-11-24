# boostchess-tournaments

A small tool that gathers chess tournaments in India from public websites into
one tidy file, `data/events.json`. Old tournaments are kept, and you can add your
own tournaments or fix mistakes by editing two simple spreadsheet-style files.

> **Source: All India Chess Federation, aicf.in. Dates and details can contain
> errors; always check with AICF.**
> Events from the other sites are only *listed* there; they are not checked by
> AICF (see "Trust labels" below).

The same JSON file is used by both the website and the Android app, so a fix
made here shows up in both.

## What it does

1. Reads up to four sources (see "The sources"), politely, one after the other.
2. Cleans each entry up (dates, codes, place, state, country).
3. **Keeps history.** A tournament is never deleted. If a site stops listing one,
   we keep it and mark it `gone_from_source`.
4. Joins entries from different sites **only** when they share an AICF event code.
5. Adds your own tournaments from `data/manual/events.csv`.
6. Applies your fixes from `data/manual/overrides.csv`.
7. Writes `data/events.json` and `data/meta.json`.

If a source looks broken (it fails, or gives less than half of last time), the tool
**keeps that source's previous events, notes the problem in `meta.json`, and carries
on with the other sources.** One broken site never stops the rest. Only if *every*
source fails does the run stop, writing nothing.

## The sources

| Source | What we read | What we store |
|---|---|---|
| `aicf` | <https://aicf.in/all-events/> (the whole list, one request) | name, codes, dates, place, brochure link |
| `chessfee` | the *Ongoing* and *Upcoming* pages of <https://www.chessfee.com/>; a tournament's details page only when it is new or its listing card changed | name, dates, venue, organiser, the tournament page link (`source_url`), the **Register Now** link (`register_url`), the category label (in `tags.categories`) |
| `chessresults_ind` | the Chess-Results list for India (`fed=IND`), using the page's own menu: *running (up to 3 weeks)*, *starting in the next 7 days* and *starting later*; a tournament page only when new or changed | name, dates, venue, organiser, tournament page link, a registration link if the page has a clearly labelled one |
| `chessbase_calendar` | the ChessBase India calendar, <https://chessbase.in/chess-calendar>: India and abroad, not online-only | name, dates, place, country, the event page link under `/chess-calendar/event/`, a brochure link |

Rules every source follows:

- We **check `robots.txt` at the start of every run**. If it does not allow a page,
  that source is skipped and the reason is written to `meta.json`.
- One clear name: `BoostchessBot (+https://github.com/sujith2krishna-cpu/boostchess-tournaments)`.
- At most **one run per day**, at least **3 seconds between requests** to the same
  site, a time-out, **one retry**, and at most **60 requests per site per run**.
- We store **facts and links only**. We never copy descriptions, posters, brochure
  files or phone numbers. A brochure is just a link to the organiser's file.
- **We only link to registration pages.** Nobody registers or pays here: the
  *Register* button on the website simply opens the organiser's own page.
- Phone numbers and e-mail addresses found on a page are removed before anything is saved.

Things to know:

- Chess-Results shows at most 50 tournaments per list, so a very busy day can hide some;
  they appear later.
- The ChessBase calendar page only contains the month that is open by default (the
  other months are loaded by the page through a data service that its `robots.txt`
  asks robots not to use, so we do not use it). A run therefore sees the current
  month plus the first month of the next year pages. We do not guess the rest.

### Switching a source off

Open `config/sources.json` (on GitHub: open the file, click the pencil, change `true`
to `false`, commit):

```json
{
  "aicf": {"enabled": true},
  "chessfee": {"enabled": false},
  "chessresults_ind": {"enabled": true},
  "chessbase_calendar": {"enabled": true}
}
```

A switched-off source is not contacted at all. Its old events stay in the file.

### Joining entries and look-alikes

- Two entries become **one event** only when they share an AICF event code (many
  titles on Chess-Results and the other sites say, for example, "AICF Event Code: 502180").
  The event keeps every site's links in `sources`. For each fact the order of
  importance is **override > manual > AICF > the other sites**; gaps (for example a
  missing registration link) are filled from the other sites.
- Without a shared code we **never join**. If two entries from different sites have
  the same start date, a very similar name and the same city, both are kept and the
  later one gets `flags.possible_duplicate_of` set to the other one's `id`.
- If several AICF events share one code, entries with that code are not joined.

### Trust labels

- `listed_by` says who listed it: `aicf`, `chessfee`, `chess-results`, `chessbase`
  or `manual`.
- `verified` is `true` **only for AICF and manual events** (and for an event joined
  to one of them). The other sites' events are listed, not verified.

## Running it

You need Python 3.

```powershell
pip install -r requirements.txt
python scripts/build_events.py
```

A source that was already fetched today is skipped (add `--force` to override).
`--summary-file` and `--github-output` are for the daily Action.
`--html some-saved-aicf-page.html` runs offline with a saved AICF page only.

To run the tests: `pip install -r requirements-dev.txt` and then `pytest`.

At the end it prints a short summary per source and overall: events found, how
many are ongoing, upcoming or past today (Indian time), how many have a register
link, how many were joined, and possible duplicates.

## The daily run (GitHub Action)

Every day at **21:40 UTC (03:10 India time)** GitHub runs `.github/workflows/daily.yml`:

1. runs the tests first (if one fails, nothing is fetched or committed);
2. runs `scripts/build_events.py` (all politeness rules above apply);
3. **commits the new data to `main` only if something real changed** (not just
   timestamps), as `github-actions[bot]`, with a message like
   `data: 2026-11-25 (+3 new, 2 changed; sources ok: aicf, chessfee, chessresults_ind, chessbase_calendar)`.
   Only the `data/` folder is ever committed;
4. publishes the `data/` folder on GitHub Pages (whether or not anything was committed) and
   checks the published files;
5. **heartbeat:** if any source has had no successful fetch for 7 days, the run fails and
   names the source.

Every run has a **job summary** (open the run on GitHub, then *Summary*): per-source
counts, ongoing / upcoming / past, any problems, and whether something was committed.

### Published addresses (for the website and the app)

- <https://sujith2krishna-cpu.github.io/boostchess-tournaments/events.json>
- <https://sujith2krishna-cpu.github.io/boostchess-tournaments/meta.json>

Only the `data/` folder is published. GitHub Pages sends
`Access-Control-Allow-Origin: *`, so a web page can read the file straight from the browser;
every run checks that, that the file is valid JSON, and that its `schema_version` is the one this
code writes.

### Run it by hand

On GitHub: **Actions** tab, **Daily tournament data** on the left, **Run workflow** button
(branch `main`), **Run workflow**. A source that was already fetched on the same Indian day is
skipped (one run per site per day), so a second press the same day does nothing new.

### What a failure e-mail means

GitHub e-mails you when a run fails. Open the run, then *Summary* and the red step:

| Red step | Meaning | What to do |
|---|---|---|
| **Run the tests** | The code or a test is broken. Nothing was fetched. | Fix the code (or revert the last change). |
| **Build the data** | *Every* source failed (or a manual file has a mistake: the message names the file and line). Nothing was written. | Fix the manual row; otherwise wait a day, then see `data/meta.json` → `sources` → `last_error`. |
| **Heartbeat** | One source has had no good fetch for 7 days (the run still published the data). | Look at that source's `last_error`: the site may have changed its pages or blocked us. Fix the module, or switch it off in `config/sources.json`. |
| **Check the published files** | The published `events.json` is wrong or not reachable. | Re-run the workflow; if it repeats, check Settings → Pages. |

If only *one* source fails the run still succeeds: you see a yellow warning on the run and a
**Problems** list in the summary. The failed source keeps its old events.

### Pausing the schedule

Actions tab → **Daily tournament data** → the **...** menu at the top right → **Disable workflow**
(turn it back on the same way). Nothing is lost while it is off. GitHub may also switch off
scheduled runs by itself if a repository has no activity for 60 days; if that e-mail ever comes,
press **Enable workflow**.

## The files

- `data/events.json`, `data/meta.json`: the result (what the website and the app read).
- `data/sources/<name>.json`: what each source last told us (history and what has
  been read already). Only the tool reads these.
- `data/manual/events.csv`, `data/manual/overrides.csv`: edited by you.
- `config/sources.json`: which sources are switched on.

### `data/events.json`

```json
{
  "schema_version": 3,
  "generated_at": "2026-11-24T10:30:00+05:30",
  "events": [ { ...one event... } ]
}
```

Events are sorted by start date.

**Schema version 3** (web and Android must read this version). What changed:

- **Version 3:** new fields `source_url`, `sources` (a list), `listed_by`,
  `verified`, `flags.possible_duplicate_of`, and `tags.categories`. `source`
  can now also be `chessfee`, `chessresults_ind` or `chessbase_calendar`.
- **Version 2:** `tags.age` is a **list** (`["U11"]`, `["U12","U18"]`, or `[]`), and
  every event has a `country`.

One event looks like this:

| Field | Meaning |
|---|---|
| `id` | `aicf-<first code>`, or `aicf-<short hash>` when AICF gave no code; `chessfee-<number>`, `chessresults_ind-<number>`, `chessbase_calendar-<id>`; `manual-...` for your own. Never changes. A joined event keeps the id of its most important entry. |
| `codes` | The 6-digit AICF codes (some events have two). |
| `name` | Name of the tournament. |
| `start`, `end` | Dates as `YYYY-MM-DD`. `null` when the source's date is unreadable. |
| `place_text` | Place as a person would read it, e.g. `Banka, Bihar`. |
| `state`, `city` | Best guess from the place or title, or `null` when we are not sure. |
| `country` | Two-letter country code (ISO 3166). `IN` for aicf, chessfee, chessresults_ind and manual (unless you say otherwise); for chessbase_calendar the event's own country, or `null` if unsure. |
| `brochure_url` | Link to the brochure, or `null`. |
| `source` | The most important source of this event. |
| `source_url` | The event's page on that source. |
| `sources` | **List** of `{source, source_url, register_url}`, one per site that lists the event (more than one only when joined by an AICF code). |
| `listed_by`, `verified` | Trust labels (see above). |
| `register_url` | The organiser's registration link, if a site shows one. We only link to it. |
| `organiser` | Organiser's name when a site shows one. |
| `tags` | `formats` (`classical`, `rapid`, `blitz`), `fide_rated` (`true` or `null`), `age` (list like `["U11"]`, `[]` when unknown), `open`, `girls` (`true` or `null`), `categories` (list of labels from the source, e.g. `"FIDE RAPID"`, `"TAMILNADU STATE LEVEL"`, `"youth"`, and `"abroad"` for an event outside India). Only set when the source clearly says so; never guessed. |
| `flags` | `dates_suspect` (the dates look wrong), `code_expanded` (AICF wrote `472175/76`, we read it as `472175` and `472176`), `code_unclear`, `possible_duplicate_of` (an event `id`, or `null`). |
| `raw_dates` | The dates exactly as the source wrote them, kept when they look wrong. |
| `first_seen`, `last_seen` | The first and last day we saw it on a source. |
| `gone_from_source` | `true` if no source lists it any more. |
| `cancelled`, `hidden` | `cancelled` is set by you in `overrides.csv` or by a source that says so; `hidden` only by you. The website should skip hidden events. |
| `note` | A free note from you. |
| `overridden` | Bookkeeping: the values that an override replaced. Ignore it. |

There is **no status field**. Whether an event is *ongoing*, *upcoming* or *past*
is worked out from `start` and `end` and today's date in Indian time
(`Asia/Kolkata`). An unusable end date counts as a one-day event. The helper
`status(event, today)` in `scripts/eventlib.py` shows the rule.

### `data/meta.json`

Counts for a quick health check: `generated_at`, `scraped_count`, `manual_count`,
`total`, `suspect_dates_count`, `missing_state_count`, `gone_from_source_count`,
and `sources`: for each source `enabled`, `status` (`ok`, `failed`, `skipped`,
`disabled`), `message` (why, when not ok), `count` (events currently listed),
`last_success` (time) and `last_error` (`{at, message}`).

## How to add an event yourself

You do not need to install anything. Do it on the GitHub website:

1. Open the repository on GitHub and go to the folder `data` → `manual`.
2. Click `events.csv`.
3. Click the pencil icon (**Edit this file**).
4. Go to the end of the file and add one new line for your tournament.
5. Click **Commit changes…** and confirm.

The next time the tool runs, your tournament appears in `events.json`.

Columns (in this order):
`id, name, start_date, end_date, place, state, country, link, brochure_url, format, age, note`

Only **name** and **start_date** are required. Example row:

```csv
id,name,start_date,end_date,place,state,country,link,brochure_url,format,age,note
pune-club-rapid-2027,Pune Club Rapid Under-11,05-01-2027,06-01-2027,"Pune, Maharashtra",,,https://example.org/register,,rapid,U11,Entry at the door
us-masters-2027,US Masters,25-11-2027,29-11-2027,"Charlotte, North Carolina",,US,,,,,
```

Tips:

- Dates can be `DD-MM-YYYY` (25-12-2026) or `YYYY-MM-DD` (2026-12-25).
  Leave `end_date` empty for a one-day event.
- `country` is a two-letter code (`IN`, `US`, `GB`, `CA`, `AU`, `DE`, ...). **Leave it
  empty for India.**
- `state`: for India it is checked against the list of Indian states and union
  territories; for `US`, `GB`, `CA` and `AU` against built-in lists (names or
  usual short codes); for any other country it is free text. It may be left empty;
  we try to work it out from `place`.
- `id` is optional. If you give one (letters, digits, dashes), you can later edit
  the row freely and the event stays the same event. Without an id, changing the
  name or start date creates a new event. It may not start with `aicf-`.
- If a value contains a comma, put it in double quotes, like `"Pune, Maharashtra"`.
- `format` can be `rapid`, `blitz`, `classical` (or e.g. `rapid/blitz`). `age`
  can be `U11` or `Under-11`, or several groups like `U12/U18`. `link` and
  `brochure_url` must start with `https://`.
- Please do not put phone numbers in a row; they are removed anyway.
- To remove an event you added, delete its line. (Git keeps the history of the file.)

## How to fix or hide an event (`overrides.csv`)

Events from the websites cannot be edited directly because they are re-read
every day. Instead, add a line to `data/manual/overrides.csv`. Columns:
`key, start_date, end_date, place, state, hide, cancelled, note`

- `key` is the event `id` (like `aicf-472290`) or the 6-digit AICF code (like `472290`).
- Fill in **only** what you want to change; leave the rest empty.
- Write `yes` in `hide` to hide the event, or in `cancelled` to mark it cancelled.

```csv
key,start_date,end_date,place,state,hide,cancelled,note
aicf-473594,03-04-2026,29-04-2026,,,,,Dates swapped on AICF page; checked brochure
aicf-111111,,,,,yes,,Duplicate listing
aicf-222222,,,,,,yes,Cancelled by organiser
aicf-333333,,,"Sagar, Madhya Pradesh",,,,
```

Order of importance: **override > manual event > AICF > other sites**. Delete the
line and the event goes back to what the sites say. A key that matches nothing is
only a warning.

## What happens when a row has a mistake

If a line in `events.csv` or `overrides.csv` has a problem (a date that does not
exist, an empty name, a misspelt state or country, a web address without `https://`, ...)
the tool **stops and writes nothing**. The old `events.json` stays as it was. It
prints a message in plain words that names the file, the line number and what is
wrong, for example:

```
data/manual/events.csv line 4: end_date 2027-02-03 is before start_date 2027-02-05.
```

Fix that line and run it again. (When an automatic daily run is added, the same
message will show in the run's log.)

If a **source's** date is wrong, the event is **not dropped**: it is kept, the text
the source wrote is saved in `raw_dates`, `flags.dates_suspect` is `true`, and
nothing is guessed. Use `overrides.csv` to correct it once you have checked the brochure.

## Notes

- Everything here is public information. There are no passwords, keys or tokens
  in this repository; please keep it that way.
- `last_seen`, `generated_at` and the times in `meta.json` change on every run; the
  rest of the files only change when something real changes. At the end of a run the
  tool says whether only those changed ("Changes vs last run"). A daily job can use
  `python scripts/build_events.py --github-output "$GITHUB_OUTPUT"`, which adds
  `real_changes=true` or `real_changes=false`, to skip a pointless commit.
