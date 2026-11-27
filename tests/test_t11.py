"""T11: fixes from docs/REVIEW_NOTES.md and docs/FIDE_CHECK.md.

1. pairs.csv: the 7 T5 "undecided" lines are "same"; Prince vs Enpassant is "not_same"; the
   REVIEW_NOTES pairs with clear evidence are in. A pairs.csv "same" across a date gap no longer
   keeps the tournament's other copies out of the group.
2. Grouped records whose start dates are more than a day apart get a "dates_disagree" line in
   review.csv; the IM Norm events show TNSCA's dates through overrides.csv.
3. "FIDE" next to Open / Chess / Tournament / TMT: an inferred yes becomes a stated yes (label
   only, never a new yes or no).
4. The 4 junk Chess-Results entries are hidden.
5. aicf-471361 (WB State Under 17) has dates from AICF's own listing.
6. AICF codes in their full form ("499268/KA(R)/2026") are read without the word AICF.
7. State from the venue text (exactly one known town), and chessfee's TAMILNADU STATE LEVEL label.
8. Pudukottai = Pudukkottai, "Tirupattur DT" = Tirupattur; a district is never its town.
9. Equal scores: the pair with the lower ids is grouped first, whatever order the records came in.
"""
import csv
import io
import json

import pytest

import build_events as be
import dedup
import quality
import verify_published as vp
from conftest import by_id, write_manual
from eventlib import (aicf_code_state_in, aicf_codes_in, canonical, fide_evidence, fide_named,
                      town_state_in)
from test_t4b import PAIRS_HEADER, compare, ev, group, run_offline, snapshot_dir

OVERRIDES_HEADER = ",".join(be.OVERRIDES_CSV_COLUMNS) + "\n"
TODAY = "2026-11-24"  # conftest.NOW


def record(**fields) -> dict:
    return canonical({"first_seen": "2026-11-01", "last_seen": "2026-11-25", "country": "IN", **fields})


def committed_pairs() -> dict:
    errors, warnings = [], []
    rows = be.load_pairs(be.DATA_DIR, errors, warnings)
    assert errors == []
    return {tuple(sorted((r["a"], r["b"]))): r for r in rows}


def committed_overrides() -> dict:
    errors, warnings = [], []
    items = be.load_overrides(be.DATA_DIR, errors, warnings)
    assert errors == [] and warnings == []
    return {item["key"]: item for item in items}


def review_rows(folder) -> list[dict]:
    return list(csv.DictReader(io.StringIO((folder / "review.csv").read_text("utf-8"))))


# ---- 1. pairs.csv ------------------------------------------------------------------------
T5_PAIRS = [("aicf-486240", "chessbase_calendar-6aaa7ca270d3171daede9adc")] + [
    (f"aicf-{code}", f"chessbase_calendar-6aaa7ca270d3171daede9a{tail}")
    for code, tail in zip(range(488283, 488289), ("f8", "f9", "fa", "fb", "fc", "fd"))]

REVIEW_NOTES_PAIRS = {
    ("chessfee-1817", "chessresults_ind-1547773"): "not_same",   # Prince vs Enpassant
    ("chessfee-1835", "chessresults_ind-1549060"): "not_same",   # Siruseri vs Aruppukottai
    ("chessfee-1842", "chessresults_ind-1541897"): "same",
    ("chessfee-1860", "chessresults_ind-1550815"): "same",
    ("aicf-486710", "chessfee-1876"): "same",
    ("aicf-486710", "chessfee-1832"): "same",                    # chessfee's first copy
    ("aicf-487790", "chessbase_calendar-6aaa7ca270d3171daede9adf"): "same",
    ("aicf-487788", "chessbase_calendar-6aaa7ca270d3171daede9ade"): "same",
    ("aicf-504058", "chessresults_ind-1514745"): "same",
    ("aicf-510558", "chessresults_ind-1545661"): "same",
    ("aicf-510562", "chessresults_ind-1538330"): "same",
    ("chessfee-1847", "chessresults_ind-1539417"): "same",
    ("chessfee-1866", "chessresults_ind-1539360"): "same",
    ("chessresults_ind-1539360", "tnsca-CO-206-TNJ-26-27"): "same",  # keeps TNSCA's copy with it
    ("chessfee-1817", "chessresults_ind-1534051"): "same",
    ("chessfee-1835", "chessresults_ind-1538873"): "same",
    ("chessfee-1859", "chessresults_ind-1539367"): "same",
}
# The notes were unsure about these (check the brochure first): they must stay out.
LEFT_OUT = [("aicf-494716", "chessresults_ind-1548787"), ("aicf-494716", "chessresults_ind-1548779"),
            ("aicf-487788", "chessresults_ind-1487030")]


