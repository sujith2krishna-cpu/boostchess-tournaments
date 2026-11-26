# FIDE rated check (27 Nov 2026)

A full check of `tags.fide_rated` on the data in `data/events.json` as committed on `main`
(`generated_at` of the 2026-11-26 run). **Report only: no rule, no data and no manual file was
changed.** The rules checked are the ones in the README section "How `fide_rated` is decided"
(`fide_evidence()` in `scripts/eventlib.py`, the KCA and ChessBase labels in their source
modules, group sharing in `_inherit_tags()` and `share_fide_with_sections()` in
`scripts/dedup.py`).

## How this was counted

- "Upcoming" means upcoming **or ongoing** on 27 Nov 2026 (India time, `status()`), and only the
  events a visitor sees: `merged_into` is `null`. 281 events: 250 upcoming, 31 ongoing.
  (With the grouped copies there are 313 records; the copies follow their primary.)
- The build stores only `fide_how` (`stated` / `inferred` / `manual`), not which rule fired. The
  reason below was worked out again from each record: its name, its site label or flag, its
  group, and its sibling sections, in the same order the build uses.
- The verdicts are judgement from the name, the site and the other sites' records of the same
  event. No brochure was opened and no site was fetched.

## Counts

| | Shown events | All records |
|---|---:|---:|
| FIDE rated = yes | **122** | 147 |
| FIDE rated = no | **0** | 0 |
| Not stated (`null`) | **159** | 166 |
| Total upcoming / ongoing | 281 | 313 |

No upcoming event is marked "no": only a name that says non-rated / unrated / not rated gives
`false`, and none does. So part 3 checks the **not stated** events instead.

**Why "yes" (122):** the name says Rated / Rating: 91 · name has "IM norm": 12 · name has
"Grandmaster ... Open/Tournament": 11 · name has "International" + Open/Tournament/Chess: 3 ·
ChessBase's own FIDE flag: 2 · sibling section of a rated event: 2 · name has "FIDE Rapid" (FIDE
+ format): 1. By source: aicf 93, chessresults_ind 14, chessbase_calendar 10, chessfee 3, kca 2.
None came from `overrides.csv` (it is empty) and none only from another site's record.

**The 40 most doubtful "yes" events:** 38 look correct, **0 look wrong**, 2 can't tell.

**"Not stated" events whose name suggests FIDE:** 15 found, **7 look wrong** (all National
championships), 8 can't tell. None of the 159 has "International", "FIDE", "Grand Prix",
"Grandmaster" or a prize of 1 lakh or more in its name: every such event is already "yes".

## What the check found

1. **The "yes" side is clean.** The two old mistakes are gone: no school or inter-school event is
   rated by inference (the 6 school-looking "yes" events all say "Rating" themselves; 3 of them
   are on AICF's list and a fourth is a Chess-Results copy of one), and all five Athens of the East sections are rated.
2. **The real gap is National championships.** AICF lists them, but their names never say
   "FIDE" or "rated", so they stay "not stated". On AICF's list (all dates) 397 of 445 events are "yes"; 48
   are not, and 28 of those 48 are National / State / Asian championships.
3. **Two "can't tell" cases on the yes side:**
   - `chessresults_ind-1538096`, "1st All India Under-08 Rapid Chess Festival (Below 1600 FIDE
     Standard & Rapid Ratings)": "Ratings" says who may play, not that the festival is rated.
   - `chessresults_ind-1526947`, "10th WMA Inter School Rapid Rating": the name says Rating, but
     it is an inter-school event that only Chess-Results lists.
   Both are better settled one by one in `overrides.csv` (`fide_rated` = yes / no) once someone
   reads the brochure, than with a new rule (see "Tried and not suggested").
4. **Not about FIDE, but seen on the way** (for a separate look):
   - The same tournament shows more than once because its records are not grouped: the six Tamil
     Nadu IM Norm events (ChessBase says 30 Jan, AICF 8 Feb, so 12 cards); the Salem Battle
     Field rapid (AICF, chessfee and Chess-Results, 3 cards); the 3S Institute Fiesta; the Dragon
     Chess Academy open; and the National Junior in Kolkata (AICF "National U19 (Junior)" and
     Chess-Results "55th National Junior Championship 2025").
   - `aicf-471361` (WB State Under 17) has suspect dates (start 23-07-2027, end 26-07-2026) and
     so counts as upcoming, though it was probably in July 2026.

## Suggested rule changes (2)

Only two changes are worth making; the other ideas tested are under "Tried and not suggested".

### 1. AICF championships count as rated (inferred)

**Rule:** an event **on AICF's list** whose name has "National", "State", "Asian" or "Zonal"
followed later by "Championship(s)", and nothing says non-rated, gets `fide_rated` = true with
`fide_how` = "inferred". Like the other inferred rules it is shared with the group (other sites'
records of the same event) but never overrides a "no".

**Would flip:** 29 records from "not stated" to "yes" (28 shown events). **Upcoming: 5 shown
events** (6 records; the sixth is the Chess-Results copy of the 63rd National).

| Example | Id | When |
|---|---|---|
| 63rd National Chess Championship – 2026 | `aicf-485283` | upcoming |
| 52nd NATIONAL WOMEN CHESS CHAMPIONSHIP 2026 | `aicf-496730` | upcoming |
| National U19 (Junior )Chess Championship 2026 | `aicf-494716` | upcoming |
| Asian Junior Chess Championship 2026 | `aicf-486699` | past |
| TAMILNADU STATE U-17 OPEN/Girls CHESS CHAMPIONSHIP 2026 | `aicf-472175` | past |

