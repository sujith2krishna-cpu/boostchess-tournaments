# boostchess-tournaments

A small tool that reads the public list of chess tournaments from the
All India Chess Federation website and turns it into one tidy file,
`data/events.json`. Old tournaments are kept, and you can add your own
tournaments or fix mistakes by editing two simple spreadsheet-style files.

> **Source: All India Chess Federation, aicf.in. Dates and details can contain
> errors; always check with AICF.**

The same JSON file is used by both the website and the Android app, so a fix
made here shows up in both.

## What it does

1. Downloads <https://aicf.in/all-events/> (one request per run, politely, with a
   clear name: `BoostchessBot`).
2. Reads the table of tournaments and cleans it up (dates, codes, place, state).
3. **Keeps history.** A tournament is never deleted. If AICF removes one from its
   page, we keep it and mark it `gone_from_source`.
4. Adds your own tournaments from `data/manual/events.csv`.
5. Applies your fixes from `data/manual/overrides.csv`.
6. Writes `data/events.json` and `data/meta.json`.

If the AICF page looks broken (for example far fewer rows than usual), the tool
**stops and leaves the existing data exactly as it was**.

## Running it

You need Python 3.

```powershell
pip install -r requirements.txt
python scripts/build_events.py
```

To run the tests: `pip install -r requirements-dev.txt` and then `pytest`.

At the end it prints a short summary: how many events, how many have doubtful
dates, and how many are ongoing, upcoming or past today (Indian time).

## The files

### `data/events.json`

```json
{
  "schema_version": 1,
  "generated_at": "2026-11-24T10:30:00+05:30",
  "events": [ { ...one event... } ]
}
```

Events are sorted by start date. One event looks like this:

| Field | Meaning |
|---|---|
| `id` | `aicf-<first code>`, or `aicf-<short hash>` when AICF gave no code; `manual-...` for your own. Never changes. |
| `codes` | The 6-digit AICF codes (some events have two). |
| `name` | Name of the tournament. |
| `start`, `end` | Dates as `YYYY-MM-DD`. `null` when AICF's date is unreadable. |
| `place_text` | Place exactly as a person would read it, e.g. `Banka, Bihar`. |
| `state`, `city` | Best guess from the place, or `null` when we are not sure. |
| `brochure_url` | Link to the brochure, or `null`. |
| `source` | `aicf` or `manual`. |
| `register_url`, `organiser` | Empty (`null`) for now. |
| `tags` | `formats` (list of `classical`, `rapid`, `blitz`), `fide_rated` (`true` or `null`), `age` (like `U11` or `null`), `open`, `girls` (`true` or `null`). Only set when the name clearly says so; never guessed. |
| `flags` | `dates_suspect` (the dates look wrong), `code_expanded` (AICF wrote `472175/76`, we read it as `472175` and `472176`), `code_unclear`. |
| `raw_dates` | The dates exactly as AICF wrote them, kept when they look wrong. |
| `first_seen`, `last_seen` | The first and last day we saw it on the AICF page. |
| `gone_from_source` | `true` if AICF no longer lists it. |
| `cancelled`, `hidden` | Set by you in `overrides.csv`. The website should skip hidden events. |
| `note` | A free note from you. |
| `overridden` | Bookkeeping: the AICF values that an override replaced. Ignore it. |

There is **no status field**. Whether an event is *ongoing*, *upcoming* or *past*
is worked out from `start` and `end` and today's date in Indian time
(`Asia/Kolkata`). An unusable end date counts as a one-day event. The helper
`status(event, today)` in `scripts/build_events.py` shows the rule.

### `data/meta.json`

Counts for a quick health check: `generated_at`, `scraped_count`, `manual_count`,
`total`, `suspect_dates_count`, `missing_state_count`, `gone_from_source_count`.

## How to add an event yourself

You do not need to install anything. Do it on the GitHub website:

1. Open the repository on GitHub and go to the folder `data` → `manual`.
2. Click `events.csv`.
3. Click the pencil icon (**Edit this file**).
4. Go to the end of the file and add one new line for your tournament.
5. Click **Commit changes…** and confirm.

The next time the tool runs, your tournament appears in `events.json`.

Columns (in this order):
`id, name, start_date, end_date, place, state, link, brochure_url, format, age, note`

Only **name** and **start_date** are required. Example row:

```csv
id,name,start_date,end_date,place,state,link,brochure_url,format,age,note
pune-club-rapid-2027,Pune Club Rapid Under-11,05-01-2027,06-01-2027,"Pune, Maharashtra",,https://example.org/register,,rapid,U11,Entry at the door
```

Tips:

- Dates can be `DD-MM-YYYY` (25-12-2026) or `YYYY-MM-DD` (2026-12-25).
  Leave `end_date` empty for a one-day event.
- `id` is optional. If you give one (letters, digits, dashes), you can later edit
  the row freely and the event stays the same event. Without an id, changing the
  name or start date creates a new event. It may not start with `aicf-`.
- If a value contains a comma, put it in double quotes, like `"Pune, Maharashtra"`.
- `format` can be `rapid`, `blitz`, `classical` (or e.g. `rapid/blitz`). `age`
  can be `U11` or `Under-11`. `link` and `brochure_url` must start with `https://`.
- `state` may be left empty; we try to work it out from `place`.
- To remove an event you added, delete its line. (Git keeps the history of the file.)

## How to fix or hide an event (`overrides.csv`)

AICF's own events cannot be edited directly because they are re-read every day.
Instead, add a line to `data/manual/overrides.csv`. Columns:
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

Order of importance: **override > manual event > AICF**. Delete the line and the
event goes back to what AICF says. A key that matches nothing is only a warning.

## What happens when a row has a mistake

If a line in `events.csv` or `overrides.csv` has a problem (a date that does not
exist, an empty name, a misspelt state, a web address without `https://`, ...)
the tool **stops and writes nothing**. The old `events.json` stays as it was. It
prints a message in plain words that names the file, the line number and what is
wrong, for example:

```
data/manual/events.csv line 4: end_date 2027-02-03 is before start_date 2027-02-05.
```

Fix that line and run it again. (When an automatic daily run is added, the same
message will show in the run's log.)

If an **AICF** date is wrong, the event is **not dropped**: it is kept, the text AICF
wrote is saved in `raw_dates`, `flags.dates_suspect` is `true`, and nothing is
guessed. Use `overrides.csv` to correct it once you have checked the brochure.

## Notes

- Everything here is public information. There are no passwords, keys or tokens
  in this repository; please keep it that way.
- `last_seen` and `generated_at` change on every run; the rest of the files only
  change when something real changes.