def test_the_seven_t5_lines_are_now_same_and_nothing_is_undecided():
    pairs = committed_pairs()
    assert not [r for r in pairs.values() if r["decision"] == "undecided"]
    for pair in T5_PAIRS:
        assert pairs[tuple(sorted(pair))]["decision"] == "same", pair


def test_review_notes_pairs_are_in_pairs_csv_with_a_note():
    pairs = committed_pairs()
    for pair, decision in REVIEW_NOTES_PAIRS.items():
        row = pairs[tuple(sorted(pair))]
        assert row["decision"] == decision and row["note"], pair
    for pair in LEFT_OUT:
        assert tuple(sorted(pair)) not in pairs


def manchester(event_id, start, **extra):
    return ev(event_id, "2nd Manchester City International Below 1800 Fide Rated Tournament", start,
              city="Coimbatore", state="Tamil Nadu", **extra)


def forced(a, b, decision="same"):
    return {"line": 2, "a": a, "b": b, "decision": decision, "note": None}


def test_a_forced_same_across_a_date_gap_keeps_the_other_copies_in_the_group():
    # AICF, chessfee, Chess-Results and TNSCA say 27 Nov; ChessBase says 21 Nov.
    records = [manchester("aicf-486240", "2026-11-27"), manchester("chessfee-1727", "2026-11-27"),
               manchester("chessresults_ind-1538894", "2026-11-27"),
               manchester("tnsca-RR-24-CBE-26-27", "2026-11-27"),
               manchester("chessbase_calendar-adc", "2026-11-21")]
    events, result, _ = group(*records, pairs=[forced("aicf-486240", "chessbase_calendar-adc")])
    assert {e["group_id"] for e in events.values()} == {"aicf-486240"}
    assert result["merged"] == 4


def test_without_the_forced_pair_the_date_gap_still_keeps_them_apart():
    records = [manchester("aicf-486240", "2026-11-27"), manchester("chessbase_calendar-adc", "2026-11-21")]
    events, _, _ = group(*records)
    assert events["chessbase_calendar-adc"]["merged_into"] is None


def test_a_vouched_date_gap_does_not_let_in_a_third_date():
    # chessfee-9 shares the AICF code (strong proof) but starts on 10 Dec: neither 27 Nov nor
    # the 21 Nov the person vouched for, so the date gap to the ChessBase record still blocks it.
    records = [manchester("aicf-486240", "2026-11-27", codes=["486240"]),
               manchester("chessbase_calendar-adc", "2026-11-21"),
               manchester("chessfee-9", "2026-12-10", codes=["486240"])]
    events, _, _ = group(*records, pairs=[forced("aicf-486240", "chessbase_calendar-adc")])
    assert events["chessbase_calendar-adc"]["merged_into"] == "aicf-486240"
    assert events["chessfee-9"]["merged_into"] is None


# ---- 2. dates that disagree --------------------------------------------------------------
IM_NORM = "45th Tamil Nadu IM Norm Closed Circuit Chess Tournament"


def im_norm_snapshot(folder):
    snapshot_dir(folder, [
        ev("aicf-488283", IM_NORM, "2027-02-08", "2027-02-13", city="Chennai", state="Tamil Nadu"),
        ev("tnsca-IM-45-TN-26-27", IM_NORM, "2027-01-30", "2027-02-04", city="Chennai", state="Tamil Nadu"),
        ev("chessbase_calendar-af8", IM_NORM, "2027-01-30", "2027-02-04", city="Chennai", state="Tamil Nadu")])
    write_manual(folder, PAIRS_HEADER + "aicf-488283,chessbase_calendar-af8,same,\n", "pairs.csv")


