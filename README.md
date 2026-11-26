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

1. Reads up to seven sources (see "The sources"), politely, one after the other.
2. Cleans each entry up (dates, codes, place, state, country).
3. **Keeps history.** A tournament is never deleted. If a site stops listing one,
   we keep it and mark it `gone_from_source`.
4. Adds your own tournaments from `data/manual/events.csv`.
5. Applies your fixes from `data/manual/overrides.csv`.
6. **Finds the same tournament on several sites and groups the records** (none is removed;
   see "Duplicates across sites").
7. Writes `data/events.json`, `data/meta.json`, the check list `data/review/dedup_review.csv`,
   the quality report `data/quality.json` and your daily to-do list `data/review.csv`
   (see "Daily review (10 minutes)").

If a source looks broken (it fails, or gives less than half of last time), the tool
**keeps that source's previous events, notes the problem in `meta.json`, and carries
on with the other sources.** One broken site never stops the rest. Only if *every*
source fails does the run stop, writing nothing.

## The sources

| Source | What we read | What we store |
|---|---|---|
| `aicf` | <https://aicf.in/all-events/> (the whole list, one request) | name, codes, dates, place, brochure link |
| `kca` | the Kerala Chess Association's events page, <https://www.keralachessassociation.com/events>: the *Upcoming & Ongoing* list, plus events in the *Completed* list that ended in the last 60 days (the previous year's list, through the page's own year menu, only when those 60 days reach back into it; older years are not read); an event's page only for upcoming events that are new or whose row changed | name, KCA event code (in `codes`, e.g. `736/CAK/2026`), dates, district (as `city`), state `Kerala`, venue, the event page link (`source_url`), brochure link, a registration link only if the page has a working one. The type label: **FIDE** gives `fide_rated` = `true` ("stated"); **STATE** gives the category `KCA state rated` and leaves `fide_rated` empty; **EVENT** adds nothing |
| `tnsca` | the Tamil Nadu State Chess Association calendar, <https://tamilchess.com/tournament-registration/>: this year's page (`?y=2026`, from the page's own year menu), next year's page when the menu offers it, and last year's page only in January and February; one request per page, no event pages. Upcoming events and those that ended in the last 60 days are kept | name, TNSCA event code (in `codes`, e.g. `RR-24/CBE/26-27`), dates, place (as `city`), state `Tamil Nadu`, the event page link (`source_url`). A row that is also in the page's *Fide Rated Events* table gives `fide_rated` = `true` ("stated"). No registration or brochure links (those are on the event pages, which we do not read) |
| `ksca` | the Karnataka State Chess Association tournaments list, <https://karnatakachess.com/tournaments/>: page 1 and the next pages through the page's own *Next Events* link (at most 8 pages, about 12 events each); upcoming and ongoing events only, no event pages | name, dates (the start from the page's machine-readable date, the end from its text), venue and address (as `place_text`), town (as `city`) and state from the address, the event page link (`source_url`), the category in `tags.categories` (*FIDE Rating Events*, *National Events*, *State Selection Tournaments*, *Monthly Tournaments*). An event filed under **FIDE Rating Events** gives `fide_rated` = `true` ("stated"). No registration or brochure links (those are on the event pages, which we do not read) |
| `chessfee` | the *Ongoing* and *Upcoming* pages of <https://www.chessfee.com/>; a tournament's details page only when it is new or its listing card changed | name, dates, venue, organiser, the tournament page link (`source_url`), the **Register Now** link (`register_url`), the category label (in `tags.categories`) |
| `chessresults_ind` | the Chess-Results list for India (`fed=IND`), using the page's own menu: *running (up to 3 weeks)*, *starting in the next 7 days* and *starting later*; a tournament page only when new or changed | name, dates, venue, organiser, tournament page link, a registration link if the page has a clearly labelled one |
| `chessbase_calendar` | the ChessBase India calendar, <https://chessbase.in/chess-calendar>: India and abroad, not online-only | name, dates, place, country, the event page link under `/chess-calendar/event/`, a brochure link |

Rules every source follows:

- We **check `robots.txt` at the start of every run**. If it does not allow a page,
  that source is skipped and the reason is written to `meta.json`.
- One clear name: `BoostchessBot (+https://github.com/sujith2krishna-cpu/boostchess-tournaments)`.
- Each source is fetched **at most once every 12 hours**, with at least **3 seconds between requests** to the same
  site, a time-out, **one retry**, and at most **60 requests per site per run**.
