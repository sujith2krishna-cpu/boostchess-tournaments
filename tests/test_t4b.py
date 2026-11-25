"""T4b: duplicates across sources (grouped, never removed), format / FIDE detection, pairs.csv."""
import csv
import io
import json

import pytest

import build_events as be
import dedup
from conftest import NOW, ROOT, by_id, load_doc, load_events, write_manual

REAL = {e["id"]: e for e in json.loads(
    (ROOT / "tests" / "fixtures" / "dedup_real_events.json").read_text("utf-8"))["events"]}
ALL_OFF = {n: False for n in be.SOURCE_MODULES}
PAIRS_HEADER = ",".join(be.PAIRS_CSV_COLUMNS) + "\n"


def ev(event_id, name, start, end=None, source=None, **extra):
    """A minimal canonical event for unit tests."""
    source = source or event_id.split("-")[0]
    return be.canonical({"id": event_id, "name": name, "start": start, "end": end or start,
                         "source": source, "country": "IN", "first_seen": "2026-11-01",
                         "last_seen": "2026-11-25", **extra})


def real(event_id, **changes):
    return be.canonical({**REAL[event_id], **changes})


def compare(a, b):
    return dedup.compare(dedup.Features(a), dedup.Features(b))


def group(*events, pairs=()):
    events = [be.canonical(e) for e in events]
    warnings = []
    result = dedup.group_events(events, list(pairs), warnings)
    return {e["id"]: e for e in events}, result, warnings


def snapshot_dir(data_dir, events):
    """Put records into data/sources/<source>.json, as if the sources had been read earlier."""
    by_source = {}
    for event in events:
        by_source.setdefault(event["source"], []).append(event)
    (data_dir / "sources").mkdir(exist_ok=True)
    for name, items in by_source.items():
        (data_dir / "sources" / f"{name}.json").write_text(json.dumps(
            {"source": name, "found": len(items), "listing": {}, "events": items}), encoding="utf-8")


def run_offline(data_dir):
    """Build from the stored snapshots only (every source switched off: no fetching at all)."""
    return be.run(data_dir, config=ALL_OFF, now=NOW)


# ---- the must-pass examples from real data -----------------------------------------
@pytest.mark.parametrize("a, b", [
    ("aicf-502180", "chessfee-1800"),   # ChessInd Academy's 2nd ... Rapid, Kerala / Kochi, 29 Nov
    ("aicf-486240", "chessfee-1727"),   # 2nd Manchester City Below 1800, Coimbatore, 27-29 Nov
    ("aicf-510448", "chessfee-1872"),   # ICC - CHESSFEE ... 6th Edition, 31 Jan (AICF end 31 Jul)
])
def test_must_pass_same(a, b):
    result = compare(real(a), real(b))
    assert result["decision"] == "same" and result["score"] >= dedup.SAME_AT, result


def test_must_pass_athens_sections_are_not_the_same():
    b_section = real("aicf-482568")  # (Category - B Below 2100); the C section is "(Category - C Blitz"
    # pretend the C section came from another site, so only the section guard can keep them apart
    c_on_chessfee = real("aicf-482570", id="chessfee-9", source="chessfee", start=b_section["start"],
                         end=b_section["end"], codes=[])
    result = compare(b_section, c_on_chessfee)
    assert result["decision"] == "different" and result["hard"] and "different" in result["reason"]


def test_must_pass_same_name_different_state_or_ten_days_apart():
    base = real("aicf-502180")
    other_state = real("chessfee-1800", state="Tamil Nadu", city="Chennai")
    assert compare(base, other_state)["reason"] == "different state"
    later = real("chessfee-1800", start="2026-12-09", end="2026-12-09")
    assert compare(base, later)["reason"] == "start dates more than 1 day apart"


def test_real_records_end_to_end_are_grouped_and_all_kept(data_dir):
    snapshot_dir(data_dir, list(REAL.values()))
    report = run_offline(data_dir)
    events = by_id(data_dir)
    assert set(events) == set(REAL)  # nothing removed, nothing hidden
    assert all(not e["hidden"] for e in events.values())
    assert events["chessfee-1800"]["merged_into"] == "aicf-502180"
    assert events["chessresults_ind-1532678"]["merged_into"] == "aicf-502180"  # shared AICF code
    assert events["chessfee-1727"]["merged_into"] == "aicf-486240"
    assert events["chessfee-1872"]["merged_into"] == "aicf-510448"
    for athens in ("aicf-482567", "aicf-482568", "aicf-482569", "aicf-482570", "aicf-482662"):
        assert events[athens]["merged_into"] is None and events[athens]["group_id"] == athens
    assert report["multi_groups"] == 3 and report["merged"] == 4
    primary = events["aicf-502180"]
    assert primary["register_url"] == REAL["chessfee-1800"]["register_url"]  # gap filled
    assert primary["results_url"] == "https://chess-results.com/tnr1532678.aspx?lan=1"
    assert primary["brochure_url"] == REAL["aicf-502180"]["brochure_url"]  # AICF's own value kept
    assert primary["city"] == "Kochi"  # AICF had none
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert (meta["groups_count"], meta["merged_count"]) == (len(REAL) - 4, 4)


