"""T5: AICF / ChessBase pairs that were not grouped.

- A name made only of filler words ("International FIDE Rated Above 1800 Open Chess Tournament
  2026") counts as a full match when it is the same word for word on both sites and the state or
  city is known and the same (the two Goa pairs).
- Start dates more than one day apart still mean "different" (the Manchester City and Tamil Nadu
  IM Norm pairs stay apart; they are in pairs.csv as "undecided" for a person to check).
- pairs.csv accepts "undecided": the line is kept and changes nothing.
"""
import pytest

import build_events as be
import dedup
from conftest import by_id, write_manual
from test_t4b import PAIRS_HEADER, compare, ev, group, run_offline, snapshot_dir

GOA_ABOVE = "International FIDE Rated Above 1800 Open Chess Tournament 2026"
GOA_BELOW = "International FIDE Rated Below 1800 Open Chess Tournament 2026"


def goa(event_id, name=GOA_ABOVE, start="2026-11-26", end="2026-12-01", **extra):
    return ev(event_id, name, start, end, **{"state": "Goa", **extra})


# ---- identical names with no distinctive words ----------------------------------------
def test_the_two_goa_pairs_are_grouped():
    events, result, _ = group(
        goa("aicf-487788"), goa("chessbase_calendar-ade"),
        goa("aicf-487790", GOA_BELOW, "2026-11-27", "2026-11-28"),
        goa("chessbase_calendar-adf", GOA_BELOW, "2026-11-27", "2026-11-28"))
    assert events["chessbase_calendar-ade"]["merged_into"] == "aicf-487788"
    assert events["chessbase_calendar-adf"]["merged_into"] == "aicf-487790"
    # the two sections stay apart
    assert events["aicf-487788"]["group_id"] != events["aicf-487790"]["group_id"]
    assert result["merged"] == 2


def test_identical_generic_name_scores_as_a_full_match():
    result = compare(goa("aicf-1"), goa("chessbase_calendar-1"))
    assert result["decision"] == "same" and result["score"] >= dedup.SAME_AT
    assert result["reason"] == "identical names (no distinctive words, same place)"


def test_identical_generic_name_with_the_same_city_and_no_state():
    a = ev("aicf-1", "FIDE Rated Open Chess Tournament", "2026-12-01", city="Salem")
    b = ev("chessfee-1", "FIDE Rated Open Chess Tournament", "2026-12-01", city="Salem")
    assert compare(a, b)["decision"] == "same"


@pytest.mark.parametrize("left_place, right_place", [
    ({"state": "Goa"}, {}),               # one side has no place at all
    ({}, {}),                             # neither has a place
])
def test_identical_generic_name_without_a_shared_place_is_not_enough(left_place, right_place):
    a = ev("aicf-1", GOA_ABOVE, "2026-11-26", **left_place)
    b = ev("chessbase_calendar-1", GOA_ABOVE, "2026-11-26", **right_place)
    result = compare(a, b)
    assert result["decision"] != "same" and "too few" in result["reason"], result


def test_identical_generic_name_in_another_state_is_different():
    result = compare(goa("aicf-1"), goa("chessbase_calendar-1", state="Kerala"))
    assert result["decision"] == "different" and result["reason"] == "different state"


def test_generic_names_that_differ_in_one_word_still_need_more():
    # the old rule: not word for word the same, so few distinctive words can only be "possible"
    a = ev("aicf-1", "6th International Open FIDE Rating Chess Tournament 2026", "2026-12-01", city="Salem")
    b = ev("chessfee-1", "6th International FIDE Rated Chess Tournament", "2026-12-01", city="Salem")
    result = compare(a, b)
    assert result["decision"] == "possible" and "too few" in result["reason"]


def test_identical_generic_names_still_respect_the_section_guard():
    result = compare(goa("aicf-1"), goa("chessbase_calendar-1", GOA_BELOW))
    assert result["decision"] == "different" and result["reason"] == "different rating limit"


