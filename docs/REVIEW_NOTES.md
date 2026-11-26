# Review notes (27 Nov 2026)

These notes are about the data on `main` at commit `de879bf`: `data/review.csv` and
`data/quality.json`, both written on 26 Nov 2026 at 17:53 IST. Nothing in the data or the code
has been changed. Every fix below is a **suggestion**, ready for you to check and apply.

`main` does not have the TNSCA (T8) or KSCA (T10) sources yet. Once they are merged, some of the
Tamil Nadu and Karnataka gaps below may fill on their own.

## Where we stand

- `review.csv` has **173 lines**: 168 events in the next 30 days with something missing, and
  **5 possible duplicates** (`quality.json` → `review` says the same).
- Fully known in the next 30 days: **17.6 %** (target 95 %). By source: AICF 65.3 %,
  ChessBase 50 %, chessfee 3.7 %, Chess-Results 1.6 %, KCA 0 %.
- What is missing (one event can miss several things): FIDE status 143, state 97,
  register or brochure link 96, format 36.
- **Dates:** no line in `review.csv` is missing dates or has suspect dates. Across the whole
  file there are 4 AICF events with suspect dates. Only one counts as upcoming:
  `aicf-471361`, *WB State Under 17 Open*, which AICF lists as 23-07-2027 to 26-07-2026. That is
  most likely a wrong start year, but it is outside the 30-day list. Check it with a dates line
  in `overrides.csv`.
- 122 of the 204 events in the next 30 days come from Chess-Results. That source causes most of
  the lines.

---

## 1. Prince vs Enpassant (possible duplicate, **not decided**)

`review.csv` line 171 / `dedup_review.csv` line 6, score 0.660 ("possible").

| | `chessfee-1817` | `chessresults_ind-1547773` |
|---|---|---|
| Name | CHENNAI - PRINCE 1ST STATE LEVEL CHILDREN CHESS TOURNAMENT – 29 NOV | 29 Nov \| Enpassant 1st Tamil Nadu State Level Children's Chess Tournament |
| Dates | 2026-11-29 (one day) | 2026-11-29 (one day) |
| Place | Prince Shri Venkateshwara Arts and Science College, Gowrivakkam, Chennai 600073 | Velankanni Public Senior Secondary School, Muthamizh Nagar, Kodungaiyur, Chennai |
| State / city | Tamil Nadu / Chennai | Tamil Nadu / Chennai |
| Organiser | G. MASILAMANI | Enpassant Chess School |
| Source | chessfee | Chess-Results |
| Source page | https://www.chessfee.com/tmt_details.php?id=1817 | https://chess-results.com/tnr1547773.aspx?lan=1 |
| Register link | https://www.chessfee.com/treg.php?id=1817 | none |
| Brochure | https://www.chessfee.com/admin/Brochure/29%20NOV-TN%20STATE%20TMT-GM%20Prince.pdf | https://chess-results.com/UploadData.aspx?lan=1&tnr=1547773&Uid=1 |
| Grouping now | its own group, shown | already grouped as **same** with `chessfee-1853` (score 1.00), not shown |
| Seen | 24–26 Nov, still listed | 25 Nov only, `gone_from_source` = true |

**How it looks: not the same tournament.** You decide, though.

- The venues differ: a college in Gowrivakkam (PIN 600073, south Chennai) and a school in
  Kodungaiyur (PIN 600118, north Chennai).
- The organisers differ: G. Masilamani vs Enpassant Chess School. The brochures differ too.
- The Chess-Results record already has its real twin: chessfee lists the Enpassant event
  as `chessfee-1853`, with the same venue and organiser, and the two are grouped at score 1.00.
- The score only reached 0.60 on the name because the shared words are generic ("children",
  "state", "1st"). The words that tell them apart, *Prince* and *Enpassant*, do not match.