- We store **facts and links only**. We never copy descriptions, posters, brochure
  files or phone numbers. A brochure is just a link to the organiser's file.
- **We only link to registration pages.** Nobody registers or pays here: the
  *Register* button on the website simply opens the organiser's own page.
- Phone numbers and e-mail addresses found on a page are removed before anything is saved.

Things to know:

- Chess-Results shows at most 50 tournaments per list, so a very busy day can hide some;
  they appear later.
- The KCA events page writes the year once, after the end date, and it is the end date's
  year. So when the start month comes later than the end month ("Dec 29 - Jan 02, 2026"),
  the tournament started in the year before: 29 Dec 2025 to 2 Jan 2026. Such an event is not
  flagged as suspect, and the page's own text stays in `raw_dates` so it can be checked.
- KCA gives a **district**, not a town, as the place (stored as `city`). When records are
  compared, a district matches the towns inside it (Ernakulam matches Kochi or Aluva), two
  different districts never match, and a town we do not know is "unknown", never "different".
- The TNSCA calendar page without `?y=` shows **2017** in its *All Events* table, so we always ask
  for a year from the page's own menu. Its *Place* is sometimes a district rather than the town
  (`Chengalpattu` for suburbs of Chennai), and its spellings can differ from AICF's (`Pudukottai` /
  `Pudukkottai`, `Tirupattur` / `Tirupattur DT`); such records are not grouped automatically yet,
  use `pairs.csv` if they matter.