# ---- each rule ----------------------------------------------------------------------
def test_rule1_different_country():
    a = ev("aicf-1", "Kochi Rapid Cup", "2026-12-01")
    b = ev("chessbase_calendar-1", "Kochi Rapid Cup", "2026-12-01", country="LK")
    assert compare(a, b)["reason"] == "different country"


def test_rule2_missing_state_or_city_never_blocks_but_different_city_does():
    a = ev("aicf-1", "Golden Knights Masters Cup", "2026-12-01", state="Kerala")
    b = ev("chessfee-1", "Golden Knights Masters Cup", "2026-12-01", city="Kochi")
    assert compare(a, b)["decision"] == "same"
    c = ev("chessfee-2", "Golden Knights Masters Cup", "2026-12-01", state="Kerala", city="Kochi")
    d = ev("aicf-2", "Golden Knights Masters Cup", "2026-12-01", state="Kerala", city="Thrissur")
    assert compare(c, d)["reason"] == "different city"


def test_rule3_one_day_apart_is_fine_two_is_not_and_end_dates_are_ignored():
    a = ev("aicf-1", "Golden Knights Masters Cup", "2026-12-01", "2027-06-30")
    assert compare(a, ev("chessfee-1", "Golden Knights Masters Cup", "2026-12-02"))["decision"] == "same"
    assert compare(a, ev("chessfee-2", "Golden Knights Masters Cup", "2026-12-03"))["decision"] == "different"


def test_rule4_names_are_normalised_and_compared_as_word_sets():
    words = dedup.name_words
    assert words("KERALA - ChessInd Academy's 2nd International Open FIDE Rated Rapid Chess Tournament - 29 NOV") \
        == words("ChessInd Academy’s 2nd International FIDE Rated Open Rapid Chess Tournament") \
        == {"chessind", "academy", "no2"}
    assert words("Shree Rudhraa State Level Tournament 2026-27") == words("2026 State Level Shree Rudhraa")
    assert words("CHENNAI - Shree Rudhraa Cup", "Chennai") == {"shree", "rudhraa", "cup"}  # place prefix
    assert "jabalpur" in words("4th Jabalpur International Open")  # a city inside a name stays
    assert words("Masters Cup | Prize Fund : Rs 3 Lakhs") == {"master", "cup"}


def test_rule4_too_few_distinctive_words_can_only_be_possible():
    a = ev("aicf-1", "6th International Open FIDE Rating Chess Tournament 2026", "2026-12-01", city="Salem")
    b = ev("chessfee-1", "6th International FIDE Rated Chess Tournament", "2026-12-01", city="Salem")
    result = compare(a, b)
    assert result["decision"] == "possible" and "too few" in result["reason"]


@pytest.mark.parametrize("left, right", [
    ("Spring Festival Below 1800", "Spring Festival Above 1800"),
    ("Spring Festival U1600", "Spring Festival Below 1800"),
    ("Spring Festival Below 1800", "Spring Festival"),
    ("Spring Festival Under-11", "Spring Festival U13"),
    ("Spring Festival (Category - B)", "Spring Festival (Category C)"),
    ("Spring Festival Rapid", "Spring Festival Blitz"),
])
def test_rule5_section_guard(left, right):
    result = compare(ev("aicf-1", left, "2026-12-01"), ev("chessfee-1", right, "2026-12-01"))
    assert result["decision"] == "different" and result["hard"], result


def test_rule5_a_missing_format_does_not_block():
    a = ev("aicf-1", "Spring Festival Knights Rapid", "2026-12-01")
    b = ev("chessfee-1", "Spring Festival Knights", "2026-12-01")
    assert compare(a, b)["decision"] == "same"


