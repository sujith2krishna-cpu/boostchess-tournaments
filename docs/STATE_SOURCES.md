# State chess associations as sources: a survey

Checked on **26 November 2026**. This is a survey only. No code or data was changed.

Sources we already read: `aicf`, `kca` (Kerala), `chessfee`, `chessresults_ind` and
`chessbase_calendar`. `tnsca` (Tamil Nadu) is on branch `t8-tamilnadu`, not merged yet.

## How the check was done

- For each association: a web search for the official site, then `robots.txt`, the home
  page and the calendar page, **one request each**, with our User-Agent
  (`BoostchessBot (+https://github.com/...)`), at least 3 seconds apart. No logins, no forms.
  Only links that the pages show were followed.
- "Upcoming" means events that start on or after 26 Nov 2026 and are shown on that page.
- "Already covered" compares the upcoming names with `data/events.json` from branch
  `t8-tamilnadu` (the data on `main` plus TNSCA), by eye and by a simple word match.
- "Reuse statement": every site that loaded shows only a generic copyright line
  (for example "© 2026 ... All rights reserved"). **None says anything about reusing its
  tournament data**, for or against. The terms pages were not read in full; they seem to
  cover registration and payment. Under our no-copy rules we would store facts and links only.

For comparison, upcoming events per state that we already have (26 Nov 2026, all sources):
Maharashtra 24, Karnataka 16, West Bengal 11, Delhi 10, Goa 8, Gujarat 6, Uttar Pradesh 6,
Rajasthan 5, Madhya Pradesh 5, Assam 3, Andhra Pradesh 2, Telangana 1, Odisha 0, Bihar 0
(116 more have no state). Tamil Nadu has 137, 63 of them from TNSCA. So a state
calendar adds the state, district and age-group events that AICF does not list.

## Ranking

| Rank | Association | Calendar page | How events are listed | Dates and places | Upcoming shown | Login / blocking / robots.txt | Already covered elsewhere | Value |
|---|---|---|---|---|---|---|---|---|
| 1 | Karnataka State Chess Association (KSCA) | <https://karnatakachess.com/tournaments/> | WordPress "The Events Calendar" list, paged (`/tournaments/list/page/2/`); the page itself offers an **"Export .ics file"** link (`/tournaments/list/?ical=1`) and categories (FIDE rating, national, state selection, monthly) | Yes: start date and time, venue name and full address with town | **12** in the next 17 days (28 Nov to 13 Dec), more on later pages | No login. robots.txt blocks only `/wp-admin/` | About half: 6 of the 12 on AICF, 3 on Chess-Results, **3 nowhere** (non-rated, age-category, festival) | **High.** Busiest state calendar found, cleanest format (iCal offered by the page), clear venue. Fills gaps in a state where we have 16 |
| 2 | Telangana State Chess Association (TSCA) | <https://www.chesstelangana.com/events/> (event pages under `/event/...`) | WordPress list of event posts. The date in the list is the **post date, not the event date**; the event page has "Tournament Starts", venue, "Registration Last Date", entry fee, a brochure link and an on-site registration. `/calendar/` is empty | Yes, but only on each event page (one extra request per new event) | ~4 to 6 new events a month (29 posts from April to November 2026); the newest ones are already past | No login. robots.txt allows everything. **Event pages also list registered players with their dates of birth: never store these** | **Almost none**: we have 0 "Telangana State Ranking" events, 0 district events, 1 Telangana event in total | **High.** Monthly state ranking tournaments plus Hyderabad and Rangareddy district age-group events that no other source has. Gives `registration_deadline` |
| 3 | All Odisha Chess Association (AOCA) | <https://odishachess.com/calendar/> | HTML table per season (2022-23 to 2026-27 tabs): name, AICF event code (e.g. `505919/505920/OD(S)/2026`), organiser, start, end, place, brochure PDF, status (Completed / Tentative) | Yes, full dates with year, venue and town | **0** dated (season's dated events all done; the rest are "Tentative" without dates) | No login. robots.txt blocks only `/wp-admin/` and similar | Little: 2 "Odisha State" events in our data. Codes would make grouping with AICF easy | **Medium.** Clean, coded table but only ~14 events a season, mostly state selections. Worth it for codes and organisers |
| 4 | All Bihar Chess Association (ABCA) | <https://biharchess.org/calendar-2026-27/> (one page per season, from the menu) | HTML table: name, city, dates, circular PDF, results | City yes. **Dates have no year** ("12-13 December", "28Apr-30 Apr"); the year must come from the season in the page title (April to March), like KCA's year rule; any other reading is a guess | **2** (State Rapid and Blitz, Jehanabad, 12 to 13 Dec); 1 row has no date | No login. robots.txt blocks only `/wp-admin/` | Partly: 13 "Bihar State" events already come from AICF; the two upcoming ones are not in our data | **Medium-low.** Small, but complete list of state championships |
| 5 | Uttar Pradesh Chess Sports Association (UPCSA) | <https://upchess.org/tournament.php> | HTML table: name, level (state / national), type, start and end, entry dates with late fee, district / city, status, brochure, result link | Yes, full dates (`05-Jan-2027`) and district | **2** (Lakhimpur Kheri 5 Jan 2027, Bareilly 2 Jan 2027); 8 rows in total | No login for the list ("Login" only for entries). No robots.txt (404) | **Yes**: both upcoming events are on AICF | **Low** for new events, but the cleanest table, and it gives entry deadlines |
| 6 | Maharashtra Chess Association (MCA) | <https://mcachess.in/chess-calendar/> | HTML table: name, start, end, venue (town), circular PDF | Yes, `DD/MM/YYYY` and town | **0**: the 19 rows end on 18 Jun 2026; **not updated for 5 months** | No login. robots.txt blocks only `/wp-admin/` | AICF already has 21 upcoming Maharashtra events | **Low now.** Good format; re-check later in case it is updated again |
| 7 | Andhra Chess Association (ACA) | <https://apchess.org/all-events/all> | The table is filled by the page's script from `/all-events-datatable-ajax/all` (JSON); the home page also links the live events | Date and name only in the list; no place; prospectus PDF; details page per event | **2** (state open rapid 29 Nov; FIDE open 10 Dec) | robots.txt allows everything. List needs the script's data call (not a link on the page) | 1 of 2 on AICF (name differs) | **Low.** Few events, no place in the list |
| 8 | Delhi Chess Association (DCA) | <https://delhichess.com/tournaments> | Script-built page (CircleChess platform); "Upcoming / Past / All" tabs | Date and venue | **2 real** (the 22nd Delhi GM Open listed twice) + one placeholder dated "20 May 2040" | No login. robots.txt is not a real file (returns the web page) | Yes, the GM Open is on AICF and ChessBase | **Low** |
| 9 | Pondicherry State Chess Association (PSCA) | <https://www.pondicherrychess.com/events.php> | Small HTML page | Date; place only in the name | **1** (blitz, 6 Dec) | No login. robots.txt is not a real file | No | **Low** |
| 10 | Gujarat State Chess Association (GSCA) | <https://gsca.in/UpcomingEvent.aspx>; circulars at `CircularWeb.aspx` | Upcoming page is **empty**; events appear only as circular PDFs | Only inside the PDFs | 0 | No login. No robots.txt (404) | AICF has 6 Gujarat events | **None** until the upcoming page is used again (PDFs are not something we read) |