The other upcoming two are the National School Chess Championship and the National Team Chess
Championship. **Keep it to AICF's list:** on all sites the same words would also catch Bihar
state school championships, the Kerala State Civil Services championship and three KCA
"State Inter School Team" events (KCA state rated), 17 records that should not be rated by
inference. Worth checking by brochure before switching it on: the CFPD National for
Differently Abled Players and the AICFB National Team for the Visually Challenged (both past).
It does not reach "National Under 15" (no word "Championship") or the two Chess-Results
National Junior records in Kolkata (not grouped with AICF's copy); those would need
`overrides.csv` or a grouping fix.

### 2. The word "FIDE" next to Open / Tournament / Chess counts as stated

**Rule:** "FIDE Open", "FIDE Chess", "FIDE Tournament", "FIDE TMT", "Open FIDE" or
"International FIDE" in a name gives `fide_how` = "stated" (today only "FIDE" + a format or a
rating limit does, and "FIDE Chess Tournament" is only "inferred" through the word
"International").

**Would flip:** 0 values. 6 records change from "inferred" to "stated" (5 shown events; 3 of
them upcoming). Its use is as a guard: a name like "St Xavier International School FIDE Chess
Tournament" is "not stated" today (the school guard blocks "International" and "FIDE" alone is
not enough); with this rule it is "yes", stated, as its name says.

| Example | Id | When |
|---|---|---|
| DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN FIDE CHESS TOURNAMENT 2026 | `aicf-503296` | upcoming |
| DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN FIDE CHESS TOURNAMENT 2026 – 2 to 6 DEC | `chessfee-1815` | upcoming (grouped copy) |
| DRAGON CHESS ACADEMY 2ND INTERNATIONAL BELOW 1700 FIDE CHESS TOURNAMENT | `aicf-503298` | upcoming |
| INTERNATIONAL FIDE OPEN CHESS TOURNAMENT | `aicf-460234` | past |
| INTERNATIONAL FIDE OPEN BELOW 1800 CHESS TOURNAMENT | `aicf-460235` | past |

## Tried and not suggested

| Idea | What it would do | Why not |
|---|---|---|
| "Rating" that is only an entry limit ("Below 1800 ... Rating", "rating players only") does not count | 7 records "yes" → "not stated" (3 upcoming) | 6 of the 7 are clearly rated events ("Winter Cup Below 1700 International Fide Rating Chess Tournament"); only the Tiruchengode Under-08 festival is in doubt. Use `overrides.csv` for that one. |
| "International ... Open" inference only for events in India | 0 records | The three abroad events that look inferred (Goris, Szentmiklós, Fallsview) are rated by ChessBase's own flag, not by the name. |
| Everything on AICF's list counts as rated | 20 more records (6 upcoming: Pune Grand Slam ×3, Kunkulol Memorial ×2, Sivasagar Open) | Also catches the Tech Mahindra Global Chess League (3 records), "AICF Chess For Every One" and school leagues, which are not clearly FIDE rated. The six upcoming ones are better set by brochure in `overrides.csv`. |
| A national / state championship on any site | 20 records outside AICF | 17 of them are school, civil-service and KCA state events (see rule 1); only 3 (National copies) would be right. |

## Details

The tables below list every upcoming "yes" event by reason, then the verdicts for parts 2 and 3.
Names are cut at 100 characters (80 in the verdict tables); `+ chessfee` etc. means the event is
grouped with records on those sites.

<!-- generated tables: 281 upcoming/ongoing events shown -->

### 1. Every upcoming event marked FIDE rated = yes, by reason

| Reason (rule that fired) | `fide_how` | Events |
|---|---|---:|
| name says rated/rating | stated | 91 |
| name: norm | inferred | 12 |
| name: grandmaster/GM | inferred | 11 |
| name: International + open/tournament/chess | inferred | 3 |
| ChessBase site flag | stated | 2 |
| sibling section | inferred | 2 |
| name says FIDE + format/limit | stated | 1 |
| **Total** | | **122** |

Sources: aicf 93, chessresults_ind 14, chessbase_calendar 10, chessfee 3, kca 2.

<details><summary><b>name says rated/rating</b> (91)</summary>