def test_rule6_strong_proof():
    # same AICF code: names may differ completely, and it beats the place and date rules
    a = ev("aicf-1", "Kochi Open", "2026-12-01", codes=["502180"], state="Kerala")
    b = ev("chessresults_ind-1", "Totally other words", None, codes=["502180"], state="Goa")
    assert compare(a, b) == {"score": 1.0, "decision": "same", "reason": "same AICF code 502180", "hard": False}
    # same Chess-Results page
    url = "https://chess-results.com/tnr1532678.aspx?lan=1"
    c = ev("manual-1", "My name for it", "2026-12-01", results_url=url)
    d = ev("chessresults_ind-1532678", "Their name", "2026-12-05", source_url=url)
    assert compare(c, d)["reason"] == "same Chess-Results page"
    # same brochure: beats the name, but not the section guard or the dates
    pdf = "https://aicf.in/b.pdf"
    e = ev("aicf-2", "Festival A", "2026-12-01", brochure_url=pdf)
    assert compare(e, ev("chessfee-2", "Something else", "2026-12-01", brochure_url=pdf))["decision"] == "same"
    assert compare(e, ev("chessfee-3", "Festival Below 1600", "2026-12-01", brochure_url=pdf))["decision"] == "different"
    assert compare(e, ev("chessfee-4", "Festival A", "2026-12-10", brochure_url=pdf))["decision"] == "different"


def test_rule6_a_code_shared_by_two_aicf_events_proves_nothing():
    events, result, warnings = group(ev("aicf-1", "Cup A", "2026-12-01", codes=["473001"]),
                                     ev("aicf-2", "Cup B", "2026-12-05", codes=["473001"]),
                                     ev("chessfee-1", "AICF 473001 Rapid", "2026-12-09", codes=["473001"]))
    assert all(e["merged_into"] is None for e in events.values())
    assert any("share one code" in w for w in warnings)


def test_rule7_thresholds():
    a = ev("aicf-1", "Golden Knights Masters Cup", "2026-12-01", city="Salem")
    half = ev("chessfee-1", "Golden Knights Masters Trophy", "2026-12-01", city="Salem")
    low = ev("chessfee-2", "Silver Pawns Festival", "2026-12-01", city="Salem")
    events, result, _ = group(a, half, low)
    assert events["chessfee-1"]["merged_into"] is None
    assert events["chessfee-1"]["flags"]["possible_duplicate_of"] == "aicf-1"
    assert events["chessfee-2"]["flags"]["possible_duplicate_of"] is None
    assert 0.5 <= compare(a, half)["score"] < 0.8 and compare(a, low)["score"] < 0.5


def test_records_from_one_source_are_never_grouped_by_the_algorithm():
    events, _, _ = group(ev("aicf-1", "Golden Knights Masters Cup", "2026-12-01"),
                         ev("aicf-2", "Golden Knights Masters Cup", "2026-12-01"))
    assert all(e["merged_into"] is None for e in events.values())


def test_a_group_never_holds_two_sections_through_a_third_record():
    a = ev("aicf-1", "Spring Festival Below 1800", "2026-12-01", brochure_url="https://x.in/b.pdf")
    b = ev("chessfee-1", "Spring Festival", "2026-12-01", brochure_url="https://x.in/b.pdf")
    c = ev("chessresults_ind-1", "Spring Festival Above 1800", "2026-12-01", brochure_url="https://x.in/b.pdf")
    events, _, _ = group(a, b, c)
    assert len({e["group_id"] for e in events.values()}) == 3


# ---- group fields --------------------------------------------------------------------
def test_primary_choice_and_dates_taken_from_a_member_with_good_dates():
    suspect = {"dates_suspect": True}
    aicf = ev("aicf-1", "Golden Knights Masters Cup", None, codes=["400001"], flags=suspect,
              raw_dates={"start": "31-02-2026", "end": ""})
    cf = ev("chessfee-1", "Golden Knights Masters Cup AICF 400001", None, codes=["400001"], flags=suspect,
            raw_dates={"start": "", "end": ""})
    cr = ev("chessresults_ind-1", "Golden Knights Masters Cup", "2026-12-01", "2026-12-02", codes=["400001"])
    events, _, _ = group(aicf, cf, cr)
    # AICF's dates are suspect, so chessfee (next in line) is the primary ...
    primary = events["chessfee-1"]
    assert primary["merged_into"] is None and events["aicf-1"]["merged_into"] == "chessfee-1"
    # ... and its own dates are suspect too, so it takes Chess-Results' dates and says so
    assert (primary["start"], primary["end"], primary["dates_from"]) == ("2026-12-01", "2026-12-02",
                                                                          "chessresults_ind-1")
    assert primary["raw_dates"] == {"start": "", "end": ""} and primary["flags"]["dates_suspect"] is False
    assert events["aicf-1"]["start"] is None  # the other records keep what their source said