- Side note: Prince's own Chess-Results page is probably `chessresults_ind-1534051` (*Prince
  Shri Venkateshwara Arts and Science College State Level Chess Tournament*, same venue, same
  day). It was not matched (score 0.26). See group B below.

**Line for you to add to `data/manual/pairs.csv` (not added).** `pairs.csv` only accepts
`same` or `not_same`. A line with `undecided` would stop the build, and
`tests/test_t4b.py::test_committed_pairs_csv_is_valid` would fail. So the line is here for
you to paste with your decision:

```csv
chessfee-1817,chessresults_ind-1547773,not_same,Prince (Gowrivakkam college) and Enpassant (Kodungaiyur school) are different venues and organisers; Enpassant is chessfee-1853
```

If you decide they are the same, change `not_same` to `same`.

---

## 2. The 20 most important problems

They are ranked by harm: wrong or doubled events on the site come first, then missing facts on
big events, then the long tail.

| # | Event(s) | Problem | Group |
|---|---|---|---|
| 1 | `chessfee-1817` / `chessresults_ind-1547773` | Possible duplicate still open (Prince vs Enpassant, section 1) | A |
| 2 | `chessresults_ind-1550485` *wkjiuwu* (organiser "ere4tgbvv") | Test/junk entry on Chess-Results, shown on the site | D |
| 3 | `chessresults_ind-1550499` *syudswfyjjvhygyerrr* (organiser "kjgfukgv") | Test/junk entry, shown on the site | D |
| 4 | `chessresults_ind-1550113`, `chessresults_ind-1550089` *REGULAR PLAYING SESSION 157/158* | Academy training sessions, not tournaments | D |
| 5 | `chessbase_calendar-…9adf` = `aicf-487790` (Goa, Below 1800, 27 Nov) and `chessbase_calendar-…9ade` = `aicf-487788` (Goa, Above 1800, 26 Nov) | Same name, date and place, but **shown twice**: the name has fewer than 2 distinctive words | B |
| 6 | `chessresults_ind-1502060` Sarji Renuka, Haveri, 29 Nov = `aicf-499268` | Shown twice; the Chess-Results name carries the AICF code `499268/KA(R)/2026`, which is not read | C |
| 7 | `chessresults_ind-1514745` 1st Raydiance, Kalyan, 29 Nov = `aicf-504058` | Shown twice (the name has extra tail words and the typo "Internationa") | B |
| 8 | `chessresults_ind-1545661` 3S Institute Fiesta, 29 Nov = `aicf-510558` | Shown twice | B |
| 9 | `chessresults_ind-1538330` 3rd "Battel" Field, 6 Dec = `aicf-510562` (Battle Field, Salem) | Shown twice (spelling "Battel") | B |
| 10 | `chessresults_ind-1548787` *55th National Junior Championship **2025** Kolkata* and `chessresults_ind-1548779` *40th National Junior Girls …2025*, 11 Dec, vs `aicf-494716` (National U19 Junior, Kolkata, codes 494716 + 494717) | Shown separately; the year in the name is wrong; the age guard blocks it (U19 on one side only) | B |
| 11 | `chessresults_ind-1539417` = `chessfee-1847` (1st RIMS International FIDE Rapid, Krishnagiri, 29 Nov) | Shown twice, **both** missing the state | B, E |
| 12 | `chessresults_ind-1539360` = `chessfee-1866` (K.R. Palanivelu Memorial, Karanthai, Thanjavur, 29 Nov) | Shown twice; the age guard blocks it (one name lists U07–U17) | B |
| 13 | `chessresults_ind-1534051` = `chessfee-1817` (Prince college, Gowrivakkam, 29 Nov) | Probably the same, not matched | B |
| 14 | `chessresults_ind-1538873` = `chessfee-1835` (4th TN State Level, Mohamed Sathak AJ Engineering College, Siruseri, Sri Raghavendra Chess Academy, 29 Nov) | Probably the same, not matched | B |
| 15 | `chessresults_ind-1541897` / `chessfee-1842` (Mohamed Sathak College of Arts & Science, Sholinganallur, 6 Dec) | Possible duplicate (0.575). Same venue and the same contact person (Sathyan K) | A |
| 16 | `chessresults_ind-1550815` / `chessfee-1860` (Vidvath Chess Trophy, Guruvayankere, 27 Nov), plus `chessresults_ind-1550805` (its second section) | Possible duplicate (0.617); both are missing the state | A, E |
| 17 | `chessresults_ind-1549060` / `chessfee-1835`, and `chessfee-1876` / `aicf-486710` | Two more possible-duplicate lines (see group A) | A |
| 18 | `aicf-485283` *63rd National Chess Championship*, Varanasi, 29 Nov; `aicf-496730` *52nd National Women Chess Championship*, Telangana, 30 Nov | National championships with an unknown FIDE status (and format for the women's) | F |
| 19 | `aicf-482567`, `aicf-482568`, `aicf-482569` *Athens of the East 6th International GM* (Categories A/B/D), Madurai, 22–26 Dec | Format unknown on all three sections | F |
| 20 | 8 chessfee *TN State Level* events (for example `chessfee-1864` Dindigul, `chessfee-1869` Aruppukottai, `chessfee-1856` Pennadam, `chessfee-1863` Kovilpatti, `chessfee-1867` Ranipet, `chessfee-1870` Pallikaranai, `chessfee-1862` Namakkal, `chessfee-1874` Sirkali) | State missing, although the site's own category says "TAMILNADU STATE LEVEL - only TAMILNADU PLAYERS" | E |

---

## 3. Groups by cause, with the cleanest fix for each

### A. Possible duplicates still to settle (5 lines)

**Cause.** Names get a middling score from generic words (*state, level, children*, the edition
number). Two of the five flagged records are **already grouped** with their real twin, but they
still carry a weaker "possible" flag that points to a third event.

| Line | Pair | How it looks | Why |
|---|---|---|---|
| 171 | `chessfee-1817` / `chessresults_ind-1547773` | not the same | see section 1 |
| 172 | `chessfee-1835` / `chessresults_ind-1549060` | not the same | Chennai (Mohamed Sathak, Sri Raghavendra) vs Aruppukottai (Genius Chess Academy); 1549060 is already grouped with `chessfee-1869`, its real twin |
| 173 | `chessfee-1842` / `chessresults_ind-1541897` | same | same college, address and contact person, 6 Dec |
| 170 | `chessfee-1860` / `chessresults_ind-1550815` | same | Vidvath Trophy, Inter-District Rapid, same college ("Guruvankere" spelling), 27 Nov |
| 174 | `aicf-486710` / `chessfee-1876` | same | Eight Square 4th International Rapid, 10 Jan, same organiser. chessfee lists it twice (`chessfee-1832` is already grouped with the AICF record), so the tool will not add a second chessfee record by itself |

**Fix (manual).** These lines are for `pairs.csv`. Check each one first:

```csv
chessfee-1835,chessresults_ind-1549060,not_same,Chennai vs Aruppukottai; different organisers; 1549060 is chessfee-1869
chessfee-1842,chessresults_ind-1541897,same,Mohamed Sathak College of Arts and Science Sholinganallur 6 Dec (same contact)
chessfee-1860,chessresults_ind-1550815,same,Vidvath Chess Trophy Inter-District Rapid 27 Nov
aicf-486710,chessfee-1876,same,Eight Square 4th International Rapid 10 Jan (chessfee lists it twice: 1832 and 1876)
```

**Rule (later).** When a record is already in a group as *same* (score 0.80 or more), do not
write a review line for a weaker *possible* match with a third event. The flag can stay in the
data.

### B. The same tournament shown twice, not even flagged (about 12 pairs)

**Causes.**

1. **Name tails Chess-Results adds** that `strip_name_tails()` does not know yet: "Contact …",
   "For Registration …", "Registration contact", "For More Details …", "Total Cash Prize …",
   "Free Lunch …", "1st Round reporting …", "Gold & Silver Coins …", a date or the venue
   written in front ("29th NOV 2026-MOHAMED SATHAK …"). These add words that lower the score
   (RIMS 0.26, Raydiance 0.22, 3S Fiesta 0.39, Anandhan 0.33, Siruseri 0.17).
2. **Names with fewer than 2 distinctive words** ("International FIDE Rated Below 1800 Open
   Chess Tournament 2026") can never prove *same*, even when everything else is identical (Goa).
3. **The age guard fires when only one side gives ages.** In `section_difference()` the rating
   limit, age group and category count as different when one name has them and the other has
   none (only the format needs both). That blocks Palanivelu (U07–U17 in the Chess-Results
   name) and National Junior (U19 on AICF).
4. Spelling differences: "Battel" / "Battle", "Internationa".

**Fix (manual, cleanest for now).** Add `pairs.csv` lines. A forced *same* also overrides
the age guard and the same-source rule. Check each one first:

```csv
aicf-487790,chessbase_calendar-6aaa7ca270d3171daede9adf,same,Goa Below 1800 27 Nov: same name date place
aicf-487788,chessbase_calendar-6aaa7ca270d3171daede9ade,same,Goa Above 1800 26 Nov: same name date place
aicf-504058,chessresults_ind-1514745,same,1st Raydiance International Rapid Kalyan 29 Nov
aicf-510558,chessresults_ind-1545661,same,3S Institute Fiesta Rapid Rating 29 Nov
aicf-510562,chessresults_ind-1538330,same,3rd Battle Field International Rapid Salem 6 Dec (Battel on Chess-Results)
chessfee-1847,chessresults_ind-1539417,same,1st RIMS International FIDE Rapid Krishnagiri 29 Nov
chessfee-1866,chessresults_ind-1539360,same,K.R. Palanivelu Memorial Karanthai Thanjavur 29 Nov
chessfee-1817,chessresults_ind-1534051,same,Prince college Gowrivakkam 29 Nov
chessfee-1835,chessresults_ind-1538873,same,4th TN State Level Mohamed Sathak AJ Engineering Siruseri 29 Nov
chessfee-1859,chessresults_ind-1539367,same,Anandhan 12th State Level Pammal 6 Dec
```

The National Junior pair needs a closer look first. AICF has **one** record with two codes
(494716 and 494717, most likely the open and girls sections), but Chess-Results has two records,
and both names say "2025". Check the AICF brochure first. If they match, add
`aicf-494716,chessresults_ind-1548787,same` and `aicf-494716,chessresults_ind-1548779,same`.

The Goa pair `aicf-487788` / `chessresults_ind-1487030` (QQChess, Quepem, "1800 and above",
26 Nov) may also be the same. The rating-limit guard blocks it because "1800 AND ABOVE" is
not read as a limit. Check the brochure first.

**Rules (later, one at a time, each with tests).**

- Add the tails above to `strip_name_tails()` (comparison only; the stored name stays).
- Read "above" when it comes *after* the number ("1800 AND ABOVE", "1800 & above") in the limit
  pattern.
- Age guard: consider treating "one side has no ages" as unknown rather than different, but
  **only** when the other side lists several ages (a festival page), so a single U11 section
  still never merges with the open event. This needs care. `pairs.csv` is safer until there
  are fixtures.

### C. AICF codes in Chess-Results names that are not read (5 records)

**Cause.** `aicf_codes_in()` only reads a code written next to the word "AICF" ("AICF Event
Code: 502180/KL(R)/2026"). Several Chess-Results names write the code alone, as
`499268/KA(R)/2026` (`chessresults_ind-1502060` Sarji Renuka, `chessresults_ind-1544300`
Puneeth Rajkumar Cup 511685, `chessresults_ind-1502344` Khannur 494719).

**Fix (rule, cleanest).** Also accept the AICF code's own full form, *6 digits / 2 letters (R or
no R) / year*, without the word AICF. This pattern is strict, so it does not catch phone
numbers or prize amounts. That gives a shared AICF code, which is strong proof, so Sarji
Renuka groups with `aicf-499268` by itself. The 2 letters are also a state (`KA` =
Karnataka, through the existing state-code table), which fills the missing state.

**Until then (manual):** `aicf-499268,chessresults_ind-1502060,same,AICF code 499268 in the Chess-Results name`

### D. Junk and non-tournament entries (4 records)

**Cause.** Chess-Results lets anyone create a tournament. Two are keyboard-mash test entries,
and two are an academy's weekly training sessions.

**Fix (manual, `overrides.csv`, hide; nothing is deleted).**

```csv
chessresults_ind-1550485,,,,,yes,,Test entry on Chess-Results (nonsense name and organiser),,,,,,
chessresults_ind-1550499,,,,,yes,,Test entry on Chess-Results (nonsense name and organiser),,,,,,
chessresults_ind-1550089,,,,,yes,,Academy training session not a tournament,,,,,,
chessresults_ind-1550113,,,,,yes,,Academy training session not a tournament,,,,,,
```

No rule is suggested: a "nonsense name" detector would guess. Hiding them by hand is safer
and rare.

### E. State missing although the page says where (97 events; about 70 fixable)

**Causes.**

1. **The town is in the venue text, not in its own field.** `_CITY_TO_STATE` knows Lucknow,
   Patna, Indore, Siliguri, Hyderabad and Cuddalore, but the town only appears inside a venue
   string ("Shivani Public School (…) Lucknow", "SGSITS Indore", "B-16 … Gaur City …
   Ghaziabad"), so `city` stays empty and the state too.
2. **Towns not in the table:** Ghaziabad, Kanpur, Prayagraj, Budaun (UP); Tumakuru, Davangere,
   Haveri, Koppal, Sullia, Belgaum (Karnataka: the table has Belagavi but not the old name
   Belgaum); Kalyan, Sangli, Nandurbar, Bhandara (Maharashtra); Krishnagiri, Dindigul,
   Kanchipuram, Namakkal, Kovilpatti, Aruppukottai, Sirkali, Ranipet, Pallikaranai (TN);
   Edappally, Karavaloor (Kerala); Puri (Odisha); Ujjain (MP); Rishra/Hooghly (WB);
   Udharbond (Assam); Pragathi Nagar / Kukatpally / Nizampet (Hyderabad).
3. **chessfee TN events:** the category "TAMILNADU STATE LEVEL - only TAMILNADU PLAYERS" is
   not used for the state.
4. **"(TN)" written in the name**: "14th LCCA … at Kanyakumari (TN)". Kanyakumari is in the
   table, but the town sits inside the name, not the place.

**Fixes (rules, cleanest; each one is best effort and leaves `null` when unsure).**

- Look for a known town **anywhere in `place_text`** (then in the name), and set the state only
  when **exactly one** known town is found. Example of why "exactly one" matters: "SILIGURI
  INDORE STADIUM" contains both Siliguri (WB) and Indore (MP). It is in Siliguri, so with two
  towns found it must stay `null`.
- Extend `_CITY_TO_STATE` with the towns in point 2 that sit in only one state. Leave out
  ambiguous ones (Sagar/Sagara, Bilaspur, Aurangabad, Udaipur stay out as now).
- chessfee: the category "TAMILNADU STATE LEVEL" gives state Tamil Nadu. This is stated by the
  site, not guessed. That alone fixes 8 lines.

**Manual (for the few that stay):** `aicf-511065` *GH Raisoni Memorial Bilaspur* has no state,
and Bilaspur is ambiguous (Chhattisgarh or Himachal). Check the brochure, then add
`aicf-511065,,,,<state>,,,Checked brochure,,,,,,`.

### F. FIDE status or format unknown on AICF, KCA and chessfee events (about 50 events)

**Cause.** The name says nothing ("National Chess Championship", "TN State Level Children's"),
and no site gives a flag. By the rules this is never guessed.

**Fix (manual, `overrides.csv`).** `review.csv` already has a ready `line_to_add` with `?` for
each of these lines. Start with the big events, because one brochure answers each of them:

- `aicf-485283` 63rd National Chess Championship (Varanasi, 29 Nov): FIDE status.
- `aicf-496730` 52nd National Women Chess Championship (30 Nov): FIDE status and format.
- `aicf-494716` National U19 Junior (Kolkata, 11 Dec) and `aicf-502253` National School
  Championship (Gujarat, 16 Dec): FIDE status and format.
- `aicf-482567`, `aicf-482568`, `aicf-482569` Athens of the East (one brochure, three
  sections): format.
- `aicf-487788`, `aicf-487790` (Goa), `aicf-484348` (Visakhapatnam), `aicf-485006` (Udaipur),
  `aicf-484279` (Dibrugarh), `aicf-503296` (Kanyakumari), `aicf-494155` (Tirupattur): format.
- KCA `kca-743/746/747-CAK-2026` (CiS team championship, three categories, one brochure) and
  `kca-740-CAK-2026`: format and FIDE status.

No rule is suggested for the chessfee *TN State Level Children's* events. They are usually
not FIDE rated, but "usually" is a guess. Use the overrides.

### G. Chess-Results: FIDE status and links (about 110 events, the long tail)

**Cause.** The Chess-Results lists do not say whether an event is FIDE rated, and few
tournament pages carry a clearly labelled registration link. Most of these are one-day school
and academy events (Hyderabad OGCA age groups, Castle & Crown Rishra, GSF Kolkata, Raisoni
Raipur, Adroit Dehradun, Chinmaya Coimbatore, Gaur City Ghaziabad, Avishkar …).

**Fix.**

- **Rule (check first):** Chess-Results tournament pages normally have a *Rating calculation*
  line. We already fetch the page for new or changed events, so reading that line would add no
  requests. Our trimmed fixtures (`tests/fixtures/sources/chessresults_tnr*.html`) do not
  contain it, so save a real page as a fixture first and check what it says. If the line says
  rated or not rated, use it as "stated". If not, leave it.
- Grouping (group B) removes many of these lines: the AICF or chessfee primary already has the
  links and state.
- The rest: overrides only for events you care about. The others can stay; they leave the list
  once they are over.
- Many of these records are `gone_from_source` = true while they are still upcoming. This is
  the 50-per-list limit of Chess-Results (see README), not a real disappearance.

### H. Names that carry extra text (display only)

Many Chess-Results names include prize money, "Free Lunch", "Registration contact",
"For More Details", ☎ or 💐 symbols, or the wrong year ("National Junior … 2025" in Dec 2026).
The phone numbers are already removed by `strip_phones()`, but the words around them stay
("Registration contact", "CONT: T.RAJU").

**Fix.** Leave the stored name as the source wrote it (facts only, no rewriting). The website
and app can trim the display. Group B's tail rule covers the comparison side. One check:
`chessresults_ind-1514745` has organiser "IA Gourav, Kumar Ray 25708651". Those 8 digits look
like a FIDE ID, not a phone number (Indian numbers have 10 digits), so `strip_phones()` is right
to keep it.

---

## Order suggested

1. Section 1 (Prince vs Enpassant) and group A: 5 `pairs.csv` lines, 10 minutes.
2. Group D: 4 hide lines.
3. Group B: the `pairs.csv` lines above, after a quick check of each brochure.
4. Group F: the national events first (brochures).
5. Rules, one pull request each, with tests: C (AICF code pattern), E (town anywhere in the
   place, TN category), then B (name tails, "1800 and above"), then G (Chess-Results rating
   line, after a real fixture).
