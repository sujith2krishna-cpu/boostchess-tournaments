"""Hand-edited files: manual events, overrides, and the error messages people see."""
import json
from datetime import timedelta

import pytest

import build_events as be
from conftest import (EVENTS_HEADER, NOW, OVERRIDES_HEADER, build, by_id, load_events,
                      row, write_manual)

NEXT_DAY = NOW + timedelta(days=1)


def files_snapshot(folder):
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


# ---- manual events ------------------------------------------------------
def test_manual_event_is_added_with_source_manual(data_dir):
    write_manual(data_dir, EVENTS_HEADER + (
        "club-open-2027,Pune Club Rapid Under-11,05-01-2027,06-01-2027,\"Pune, Maharashtra\","
        ",,https://example.org/register,https://example.org/b.pdf,rapid,,Entry at the door\n"))
    report = build(data_dir, [row("AICF one", "400001")])
    event = by_id(data_dir)["club-open-2027"]
    assert event["source"] == "manual" and event["codes"] == []
    assert (event["start"], event["end"]) == ("2027-01-05", "2027-01-06")
    assert (event["city"], event["state"]) == ("Pune", "Maharashtra")
    assert event["register_url"] == "https://example.org/register"
    assert event["brochure_url"] == "https://example.org/b.pdf"
    assert event["tags"]["formats"] == ["rapid"] and event["tags"]["age"] == ["U11"]
    assert event["note"] == "Entry at the door"
    assert report["meta"]["manual_count"] == 1 and report["meta"]["total"] == 2


def test_manual_dates_in_both_styles_and_one_day_default(data_dir):
    write_manual(data_dir, EVENTS_HEADER
                 + ",Iso style,2027-02-03,2027-02-04,Goa,,,,,,,\n"
                 + ",One day only,03-02-2027,,Goa,,,,,,,\n")
    build(data_dir, [row()])
    manual = {e["name"]: e for e in load_events(data_dir) if e["source"] == "manual"}
    assert (manual["Iso style"]["start"], manual["Iso style"]["end"]) == ("2027-02-03", "2027-02-04")
    assert (manual["One day only"]["start"], manual["One day only"]["end"]) == ("2027-02-03", "2027-02-03")
    assert all(e["id"].startswith("manual-") for e in manual.values())


def test_manual_id_is_stable_between_runs(data_dir):
    write_manual(data_dir, EVENTS_HEADER + ",Stable Cup,03-02-2027,,Goa,,,,,,,\n")
    build(data_dir, [row()])
    first = {e["id"]: e for e in load_events(data_dir) if e["source"] == "manual"}
    build(data_dir, [row()], now=NEXT_DAY)
    second = {e["id"]: e for e in load_events(data_dir) if e["source"] == "manual"}
    assert list(first) == list(second)
    only = next(iter(second.values()))
    assert only["first_seen"] == "2026-11-24" and only["last_seen"] == "2026-11-25"


@pytest.mark.parametrize("line, expected", [
    (",,03-02-2027,,Goa,,,,,,,", "line 2: the name is empty"),
    (",Cup,,,Goa,,,,,,,", "line 2: start_date is empty"),
    (",Cup,31-02-2027,,Goa,,,,,,,", "line 2: start_date '31-02-2027' is not a date"),
    (",Cup,05-02-2027,03-02-2027,Goa,,,,,,,", "line 2: end_date 2027-02-03 is before start_date 2027-02-05"),
    (",Cup,03-02-2027,,Goa,Tamilnaduu,,,,,,", "line 2: state 'Tamilnaduu' is not an Indian state"),
    (",Cup,03-02-2027,,Goa,,,example.org,,,,", "line 2: link 'example.org' is not a full web address"),
    (",Cup,03-02-2027,,Goa,,,,,fast,,", "line 2: format 'fast' is not understood"),
    (",Cup,03-02-2027,,Goa,,,,,,eleven,", "line 2: age 'eleven' is not understood"),
    ("aicf-123456,Cup,03-02-2027,,Goa,,,,,,,", "reserved for AICF events"),
    ("bad id,Cup,03-02-2027,,Goa,,,,,,,", "may only use letters"),
    (",Cup,03-02-2027,,Goa,,,,,,,extra,more,again", "more values than the header has columns"),
])
def test_manual_row_error_stops_with_plain_message_and_writes_nothing(data_dir, line, expected):
    build(data_dir, [row("Existing", "400001")])
    before = files_snapshot(data_dir)
    write_manual(data_dir, EVENTS_HEADER + line + "\n")
    before_csv_changed = files_snapshot(data_dir)
    with pytest.raises(be.DataFileError) as caught:
        build(data_dir, [row("Existing", "400001"), row("New", "400009")], now=NEXT_DAY)
    message = str(caught.value)
    assert "data/manual/events.csv" in message and expected in message
    after = files_snapshot(data_dir)
    assert after["events.json"] == before["events.json"] == before_csv_changed["events.json"]
    assert after["meta.json"] == before["meta.json"]