def test_grouped_records_days_apart_get_a_dates_disagree_line(data_dir):
    im_norm_snapshot(data_dir)
    run_offline(data_dir)
    events = by_id(data_dir)
    assert {e["group_id"] for e in events.values()} == {"aicf-488283"}
    rows = [r for r in review_rows(data_dir) if r["kind"] == "dates_disagree"]
    assert len(rows) == 1
    line = rows[0]
    assert line["id"] == "aicf-488283"
    assert line["other_id"].split() == ["tnsca-IM-45-TN-26-27", "chessbase_calendar-af8"]
    assert line["missing"].startswith(
        "start dates disagree: aicf 2027-02-08 to 2027-02-13 (aicf-488283); tnsca, chessbase_calendar "
        "2027-01-30 to 2027-02-04 (tnsca-IM-45-TN-26-27, chessbase_calendar-af8)")
    assert line["add_to_file"] == "data/manual/overrides.csv"
    assert line["line_to_add"] == "aicf-488283,?,?,,,,,,,,,,,"
    written = json.loads((data_dir / "quality.json").read_text("utf-8"))
    assert written["review"]["dates_disagree"] == 1


def test_an_override_with_the_organisers_dates_settles_the_line(data_dir):
    im_norm_snapshot(data_dir)
    write_manual(data_dir, OVERRIDES_HEADER + "aicf-488283,30-01-2027,04-02-2027,,,,,"
                 "dates from TNSCA (the organiser),,,,,,\n", "overrides.csv")
    run_offline(data_dir)
    shown = by_id(data_dir)["aicf-488283"]
    assert (shown["start"], shown["end"]) == ("2027-01-30", "2027-02-04")
    assert shown["overridden"] == {"start": "2027-02-08", "end": "2027-02-13"}  # AICF's dates kept
    assert shown["note"] == "dates from TNSCA (the organiser)"
    assert not [r for r in review_rows(data_dir) if r["kind"] == "dates_disagree"]


def two(start_a, start_b, end=None):
    return [ev("aicf-1", IM_NORM, start_a, end, city="Chennai"),
            ev("chessbase_calendar-1", IM_NORM, start_b, end, city="Chennai")]


def grouped_rows(events, today="2026-11-24"):
    from datetime import date
    events = [canonical(e) for e in events]
    dedup.group_events(events, [forced("aicf-1", "chessbase_calendar-1")], [])
    return quality.review_rows(events, date.fromisoformat(today))


def test_no_dates_line_within_a_day_or_for_a_past_tournament():
    assert not [r for r in grouped_rows(two("2027-01-30", "2027-01-31")) if r["kind"] == "dates_disagree"]
    past = grouped_rows(two("2026-10-01", "2026-10-09", end="2026-10-10"))
    assert not [r for r in past if r["kind"] == "dates_disagree"]
    assert [r["kind"] for r in grouped_rows(two("2027-01-30", "2027-02-08"))
            if r["kind"] == "dates_disagree"] == ["dates_disagree"]


def test_committed_overrides_show_tnsca_dates_for_the_six_im_norm_events():
    overrides = committed_overrides()
    for code in range(488283, 488289):
        item = overrides[f"aicf-{code}"]
        assert (item["start_date"].isoformat(), item["end_date"].isoformat()) == ("2027-01-30", "2027-02-04")
        assert "TNSCA (the organiser)" in item["note"] and "AICF lists 8 to 13 Feb 2027" in item["note"]


def test_the_live_check_counts_dates_disagree_lines():
    rows = [{"kind": k, **{c: "" for c in quality.REVIEW_COLUMNS if c != "kind"}}
            for k in ("missing", "dates_disagree", "possible_duplicate")]
    text = quality.review_csv(rows).decode("utf-8")
    problems, _, read = vp.check_file("review.csv", 200, {"access-control-allow-origin": "*"}, text)
    assert problems == []
    assert read == quality.review_counts(rows) == {"missing": 1, "dates_disagree": 1, "possible_duplicates": 1}
    # an older quality.json without the key still matches a list with no dates lines
    assert vp.check_together({"quality.json": {"review": {"missing": 1, "possible_duplicates": 0}},
                              "review.csv": {"missing": 1, "dates_disagree": 0, "possible_duplicates": 0}}) == []
    assert "1 dates disagree" in vp.check_together(
        {"quality.json": {"review": {"missing": 1, "dates_disagree": 0, "possible_duplicates": 0}},
         "review.csv": {"missing": 1, "dates_disagree": 1, "possible_duplicates": 0}})[0]