## Associations with no usable calendar

| Association | What was found |
|---|---|
| Bengal Chess Association (West Bengal) | `bengalchess.org` does not answer (`www` gives a Cloudflare 530 error). Events show up on AICF and Chess-Results only |
| Goa Chess Association | No working official site found (`gmgoa.com`, named in old listings, does not resolve). Events are on AICF and Chess-Results |
| Punjab State Chess Association | No official site found; events only on AICF |
| Rajasthan Chess Association | No official site found; events (Bhilwara, Udaipur, Kota) only as AICF brochures |
| Madhya Pradesh | No official site found; state events run by an "M.P. Chess Ad-hoc Committee" and posted on AICF |
| All Assam Chess Association | The address in its 2024 circulars (assamchess.org) **now shows a gambling site**: the domain seems to have lapsed. Do not link to it |
| All Jharkhand Chess Association | `jharkhandchess.in` is a script-only app; nothing readable without running it |
| Haryana, Chhattisgarh, Uttarakhand | No official sites with a calendar found |
| Andhra Pradesh Chess Association (APCA, `apca.in`) | The domain is parked (for sale). The AICF-affiliated body is ACA (`apchess.org`, rank 7) |

**District and city associations:** none with its own working calendar was found. District
events are best reached through the state pages: Telangana (Hyderabad, Rangareddy) and
Odisha list them, and Tamil Nadu's districts are in TNSCA.

## Recommendation

1. **Karnataka (KSCA)**: add next. Read the page's own iCal export (or the list pages)
   once per run; most work is matching with AICF.
2. **Telangana (TSCA)**: read the events list, then each new event's page for the real
   date, venue and registration deadline. The parser must skip the participants table
   (names and dates of birth).
3. **Odisha (AOCA)**: one page a run, the current season's tab; AICF codes go into `codes`.
4. **Bihar (ABCA)**: small; needs a "season year" rule written down like KCA's, with
   `dates_suspect` for anything that does not fit.
5. **Uttar Pradesh (UPCSA)**: small and mostly on AICF, but clean and gives entry deadlines.

Maharashtra (MCA) would be worth adding if its calendar is kept up to date again.
Everything here is shared data: a new source changes `data/events.json` only, the same for
the website and the Android app.