def test_all_mistakes_are_listed_together_with_their_lines(data_dir):
    write_manual(data_dir, EVENTS_HEADER
                 + ",Fine,03-02-2027,,Goa,,,,,,,\n"
                 + ",,03-02-2027,,Goa,,,,,,,\n"
                 + ",Late,xx,,Goa,,,,,,,\n")
    with pytest.raises(be.DataFileError) as caught:
        build(data_dir, [row()])
    message = str(caught.value)
    assert "line 3: the name is empty" in message and "line 4: start_date 'xx'" in message
    assert not (data_dir / "events.json").exists()


def test_wrong_header_names_the_problem(data_dir):
    write_manual(data_dir, "name,strat_date\nCup,03-02-2027\n")
    with pytest.raises(be.DataFileError, match=r"line 1: unknown column name.*strat_date"):
        build(data_dir, [row()])


def test_duplicate_manual_id_names_both_lines(data_dir):
    write_manual(data_dir, EVENTS_HEADER + "x1,A,03-02-2027,,Goa,,,,,,,\nx1,B,04-02-2027,,Goa,,,,,,,\n")
    with pytest.raises(be.DataFileError, match="line 3: id 'x1' is already used on line 2"):
        build(data_dir, [row()])


def test_manual_ids_may_not_use_the_aicf_prefix(data_dir):
    write_manual(data_dir, EVENTS_HEADER + "aicf-x,A,03-02-2027,,Goa,,,,,,,\n")
    with pytest.raises(be.DataFileError, match="reserved"):
        build(data_dir, [row()])


def test_excel_style_file_with_bom_and_blank_lines_is_fine(data_dir):
    (data_dir / "manual" / "events.csv").write_bytes(
        b"\xef\xbb\xbf" + (EVENTS_HEADER + "\n,Cup,03-02-2027,,Goa,,,,,,,\n\n").encode("utf-8"))
    build(data_dir, [row()])
    assert sum(1 for e in load_events(data_dir) if e["source"] == "manual") == 1


def test_missing_manual_files_are_only_a_warning(data_dir):
    (data_dir / "manual" / "events.csv").unlink()
    (data_dir / "manual" / "overrides.csv").unlink()
    report = build(data_dir, [row()])
    assert len(report["warnings"]) == 2 and report["meta"]["total"] == 1


# ---- overrides ----------------------------------------------------------
def with_override(folder, line):
    write_manual(folder, OVERRIDES_HEADER + line + "\n", "overrides.csv")


def test_override_hides_an_event(data_dir):
    with_override(data_dir, "aicf-400001,,,,,yes,,")
    build(data_dir, [row("Hide me", "400001"), row("Keep", "400002")])
    events = by_id(data_dir)
    assert events["aicf-400001"]["hidden"] is True and events["aicf-400002"]["hidden"] is False


def test_override_by_aicf_code_cancels_an_event_with_a_note(data_dir):
    with_override(data_dir, "472291,,,,,,yes,Called off by the organiser")
    build(data_dir, [row("Two codes", "472290/472291")])
    event = by_id(data_dir)["aicf-472290"]
    assert event["cancelled"] is True and event["note"] == "Called off by the organiser"


def test_override_fixes_bad_dates_and_clears_the_suspect_flag(data_dir):
    with_override(data_dir, "aicf-400001,03-04-2026,29-04-2026,,,,,Fixed after checking brochure")
    build(data_dir, [row("Bad", "400001", start="29-04-2026", end="03-04-2026")])
    event = by_id(data_dir)["aicf-400001"]
    assert (event["start"], event["end"]) == ("2026-04-03", "2026-04-29")
    assert event["flags"]["dates_suspect"] is False
    assert event["raw_dates"] == {"start": "29-04-2026", "end": "03-04-2026"}  # what AICF said
    assert event["overridden"]["start"] == "2026-04-29"


def test_override_fixes_place_and_state(data_dir):
    with_override(data_dir, "aicf-400001,,,\"Sagar, Madhya Pradesh\",,,,")
    build(data_dir, [row("X", "400001", place="Sagar")])
    event = by_id(data_dir)["aicf-400001"]
    assert (event["place_text"], event["city"], event["state"]) == (
        "Sagar, Madhya Pradesh", "Sagar", "Madhya Pradesh")
    with_override(data_dir, "aicf-400001,,,,Kerala,,,")
    build(data_dir, [row("X", "400001", place="Sagar")], now=NEXT_DAY)
    assert by_id(data_dir)["aicf-400001"]["state"] == "Kerala"