# ---- 3. FIDE rule 2: a label only ------------------------------------------------------
@pytest.mark.parametrize("name", [
    "DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN FIDE CHESS TOURNAMENT 2026",
    "INTERNATIONAL FIDE OPEN CHESS TOURNAMENT",
    "INTERNATIONAL FIDE OPEN BELOW 1800 CHESS TOURNAMENT",
    "DRAGON CHESS ACADEMY 2ND INTERNATIONAL BELOW 1700 FIDE CHESS TOURNAMENT",
])
def test_fide_next_to_open_chess_or_tournament_is_stated(name):
    assert fide_evidence(name) == (True, "stated")


@pytest.mark.parametrize("name, expected", [
    # not stated before, not stated now: the rule never makes a new yes
    ("St Xavier International School FIDE Chess Tournament", (None, None)),
    ("Kochi FIDE Open 2026", (None, None)),
    ("FIDE Chess Tournament for Schools", (None, None)),
    ("Kovai International FIDE TMT 2027", (None, None)),  # nothing inferred to relabel
    # a no stays a no
    ("Non-Rated International Open FIDE Chess Tournament", (False, "stated")),
    # inferred without the word FIDE next to it stays inferred
    ("Chennai International Open Chess Tournament", (True, "inferred")),
    ("Grandmaster Open 2027", (True, "inferred")),
])
def test_rule_2_changes_no_yes_or_no_value(name, expected):
    assert fide_evidence(name) == expected


def test_stored_inferred_events_are_relabelled_on_the_next_run():
    stored = record(**{"id": "aicf-503296", "name": "DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN FIDE "
                        "CHESS TOURNAMENT 2026", "start": "2026-12-02", "source": "aicf",
                        "tags": {"fide_rated": True, "fide_how": "inferred"}})
    plain = record(**{"id": "aicf-2", "name": "Chennai International Open Chess Tournament",
                       "start": "2026-12-02", "source": "aicf",
                       "tags": {"fide_rated": True, "fide_how": "inferred"}})
    for event in (stored, plain):
        be.fill_tags(event)
    assert (stored["tags"]["fide_rated"], stored["tags"]["fide_how"]) == (True, "stated")
    assert (plain["tags"]["fide_rated"], plain["tags"]["fide_how"]) == (True, "inferred")
    assert fide_named("Open FIDE Rapid") and not fide_named("non-rated FIDE open")


# ---- 4 and 5. committed overrides -------------------------------------------------------
@pytest.mark.parametrize("event_id", ["chessresults_ind-1550485", "chessresults_ind-1550499",
                                      "chessresults_ind-1550089", "chessresults_ind-1550113"])
def test_the_four_junk_entries_are_hidden_with_a_note(event_id):
    item = committed_overrides()[event_id]
    assert item["hide"] is True and item["note"]


def test_wb_state_under_17_has_dates_from_aicfs_own_listing(data_dir):
    item = committed_overrides()["aicf-471361"]
    assert (item["start_date"].isoformat(), item["end_date"].isoformat()) == ("2026-07-23", "2026-07-26")
    assert "aicf-471362" in item["note"]
    bad = ev("aicf-471361", "WB State Under 17 Open FIDE Rated Chess Championship 2026", "2027-07-23",
             "2026-07-26", city="Jalpaiguri", state="West Bengal",
             flags={"dates_suspect": True}, raw_dates={"start": "23-07-2027", "end": "26-07-2026"})
    snapshot_dir(data_dir, [bad])
    write_manual(data_dir, OVERRIDES_HEADER + "aicf-471361,23-07-2026,26-07-2026,,,,,from AICF's listing,,,,,,\n",
                 "overrides.csv")
    run_offline(data_dir)
    fixed = by_id(data_dir)["aicf-471361"]
    assert (fixed["start"], fixed["end"], fixed["flags"]["dates_suspect"]) == ("2026-07-23", "2026-07-26", False)
    assert fixed["raw_dates"] == {"start": "23-07-2027", "end": "26-07-2026"}  # what AICF wrote stays