- The KSCA list writes the year only when it is not the current one ("December 30 @ 9:00 am -
  January 3, 2027 @ 6:00 pm"). An end without a year is in the start's year; if that puts the end
  before the start, the event is flagged as suspect and the text kept, never fixed. Events leave the
  list once they are over, so a finished KSCA event is kept with `gone_from_source` = `true`.
- Renamed towns count as one place when records are compared (`Bangalore` / `Bengaluru`,
  `Belgaum` / `Belagavi`, `Hubli` / `Hubballi`, `Bombay` / `Mumbai`, ...: `TOWN_RENAMES` in
  `scripts/dedup.py`, official renames only). A short AICF name can still be too vague to prove a
  match (`INVENTIVE 2.0 FIDE-rated Rapid Chess Tournament` has one distinctive word); use
  `pairs.csv` for those.
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

### Duplicates across sites

Many tournaments are listed on two or three sites. **Every site's record stays in
`events.json`**; records of the same tournament are **grouped**, never removed or hidden.

- Every event has a `group_id`. In a group of several records one is the **primary**: the AICF
  record if there is one and its dates are not suspect; otherwise manual, then KCA, then TNSCA, then KSCA, then chessfee,
  then Chess-Results, then ChessBase. The others get `merged_into` = the primary's `id`.
- **Website and app: show only events with `merged_into` = `null`** (and `hidden` = `false`).
  The primary lists the other sites in `also_listed_on` and fills its own gaps (registration,
  results and brochure links, city, state, organiser) from them. It never overwrites a value it
  already has. If the primary's dates are suspect and another record's are fine, the primary
  shows those dates and `dates_from` names the record they came from (`raw_dates` still shows
  what its own site wrote).

How two records from **different sites** are compared, in this order:

1. Different country: not the same.
2. Different state, or different city: not the same, but only when **both** are known. A
   missing state or city never blocks.
3. Start dates more than 1 day apart: not the same. End dates are not used (sites often get
   them wrong).
4. Names are cleaned up. First the **tails** that Chess-Results often adds at the end are
   dropped: "Organised by ...", a bracketed person's name like "(Mr. ...)", a date
   ("20th Dec 2026", "-> 27 Nov 2026 - 29 Nov 2026", "2 to 6 DEC") and a place that equals the
   event's own city ("... - Coimbatore"), only at the very end and never the whole name. Then:
   lower case, no punctuation, no dates written in the title ("29 NOV"),
   no years, no Indian state names, no "CITY - " in front, no filler words (chess, tournament,
   international, open, fide, rated, rating, edition, the, of, level, championship, prize fund,
   ...). The remaining words are compared as a **set**, in any order: shared words divided by
   all words. A name with fewer than 2 distinctive words can never prove "same" on its own.
5. **Section guard:** if the rating limit ("below 1800", "above 2100", "U1600"), the age group
   (U11, ...), the category letter ("Category B" vs "Category C") or the format (rapid vs
   blitz, when both say one) differ, they are **not** the same, whatever else matches.
6. **Strong proof:** the same AICF event code or the same Chess-Results page means the same
   tournament (this beats rules 2 to 5). The same brochure link beats the name (rule 4) only,
   because one brochure often covers several sections.
7. **Score** = 0.85 x name + 0.10 x place (same city 1, same state 0.5) + 0.05 x same end
   date. **0.80 or more: same group. 0.50 to 0.80: kept apart and flagged** with
   `flags.possible_duplicate_of` (the better-ranked record's `id`). Below 0.50: different.

Two records from the same site are never grouped automatically, and a group never takes in two
records that a rule above calls different (so two sections cannot end up together through a
third record). If several AICF events share one code, that code proves nothing.

**Check list:** `data/review/dedup_review.csv` lists every *same* and *possible* pair, lowest
score first: both ids, sources, names, dates and places, the score, the decision and why.
Open it on GitHub to check the grouping.

**You decide:** `data/manual/pairs.csv` forces a pair to be the same or not, and beats all of
the above (see "How to say two events are (not) the same").

### Trust labels

- `listed_by` says who listed it: `aicf`, `kca`, `tnsca`, `ksca`, `chessfee`, `chess-results`, `chessbase`
  or `manual`. Names for people: `aicf` All India Chess Federation, `kca` Kerala Chess
  Association, `tnsca` Tamil Nadu State Chess Association, `ksca` Karnataka State Chess Association, `chessfee` chessfee, `chess-results` Chess-Results, `chessbase` ChessBase India
  (`SOURCE_LABELS` in `scripts/eventlib.py`; the website keeps its own copy).
- `verified` is `true` **only for AICF, KCA, TNSCA and KSCA (the state associations, affiliated to AICF)
  and manual events** (and for the primary of a group that contains one of them). The other
  sites' events are listed, not verified.
- Importance when values differ: override > manual > AICF > KCA > TNSCA > KSCA > the other sites.

## Running it

You need Python 3.

```powershell
pip install -r requirements.txt
python scripts/build_events.py
```

A source fetched less than 12 hours ago is skipped (add `--force` for a deliberate refresh).
`--summary-file` and `--github-output` are for the daily Action.
`--html some-saved-aicf-page.html` runs offline with a saved AICF page only.

To run the tests: `pip install -r requirements-dev.txt` and then `pytest`.

At the end it prints a short summary per source and overall: events found, how
many are ongoing, upcoming or past today (Indian time), how many have a register
link, how many records were grouped as the same tournament, and possible duplicates.

## The daily run (GitHub Action)

Every **3 hours, at minute 17** (`17 */3 * * *`, a quiet minute, because GitHub drops busy-hour
schedules), GitHub runs `.github/workflows/daily.yml`. Each source is fetched only when its
last good fetch is **12 or more hours old**, so most runs fetch nothing: they test, publish and
check, and finish in about a minute. The steps:

1. runs the tests first (if one fails, nothing is fetched or committed);
2. runs `scripts/build_events.py` (all politeness rules above apply);
3. **commits the new data to `main` only if something real changed** (not just
   timestamps), as `github-actions[bot]`, with a message like
   `data: 2026-11-25 (+3 new, 2 changed; sources ok: aicf, chessfee, chessresults_ind, chessbase_calendar)`.
   Only the `data/` folder is ever committed;
4. publishes the `data/` folder on GitHub Pages (whether or not anything was committed) and
   checks the published files;
5. **stale-data alarm:** if even the newest successful fetch of any source is more than
   **30 hours** old, the run fails (the robot has stopped bringing in data);
6. **heartbeat:** if any source has had no successful fetch for 3 days, the run fails and
   names the source;
7. **missed-fetch alarm:** if a switched-on source has been **due for more than 6 hours**
   (due = 12 hours after its last good fetch) **without any fetch attempt**, the run fails and
   names the source. The run compares `meta.json` from *before* its own build with the time it
   started, so the first run after GitHub skipped some scheduled runs fails and tells you.
   (GitHub can only e-mail you when a run happens: if it stops running the schedule
   altogether, the next run that does happen raises this alarm.)

Every run has a **job summary** (open the run on GitHub, then *Summary*): per-source
counts, ongoing / upcoming / past, any problems, whether something was committed, and the
**data quality** table (see "Quality report"). A quality drop shows as a yellow warning on the
run; it does not fail it.

A change in `data/review.csv` or in the numbers of `data/quality.json` also counts as a real
change and is committed (a new day moves the 30-day window), so the files you open on GitHub
are up to date. Their times alone never cause a commit.

### Published addresses (for the website and the app)

- <https://sujith2krishna-cpu.github.io/boostchess-tournaments/events.json>
- <https://sujith2krishna-cpu.github.io/boostchess-tournaments/meta.json>
- <https://sujith2krishna-cpu.github.io/boostchess-tournaments/quality.json>
- <https://sujith2krishna-cpu.github.io/boostchess-tournaments/review.csv>

Only the `data/` folder is published. GitHub Pages sends
`Access-Control-Allow-Origin: *`, so a web page can read the file straight from the browser;
every run checks that, that the file is valid JSON, and that its `schema_version` is the one this
code writes.

### Run it by hand

On GitHub: **Actions** tab, **Daily tournament data** on the left, **Run workflow** button
(branch `main`), **Run workflow**. Without ticking anything, it fetches only the sources that
are due (12 hours since their last good fetch); otherwise it just republishes. Tick
**force** for a deliberate refresh of every source now (the schedule never does this; please
use it rarely, the sites are small).

### What a failure e-mail means

GitHub e-mails you when a run fails. Open the run, then *Summary* and the red step:

| Red step | Meaning | What to do |
|---|---|---|
| **Run the tests** | The code or a test is broken. Nothing was fetched. | Fix the code (or revert the last change). |
| **Build the data** | *Every* source failed (or a manual file has a mistake: the message names the file and line). Nothing was written. | Fix the manual row; otherwise wait a day, then see `data/meta.json` → `sources` → `last_error`. |
| **Heartbeat**, "Stale data" | No source has been fetched for over 30 hours: the schedule has stopped or every source fails (the run still published the old data). | Open the Actions tab: are runs happening every 3 hours? If not, see "Pausing the schedule" (it may be switched off). If they run, read the summary of the last ones. |
| **Heartbeat**, "Missed fetch" | A source was due for over 6 hours and nothing tried to fetch it. Almost always GitHub skipped scheduled runs (it does this when it is busy); the run that raised the alarm has usually fetched it already. | Open the Actions tab: is there a run every 3 hours? A one-off gap needs nothing. If it keeps happening, tell the developer (the schedule may need more runs). If runs happen but fetch nothing, the 12-hour rule has a bug. |
| **Heartbeat**, "Source ... gone quiet" | One source has had no good fetch for 3 days (the run still published the data). | Look at that source's `last_error`: the site may have changed its pages or blocked us. Fix the module, or switch it off in `config/sources.json`. |
| **Check the published files** | A published file (`events.json`, `meta.json`, `quality.json`, `review.csv`) is wrong or not reachable, or the review counts in `quality.json` do not match `review.csv`. | Re-run the workflow; if it repeats, check Settings → Pages. |

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
- `data/manual/events.csv`, `data/manual/overrides.csv`, `data/manual/pairs.csv`: edited by you.
- `data/review/dedup_review.csv`: the duplicate check list (written by the tool).
- `data/quality.json`: how complete the data is (written by the tool, published).
- `data/review.csv`: your daily to-do list (written by the tool, published).
- `config/sources.json`: which sources are switched on.

### `data/events.json`

```json
{
  "schema_version": 6,
  "generated_at": "2026-11-24T10:30:00+05:30",
  "events": [ { ...one event... } ]
}
```

Events are sorted by start date.

**Schema version 6** (web and Android must read this version). What changed:

- **Version 6:** new field `registration_deadline` (right after `results_url`): the last day to
  register, `YYYY-MM-DD`, or `null`. For now only set by you in `overrides.csv`.
  `tags.fide_how` can also be `"manual"`: you set `fide_rated` in `overrides.csv`.
- **Version 5:** records of the same tournament from different sites are no longer folded into
  one event; **all records stay** and are grouped. New fields `group_id`, `merged_into`,
  `also_listed_on` (right after `verified`) and `dates_from` (after `raw_dates`).
  **Show only events whose `merged_into` is `null`.** `tags.fide_rated` can now also be `false`
  (the name says non-rated), and the new `tags.fide_how` says where a `true`/`false` comes from
  (see below). New counts in `meta.json`: `groups_count`, `merged_count`,
  `possible_duplicates_count`.

**How `fide_rated` is decided** (`true` still simply means "FIDE rated"):

| `fide_how` | When |
|---|---|
| `"manual"` | You set it in `overrides.csv` (`fide_rated` = yes / no). It wins over everything else. |
| `"stated"` | The name says so ("FIDE Rated", "Rating", "Rated", "FIDE RAPID", "FIDE Below 1800"; or "non-rated", "unrated", "not rated", which give `false`), or a site's own flag or label says so, or another site's record of the same tournament says so. |
| `"inferred"` | The name does not say "FIDE"/"rated", but uses words only FIDE-rated events use: "Grandmaster"/"GM" followed by Open, Tournament, Chess or Category; "IM norm", "GM norm", "norm tournament"; or "International" together with Open, Tournament, Chess or Rating, unless the name contains "school" anywhere (a school's name or a school championship; "FIDE"/"rated" in such a name still counts as stated). Also a section of a festival whose sibling section is rated: siblings share the same brochure link, or the same name once the section part (category letter, rating limit, age group, format) is removed, with the same start date and city. |
| `null` | `fide_rated` is `null`: nothing says either way. |

A name that says non-rated / unrated / not rated is always `false`, whatever else it says. Only a
`true` is ever passed from a sibling section or from another record of the same tournament; a
`false` never is.
- **Version 4:** new field `results_url` (right after `register_url`): where the results are.
  For Chess-Results events it is the tournament page; for others it is empty until a link is
  known (you can add one in `overrides.csv`). It stays on the event after the event ends.

- **Version 3:** new fields `source_url`, `sources` (a list), `listed_by`,
  `verified`, `flags.possible_duplicate_of`, and `tags.categories`. `source`
  can now also be `chessfee`, `chessresults_ind` or `chessbase_calendar`.
- **Version 2:** `tags.age` is a **list** (`["U11"]`, `["U12","U18"]`, or `[]`), and
  every event has a `country`.

One event looks like this:

| Field | Meaning |
|---|---|
| `id` | `aicf-<first code>`, or `aicf-<short hash>` when AICF gave no code; `kca-<KCA code with / as ->` (e.g. `kca-736-CAK-2026`), `tnsca-<TNSCA code with / as ->` (e.g. `tnsca-RR-24-CBE-26-27`; two rows sharing a code get a short name hash added), `ksca-<WordPress post number>` (e.g. `ksca-7128`), `chessfee-<number>`, `chessresults_ind-<number>`, `chessbase_calendar-<id>`; `manual-...` for your own. Never changes. |
| `codes` | The 6-digit AICF codes (some events have two); for a `kca` record its KCA code, like `736/CAK/2026`; for a `tnsca` record its TNSCA code, like `RR-24/CBE/26-27`. |
| `name` | Name of the tournament. |
| `start`, `end` | Dates as `YYYY-MM-DD`. `null` when the source's date is unreadable. |
| `place_text` | Place as a person would read it, e.g. `Banka, Bihar`. |
| `state`, `city` | Best guess from the place or title, or `null` when we are not sure. |
| `country` | Two-letter country code (ISO 3166). `IN` for aicf, kca, tnsca, ksca, chessfee, chessresults_ind and manual (unless you say otherwise); for chessbase_calendar the event's own country, or `null` if unsure. |
| `brochure_url` | Link to the brochure, or `null`. |
| `source` | The site this record comes from. |
| `source_url` | The event's page on that source. |
| `sources` | **List** of `{source, source_url, register_url}`, one per site that lists the event (more than one only on a group's primary). |
| `listed_by`, `verified` | Trust labels (see above). |
| `group_id` | The `id` of the group's primary (its own `id` when no other site lists it). |
| `merged_into` | `null` for the record to show; otherwise the primary's `id` (this record is the same tournament on another site). |
| `also_listed_on` | On the primary: `[{source, source_url, register_url, results_url, brochure_url}]` for each other record in the group; `[]` otherwise. |
| `register_url` | The organiser's registration link, if a site shows one (or you add one). We only link to it. |
| `results_url` | Where to see results, e.g. the Chess-Results tournament page; `null` when not known. |
| `registration_deadline` | Last day to register (`YYYY-MM-DD`), or `null`. Only from `overrides.csv` for now. |
| `organiser` | Organiser's name when a site shows one. |
| `tags` | `formats` (`classical`, `rapid`, `blitz`), `fide_rated` (`true`, `false` when the name says non-rated, or `null`), `fide_how` (`"manual"`, `"stated"`, `"inferred"` or `null`, see "How `fide_rated` is decided"), `age` (list like `["U11"]`, `[]` when unknown), `open`, `girls` (`true` or `null`), `categories` (list of labels from the source, e.g. `"FIDE RAPID"`, `"TAMILNADU STATE LEVEL"`, `"youth"`, and `"abroad"` for an event outside India). Only set when there is evidence (the name, the site's category label, Chess-Results' time control, or another record in the same group); never guessed. |
| `flags` | `dates_suspect` (the dates look wrong), `code_expanded` (AICF wrote `472175/76`, we read it as `472175` and `472176`), `code_unclear`, `possible_duplicate_of` (an event `id`, or `null`). |
| `raw_dates` | The dates exactly as the source wrote them, kept when they look wrong (and for a KCA range across New Year, whose start year is read from the page's format). |
| `dates_from` | Set on a primary whose own dates were suspect: the `id` of the group record whose dates it now shows. `null` otherwise. |
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

Counts for a quick health check: `generated_at`, `last_run_at` (the time of the latest
run, even one that fetched nothing; proof the robot is alive), `scraped_count`, `manual_count`,
`total`, `suspect_dates_count`, `missing_state_count`, `gone_from_source_count`,
`groups_count` (tournaments after grouping), `merged_count` (records with `merged_into` set),
`possible_duplicates_count`, and `sources`: for each source `enabled`, `status` (`ok`, `failed`, `skipped`,
`disabled`), `message` (why, when not ok), `count` (events currently listed),
`last_success` (time), `last_error` (`{at, message}`) and `next_due` (the earliest time it
will be fetched again).

### `data/quality.json` (quality report)

Written by every run. It looks only at the events the website shows (not hidden, not
cancelled, `merged_into` = `null`), by start date in Indian time, in two windows:
`next_30_days` (today up to today + 30) and `upcoming` (today or later).

- `overall` and `sources` (one entry per source): for each window `events`, and the count and
  percentage (`..._pct`) of `unknown_format`, `unknown_fide` (`fide_rated` is `null`),
  `no_state`, `suspect_dates`, `no_register_link`, `no_brochure`, and `fully_known`.
- **Fully known** = format, FIDE (yes or no), state and good dates are all known, and there is a
  register link or a brochure link.
- `target`: the goal is **95% fully known for the next 30 days**; `now_pct` and `met` say where
  we are.
- `alerts`: compared with the previous run, a source whose fully-known % fell by **10 points or
  more**, or whose number of upcoming events **halved** (only when both runs have at least 5
  events in that window).
- `review`: how many lines `data/review.csv` has.

## Daily review (10 minutes)

The tool writes a to-do list for you every run: `data/review.csv`. It lists the shown events
that **start in the next 30 days and miss something**, soonest first, and after them any
**possible duplicates** still to settle.

1. On GitHub, open `data/review.csv`. GitHub shows it as a table. The `missing` column says what
   is not known, for example `format, fide`.
2. For an event, open its `brochure_url` (or `source_url`, or a link in `also_listed_on`) and find
   the missing facts.
3. Copy the `line_to_add` cell. It is a ready line for `data/manual/overrides.csv`: the event id
   first, and a `?` in every column you need to fill.
4. Open `data/manual/overrides.csv`, click the pencil, paste the line at the bottom, and replace
   each `?` with what the brochure says (`fide_rated`: `yes` or `no`; `format`: `rapid`, or
   `rapid|blitz`; `state`: like `Kerala`; a register link starting with `https://`). Leave a
   column empty if the brochure does not say. A `?` you forget is only a warning: it is ignored
   until you fill it in.
5. Click **Commit changes**. The next run uses your values and the event leaves the list.

For a `possible_duplicate` line: check both events (`id` and `other_id`). If they are the same
tournament, paste `line_to_add` into `data/manual/pairs.csv` as it is; if not, change `same` to
`not_same` first.

If a line has a mistake (a date that does not exist, `fide_rated` = `maybe`, ...), the next run
stops and names the file and the line; nothing is lost. Fix the line and commit again.

## How to add an event yourself

You do not need to install anything. Do it on the GitHub website:

1. Open the repository on GitHub and go to the folder `data` → `manual`.
2. Click `events.csv`.
3. Click the pencil icon (**Edit this file**).
4. Go to the end of the file and add one new line for your tournament.
5. Click **Commit changes…** and confirm.

The next time the tool runs, your tournament appears in `events.json`.

Columns (in this order):
`id, name, start_date, end_date, place, state, country, link, brochure_url, format, age, note, results_url`

Only **name** and **start_date** are required. Example row:

```csv
id,name,start_date,end_date,place,state,country,link,brochure_url,format,age,note,results_url
pune-club-rapid-2027,Pune Club Rapid Under-11,05-01-2027,06-01-2027,"Pune, Maharashtra",,,https://example.org/register,,rapid,U11,Entry at the door,
us-masters-2027,US Masters,25-11-2027,29-11-2027,"Charlotte, North Carolina",,US,,,,,,
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
`key, start_date, end_date, place, state, hide, cancelled, note, register_url, results_url,
fide_rated, format, age, registration_deadline`

- `key` is the event `id` (like `aicf-472290`) or the 6-digit AICF code (like `472290`).
- Fill in **only** what you want to change; leave the rest empty. Lines written before the last
  four columns existed (with fewer commas) still work.
- Write `yes` in `hide` to hide the event, or in `cancelled` to mark it cancelled.
- `fide_rated`: `yes` or `no`. `format`: `classical`, `rapid` or `blitz`; several with `|`
  (`rapid|blitz`). `age`: like `U-9`, several with `|` (`U-9|U-11`). `registration_deadline`:
  the last day to register, `DD-MM-YYYY` (or `YYYY-MM-DD`). These four win over everything the
  sites say (also over another site's record of the same tournament); `fide_how` becomes
  `"manual"`.
- A cell that is just `?` means "not filled in yet": it is ignored, with a warning.

```csv
key,start_date,end_date,place,state,hide,cancelled,note,register_url,results_url,fide_rated,format,age,registration_deadline
aicf-473594,03-04-2026,29-04-2026,,,,,Dates swapped on AICF page; checked brochure,,
aicf-111111,,,,,yes,,Duplicate listing,,
aicf-222222,,,,,,yes,Cancelled by organiser,,
aicf-333333,,,"Sagar, Madhya Pradesh",,,,,,
aicf-444444,,,,,,,,,,yes,rapid|blitz,U-9|U-11,05-12-2026
```

Order of importance: **override > manual event > AICF > other sites**. Delete the
line and the event goes back to what the sites say. A key that matches nothing is
only a warning.

## How to add a link yourself

Found the registration page or the results page for an event? Add a line to
`data/manual/overrides.csv` (on GitHub: open the file, pencil, add the line, **Commit changes**).
Leave every other column empty. The address must start with `https://` (or `http://`); if it
does not, the run stops and names the line.

Registration link:

```csv
aicf-473594,,,,,,,,https://example.org/register-for-kpk-open,
```

Results link:

```csv
aicf-473594,,,,,,,,,https://chess-results.com/tnr1234567.aspx?lan=1
```

(Both can go on the same line.) Your link wins over a link a site gives. For your own events
in `events.csv`, put the registration link in `link` and the results link in `results_url`.

## How to say two events are (not) the same (`pairs.csv`)

If the tool grouped two records that are different tournaments, or missed two that are the
same, add a line to `data/manual/pairs.csv` (on GitHub: open the file, pencil, add the line,
**Commit changes**). Columns: `id_a, id_b, decision, note`

- `id_a`, `id_b`: the two event ids (see `data/review/dedup_review.csv` or `events.json`).
- `decision`: `same` or `not_same`.
- `note`: optional, why.

```csv
id_a,id_b,decision,note
aicf-486240,chessfee-1727,same,same brochure
aicf-482568,chessbase_calendar-6aaa7ca270d3171daede9af6,not_same,different sections
```

Your line beats the tool. An id that matches nothing is only a warning (the event may come back
later); a wrong `decision`, or the same id twice, stops the run and names the line.

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
