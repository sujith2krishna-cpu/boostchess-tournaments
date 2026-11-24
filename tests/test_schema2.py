"""Schema version 2: age is a list, every event has a country, timestamp-only detection."""
import json
from datetime import timedelta

import pytest

import build_events as be
from conftest import (EVENTS_HEADER, NOW, build, by_id, load_doc, load_events, row,
                      write_manual)

NEXT_DAY = NOW + timedelta(days=1)


# ---- age list -----------------------------------------------------------
def test_age_is_a_list_in_the_output(data_dir):
    build(data_dir, [row("Under 12 & 18 Team Cup", "400001"),
                     row("U11 Open", "400002"),
                     row("Plain Open", "400003")])
    ages = {e["name"]: e["tags"]["age"] for e in load_events(data_dir)}
    assert ages == {"Under 12 & 18 Team Cup": ["U12", "U18"], "U11 Open": ["U11"], "Plain Open": []}


def test_schema_version_is_2(data_dir):
    build(data_dir, [row()])
    assert load_doc(data_dir)["schema_version"] == be.SCHEMA_VERSION == 2


@pytest.mark.parametrize("cell, expected", [
    ("U11", ["U11"]), ("Under-11", ["U11"]), ("U12/U18", ["U12", "U18"]),
    ("Under 12 & 18", ["U12", "U18"]), ("u9, u11", ["U9", "U11"]),
])
def test_manual_age_column_accepts_one_or_several_groups(data_dir, cell, expected):
    write_manual(data_dir, EVENTS_HEADER + f',Cup,03-02-2027,,Goa,,,,,"{cell}",\n')
    build(data_dir, [row()])
    manual = next(e for e in load_events(data_dir) if e["source"] == "manual")
    assert manual["tags"]["age"] == expected


@pytest.mark.parametrize("cell", ["eleven", "11", "12/18"])
def test_manual_age_column_rejects_unclear_values(data_dir, cell):
    write_manual(data_dir, EVENTS_HEADER + f',Cup,03-02-2027,,Goa,,,,,"{cell}",\n')
    with pytest.raises(be.DataFileError, match="line 2: age"):
        build(data_dir, [row()])


def test_old_schema_data_is_migrated_for_events_that_left_the_page(data_dir):
    """A schema-1 file (age as a string/null, no country) still loads; gone events are upgraded."""
    build(data_dir, [row("Under-11 Open", "400001"), row("Plain", "400002"), row("Stays", "400003"), row("Stays too", "400004")])
    doc = load_doc(data_dir)
    for event in doc["events"]:
        event["tags"]["age"] = event["tags"]["age"][0] if event["tags"]["age"] else None
        del event["country"]
    doc["schema_version"] = 1
    (data_dir / "events.json").write_text(json.dumps(doc), encoding="utf-8")
    build(data_dir, [row("Stays", "400003"), row("Stays too", "400004")], now=NEXT_DAY)
    events = by_id(data_dir)
    assert events["aicf-400001"]["gone_from_source"] is True
    assert events["aicf-400001"]["tags"]["age"] == ["U11"]
    assert events["aicf-400002"]["tags"]["age"] == []
    assert {e["country"] for e in events.values()} == {"IN"}
    assert load_doc(data_dir)["schema_version"] == 2


# ---- country ------------------------------------------------------------
def test_every_event_has_a_country_and_state_city_are_unchanged(data_dir):
    write_manual(data_dir, EVENTS_HEADER + ",Pune Cup,03-02-2027,,\"Pune, Maharashtra\",,,,,,\n")
    build(data_dir, [row("A", "400001", place="Banka,\nBihar"), row("B", "400002", place="")])
    events = load_events(data_dir)
    assert [e["country"] for e in events] == ["IN"] * 3
    by_name = {e["name"]: e for e in events}
    assert (by_name["A"]["city"], by_name["A"]["state"]) == ("Banka", "Bihar")
    assert (by_name["Pune Cup"]["city"], by_name["Pune Cup"]["state"]) == ("Pune", "Maharashtra")
    assert (by_name["B"]["city"], by_name["B"]["state"]) == (None, None)
    assert list(events[0])[list(events[0]).index("city") + 1] == "country"


@pytest.mark.parametrize("source", ["aicf", "chessfee", "chessresults_ind", "manual"])
def test_indian_sources_are_always_in(source):
    assert be.country_for(source) == "IN"
    assert be.country_for(source, "us") == "IN"  # their own field is not consulted