# ---- 6. AICF codes in their full form ---------------------------------------------------
@pytest.mark.parametrize("text, codes, state", [
    ("Sarji Renuka All India Open FIDE Rapid Rating Chess Tournament 2026 499268/KA(R)/2026, "
     "KSCA/GO104/2627/A", ["499268"], "Karnataka"),
    ("Puneeth Rajkumar Cup 2026 511685/KA(R)/2026 December 20th 2026", ["511685"], "Karnataka"),
    ("63rd National Chess Championship 2026 AICF code 485283/UP/2026", ["485283"], "Uttar Pradesh"),
    ("Chessind Academy AICF Event Code:502180/KL(R)/2026", ["502180"], "Kerala"),
    ("Khannur 494719 / KA (R) / 2026", ["494719"], "Karnataka"),
    ("Total Cash Prize Rs 250000/- Contact 9876543210", [], None),
    ("Code 123456/XX/2026 is not a state", [], None),
    ("Two codes 499268/KA(R)/2026 and 502180/KL(R)/2026", ["499268", "502180"], None),
])
def test_full_form_aicf_codes_without_the_word_aicf(text, codes, state):
    assert aicf_codes_in(text) == codes
    assert aicf_code_state_in(text) == state


def test_a_code_in_a_chess_results_name_groups_and_gives_the_state(data_dir):
    snapshot_dir(data_dir, [
        ev("aicf-499268", "SARJI RENUKA DEVADHAR ALL INDIA FIDE RAPID RATING OPEN CHESS TOURNAMENT",
           "2026-11-29", codes=["499268"], city="Haveri", state="Karnataka"),
        ev("chessresults_ind-1502060", "Sarji Renuka All India Open FIDE Rapid Rating Chess Tournament "
           "2026 499268/KA(R)/2026, KSCA/GO104/2627/A", "2026-11-29",
           place_text="Jilla Valmiki Bhavan, Hangal Road, Haveri")])
    run_offline(data_dir)
    record = by_id(data_dir)["chessresults_ind-1502060"]
    assert record["codes"] == ["499268"] and record["state"] == "Karnataka"
    assert record["merged_into"] == "aicf-499268"
    stored = json.loads((data_dir / "sources" / "chessresults_ind.json").read_text("utf-8"))
    assert stored["events"][0]["codes"] == []  # the snapshot keeps what the site said


# ---- 7. state from the venue, and chessfee's label -------------------------------------
@pytest.mark.parametrize("venue, state", [
    ("Jilla Valmiki Bhavan, Hangal Road, Haveri", "Karnataka"),
    ("B-16, 5th Ave, Gaur City 1, Sector 4, Ghaziabad", "Uttar Pradesh"),
    ("Shivani Public School (CBSE) Lucknow", "Uttar Pradesh"),
    ("SGSITS Indore", "Madhya Pradesh"),
    ("Kalyan Nagar, Bengaluru", "Karnataka"),            # "Kalyan Nagar" is a part of Bengaluru
    ("Pragathi Nagar, Kukatpally, Hyderabad", "Telangana"),  # parts of one city: one town
    ("Rishra Sewak Sangh, Rishra, Hoogly", "West Bengal"),
    ("Mysore Palace grounds, Mysuru", "Karnataka"),      # two spellings of one town
    ("RIMS Vidyashram School, Kuppam Road, Kathinayanapalli, Krishnagiri - 635120", "Tamil Nadu"),
    ("SILIGURI INDORE STADIUM", None),                   # two known towns: not sure
    ("Nagercoil, Kanyakumari", None),                    # two known towns
    ("Velankanni Public School, Kodungaiyur", None),     # no known town
    ("", None),
    (None, None),
])
def test_state_from_exactly_one_known_town_in_the_venue(venue, state):
    assert town_state_in(venue) == state