def test_removing_an_override_brings_the_scraped_values_back(data_dir):
    with_override(data_dir, "aicf-400001,01-01-2027,02-01-2027,,,yes,,")
    build(data_dir, [row("X", "400001", start="10-12-2026", end="11-12-2026")])
    assert by_id(data_dir)["aicf-400001"]["start"] == "2027-01-01"
    write_manual(data_dir, OVERRIDES_HEADER, "overrides.csv")
    build(data_dir, [row("X", "400001", start="10-12-2026", end="11-12-2026")], now=NEXT_DAY)
    event = by_id(data_dir)["aicf-400001"]
    assert event["start"] == "2026-12-10" and event["hidden"] is False and event["overridden"] is None


def test_removing_an_override_also_works_for_a_gone_event(data_dir):
    with_override(data_dir, "aicf-400001,01-01-2027,02-01-2027,,,,,")
    build(data_dir, [row("X", "400001", start="10-12-2026", end="11-12-2026"), row("Y", "400002")])
    build(data_dir, [row("Y", "400002")], now=NEXT_DAY)  # X vanishes; override still applies
    assert by_id(data_dir)["aicf-400001"]["start"] == "2027-01-01"
    assert by_id(data_dir)["aicf-400001"]["gone_from_source"] is True
    write_manual(data_dir, OVERRIDES_HEADER, "overrides.csv")
    build(data_dir, [row("Y", "400002")], now=NEXT_DAY + timedelta(days=1))
    assert by_id(data_dir)["aicf-400001"]["start"] == "2026-12-10"


def test_override_beats_manual_beats_scraped(data_dir):
    write_manual(data_dir, EVENTS_HEADER + "mine,My Cup,10-01-2027,11-01-2027,Goa,,,,,,,Original note\n")
    with_override(data_dir, "mine,20-01-2027,21-01-2027,,,,,Moved")
    build(data_dir, [row()])
    event = by_id(data_dir)["mine"]
    assert (event["start"], event["note"]) == ("2027-01-20", "Moved")


def test_unknown_override_key_is_a_warning_not_an_error(data_dir):
    with_override(data_dir, "999999,,,,,yes,,")
    report = build(data_dir, [row()])
    assert len(report["warnings"]) == 1
    assert "overrides.csv line 2" in report["warnings"][0] and "999999" in report["warnings"][0]
    assert report["meta"]["total"] == 1


def test_override_code_shared_by_two_events_warns(data_dir):
    with_override(data_dir, "507610,,,,,,yes,")
    report = build(data_dir, [row("A", "507610", start="18-11-2026"), row("B", "507610", start="21-11-2026")])
    assert any("belongs to 2 events" in w for w in report["warnings"])
    assert all(e["cancelled"] for e in load_events(data_dir))


@pytest.mark.parametrize("line, expected", [
    ("aicf-400001,31-02-2027,,,,,,", "line 2: start_date '31-02-2027' is not a date"),
    ("aicf-400001,,,,Narnia,,,", "line 2: state 'Narnia' is not an Indian state"),
    ("aicf-400001,,,,,maybe,,", "line 2: hide must be 'yes' or empty"),
    (",,,,,yes,,", "line 2: key is empty"),
    ("aicf-400001,,01-01-2020,,,,,", "would put the end"),
])
def test_override_mistakes_stop_with_line_numbers_and_write_nothing(data_dir, line, expected):
    build(data_dir, [row("X", "400001", start="10-12-2026", end="11-12-2026")])
    before = files_snapshot(data_dir)
    with_override(data_dir, line)
    with pytest.raises(be.DataFileError) as caught:
        build(data_dir, [row("X", "400001", start="10-12-2026", end="11-12-2026")], now=NEXT_DAY)
    assert "data/manual/overrides.csv" in str(caught.value) and expected in str(caught.value)
    assert files_snapshot(data_dir)["events.json"] == before["events.json"]


def test_manual_event_removed_from_the_csv_leaves_the_data(data_dir):
    write_manual(data_dir, EVENTS_HEADER + "mine,My Cup,10-01-2027,,Goa,,,,,,,\n")
    build(data_dir, [row()])
    write_manual(data_dir, EVENTS_HEADER)
    build(data_dir, [row()], now=NEXT_DAY)
    assert "mine" not in by_id(data_dir)  # manual.csv is the record; git keeps its history
