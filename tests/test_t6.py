"""T6: missed-fetch alarm, quality report, review list, more override columns, name tails."""
import csv
import io
import json
import re
from datetime import date, datetime, timedelta

import pytest

import build_events as be
import daily
import dedup
import heartbeat
import quality
from conftest import NOW, OVERRIDES_HEADER, ROOT, build, by_id, row, write_manual

IST = be.IST
WORKFLOW = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
TAILS = {e["id"]: e for e in json.loads(
    (ROOT / "tests" / "fixtures" / "dedup_name_tails.json").read_text("utf-8"))["events"]}
BROCHURE = '<a href="https://x.org/brochure.pdf">Download</a>'


def override(**values) -> str:
    """One overrides.csv line with the given columns filled in (the others empty)."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="").writerow([values.get(c, "") for c in be.OVERRIDES_CSV_COLUMNS])
    return buffer.getvalue()


def with_overrides(folder, *lines, header=OVERRIDES_HEADER):
    write_manual(folder, header + "".join(line + "\n" for line in lines), "overrides.csv")


def review(folder) -> list[dict]:
    return list(csv.DictReader(io.StringIO((folder / "review.csv").read_text("utf-8"))))


def load_quality(folder) -> dict:
    return json.loads((folder / "quality.json").read_text("utf-8"))


# ======================================================================================
# 1-2. Missed fetches
# ======================================================================================
def source(last_success, error_at=None, enabled=True):
    info = {"enabled": enabled, "status": "ok" if enabled else "disabled", "last_success": last_success,
            "last_error": {"at": error_at, "message": "x"} if error_at else None}
    return info


def at(hour, minute=0, day=25):
    return datetime(2026, 11, day, hour, minute, tzinfo=IST)


def test_a_source_due_for_more_than_six_hours_without_an_attempt_is_a_missed_fetch():
    meta = {"sources": {"aicf": source("2026-11-25T00:28:06+05:30")}}  # due at 12:28
    assert heartbeat.MISSED_FETCH_HOURS == 6 and be.FETCH_INTERVAL_HOURS == 12
    assert heartbeat.missed_fetches(meta, at(18, 28)) == []  # exactly 6 hours: still fine
    found = heartbeat.missed_fetches(meta, at(18, 30))
    assert [(m["source"], m["waiting_hours"]) for m in found] == [("aicf", 6.0)]
    assert found[0]["due_since"].startswith("2026-11-25T12:28")


def test_todays_timeline_the_1620_run_was_late_but_not_yet_an_alarm():
    """Due 12:28; GitHub never created the 14:47 run; the 16:20 run came 3.9 hours late."""
    meta = {"sources": {n: source("2026-11-25T00:28:06+05:30") for n in ("aicf", "chessfee")}}
    assert heartbeat.missed_fetches(meta, at(16, 20)) == []
    late = heartbeat.missed_fetches(meta, at(20, 47))  # had 14:47 and 17:47 both been skipped
    assert {m["source"] for m in late} == {"aicf", "chessfee"} and late[0]["waiting_hours"] == 8.3
    text = heartbeat.missed_message(late)
    assert "Missed fetch: source 'aicf' has been due since 2026-11-25 12:28" in text
    assert "GitHub skipped scheduled runs" in text and "Actions tab" in text


def test_a_failed_attempt_counts_as_an_attempt_and_switched_off_or_never_tried_sources_are_left_out():
    meta = {"sources": {
        "aicf": source("2026-11-23T10:00:00+05:30", error_at="2026-11-25T15:00:00+05:30"),  # tried 15:00
        "chessfee": source(None, error_at="2026-11-25T09:00:00+05:30"),  # never worked, tried 9:00
        "kca": source(None),  # never tried: the 3-day alarm says "never fetched"
        "chessbase_calendar": source("2026-11-20T10:00:00+05:30", enabled=False),
    }}
    found = heartbeat.missed_fetches(meta, at(18, 0))
    assert [(m["source"], m["waiting_hours"]) for m in found] == [("chessfee", 9.0)]


def test_heartbeat_compares_meta_from_before_the_build_with_the_run_start(tmp_path, capsys):
    now = datetime.now(IST)
    fresh = {"sources": {"aicf": source(now.isoformat())}}  # this run fetched it
    (tmp_path / "meta.json").write_text(json.dumps(fresh), encoding="utf-8")
    before = tmp_path / "meta-before.json"
    before.write_text(json.dumps({"sources": {"aicf": source((now - timedelta(hours=19)).isoformat())}}),
                      encoding="utf-8")
    started = (now - timedelta(minutes=2)).isoformat()
    summary = tmp_path / "summary.md"
    assert heartbeat.main(["--data-dir", str(tmp_path)]) == 0  # the data itself is fine
    assert heartbeat.main(["--data-dir", str(tmp_path), "--before", str(before), "--started", started,
                           "--summary-file", str(summary)]) == 1
    captured = capsys.readouterr()
    assert "::error title=Missed fetch::aicf: due for 7 hours without a fetch attempt" in captured.out
    assert "Missed fetch: source 'aicf'" in captured.err and "Heartbeat FAILED" in summary.read_text()
    before.write_text(json.dumps({"sources": {"aicf": source((now - timedelta(hours=13)).isoformat())}}),
                      encoding="utf-8")
    assert heartbeat.main(["--data-dir", str(tmp_path), "--before", str(before), "--started", started]) == 0
    # no meta.json before the first run: nothing to compare, no alarm
    assert heartbeat.main(["--data-dir", str(tmp_path), "--before", str(tmp_path / "none.json")]) == 0


def test_workflow_keeps_meta_from_before_the_build_for_the_heartbeat():
    remember = WORKFLOW.index('cp data/meta.json "$RUNNER_TEMP/meta-before.json"')
    assert WORKFLOW.index("python -m pytest -q") < remember < WORKFLOW.index("scripts/build_events.py")
    assert 'RUN_STARTED=$(date -u' in WORKFLOW and '>> "$GITHUB_ENV"' in WORKFLOW
    beat = WORKFLOW[WORKFLOW.index("python scripts/heartbeat.py"):]
    assert '--before "$RUNNER_TEMP/meta-before.json" --started "$RUN_STARTED"' in beat.split("deploy:")[0]


# ======================================================================================
# 3. Quality report
# ======================================================================================
def ev(event_id, start, **extra):
    tags = extra.pop("tags", {})
    return be.canonical({"id": event_id, "name": event_id, "start": start, "end": start,
                         "first_seen": "2026-11-01", "last_seen": "2026-11-25",
                         "source": event_id.split("-")[0], "country": "IN", "state": "Kerala",
                         "brochure_url": "https://x.org/b.pdf",
                         "tags": {"formats": ["rapid"], "fide_rated": True, "fide_how": "stated", **tags},
                         **extra})


TODAY = date(2026, 11, 25)


def test_fully_known_needs_format_fide_state_dates_and_a_register_or_brochure_link():
    good = ev("aicf-1", "2026-12-01")
    assert quality.fully_known(good)
    assert quality.fully_known(ev("aicf-1", "2026-12-01", brochure_url=None, register_url="https://r.org"))
    assert quality.fully_known(ev("aicf-1", "2026-12-01", tags={"fide_rated": False}))  # "not rated" is known
    for broken, label in ((ev("aicf-1", "2026-12-01", tags={"formats": []}), "format"),
                          (ev("aicf-1", "2026-12-01", tags={"fide_rated": None}), "fide"),
                          (ev("aicf-1", "2026-12-01", state=None), "state"),
                          (ev("aicf-1", "2026-12-01", flags={"dates_suspect": True}), "dates"),
                          (ev("aicf-1", "2026-12-01", brochure_url=None), "register or brochure link")):
        assert quality.missing_parts(broken) == [label]


def test_windows_and_which_events_count_as_shown():
    events = [ev("aicf-today", "2026-11-25"), ev("aicf-day30", "2026-12-25"), ev("aicf-day31", "2026-12-26"),
              ev("aicf-past", "2026-11-24"), ev("aicf-nodate", None),
              ev("aicf-hidden", "2026-12-01", hidden=True), ev("aicf-cancelled", "2026-12-01", cancelled=True),
              ev("chessfee-merged", "2026-12-01", merged_into="aicf-today")]
    report = quality.quality_report(events, TODAY, "t")
    assert report["windows"]["next_30_days"] == {"from": "2026-11-25", "to": "2026-12-25"}
    assert report["overall"]["next_30_days"]["events"] == 2  # today and day 30
    assert report["overall"]["upcoming"]["events"] == 3  # ... and day 31
    assert report["sources"]["chessfee"]["upcoming"]["events"] == 0


def test_percentages_per_source_and_overall_and_the_95_percent_target():
    events = [ev("aicf-1", "2026-12-01"), ev("aicf-2", "2026-12-02", tags={"formats": [], "fide_rated": None}),
              ev("chessfee-1", "2026-12-03", state=None, brochure_url=None),
              ev("chessfee-2", "2026-12-04", brochure_url=None, register_url="https://r.org")]
    report = quality.quality_report(events, TODAY, "2026-11-25T10:00:00+05:30")
    aicf = report["sources"]["aicf"]["next_30_days"]
    assert (aicf["events"], aicf["fully_known_pct"], aicf["unknown_format_pct"], aicf["unknown_fide_pct"]) == \
        (2, 50.0, 50.0, 50.0)
    chessfee = report["sources"]["chessfee"]["next_30_days"]
    assert (chessfee["no_state_pct"], chessfee["no_brochure_pct"], chessfee["no_register_link_pct"]) == \
        (50.0, 100.0, 50.0)
    overall = report["overall"]["next_30_days"]
    assert (overall["events"], overall["fully_known"], overall["fully_known_pct"], overall["suspect_dates_pct"]) == \
        (4, 2, 50.0, 0.0)
    assert report["target"] == {"window": "next_30_days", "fully_known_pct": 95.0, "now_pct": 50.0, "met": False}
    assert report["sources"]["kca"]["next_30_days"]["fully_known_pct"] is None  # no events: no percentage


def test_alerts_for_a_ten_point_drop_or_a_halved_count_compared_with_the_previous_run():
    def run_with(known, unknown, previous=None):
        events = [ev(f"aicf-{i}", "2026-12-01") for i in range(known)]
        events += [ev(f"aicf-u{i}", "2026-12-01", state=None) for i in range(unknown)]
        return quality.quality_report(events, TODAY, "t", previous)

    assert run_with(10, 0)["alerts"] == []  # nothing to compare with
    ten = run_with(18, 2, run_with(20, 0))  # 100% -> 90%: a drop of exactly 10 points
    assert [a["what"] for a in ten["alerts"]] == ["fully_known_drop", "fully_known_drop"]
    assert ten["alerts"][0]["message"] == "aicf: fully known (next 30 days) fell from 100% to 90%"
    almost = run_with(91, 9, run_with(100, 0))  # 100% -> 91%: 9 points, no alert
    assert almost["alerts"] == []
    halved = run_with(5, 0, run_with(10, 0))
    assert [a["what"] for a in halved["alerts"]] == ["count_halved"]
    assert halved["alerts"][0]["message"] == "aicf: upcoming events fell from 10 to 5 (half or fewer)"
    assert run_with(2, 0, run_with(4, 0))["alerts"] == []  # too few events to judge


def test_quality_json_is_written_every_run_and_shown_in_the_summary(data_dir):
    report = build(data_dir, [row("Rapid Open", "400001", start="01-12-2026", end="01-12-2026",
                                  place="Kochi, Kerala", brochure=BROCHURE),
                              row("Plain Cup", "400002", start="02-12-2026", end="02-12-2026", place="Kochi")])
    written = load_quality(data_dir)
    assert written == report["quality"] and written["today"] == "2026-11-24"
    assert written["overall"]["next_30_days"]["events"] == 2
    assert set(written["sources"]) == set(be.SOURCE_PRIORITY)
    assert written["review"] == {"missing": 2, "possible_duplicates": 0}
    text = daily.summary_markdown(report)
    assert "### Data quality (shown events starting in the next 30 days)" in text
    assert "**Target:** 95% fully known" in text and "| aicf | 2 |" in text
    assert "**Review list** (`data/review.csv`): 2 events to complete" in text


def test_a_quality_alert_becomes_a_warning_on_the_run(data_dir):
    rows = [row(f"FIDE Rated Rapid Open {i}", str(400001 + i), start="01-12-2026", end="01-12-2026",
                place="Kochi, Kerala", brochure=BROCHURE) for i in range(6)]
    build(data_dir, rows)
    worse = [r if i % 2 else row(f"Plain Cup {i}", str(400001 + i), start="01-12-2026", end="01-12-2026",
                                   place="Kochi") for i, r in enumerate(rows)]
    report = build(data_dir, worse, now=NOW.replace(hour=20))
    assert any(a["what"] == "fully_known_drop" for a in report["quality"]["alerts"])
    assert any(line.startswith("::warning title=Quality alert::aicf: fully known") for line in daily.annotations(report))
    assert "**Quality alerts** (compared with the previous run):" in daily.summary_markdown(report)
    assert report["only_timestamps_changed"] is False


def test_same_input_twice_changes_only_timestamps_also_in_the_quality_files(data_dir):
    rows = [row("Plain Cup", "400001", start="01-12-2026", end="01-12-2026", place="Kochi")]
    build(data_dir, rows)
    first = (data_dir / "quality.json").read_text("utf-8"), (data_dir / "review.csv").read_bytes()
    report = build(data_dir, rows, now=NOW.replace(hour=21))
    assert report["only_timestamps_changed"] is True
    again = (data_dir / "quality.json").read_text("utf-8"), (data_dir / "review.csv").read_bytes()
    assert again[1] == first[1]
    assert re.sub(r'"generated_at": "[^"]+"', "", again[0]) == re.sub(r'"generated_at": "[^"]+"', "", first[0])


# ======================================================================================
# 4. The review list
# ======================================================================================
def test_review_csv_lists_shown_events_of_the_next_30_days_that_miss_something(data_dir):
    build(data_dir, [row("Later Plain Cup", "400003", start="20-12-2026", end="20-12-2026", place="Kochi"),
                     row("Rapid Open", "400001", start="01-12-2026", end="01-12-2026", place="Kochi, Kerala",
                         brochure=BROCHURE),
                     row("Blitz Cup", "400002", start="02-12-2026", end="02-12-2026", place="Kochi"),
                     row("Too Far Cup", "400004", start="10-01-2027", end="10-01-2027", place="Kochi")])
    rows = review(data_dir)
    assert list(rows[0]) == list(quality.REVIEW_COLUMNS)
    assert [r["id"] for r in rows] == ["aicf-400001", "aicf-400002", "aicf-400003"]  # by start date
    first = rows[0]
    assert (first["kind"], first["missing"], first["state"], first["city"]) == ("missing", "fide", "Kerala", "Kochi")
    assert rows[1]["missing"] == "fide, register or brochure link"
    assert rows[2]["missing"] == "format, fide, register or brochure link"
    assert first["brochure_url"] == "https://x.org/brochure.pdf" and first["add_to_file"] == "data/manual/overrides.csv"
    cells = next(csv.reader([rows[2]["line_to_add"]]))
    filled = dict(zip(be.OVERRIDES_CSV_COLUMNS, cells))
    assert len(cells) == len(be.OVERRIDES_CSV_COLUMNS) and filled["key"] == "aicf-400003"
    assert {c for c, v in filled.items() if v == "?"} == {"format", "fide_rated", "register_url"}


def test_the_ready_line_can_be_pasted_as_it_is_and_then_filled_in(data_dir):
    rows = [row("Plain Cup", "400001", start="01-12-2026", end="01-12-2026", place="Kochi")]
    build(data_dir, rows)
    line = review(data_dir)[0]["line_to_add"]
    with_overrides(data_dir, line)
    report = build(data_dir, rows, now=NOW.replace(hour=20))  # pasted, nothing filled in: still runs
    assert any("overrides.csv line 2: register_url, fide_rated, format still have '?'" in w
               for w in report["warnings"])
    filled = line.replace("?", "https://r.org/register", 1).replace("?", "yes", 1).replace("?", "rapid", 1)
    with_overrides(data_dir, filled)
    build(data_dir, rows, now=NOW.replace(hour=21))
    event = by_id(data_dir)["aicf-400001"]
    assert event["tags"]["formats"] == ["rapid"] and event["tags"]["fide_how"] == "manual"
    assert event["register_url"] == "https://r.org/register"
    assert review(data_dir) == [] and load_quality(data_dir)["overall"]["next_30_days"]["fully_known_pct"] == 100.0


def test_possible_duplicates_are_listed_with_both_ids_and_a_pairs_line():
    a = ev("aicf-1", "2026-12-01")
    b = ev("chessfee-9", "2027-03-01", flags={"possible_duplicate_of": "aicf-1"})
    rows = quality.review_rows([a, b], TODAY)
    assert len(rows) == 1  # aicf-1 is fully known; chessfee-9 is outside the 30 days, but listed as a pair
    pair = rows[0]
    assert (pair["kind"], pair["id"], pair["other_id"]) == ("possible_duplicate", "chessfee-9", "aicf-1")
    assert pair["add_to_file"] == "data/manual/pairs.csv" and pair["line_to_add"] == "aicf-1,chessfee-9,same,"
    assert "not_same" in pair["missing"]


def test_review_list_shows_other_sites_links():
    primary = ev("aicf-1", "2026-12-01", state=None, also_listed_on=[
        {"source": "chessfee", "source_url": "https://chessfee.com/e/1"},
        {"source": "chessresults_ind", "source_url": "https://chess-results.com/tnr1.aspx"}])
    rows = quality.review_rows([primary], TODAY)
    assert rows[0]["also_listed_on"] == "https://chessfee.com/e/1 | https://chess-results.com/tnr1.aspx"
    assert rows[0]["missing"] == "state"


def test_committed_review_and_quality_files_match_the_committed_events():
    events = json.loads((ROOT / "data" / "events.json").read_text("utf-8"))["events"]
    written = load_quality(ROOT / "data")
    today = date.fromisoformat(written["today"])
    assert quality.review_csv(quality.review_rows(events, today)) == (ROOT / "data" / "review.csv").read_bytes()
    assert written["overall"] == quality.quality_report(events, today, "t")["overall"]


# ======================================================================================
# 5. More override columns
# ======================================================================================
def test_new_columns_are_added_at_the_end_and_old_lines_still_work(data_dir):
    assert be.OVERRIDES_CSV_COLUMNS[-4:] == ("fide_rated", "format", "age", "registration_deadline")
    old_header = "key,start_date,end_date,place,state,hide,cancelled,note,register_url,results_url\n"
    with_overrides(data_dir, "aicf-400001,,,,,,,checked,,", header=old_header)
    build(data_dir, [row("X", "400001")])
    assert by_id(data_dir)["aicf-400001"]["note"] == "checked"
    with_overrides(data_dir, "aicf-400001,,,,,,,checked again")  # a short line in the new file
    build(data_dir, [row("X", "400001")])
    assert by_id(data_dir)["aicf-400001"]["note"] == "checked again"


def test_manual_fide_format_age_and_deadline(data_dir):
    with_overrides(data_dir,
                   override(key="aicf-400001", fide_rated="yes", format="rapid|blitz", age="U-9|U-11",
                            registration_deadline="05-12-2026"),
                   override(key="aicf-400002", fide_rated="No", format="classical", registration_deadline="2026-12-06"))
    build(data_dir, [row("Kids Cup", "400001"), row("FIDE Rated Rapid Open", "400002")])
    events = by_id(data_dir)
    one, two = events["aicf-400001"], events["aicf-400002"]
    assert (one["tags"]["fide_rated"], one["tags"]["fide_how"]) == (True, "manual")
    assert one["tags"]["formats"] == ["rapid", "blitz"] and one["tags"]["age"] == ["U9", "U11"]
    assert one["registration_deadline"] == "2026-12-05" and two["registration_deadline"] == "2026-12-06"
    # manual wins over what the name says, and the replaced values are remembered
    assert (two["tags"]["fide_rated"], two["tags"]["fide_how"], two["tags"]["formats"]) == (False, "manual", ["classical"])
    assert two["overridden"] == {"tags.formats": ["rapid"], "tags.fide_rated": True, "tags.fide_how": "stated",
                                 "registration_deadline": None}
    # delete the line: the event goes back to what the site says
    with_overrides(data_dir)
    build(data_dir, [row("Kids Cup", "400001"), row("FIDE Rated Rapid Open", "400002")])
    two = by_id(data_dir)["aicf-400002"]
    assert (two["tags"]["fide_rated"], two["tags"]["fide_how"], two["tags"]["formats"], two["overridden"]) == \
        (True, "stated", ["rapid"], None)


@pytest.mark.parametrize("values, expected", [
    ({"fide_rated": "maybe"}, "line 2: fide_rated must be 'yes' or 'no' (or empty), not 'maybe'"),
    ({"format": "bullet"}, "line 2: format 'bullet' is not understood. Write classical, rapid or blitz"),
    ({"format": "rapid|bullet"}, "line 2: format 'rapid|bullet' is not understood"),
    ({"age": "nine"}, "line 2: age 'nine' is not understood. Write it like U-9"),
    ({"age": "U-9|kids"}, "line 2: age 'U-9|kids' is not understood"),
    ({"registration_deadline": "31-02-2026"}, "line 2: registration_deadline '31-02-2026' is not a date"),
])
def test_a_bad_value_in_a_new_column_stops_the_build_and_names_file_and_line(data_dir, values, expected):
    build(data_dir, [row("X", "400001")])
    before = (data_dir / "events.json").read_bytes()
    with_overrides(data_dir, override(key="aicf-400001", **values))
    with pytest.raises(be.DataFileError) as caught:
        build(data_dir, [row("X", "400001")], now=NOW.replace(hour=20))
    assert "data/manual/overrides.csv" in str(caught.value) and expected in str(caught.value)
    assert (data_dir / "events.json").read_bytes() == before


def group_with_overrides(events, overrides):
    events = [be.canonical(e) for e in events]
    errors, warnings = [], []
    be.apply_overrides(events, overrides, errors, warnings)
    dedup.group_events(events, [], warnings)
    be.reapply_manual_values(events, overrides)
    assert not errors
    return {e["id"]: e for e in events}


def item(key, **values):
    return {"line": 2, "key": key, "start_date": None, "end_date": None, "place": None, "state": None,
            "hide": False, "cancelled": False, "note": None, "register_url": None, "results_url": None,
            "fide_rated": None, "formats": None, "age": None, "registration_deadline": None, **values}


def test_manual_values_win_over_grouping_and_sibling_sections():
    aicf = ev("aicf-1", "2026-12-01", name="Kochi Chess Academy Rapid Open", city="Kochi",
              tags={"formats": ["rapid"], "fide_rated": True, "fide_how": "stated", "age": ["U11"]})
    chessfee = ev("chessfee-1", "2026-12-01", name="Kochi Chess Academy Rapid Open", city="Kochi",
                  tags={"formats": ["rapid"], "fide_rated": None, "age": ["U13"]})
    # a line on the record that is merged into the AICF one: shown on the primary too
    events = group_with_overrides([aicf, chessfee], [item("chessfee-1", fide_rated=False, formats=["blitz"],
                                                         age=["U9"], registration_deadline="2026-11-28")])
    assert events["chessfee-1"]["merged_into"] == "aicf-1"
    for e in events.values():
        assert (e["tags"]["fide_rated"], e["tags"]["fide_how"], e["tags"]["formats"], e["tags"]["age"]) == \
            (False, "manual", ["blitz"], ["U9"])
        assert e["registration_deadline"] == "2026-11-28"
    # a manual "no" on one section is never replaced by a rated sibling section's "yes"
    rated = ev("aicf-2", "2026-12-05", name="Big Festival (Category A)", city="Madurai",
               brochure_url="https://x.org/fest.pdf")
    other = ev("aicf-3", "2026-12-05", name="Big Festival (Category B)", city="Madurai",
               brochure_url="https://x.org/fest.pdf", tags={"fide_rated": None})
    events = group_with_overrides([rated, other], [item("aicf-3", fide_rated=False)])
    assert (events["aicf-3"]["tags"]["fide_rated"], events["aicf-3"]["tags"]["fide_how"]) == (False, "manual")


def test_schema_6_has_registration_deadline_and_old_events_migrate():
    keys = list(be.EVENT_KEYS)
    assert be.SCHEMA_VERSION == 6
    assert keys.index("registration_deadline") == keys.index("results_url") + 1
    old = {"id": "aicf-1", "name": "A", "source": "aicf", "start": "2026-12-01", "end": "2026-12-01",
           "first_seen": "2026-11-01", "last_seen": "2026-11-25"}
    assert be.canonical(old)["registration_deadline"] is None


def test_committed_overrides_csv_has_the_new_header():
    header = (ROOT / "data" / "manual" / "overrides.csv").read_text("utf-8").splitlines()[0]
    assert header == ",".join(be.OVERRIDES_CSV_COLUMNS)


# ======================================================================================
# 6. Chess-Results name tails
# ======================================================================================
@pytest.mark.parametrize("name, city, expected", [
    ("3rd Pune International Speed Festival 2026 - RAPID Rating Chess Tournament Organised by 8x8 Chess "
     "Academy Pune", "Pune", "3rd Pune International Speed Festival 2026 - RAPID Rating Chess Tournament"),
    ("1st Late Sunil Swarup Barse Memorial Rapid, Jalgaon 20th Dec 2026 (Mr. Jatin Barse )", None,
     "1st Late Sunil Swarup Barse Memorial Rapid, Jalgaon"),
    ("2nd Manchester City Below 1800 Tournament -> 27 Nov 2026 - 29 Nov 2026 - Coimbatore", "COIMBATORE",
     "2nd Manchester City Below 1800 Tournament"),
    ("DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN 2026 – 2 to 6 DEC", "Kanyakumari",
     "DRAGON CHESS ACADEMY 1ST INTERNATIONAL OPEN 2026"),
    ("Kochi Open (Dr. A. Kumar)", "Kochi", "Kochi Open"),
    ("Kochi Rapid Open", "Kochi", "Kochi Rapid Open"),  # the city at the start stays
    ("Coimbatore", "Coimbatore", "Coimbatore"),  # never strip a name down to nothing
    ("Open Organised by Club and More", None, "Open"),
    ("Chennai Rapid (Category A)", "Chennai", "Chennai Rapid (Category A)"),  # not a person
])
def test_strip_name_tails(name, city, expected):
    assert dedup.strip_name_tails(name, city) == expected


@pytest.mark.parametrize("a, b", [
    ("aicf-486240", "chessresults_ind-1538894"),  # Manchester City: date and place tail
    ("aicf-504554", "chessresults_ind-1522214"),  # Pune Rapid: "Organised by ..."
    ("aicf-504557", "chessresults_ind-1522216"),  # Pune Blitz: "Organised by ..."
    ("aicf-508734", "chessresults_ind-1540498"),  # Sunil Swarup Barse: date and "(Mr. ...)"
    ("aicf-503296", "chessfee-1815"),  # Dragon: "2 to 6 DEC" (was already same; must stay same)
])
def test_the_pairs_settled_by_hand_now_match_on_their_own(a, b):
    result = dedup.compare(dedup.Features(be.canonical(TAILS[a])), dedup.Features(be.canonical(TAILS[b])))
    assert result["decision"] == "same" and result["score"] >= dedup.SAME_AT, result
    events = [be.canonical(TAILS[a]), be.canonical(TAILS[b])]
    dedup.group_events(events, [], [])  # no pairs.csv
    assert events[1]["merged_into"] == a or events[0]["merged_into"] == b


def test_festival_sections_stay_apart():
    events = [be.canonical(e) for e in TAILS.values()]
    dedup.group_events(events, [], [])
    groups = {}
    for e in events:
        groups.setdefault(e["group_id"], []).append(e)
    for label, word in (("Athens", "athens of the east"), ("Akshaya", "akshaya"), ("Delhi", "22nd delhi")):
        festival = [g for g in groups.values() if word in (g[0]["name"] or "").lower()]
        for members in festival:
            letters = {dedup.sections(m["name"])["categories"] for m in members}
            assert len(letters) == 1, (label, [m["id"] for m in members])
        count = {"Athens": 5, "Akshaya": 4, "Delhi": 3}[label]
        assert len(festival) == count, label
    athens = [e for e in events if "athens" in e["name"].lower()]
    assert all(e["merged_into"] is None and e["group_id"] == e["id"] for e in athens)


def test_name_tails_fixture_has_no_phone_numbers():
    def texts(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for v in value.values():
                yield from texts(v)
        elif isinstance(value, list):
            for v in value:
                yield from texts(v)
    for text in texts(list(TAILS.values())):
        assert be.strip_phones(text) == text