def test_aicf_with_good_dates_is_primary_and_keeps_its_own_values():
    aicf = ev("aicf-1", "Golden Knights Masters Cup", "2026-12-01", register_url="https://aicf.in/reg",
              city="Salem")
    manual = ev("manual-1", "Golden Knights Masters Cup", "2026-12-01", register_url="https://x.in/reg",
                results_url="https://x.in/results", city="Attur")
    events, _, _ = group(aicf, manual, pairs=[{"line": 2, "a": "aicf-1", "b": "manual-1",
                                               "decision": "same", "note": None}])
    primary = events["aicf-1"]
    assert primary["register_url"] == "https://aicf.in/reg" and primary["city"] == "Salem"
    assert primary["results_url"] == "https://x.in/results"
    assert primary["also_listed_on"] == [{"source": "manual", "source_url": None,
                                          "register_url": "https://x.in/reg",
                                          "results_url": "https://x.in/results", "brochure_url": None}]
    assert events["manual-1"]["also_listed_on"] == [] and events["manual-1"]["group_id"] == "aicf-1"


def test_every_event_has_group_fields_and_old_data_migrates():
    old = {"id": "aicf-9", "name": "X", "source": "aicf", "first_seen": "2026-11-01",
           "last_seen": "2026-11-02"}
    new = be.canonical(old)
    assert (new["group_id"], new["merged_into"], new["also_listed_on"], new["dates_from"]) == \
        ("aicf-9", None, [], None)
    keys = list(be.EVENT_KEYS)
    assert keys.index("group_id") == keys.index("verified") + 1
    assert keys[keys.index("group_id"):keys.index("group_id") + 3] == ["group_id", "merged_into", "also_listed_on"]
    assert be.SCHEMA_VERSION == 5


# ---- pairs.csv -----------------------------------------------------------------------
def test_pairs_csv_forces_same_and_not_same(data_dir):
    snapshot_dir(data_dir, list(REAL.values()) + [
        ev("chessfee-50", "A Completely Different Title", "2026-11-29", city="Kochi", state="Kerala")])
    write_manual(data_dir, PAIRS_HEADER
                 + "aicf-486240,chessfee-1727,not_same,checked: different sections\n"
                 + "chessfee-50, aicf-502180 ,Same,organiser confirmed\n", "pairs.csv")
    run_offline(data_dir)
    events = by_id(data_dir)
    assert events["chessfee-1727"]["merged_into"] is None
    assert events["chessfee-50"]["merged_into"] == "aicf-502180"
    rows = list(csv.DictReader(io.StringIO((data_dir / "review" / "dedup_review.csv").read_text("utf-8"))))
    forced = {(r["id_a"], r["id_b"]): r for r in rows if r["reason"].startswith("pairs.csv")}
    assert forced[("aicf-486240", "chessfee-1727")]["decision"] == "not_same"
    assert forced[("aicf-502180", "chessfee-50")]["decision"] == "same"


def test_pairs_csv_mistakes_stop_the_run_with_file_and_line(data_dir):
    snapshot_dir(data_dir, list(REAL.values()))
    write_manual(data_dir, PAIRS_HEADER + "aicf-486240,chessfee-1727,maybe,\n"
                 + "aicf-486240,aicf-486240,same,\n", "pairs.csv")
    with pytest.raises(be.DataFileError) as info:
        run_offline(data_dir)
    text = str(info.value)
    assert "data/manual/pairs.csv line 2: decision 'maybe' is not understood" in text
    assert "data/manual/pairs.csv line 3: id_a and id_b are the same id" in text
    assert not (data_dir / "events.json").exists()


def test_pairs_csv_unknown_id_is_only_a_warning(data_dir):
    snapshot_dir(data_dir, list(REAL.values()))
    write_manual(data_dir, PAIRS_HEADER + "aicf-486240,chessfee-0000,same,\n", "pairs.csv")
    report = run_offline(data_dir)
    assert any("pairs.csv line 2: no event has the id 'chessfee-0000'" in w for w in report["warnings"])


def test_committed_pairs_csv_is_valid():
    errors, warnings = [], []
    be.load_pairs(ROOT / "data", errors, warnings)
    assert errors == []