def filled(**fields):
    event = record(**{"id": "chessresults_ind-1", "name": "Open Rapid", "start": "2026-12-06",
                      "source": "chessresults_ind", **fields})
    be.fill_codes_and_state(event)
    return event


def test_state_is_filled_only_when_empty_and_only_in_india():
    assert filled(place_text="SGSITS Indore")["state"] == "Madhya Pradesh"
    assert filled(place_text="SGSITS Indore", state="Kerala")["state"] == "Kerala"
    assert filled(place_text="SGSITS Indore", country="US")["state"] is None
    assert filled(place_text="SILIGURI INDORE STADIUM")["state"] is None


def test_chessfee_tamil_nadu_state_level_label_gives_tamil_nadu():
    event = record(**{"id": "chessfee-1864", "name": "DINDIGUL - PANNAI BVR Marimuthu Memorial 2nd State Level",
                       "start": "2026-11-29", "source": "chessfee", "country": "IN",
                       "place_text": "Pannai Public School, Arokiasami Nagar, Trichy Road, Dindigul",
                       "tags": {"categories": ["TAMILNADU STATE LEVEL - only TAMILNADU PLAYERS"]}})
    be.fill_codes_and_state(event)
    assert event["state"] == "Tamil Nadu"
    # the label alone is enough, even when the venue names no known town
    event = record(**{"id": "chessfee-1856", "name": "Lotus State Level", "start": "2026-11-29",
                       "source": "chessfee", "country": "IN", "place_text": "Lotus School, Pennadam",
                       "tags": {"categories": ["TAMILNADU STATE LEVEL - only TAMILNADU PLAYERS - UNDER 16"]}})
    be.fill_codes_and_state(event)
    assert event["state"] == "Tamil Nadu"


# ---- 8. town spellings ---------------------------------------------------------------
@pytest.mark.parametrize("a, b, same", [
    ("Pudukottai", "Pudukkottai", True),
    ("Tirupattur DT", "Tirupattur", True),
    ("Bangalore", "Bengaluru", True),
    ("Chengalpattu", "Chennai", False),   # a district (and its town) is not the city next to it
    ("Kanyakumari", "Nagercoil", False),
])
def test_town_spellings(a, b, same):
    assert dedup._same_town(a, b) is same


def test_tnsca_pudukottai_and_aicf_pudukkottai_now_group():
    name = "7th SSS International Below 1800 FIDE Rated Chess Tournament"
    aicf = ev("aicf-490387", name, "2026-10-30", "2026-11-01", city="Pudukkottai", state="Tamil Nadu")
    tnsca = ev("tnsca-RR-25-PDU-26-27", name, "2026-10-30", "2026-11-01", city="Pudukottai", state="Tamil Nadu")
    assert compare(aicf, tnsca)["decision"] == "same"
    district = ev("tnsca-CO-1-CGL", name, "2026-10-30", "2026-11-01", city="Chengalpattu", state="Tamil Nadu")
    chennai = ev("aicf-1", name, "2026-10-30", "2026-11-01", city="Chennai", state="Tamil Nadu")
    assert compare(chennai, district)["reason"] == "different city"


# ---- 9. a stable tie-break ---------------------------------------------------------------
EIGHT_SQUARE = "Eight Square Chess Academy 4th International FIDE Rated Rapid Chess Tournament 2027"


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 2, 0), (2, 0, 1)])
def test_equal_scores_pick_the_lower_id_whatever_the_order(order):
    records = [ev("aicf-486710", EIGHT_SQUARE, "2027-01-10", city="Chennai", state="Tamil Nadu"),
               ev("chessfee-1876", EIGHT_SQUARE, "2027-01-10"),
               ev("chessfee-1832", EIGHT_SQUARE, "2027-01-10")]
    events, _, _ = group(*[records[i] for i in order])
    assert events["chessfee-1832"]["merged_into"] == "aicf-486710"
    assert events["chessfee-1876"]["merged_into"] is None
    assert events["chessfee-1876"]["flags"]["possible_duplicate_of"] == "aicf-486710"


def test_ids_compare_numbers_as_numbers():
    assert sorted(["chessfee-1832", "chessfee-999", "aicf-10"], key=dedup.id_order) == \
        ["aicf-10", "chessfee-999", "chessfee-1832"]