def test_tails_are_ignored_in_the_identical_name_check():
    a = ev("aicf-1", "FIDE Rated Open Chess Tournament", "2026-12-01", city="Salem")
    b = ev("chessresults_ind-1", "FIDE Rated Open Chess Tournament - 1 Dec 2026 - Salem", "2026-12-01",
           city="Salem")
    assert compare(a, b)["decision"] == "same"


# ---- start dates far apart: still different -------------------------------------------
@pytest.mark.parametrize("name, aicf_start, other_start", [
    ("2nd Manchester City International Below 1800 Fide Rated Tournament", "2026-11-27", "2026-11-21"),
    ("45th Tamil Nadu IM Norm Closed Circuit Chess Tournament", "2027-02-08", "2027-01-30"),
])
def test_same_name_and_city_but_days_apart_stays_different(name, aicf_start, other_start):
    a = ev("aicf-1", name, aicf_start, city="Chennai", state="Tamil Nadu")
    b = ev("chessbase_calendar-1", name, other_start, city="Chennai", state="Tamil Nadu")
    result = compare(a, b)
    assert result["decision"] == "different" and result["reason"] == "start dates more than 1 day apart"


# ---- pairs.csv "undecided" -------------------------------------------------------------
def test_pairs_csv_undecided_is_accepted_and_changes_nothing(data_dir):
    name = "45th Tamil Nadu IM Norm Closed Circuit Chess Tournament"
    snapshot_dir(data_dir, [
        ev("aicf-1", name, "2027-02-08", city="Chennai", state="Tamil Nadu"),
        ev("chessbase_calendar-1", name, "2027-01-30", city="Chennai", state="Tamil Nadu"),
        goa("aicf-2"), goa("chessbase_calendar-2")])
    write_manual(data_dir, PAIRS_HEADER
                 + "aicf-1,chessbase_calendar-1,undecided,dates differ: check the brochure\n"
                 + "aicf-2,chessbase_calendar-2, Undecided ,\n", "pairs.csv")
    report = run_offline(data_dir)
    events = by_id(data_dir)
    assert events["chessbase_calendar-1"]["merged_into"] is None  # rules decide: dates far apart
    assert events["chessbase_calendar-2"]["merged_into"] == "aicf-2"  # rules decide: same
    assert not any("pairs.csv" in w for w in report["warnings"])


def test_pairs_csv_undecided_with_an_unknown_id_is_still_a_warning(data_dir):
    snapshot_dir(data_dir, [goa("aicf-2")])
    write_manual(data_dir, PAIRS_HEADER + "aicf-2,chessbase_calendar-9,undecided,\n", "pairs.csv")
    report = run_offline(data_dir)
    assert any("pairs.csv line 2: no event has the id 'chessbase_calendar-9'" in w
               for w in report["warnings"])


def test_pairs_csv_wrong_decision_names_all_three_choices(data_dir):
    snapshot_dir(data_dir, [goa("aicf-2")])
    write_manual(data_dir, PAIRS_HEADER + "aicf-2,chessbase_calendar-2,unsure,\n", "pairs.csv")
    with pytest.raises(be.DataFileError) as info:
        run_offline(data_dir)
    assert ("data/manual/pairs.csv line 2: decision 'unsure' is not understood. Write 'same', "
            "'not_same' or 'undecided'.") in str(info.value)


def test_committed_undecided_pairs_are_aicf_and_chessbase_lines_with_a_note():
    errors, warnings = [], []
    rows = be.load_pairs(be.DATA_DIR, errors, warnings)
    assert errors == []
    undecided = [r for r in rows if r["decision"] == "undecided"]
    assert len(undecided) == 7
    for row in undecided:
        assert row["a"].startswith("aicf-") and row["b"].startswith("chessbase_calendar-")
        assert row["note"] and row["note"].startswith("T5 check")