# ---- nothing is ever removed; the review file ----------------------------------------
def test_nothing_is_ever_removed_from_events_json(data_dir):
    records = list(REAL.values())
    snapshot_dir(data_dir, records)
    write_manual(data_dir, ",".join(be.EVENTS_CSV_COLUMNS) + "\n"
                 + "mine,ChessInd Academy 2nd Rapid,29-11-2026,,Kochi,Kerala,,,,,,,\n")
    run_offline(data_dir)
    ids = [e["id"] for e in load_events(data_dir)]
    assert sorted(ids) == sorted([r["id"] for r in records] + ["mine"])
    assert all(not e["hidden"] for e in load_events(data_dir))


def test_review_csv_lists_every_same_and_possible_pair(data_dir):
    snapshot_dir(data_dir, list(REAL.values()))
    run_offline(data_dir)
    text = (data_dir / "review" / "dedup_review.csv").read_text("utf-8")
    assert text.splitlines()[0] == ",".join(dedup.REVIEW_COLUMNS)
    rows = list(csv.DictReader(io.StringIO(text)))
    pairs = {(r["id_a"], r["id_b"]): r for r in rows}
    row = pairs[("aicf-486240", "chessfee-1727")]
    assert row["decision"] == "same" and float(row["score"]) >= 0.8
    assert row["name_a"].startswith("2nd Manchester City") and row["source_b"] == "chessfee"
    assert row["start_a"] == "2026-11-27" and row["place_b"] == "Coimbatore, Tamil Nadu"
    assert row["group_id"] == "aicf-486240"
    assert all(r["decision"] in ("same", "possible", "not_same") for r in rows)
    assert [float(r["score"]) for r in rows] == sorted(float(r["score"]) for r in rows)  # lowest first


# ---- format and FIDE detection --------------------------------------------------------
@pytest.mark.parametrize("text, formats, rated", [
    ("2nd RCPP Rapid Rating Tournaments 2026", ["rapid"], True),
    ("FIDE RAPID TMT - PRIZE MONEY Rs. 4,00,000/-", ["rapid"], True),
    ("FIDE BELOW 1800", [], True),
    ("The Resurrection Race III Open Standard FIDE Rated", ["classical"], True),
    ("District Open Non-Rated Rapid", ["rapid"], False),
    ("Unrated Kids Blitz", ["blitz"], False),
    ("TAMILNADU STATE U-17 OPEN/Girls CHESS CHAMPIONSHIP 2026", [], None),
    ("FIDE Master Memorial Cup", [], None),
])
def test_format_and_fide_need_evidence(text, formats, rated):
    tags = be.derive_tags(text)
    assert (tags["formats"], tags["fide_rated"]) == (formats, rated)


def test_category_labels_fill_gaps_in_stored_events(data_dir):
    plain = ev("chessfee-7", "Golden Knights Cup", "2026-12-01",
               tags={"categories": ["FIDE RAPID TMT"]})
    snapshot_dir(data_dir, [plain])
    run_offline(data_dir)
    tags = by_id(data_dir)["chessfee-7"]["tags"]
    assert (tags["formats"], tags["fide_rated"]) == (["rapid"], True)


def test_format_and_fide_are_inherited_within_a_group_only_when_members_agree():
    a = ev("aicf-1", "Golden Knights Masters Cup", "2026-12-01")
    b = ev("chessfee-1", "Golden Knights Masters Cup", "2026-12-01",
           tags={"formats": ["rapid"], "fide_rated": True})
    events, _, _ = group(a, b)
    assert events["aicf-1"]["tags"]["formats"] == ["rapid"] and events["aicf-1"]["tags"]["fide_rated"] is True
    # no evidence anywhere: stays unknown
    events, _, _ = group(ev("aicf-2", "Golden Knights Masters Cup", "2026-12-01"),
                         ev("chessfee-2", "Golden Knights Masters Cup", "2026-12-01"))
    assert events["aicf-2"]["tags"]["formats"] == [] and events["aicf-2"]["tags"]["fide_rated"] is None
    # members disagree: nobody inherits
    c = ev("aicf-3", "Golden Knights Masters Cup", "2026-12-01")
    d = ev("chessfee-3", "Golden Knights Masters Cup", "2026-12-01", tags={"fide_rated": True})
    e = ev("chessresults_ind-3", "Golden Knights Masters Cup", "2026-12-01", tags={"fide_rated": False})
    events, _, _ = group(c, d, e)
    assert events["aicf-3"]["tags"]["fide_rated"] is None


def test_committed_events_read_cleanly_as_schema_5():
    doc = load_doc(ROOT / "data")
    for event in doc["events"]:
        assert list(be.canonical(event)) == list(be.EVENT_KEYS)