| Start | Name | Source | Id |
|---|---|---|---|
| 2026-11-26 | International FIDE Rated Above 1800 Open Chess Tournament 2026 | aicf | `aicf-487788` |
| 2026-11-26 | International FIDE Rated Above 1800 Open Chess Tournament 2026 | chessbase_calendar | `chessbase_calendar-6aaa7ca270d3171daede9ade` |
| 2026-11-26 | QQCHESS INTERNATIONAL OPEN 1800 AND ABOVE FIDE RATING CHESS TOURNAMENT 2026 | chessresults_ind | `chessresults_ind-1487030` |
| 2026-11-27 | 2nd Manchester City International Below 1800 Fide Rated Tournament | aicf + chessfee, chessresults_ind | `aicf-486240` |
| 2026-11-27 | International FIDE Rated Below 1800 Open Chess Tournament 2026 | aicf | `aicf-487790` |
| 2026-11-27 | International FIDE Rated Below 1800 Open Chess Tournament 2026 | chessbase_calendar | `chessbase_calendar-6aaa7ca270d3171daede9adf` |
| 2026-11-28 | 3rd Pune International Speed Festival 2026 – RAPID Rating Chess Tournament | aicf + chessresults_ind | `aicf-504554` |
| 2026-11-29 | SARJI RENUKA DEVADHAR ALL INDIA FIDE RAPID RATING OPEN CHESS TOURNAMENT | aicf | `aicf-499268` |
| 2026-11-29 | 2nd MVIT King Trophy International Rapid FIDE Rating Chess Tournament 2026 | aicf + chessresults_ind | `aicf-500404` |
| 2026-11-29 | Khannur Rapid Rated Chess Tournament – Bengaluru | aicf | `aicf-501318` |
| 2026-11-29 | ChessInd Academy’s 2nd International FIDE Rated Open Rapid Chess Tournament | aicf + chessfee, chessresults_ind, kca | `aicf-502180` |
| 2026-11-29 | 1st RAYDIANCE International Open Fide Rapid Rating Chess Tournament 2026 | aicf | `aicf-504058` |
| 2026-11-29 | 3rd Pune International Speed Festival 2026 – BLITZ Rating Chess Tournament | aicf + chessresults_ind | `aicf-504557` |
| 2026-11-29 | 3S INSTITUTE RAPID RATING FIESTA 2026 BY CHESS AT SCHOOL | aicf | `aicf-510558` |
| 2026-11-29 | KRISHNAGIRI - 1st RIMS INTERNATIONAL FIDE RAPID RATED CHESS TOURNAMENT – 29 NOV | chessfee | `chessfee-1847` |
| 2026-11-29 | Sarji Renuka All India Open FIDE Rapid Rating Chess Tournament 2026 499268/KA(R)/2026, KSCA/GO104/2… | chessresults_ind | `chessresults_ind-1502060` |
| 2026-11-29 | Khannur Fide Rapid Rating Chess Tournament 2026 494719/KA(R)/2026 November 29th 2026, 3 lakh cash P… | chessresults_ind | `chessresults_ind-1502344` |
| 2026-11-29 | 1st Raydiance Internationa Open FIDE Rapid Rating Chess Tournament 2026 For More Details Contact IA… | chessresults_ind | `chessresults_ind-1514745` |
| 2026-11-29 | ABHERAJ BALDOTA GRAND PRIX ALL INDIA OPEN FIDE RAPID RATING CHESS TOURNAMENT | chessresults_ind | `chessresults_ind-1522500` |
| 2026-11-29 | 10th WMA Inter School Rapid Rating Chess Tournamnet 2026 1 lakh Prize worth For Registration : ( Ra… | chessresults_ind | `chessresults_ind-1526947` |
| 2026-11-29 | 1st RIMS International FIDE Rapid Rated Chess Tournament 2026 Gold & Silver Coins - Contact Person | chessresults_ind | `chessresults_ind-1539417` |
| 2026-11-29 | 1 Lakh Cash Prize @399 Entry fees - "Late. Madanbhau Patil Memorial International Open FIDE Rapid R… | chessresults_ind | `chessresults_ind-1540566` |
| 2026-11-29 | 3S INSTITUTE presents FIESTA All India Rapid Rating Chess Tournament 2026. For Registration Contact… | chessresults_ind | `chessresults_ind-1545661` |
| 2026-12-04 | Chessinfo & Golden Knights Chess Academy – 1st International FIDE Rating 2nd Below 1700 Chess Tourn… | aicf + chessfee | `aicf-494155` |
| 2026-12-05 | INVENTIVE 2.0 FIDE-rated Rapid Chess Tournament | aicf | `aicf-503301` |
| 2026-12-05 | Mahaguru Chashak: 1st Joseph D’Souza Memorial Open Fide Rapid Rating Chess Tournament, Pune 2026 | aicf | `aicf-506267` |
| 2026-12-06 | 8th Tarabai Shinde FIDE Rapid Rating Chess Tournament, Nerul, Navi Mumbai | aicf | `aicf-484749` |
| 2026-12-06 | 2nd Little Star Chess Academy All India Open FIDE Rapid Rating Chess Tournament 2026 | aicf | `aicf-496019` |
| 2026-12-06 | Mahaguru Chashak: 2nd Joseph D’Souza Memorial Open Fide Blitz Rating Chess Tournament 2026 | aicf | `aicf-506268` |
| 2026-12-06 | 1st Adhiraj Gadchiroli International Open FIDE Rapid Rating Chess Tournament – 2026 | aicf | `aicf-506787` |
| 2026-12-06 | playu – 3 rd International FIDE Rapid Rated Open Chess Tournament 2026 | aicf + chessfee | `aicf-507988` |
| 2026-12-06 | 3rd Battle Field International FIDE Rapid Rating Chess Tournament 2026 | aicf | `aicf-510562` |
| 2026-12-06 | Chadurangotsava All India Open Rapid Rated Tournament 2026 | aicf | `aicf-511064` |
| 2026-12-06 | 1st INTERNATIONAL RAPID RATING CHESS TOURNAMENT | aicf | `aicf-511467` |
| 2026-12-06 | Under 18 Open Rapid Rating Chess Tournament 2026 | aicf | `aicf-511857` |
| 2026-12-06 | SALEM - 3rd BattleField International Open FIDE Rapid Rating Chess Tournament 2026 – 6 DEC | chessfee | `chessfee-1858` |
| 2026-12-06 | 06 Dec; 3rd Battel Field International Open FIDE Rapid Rating Chess Tournament 2026 Total Cash Priz… | chessresults_ind | `chessresults_ind-1538330` |
| 2026-12-06 | GIRISTUTI CHECKMATE SCHOOL OF CHESS PRESENTS Under-18 Children's Day Fide Rapid Rating Chess Tourna… | chessresults_ind | `chessresults_ind-1545810` |
| 2026-12-10 | International FIDE open RATING CHESS TOURNAMENT- 2026 | aicf | `aicf-484348` |
| 2026-12-12 | 1st SCC All India FIDE Rated Rapid Chess Tournament 2026 | aicf | `aicf-487700` |
| 2026-12-13 | 1st late Shriram Kute Guruji Memorial All India Open Fide Rating Rapid Chess Tournament | aicf | `aicf-504550` |
| 2026-12-15 | 24th North East Fide Rating Chess Championship | aicf + chessresults_ind | `aicf-503517` |
| 2026-12-19 | GH Raisoni Memorial Bilaspur International FIDE Rapid Rating Chess Tournament – 2026 | aicf | `aicf-511065` |
| 2026-12-20 | 1st Late Sunil Swarup Barse Memorial All India Open Fide Rapid Rating Chess Tournament | aicf + chessresults_ind | `aicf-508734` |
| 2026-12-20 | Puneeth Rajkumar Cup All India Fide Rating Open Chess Tournament 2026 511685/KA(R)/2026 December 20… | chessresults_ind | `chessresults_ind-1544300` |
| 2026-12-21 | 2nd All India under 18 Open FIDE Rated Rapid Chess Tournament – 2026 | aicf | `aicf-510446` |
| 2026-12-22 | Winter Cup Below 1700 International Fide Rating Chess Tournament 2026 | aicf | `aicf-485006` |
| 2026-12-23 | 3rd Rotaract RUAS – Children Chess Academy All India Open FIDE Rated Classical Chess Tournament | aicf | `aicf-494566` |
| 2026-12-24 | 2nd MAHARATHI INTERNATIONAL OPEN CLASSICAL FIDE RATED CHESS TOURNAMENT | aicf | `aicf-471843` |
| 2026-12-25 | 3rd Bhilwara International Open FIDE Classical Rating Chess Tournament 2026 | aicf | `aicf-471849` |
| 2026-12-25 | 3rd Ramabai Ranade FIDE Classical Rating Chess Tournament | aicf | `aicf-480521` |
| 2026-12-25 | 10th Kurukshetra Open FIDE Rating Chess Tournament 2026 | aicf | `aicf-484279` |
| 2026-12-26 | 1st Bhilwara International Open FIDE Rapid Rating Chess Tournament 2026 | aicf | `aicf-471850` |
| 2026-12-26 | 1st Vedic Dehradun International Open FIDE Rated Rapid Chess Tournament 2026 | aicf | `aicf-512596` |
| 2026-12-27 | 5th Late Shri. Shankar Shet Memorial 1st Open FIDE Rated Rapid Chess Tournament 2026 | aicf | `aicf-501321` |
| 2026-12-27 | 1st CLOUD LABS INTERNATIONAL OPEN FIDE RAPID RATING CHESS TOURNAMENT | aicf | `aicf-509586` |
| 2026-12-28 | 4th Rotaract RUAS – Children Chess Academy Below 1800 All India FIDE Rated Classical Chess Tourname… | aicf | `aicf-494627` |
| 2027-01-01 | 1st All India Under-08 Rapid Chess Festival (Below 1600 FIDE Standard & Rapid Ratings) at Tirucheng… | chessresults_ind | `chessresults_ind-1538096` |
| 2027-01-02 | Shri Sanjay Agarwal Memorial International FIDE Rated Rapid Chess Tournament | aicf | `aicf-495857` |
| 2027-01-02 | Category A: MCT International FIDE Rapid Rating Chess Tournament 2027 | aicf | `aicf-511169` |
| 2027-01-03 | 1st DPSS Rapid Rating Chess Tournament 2027 | aicf | `aicf-499438` |
| 2027-01-03 | 3rd Morde Foundation International FIDE Rapid Rating Tournament | aicf | `aicf-507804` |
| 2027-01-05 | KAPIL DEV KHARE MEMORIAL FIDE RATED OPEN CLASSICAL CHESS TOURNAMENT | aicf + chessbase_calendar | `aicf-505328` |
| 2027-01-09 | 4th Jabalpur International Open Fide Rapid Rating Chess Tournament 2027 | aicf + chessbase_calendar | `aicf-490886` |
| 2027-01-10 | Eight Square Chess Academy – 4th International FIDE Rated Rapid Chess Tournament – 2027 | aicf + chessfee | `aicf-486710` |
| 2027-01-10 | Late Kisanrao & Kausalyabai Chavan Memorial 4th Power Chess Academy All lndia Open FIDE Rapid Ratin… | aicf | `aicf-506426` |
| 2027-01-10 | Eight Square Chess Academy 4th International FIDE Rated Rapid Chess Tournament 2027 – 10 JAN | chessfee | `chessfee-1876` |
| 2027-01-11 | 1st Akshaya International Grandmaster Open Chess Tournament – 2027 (Category A) above 2000 rating p… | aicf + chessbase_calendar | `aicf-482202` |
| 2027-01-11 | 1st Akshaya International Grandmaster Open Chess Tournament – 2027 (Category B) below 2000 rating p… | aicf + chessbase_calendar | `aicf-482207` |
| 2027-01-15 | 1st Akshaya International Grandmaster Open Chess Tournament – 2027 (Category D) Below 1700 rating p… | aicf + chessbase_calendar | `aicf-482208` |
| 2027-01-16 | 2nd Kota International Open Fide Rapid Rating Chess Tournament 2027 | aicf | `aicf-504951` |
| 2027-01-17 | FIDE Rated Chess Tournament | aicf | `aicf-496728` |
| 2027-01-22 | 8th Khannur Below 1700 FIDE Rated Classical Chess Tournament | aicf | `aicf-499274` |
| 2027-01-23 | The Heritage School Chaturanga Rapid Rating Chess Tournament 2027 | aicf | `aicf-511499` |
| 2027-01-24 | 1st Pixel All India Open FIDE rated Rapid Tournament | aicf | `aicf-506782` |
| 2027-01-24 | The Heritage School Chaturanga Blitz Rating 2027 | aicf | `aicf-511500` |
| 2027-01-30 | Sushruta Reddy – Zenith Rapid FIDE Rating Chess Tournament | aicf | `aicf-511686` |
| 2027-01-31 | SportsCentric FIDE Rated Chess Tournament | aicf | `aicf-503923` |
| 2027-01-31 | ICC – CHESSFEE International FIDE RAPID Rating OPEN Chess Tournament 2027 – 6th Edition | aicf + chessfee | `aicf-510448` |
| 2027-02-06 | 17th BBCF International FIDE Below 1650 Rated Chess Tournament | aicf | `aicf-507612` |
| 2027-02-13 | 1st ChessBinder.com open FIDE Rated Rapid tournament powered by BKCC | aicf | `aicf-506423` |
| 2027-02-13 | Rapid FIDE Rated Tournament | kca | `kca-729-CAK-2026` |
| 2027-02-14 | 9th Tarabai Shinde FIDE Rapid Rating Chess Tournament, Nerul, Navi Mumbai | aicf | `aicf-500571` |
| 2027-02-14 | Blitz FIDE Rated Tournament | kca | `kca-730-CAK-2026` |
| 2027-03-26 | 2nd MAHARATHI INTERNATIONAL BELOW 1800 CLASSICAL FIDE RATED CHESS TOURNAMENT | aicf | `aicf-471844` |
| 2027-03-30 | 8th Holi Cup International Open Fide Rating Chess Tournament 2027 | aicf | `aicf-506145` |
| 2027-04-17 | SHRI DHANPAT RAI SACHDEVA MEMORIAL INTERNATIONAL OPEN FIDE RATED RAPID CHESS TOURNAMENT 2027 | aicf | `aicf-507843` |
| 2027-04-18 | SHRI DHANPAT RAI SACHDEVA MEMORIAL INTERNATIONAL OPEN FIDE RATED BLITZ CHESS TOURNAMENT 2027 | aicf | `aicf-507844` |
| 2027-06-18 | Summer Cup Below 1800 International Fide Rating Chess Tournament 2027 | aicf | `aicf-506146` |
| 2027-07-07 | th Ayodhana International Fide Rating Chess Tournament,2027 | aicf | `aicf-487637` |
| 2027-07-23 | WB State Under 17 Open FIDE Rated Chess Championship 2026 | aicf | `aicf-471361` |

</details>

<details><summary><b>name: norm</b> (12)</summary>

| Start | Name | Source | Id |
|---|---|---|---|
| 2027-01-30 | 45th Tamil Nadu IM Norm Closed Circuit Chess Tournament | chessbase_calendar | `chessbase_calendar-6aaa7ca270d3171daede9af8` |
| 2027-01-30 | 46th Tamil Nadu IM Norm Closed Circuit Chess Tournament | chessbase_calendar | `chessbase_calendar-6aaa7ca270d3171daede9af9` |
| 2027-01-30 | 47th Tamil Nadu IM Norm Closed Circuit Chess Tournament | chessbase_calendar | `chessbase_calendar-6aaa7ca270d3171daede9afa` |
| 2027-01-30 | 48th Tamil Nadu IM Norm Closed Circuit Chess Tournament | chessbase_calendar | `chessbase_calendar-6aaa7ca270d3171daede9afb` |
| 2027-01-30 | 49th Tamil Nadu IM Norm Closed Circuit Chess Tournament | chessbase_calendar | `chessbase_calendar-6aaa7ca270d3171daede9afc` |
| 2027-01-30 | 50th Tamil Nadu IM Norm Closed Circuit Chess Tournament | chessbase_calendar | `chessbase_calendar-6aaa7ca270d3171daede9afd` |
| 2027-02-08 | 45th Tamil Nadu IM Norm Closed Circuit Chess Tournament | aicf | `aicf-488283` |
| 2027-02-08 | 46th Tamil Nadu IM Norm Closed Circuit Chess Tournament | aicf | `aicf-488284` |
| 2027-02-08 | 47th Tamil Nadu IM Norm Closed Circuit Chess Tournament | aicf | `aicf-488285` |
| 2027-02-08 | 48th Tamil Nadu IM Norm Closed Circuit Chess Tournament | aicf | `aicf-488286` |
| 2027-02-08 | 49th Tamil Nadu IM Norm Closed Circuit Chess Tournament | aicf | `aicf-488287` |
| 2027-02-08 | 50th Tamil Nadu IM Norm Closed Circuit Chess Tournament | aicf | `aicf-488288` |

</details>

<details><summary><b>name: grandmaster/GM</b> (11)</summary>

| Start | Name | Source | Id |
|---|---|---|---|
| 2026-12-22 | Athens of the East 6 th International Grandmaster Chess Tournaments – (Category – A Above 2100) | aicf | `aicf-482567` |
| 2026-12-22 | Athens of the East 6th International Grandmaster Open Chess Tournament (Category – B Below 2100) | aicf | `aicf-482568` |
| 2026-12-25 | Athens of the East 6th International Grandmaster Open Chess Tournament (Category – C Blitz | aicf | `aicf-482570` |
| 2026-12-26 | Athens of the East 6th International Grandmaster Open Chess Tournament (Category – D Below 1800) | aicf | `aicf-482569` |
| 2026-12-29 | Athens of the East 6th International Grandmaster Open Chess Tournament (Category – E Below 1600) | aicf | `aicf-482662` |
| 2027-01-02 | 17th Chennai Open International Grandmaster Chess Tournament 2026 for Sakthi Group Dr.N.Mahalingam… | aicf + chessbase_calendar | `aicf-482602` |
| 2027-01-14 | 1st Akshaya International Grandmaster Open Chess Tournament – 2027 (Category C) Blitz | aicf + chessbase_calendar | `aicf-482298` |
| 2027-01-21 | 22nd Delhi International Open Grandmasters Chess Tournament – 2027 (Category ‘A’) | aicf + chessbase_calendar | `aicf-484271` |
| 2027-01-21 | 22nd Delhi International Open Grandmasters Chess Tournament – 2027 (Category ‘B’) | aicf + chessbase_calendar | `aicf-484272` |
| 2027-01-25 | 22nd Delhi International Open Grandmasters Chess Tournament – 2027 (Category ‘C’) | aicf + chessbase_calendar | `aicf-484273` |
| 2027-01-30 | “ Late Shri Manohar Parrikar” Goa International Open Grand Master Chess Tournament 2027 (Cat “A”) | aicf | `aicf-505083` |

</details>

<details><summary><b>name: International + open/tournament/chess</b> (3)</summary>

| Start | Name | Source | Id |
|---|---|---|---|
| 2026-12-02 | DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN FIDE CHESS TOURNAMENT 2026 | aicf + chessfee | `aicf-503296` |
| 2026-12-02 | "2-6 DEC" - KANYAKUMARI (TN) - DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN FIDE CHESS TOURNAMENT; P… | chessresults_ind | `chessresults_ind-1519059` |
| 2027-02-26 | DRAGON CHESS ACADEMY 2ND INTERNATIONAL BELOW 1700 FIDE CHESS TOURNAMENT | aicf | `aicf-503298` |

</details>

<details><summary><b>ChessBase site flag</b> (2)</summary>

| Start | Name | Source | Id |
|---|---|---|---|
| 2026-11-21 | The 2nd “Goris Open” International Chess Tournament | chessbase_calendar | `chessbase_calendar-6aed8c9471eeb38805e8d632` |
| 2027-01-16 | VII. SZENTMIKLÓS RAPID OPEN INTERNATIONAL CHESS TOURNAMENT -PRIZE FUND: 1,250 EUR | chessbase_calendar | `chessbase_calendar-6adf890fcc9694e96bf0b4f9` |

</details>

<details><summary><b>sibling section</b> (2)</summary>

| Start | Name | Source | Id |
|---|---|---|---|
| 2027-01-30 | Late Shri Manohar Parrikar” Goa Below 2000 Chess Tournament 2027 (Cat “B”) (via sibling aicf-505083) | aicf | `aicf-505084` |
| 2027-02-03 | Late Shri Manohar Parrikar” Goa Below 1700 Chess Tournament 2027 (Cat “C”) (via sibling aicf-505083) | aicf | `aicf-505086` |

</details>

<details><summary><b>name says FIDE + format/limit</b> (1)</summary>

| Start | Name | Source | Id |
|---|---|---|---|
| 2026-11-28 | South Open FIDE Rapid Chess Tournament 2026 | aicf | `aicf-507029` |

</details>

### 2. The 40 most doubtful "yes" events

**School / inter-school**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| can't tell | 10th WMA Inter School Rapid Rating Chess Tournamnet 2026 1 lakh Prize worth For… (`chessresults_ind-1526947`) | chessresults_ind | Name says "Rapid Rating", but it is an inter-school event seen only on Chess-Results, not on AICF's list. |
| looks correct | 3S INSTITUTE RAPID RATING FIESTA 2026 BY CHESS AT SCHOOL (`aicf-510558`) | aicf | On AICF's list and says "Rapid Rating"; "Chess at School" is the organiser, not a school event. |
| looks correct | 3S INSTITUTE presents FIESTA All India Rapid Rating Chess Tournament 2026. For… (`chessresults_ind-1545661`) | chessresults_ind | The same 3S Institute festival as aicf-510558 (the two are not grouped). |
| looks correct | The Heritage School Chaturanga Rapid Rating Chess Tournament 2027 (`aicf-511499`) | aicf | On AICF's list and says "Rapid Rating"; the school is only the host. |
| looks correct | The Heritage School Chaturanga Blitz Rating 2027 (`aicf-511500`) | aicf | Blitz section of the same Heritage School event; on AICF's list, says "Blitz Rating". |
| looks correct | GIRISTUTI CHECKMATE SCHOOL OF CHESS PRESENTS Under-18 Children's Day Fide Rapid… (`chessresults_ind-1545810`) | chessresults_ind | Says "Fide Rapid Rating"; "Checkmate School of Chess" is an academy. |

**Generic names**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks correct | FIDE Rated Chess Tournament (`aicf-496728`) | aicf | Says "FIDE Rated" and is on AICF's list; the name tells nothing else (no city). |
| looks correct | SportsCentric FIDE Rated Chess Tournament (`aicf-503923`) | aicf | Says "FIDE Rated"; on AICF's list. |
| looks correct | Rapid FIDE Rated Tournament (`kca-729-CAK-2026`) | kca | KCA's own type label is FIDE and the name says "FIDE Rated". |
| looks correct | Blitz FIDE Rated Tournament (`kca-730-CAK-2026`) | kca | KCA's own type label is FIDE and the name says "FIDE Rated". |
| looks correct | International FIDE Rated Above 1800 Open Chess Tournament 2026 (`aicf-487788`) | aicf | Says "FIDE Rated"; ChessBase lists it with the same name. |
| looks correct | International FIDE Rated Below 1800 Open Chess Tournament 2026 (`aicf-487790`) | aicf | Says "FIDE Rated"; ChessBase lists it with the same name. |
| looks correct | 1st INTERNATIONAL RAPID RATING CHESS TOURNAMENT (`aicf-511467`) | aicf | Says "Rapid Rating"; on AICF's list. |
| looks correct | th Ayodhana International Fide Rating Chess Tournament,2027 (`aicf-487637`) | aicf | Says "Fide Rating"; the name starts with a cut-off "th" on AICF's page. |

**"Rated" / "Rating" without the word FIDE**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks correct | Khannur Rapid Rated Chess Tournament – Bengaluru (`aicf-501318`) | aicf | On AICF's list; the Chess-Results copy says "Fide Rapid Rating" with code 494719/KA(R)/2026. |
| looks correct | Chadurangotsava All India Open Rapid Rated Tournament 2026 (`aicf-511064`) | aicf | "Rapid Rated" on AICF's list. |
| looks correct | 1st DPSS Rapid Rating Chess Tournament 2027 (`aicf-499438`) | aicf | "Rapid Rating" on AICF's list. |
| looks correct | Under 18 Open Rapid Rating Chess Tournament 2026 (`aicf-511857`) | aicf | "Rapid Rating" on AICF's list. |
| looks correct | 3rd Pune International Speed Festival 2026 – RAPID Rating Chess Tournament (`aicf-504554`) | aicf | "RAPID Rating" section of the Pune festival; on AICF's list and Chess-Results. |
| looks correct | 3rd Pune International Speed Festival 2026 – BLITZ Rating Chess Tournament (`aicf-504557`) | aicf | "BLITZ Rating" section of the same festival. |
| looks correct | 24th North East Fide Rating Chess Championship (`aicf-503517`) | aicf | "Fide Rating Chess Championship"; on AICF's list and Chess-Results. |

**"Rating" that is only an entry limit**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| can't tell | 1st All India Under-08 Rapid Chess Festival (Below 1600 FIDE Standard & Rapid R… (`chessresults_ind-1538096`) | chessresults_ind | "Below 1600 FIDE Standard & Rapid Ratings" is who may play, not a statement that the festival is rated; only on Chess-Results. |
| looks correct | 1st Akshaya International Grandmaster Open Chess Tournament – 2027 (Category B)… (`aicf-482207`) | aicf | Right answer for a weak reason: "below 2000 rating players only" is a limit, but the Grandmaster Open rule would rate it anyway. |
| looks correct | 1st Akshaya International Grandmaster Open Chess Tournament – 2027 (Category D)… (`aicf-482208`) | aicf | Same as above (Category D, below 1700). |

**Site label disagrees with the name**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks correct | SALEM - 3rd BattleField International Open FIDE Rapid Rating Chess Tournament 2… (`chessfee-1858`) | chessfee | chessfee's label says "TAMILNADU STATE LEVEL", but the name says "International Open FIDE Rapid Rating" and AICF lists it (aicf-510562). |
| looks correct | 06 Dec; 3rd Battel Field International Open FIDE Rapid Rating Chess Tournament… (`chessresults_ind-1538330`) | chessresults_ind | Same Salem event a third time; the three copies are not grouped, so it shows three times. |

**"Open" / "International" with no FIDE or rated word (inferred)**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks correct | The 2nd “Goris Open” International Chess Tournament (`chessbase_calendar-6aed8c9471eeb38805e8d632`) | chessbase_calendar | Armenia. The name says only "International ... Tournament", but ChessBase's own flag says FIDE rated (the name rule never ran). |
| looks correct | VII. SZENTMIKLÓS RAPID OPEN INTERNATIONAL CHESS TOURNAMENT -PRIZE FUND: 1,250 E… (`chessbase_calendar-6adf890fcc9694e96bf0b4f9`) | chessbase_calendar | Hungary. Same: ChessBase's own flag says FIDE rated. |
| looks correct | DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN FIDE CHESS TOURNAMENT 2026 (`aicf-503296`) | aicf | Says "FIDE" (just not "FIDE Rated"), so the rule's answer is right; the reason recorded is "inferred". |
| looks correct | "2-6 DEC" - KANYAKUMARI (TN) - DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN FIDE… (`chessresults_ind-1519059`) | chessresults_ind | Same Dragon event as aicf-503296; not grouped with it. |
| looks correct | DRAGON CHESS ACADEMY 2ND INTERNATIONAL BELOW 1700 FIDE CHESS TOURNAMENT (`aicf-503298`) | aicf | "International Below 1700 FIDE Chess Tournament"; says FIDE. |
| looks correct | 17th Chennai Open International Grandmaster Chess Tournament 2026 for Sakthi Gr… (`aicf-482602`) | aicf | Chennai Open International Grandmaster: a well-known rated open. |

**Blitz side events of Grandmaster festivals**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks correct | Athens of the East 6th International Grandmaster Open Chess Tournament (Categor… (`aicf-482570`) | aicf | "Category C Blitz" of the Athens of the East GM Open, listed separately on AICF. |
| looks correct | 1st Akshaya International Grandmaster Open Chess Tournament – 2027 (Category C)… (`aicf-482298`) | aicf | "Category C Blitz" of the Akshaya GM Open, on AICF and ChessBase. |

**Sibling sections**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks correct | Late Shri Manohar Parrikar” Goa Below 2000 Chess Tournament 2027 (Cat “B”) (`aicf-505084`) | aicf | Goa Below 2000 (Cat B): sibling of the Goa International GM Open (Cat A), same brochure; on AICF's list. |
| looks correct | Late Shri Manohar Parrikar” Goa Below 1700 Chess Tournament 2027 (Cat “C”) (`aicf-505086`) | aicf | Goa Below 1700 (Cat C): same festival. |

**Norm events**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks correct | 45th Tamil Nadu IM Norm Closed Circuit Chess Tournament (`aicf-488283`) | aicf | IM norm closed tournaments are FIDE rated by definition. |
| looks correct | 45th Tamil Nadu IM Norm Closed Circuit Chess Tournament (`chessbase_calendar-6aaa7ca270d3171daede9af8`) | chessbase_calendar | Rated is right, but ChessBase gives 30 Jan, AICF 8 Feb, so the six TN IM Norm events show twice (12 cards). |

**Other**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks correct | WB State Under 17 Open FIDE Rated Chess Championship 2026 (`aicf-471361`) | aicf | Says "FIDE Rated". But its dates are suspect (start 23-07-2027, end 26-07-2026): it was probably July 2026 and is not really upcoming. |
| looks correct | 1 Lakh Cash Prize @399 Entry fees - "Late. Madanbhau Patil Memorial Internation… (`chessresults_ind-1540566`) | chessresults_ind | "1 Lakh Cash Prize" name that also says "International Open FIDE Rapid Rating". |

### 3. "Not stated" events whose name suggests FIDE

**National championships**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| looks wrong | 63rd National Chess Championship – 2026 (`aicf-485283`) | aicf | 63rd National Chess Championship: India's national championship, FIDE rated; on AICF's list. |
| looks wrong | 52nd NATIONAL WOMEN CHESS CHAMPIONSHIP 2026 (`aicf-496730`) | aicf | 52nd National Women Chess Championship: FIDE rated. |
| looks wrong | National U19 (Junior )Chess Championship 2026 (`aicf-494716`) | aicf | National U19 (Junior) Championship: FIDE rated. |
| looks wrong | 55th National Junior Championship 2025 Kolkata (`chessresults_ind-1548787`) | chessresults_ind | 55th National Junior Championship, Kolkata: the Chess-Results copy of aicf-494716 (same dates and city), not grouped because the name says 2025. |
| looks wrong | 40th National Junior Girls Championship 2025 Kolkata (`chessresults_ind-1548779`) | chessresults_ind | 40th National Junior Girls Championship, Kolkata: the girls' section of the same event. |
| looks wrong | National School Chess Championship 2026 (`aicf-502253`) | aicf | National School Chess Championship: an AICF national championship; these are rated (check the brochure to be sure). |
| looks wrong | National Team Chess Championship (`aicf-504954`) | aicf | National Team Chess Championship: rated classical team event (check the brochure to be sure). |

**Open festivals on AICF's list, name says nothing**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| can't tell | Pune Grand Slam Chess Festival – CLASSICAL (`aicf-484584`) | aicf | Pune Grand Slam Chess Festival - Classical: almost everything on AICF's list is rated, but the name does not say. |
| can't tell | Pune Grand Slam Chess Festival – RAPID (`aicf-484586`) | aicf | Pune Grand Slam - Rapid: same. |
| can't tell | Pune Grand Slam Chess Festival – BLITZ (`aicf-484587`) | aicf | Pune Grand Slam - Blitz: same. |
| can't tell | 1st Late Bharatji Budhmalji Kunkulol Memorial Rapid Chess tournament 2026 (`aicf-484619`) | aicf | Kunkulol Memorial Rapid: on AICF's list, name says nothing. |
| can't tell | 2nd Late Bharatji Budhmalji Kunkulol Memorial Blitz Chess tournament 2026 (`aicf-484620`) | aicf | Kunkulol Memorial Blitz: same. |
| can't tell | SIVASAGAR OPEN 2027 (`aicf-481938`) | aicf | Sivasagar Open 2027: on AICF's list, name says nothing. |

**Prize-money opens and abroad**

| Verdict | Name | Source | Reason |
|---|---|---|---|
| can't tell | 5th Sajjan Academy Open Blitz Chess Tournament 2026 PRIZE FUND - 50,000/- Early… (`chessresults_ind-1528935`) | chessresults_ind | Sajjan Academy Open Blitz, prize fund 50,000: only on Chess-Results; small prize, leans not rated. |
| can't tell | 2026 US Masters (`chessbase_calendar-6aaa7ca270d3171daede9add`) | chessbase_calendar | 2026 US Masters (USA): a known FIDE-rated norm event, but nothing on ChessBase's listing says so. |