@pytest.mark.parametrize("given, expected", [
    ("DE", "DE"), (" us ", "US"), ("gb", "GB"), ("IN", "IN"),
    ("UK", None), ("XX", None), ("GER", None), ("", None), (None, None), ("Germany", None),
])
def test_chessbase_calendar_uses_the_events_own_iso_code(given, expected):
    assert be.country_for("chessbase_calendar", given) == expected


def test_unknown_source_has_no_country():
    assert be.country_for("somewhere_else", "IN") is None


def test_iso_code_list_is_complete():
    assert len(be.ISO_COUNTRIES) == 249


# ---- "only timestamps changed" (for the daily job) ----------------------
def test_first_run_has_real_changes(data_dir):
    assert build(data_dir, [row()])["only_timestamps_changed"] is False


def test_same_page_next_day_changes_only_timestamps(data_dir):
    rows = [row("A", "400001"), row("B", "400002")]
    build(data_dir, rows)
    report = build(data_dir, rows, now=NEXT_DAY)
    assert report["only_timestamps_changed"] is True
    assert load_events(data_dir)[0]["last_seen"] == "2026-11-25"  # it did move


@pytest.mark.parametrize("second_page", [
    [row("A", "400001"), row("B", "400002"), row("C", "400003")],            # new event
    [row("A", "400001")],                                                    # one vanished
    [row("A", "400001", end="13-12-2026"), row("B", "400002")],              # new end date
    [row("A", "400001"), row("B", "400002", place="Pune")],                  # new place
    [row("A", "400001"), row("B", "400002", brochure='<a href="https://x.org/b.pdf">Download</a>')],
])
def test_any_real_change_is_reported(data_dir, second_page):
    build(data_dir, [row("A", "400001"), row("B", "400002")])
    assert build(data_dir, second_page, now=NEXT_DAY)["only_timestamps_changed"] is False


def test_a_changed_manual_file_or_override_counts_as_real(data_dir):
    rows = [row("A", "400001")]
    build(data_dir, rows)
    write_manual(data_dir, EVENTS_HEADER + ",Cup,03-02-2027,,Goa,,,,,,\n")
    assert build(data_dir, rows, now=NEXT_DAY)["only_timestamps_changed"] is False
    assert build(data_dir, rows, now=NEXT_DAY + timedelta(days=1))["only_timestamps_changed"] is True
    write_manual(data_dir, "key,start_date,end_date,place,state,hide,cancelled,note\n"
                           "aicf-400001,,,,,yes,,\n", "overrides.csv")
    assert build(data_dir, rows, now=NEXT_DAY + timedelta(days=2))["only_timestamps_changed"] is False


def test_upgrading_from_schema_1_counts_as_a_real_change(data_dir):
    rows = [row("A", "400001")]
    build(data_dir, rows)
    doc = load_doc(data_dir)
    doc["schema_version"] = 1
    (data_dir / "events.json").write_text(json.dumps(doc), encoding="utf-8")
    assert build(data_dir, rows, now=NEXT_DAY)["only_timestamps_changed"] is False


def test_function_ignores_exactly_the_timestamps():
    event = {"id": "x", "source": "aicf", "name": "A", "first_seen": "2026-11-24",
             "last_seen": "2026-11-24"}
    old = {"schema_version": 2, "generated_at": "t1", "events": [event]}
    meta = {"generated_at": "t1", "total": 1}
    same = {"schema_version": 2, "generated_at": "t2", "events": [dict(event, last_seen="2026-11-25")]}
    assert be.only_timestamps_changed(old, meta, same, dict(meta, generated_at="t2")) is True
    renamed = {"schema_version": 2, "generated_at": "t2", "events": [dict(event, name="B")]}
    assert be.only_timestamps_changed(old, meta, renamed, meta) is False
    assert be.only_timestamps_changed(old, meta, same, dict(meta, total=2)) is False
    assert be.only_timestamps_changed({}, {}, same, meta) is False


def test_github_output_flag_and_summary_line(data_dir, tmp_path, capsys):
    from conftest import make_html
    page = tmp_path / "page.html"
    page.write_text(make_html([row(f"E{i}", str(400000 + i), start="01-12-2026", end="02-12-2026")
                               for i in range(150)]), encoding="utf-8")
    out = tmp_path / "gh_output.txt"
    args = ["--html", str(page), "--data-dir", str(data_dir), "--github-output", str(out)]
    assert be.main(args) == 0
    assert out.read_text() == "real_changes=true\n"          # first run: new data
    assert "real changes" in capsys.readouterr().out
    assert be.main(args) == 0
    assert out.read_text() == "real_changes=true\nreal_changes=false\n"  # nothing but timestamps
    assert "none, only last_seen/generated_at differ" in capsys.readouterr().out
