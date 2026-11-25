"""T4a: the 12-hour fetch rule, the quick no-op run, the stale-data alarm, results links,
manual register/results links, schema 4."""
import json
import re
from datetime import datetime, timedelta

import pytest

import build_events as be
import daily
import heartbeat
from conftest import (EVENTS_HEADER, NOW, OVERRIDES_HEADER, ROOT, by_id, fx, load_doc, load_events,
                      padding, row, run_all, serve_aicf, serve_chessfee, serve_chessresults,
                      web, write_manual)  # noqa: F401

CR = "https://chess-results.com/"
ONLY = lambda *names: {n: (n in names) for n in be.SOURCE_MODULES}  # noqa: E731


def files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*"))
            if p.is_file() and "manual" not in p.relative_to(folder).parts}


# ---- the 12-hour rule ---------------------------------------------------------------
def test_due_time_is_12_hours_after_the_last_success():
    assert be.fetch_due_at(None, 12) is None  # never fetched: due right away
    assert be.fetch_due_at("2026-11-25T00:27:00+05:30", None) is None  # no rule (force)
    assert be.fetch_due_at("2026-11-25T00:27:00+05:30", 12).isoformat() == "2026-11-25T12:27:00+05:30"
    assert be.FETCH_INTERVAL_HOURS == 12


@pytest.mark.parametrize("hours_later, fetched", [(11.9, False), (12, True), (30, True)])
def test_source_is_due_only_after_12_hours(web, data_dir, hours_later, fetched):
    serve_chessfee(web)
    run_all(data_dir, config=ONLY("chessfee"))
    web.calls.clear()
    report = run_all(data_dir, config=ONLY("chessfee"), min_hours_between_fetches=12,
                     now=NOW + timedelta(hours=hours_later))
    assert bool(web.calls) is fetched
    assert report["per_source"]["chessfee"]["due"] is fetched


def test_each_source_has_its_own_clock(web, data_dir):
    serve_aicf(web, [row("Cup", "400001")])
    serve_chessfee(web)
    run_all(data_dir, config=ONLY("aicf"))
    run_all(data_dir, config=ONLY("chessfee"), now=NOW + timedelta(hours=6))
    web.calls.clear()
    report = run_all(data_dir, config=ONLY("aicf", "chessfee"), min_hours_between_fetches=12,
                     now=NOW + timedelta(hours=13))
    assert report["per_source"]["aicf"]["due"] is True and report["per_source"]["chessfee"]["due"] is False
    assert web.urls("aicf") and not web.urls("chessfee")


def test_command_line_uses_12_hours_and_force_ignores_it(monkeypatch, data_dir):
    seen = []

    def fake_run(folder, **kwargs):
        seen.append(kwargs["min_hours_between_fetches"])
        raise be.BuildError("stop here")

    monkeypatch.setattr(be, "run", fake_run)
    be.main(["--data-dir", str(data_dir)])
    be.main(["--data-dir", str(data_dir), "--force"])
    assert seen == [12, None]


def test_a_failed_fetch_is_retried_on_the_next_run_not_12_hours_later(web, data_dir):
    serve_chessfee(web)
    run_all(data_dir, config=ONLY("chessfee"))
    web.add("https://www.chessfee.com/tournament_ongoing.php", "down", status=500)
    with pytest.raises(be.SourceError):  # the only source failed
        run_all(data_dir, config=ONLY("chessfee"), min_hours_between_fetches=12, now=NOW + timedelta(hours=13))
    serve_chessfee(web)
    web.calls.clear()
    run_all(data_dir, config=ONLY("chessfee"), min_hours_between_fetches=12, now=NOW + timedelta(hours=16))
    assert web.calls  # last success was 16 h ago: still due


# ---- the quick no-op run ------------------------------------------------------------
def test_a_run_with_nothing_due_fetches_nothing_and_has_no_real_changes(web, data_dir, tmp_path):
    serve_aicf(web, [row("Cup", "400001")])
    serve_chessfee(web)
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("aicf", "chessfee", "chessresults_ind"))
    before = files(data_dir)
    web.calls.clear()
    later = NOW + timedelta(hours=3)
    report = run_all(data_dir, config=ONLY("aicf", "chessfee", "chessresults_ind"),
                     min_hours_between_fetches=12, now=later)
    assert web.calls == [] and report["fetched_any"] is False
    assert report["only_timestamps_changed"] is True  # so the workflow does not commit
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert meta["last_run_at"] == later.isoformat()  # the robot is visibly alive
    assert meta["sources"]["chessfee"]["status"] == "ok" and meta["sources"]["chessfee"]["message"] is None
    assert meta["sources"]["chessfee"]["next_due"] == (NOW + timedelta(hours=12)).isoformat()
    after = files(data_dir)
    assert after["sources/chessfee.json"] == before["sources/chessfee.json"]
    strip = lambda b: re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", "WHEN", b.decode())  # noqa: E731
    assert strip(after["events.json"]) == strip(before["events.json"])
    text = daily.summary_markdown(report)
    assert "No source was due" in text and "no, next due" in text


def test_no_op_run_through_the_command_line_says_no_real_changes(web, data_dir, tmp_path, monkeypatch):
    serve_aicf(web, padding(150))
    monkeypatch.setattr(be, "load_config", lambda path=be.CONFIG_PATH, warnings=None: ONLY("aicf"))
    out = tmp_path / "out.txt"
    assert be.main(["--data-dir", str(data_dir), "--github-output", str(out)]) == 0
    web.calls.clear()
    assert be.main(["--data-dir", str(data_dir), "--github-output", str(out)]) == 0
    assert web.calls == []
    assert out.read_text().splitlines()[2] == "real_changes=false"


def test_next_due_is_now_for_a_source_that_never_succeeded_and_null_when_off(web, data_dir):
    web.add("https://www.chessfee.com/tournament_ongoing.php", "down", status=500)
    serve_aicf(web, [row("Cup", "400001")])
    run_all(data_dir, config=ONLY("aicf", "chessfee"))
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert meta["sources"]["chessfee"]["next_due"] == NOW.isoformat()
    assert meta["sources"]["chessbase_calendar"]["next_due"] is None


# ---- the stale-data alarm -----------------------------------------------------------
def stamp(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def meta(**ages):
    return {"sources": {n: {"enabled": True, "status": "ok", "last_success": stamp(h) if h is not None else None}
                        for n, h in ages.items()}}


def test_stale_alarm_at_31_hours_but_not_29():
    assert heartbeat.stale_data(meta(aicf=29, chessfee=40), NOW) is None  # the newest is 29 h old
    text = heartbeat.stale_data(meta(aicf=31, chessfee=40), NOW)
    assert text.startswith("Stale data: the newest successful fetch of any source was 31.0 hours ago")


def test_stale_alarm_ignores_switched_off_sources_and_catches_never_fetched():
    m = meta(aicf=50, chessfee=1)
    m["sources"]["chessfee"]["enabled"] = False
    assert "50.0 hours ago" in heartbeat.stale_data(m, NOW)
    assert "ever been fetched successfully" in heartbeat.stale_data(meta(aicf=None), NOW)


def test_heartbeat_command_fails_on_stale_data_and_keeps_the_7_day_rule(tmp_path, capsys):
    now = datetime.now(be.IST)
    fresh = {"sources": {"aicf": {"enabled": True, "last_success": (now - timedelta(hours=2)).isoformat()},
                         "chessfee": {"enabled": True, "last_success": (now - timedelta(days=8)).isoformat()}}}
    (tmp_path / "meta.json").write_text(json.dumps(fresh), encoding="utf-8")
    assert heartbeat.main(["--data-dir", str(tmp_path)]) == 1  # chessfee silent 8 days
    assert "Source 'chessfee'" in capsys.readouterr().err
    old = {"sources": {"aicf": {"enabled": True, "last_success": (now - timedelta(hours=31)).isoformat()}}}
    (tmp_path / "meta.json").write_text(json.dumps(old), encoding="utf-8")
    assert heartbeat.main(["--data-dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "Stale data" in captured.err and "::error title=Stale data::" in captured.out
    ok = {"sources": {"aicf": {"enabled": True, "last_success": (now - timedelta(hours=29)).isoformat(),
                               "last_error": {"at": (now - timedelta(hours=1)).isoformat()}}}}
    (tmp_path / "meta.json").write_text(json.dumps(ok), encoding="utf-8")
    assert heartbeat.main(["--data-dir", str(tmp_path)]) == 0


# ---- results links ------------------------------------------------------------------
def test_chessresults_events_get_their_tournament_page_as_results_url(web, data_dir):
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("chessresults_ind"))
    for event in load_events(data_dir):
        assert event["results_url"] == event["source_url"]
        assert re.fullmatch(r"https://chess-results\.com/tnr\d+\.aspx\?lan=1", event["results_url"])


def test_results_url_is_kept_after_the_event_ends_and_leaves_the_list(web, data_dir):
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("chessresults_ind"))
    web.add(CR + "fed.aspx?lan=1&fed=IND", lambda data: fx("chessresults_fed_ind.html"), method="POST")
    run_all(data_dir, config=ONLY("chessresults_ind"), now=NOW + timedelta(days=30))
    event = by_id(data_dir)["chessresults_ind-1539989"]
    assert event["gone_from_source"] is True
    assert event["results_url"] == CR + "tnr1539989.aspx?lan=1"


def test_other_sources_have_no_results_url_yet(web, data_dir):
    serve_aicf(web, [row("Cup", "400001")])
    serve_chessfee(web)
    run_all(data_dir, config=ONLY("aicf", "chessfee"))
    assert all(e["results_url"] is None for e in load_events(data_dir))


def test_joined_event_takes_the_results_link_from_chess_results(web, data_dir):
    serve_aicf(web, [row("AICF Rapid Cup 2026", "473001", start="05-12-2026", end="06-12-2026")])
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("aicf", "chessresults_ind"))
    assert by_id(data_dir)["aicf-473001"]["results_url"] == CR + "tnr1550001.aspx?lan=1"


# ---- schema 4 -----------------------------------------------------------------------
def test_schema_4_and_results_url_sits_after_register_url():
    keys = list(be.EVENT_KEYS)
    assert be.SCHEMA_VERSION >= 4 and keys.index("results_url") == keys.index("register_url") + 1


def test_schema_3_data_is_migrated(web, data_dir):
    serve_chessresults(web)
    run_all(data_dir, config=ONLY("chessresults_ind"))
    # turn the stored files back into schema 3 (no results_url anywhere)
    for path in [data_dir / "events.json", data_dir / "sources" / "chessresults_ind.json"]:
        doc = json.loads(path.read_text("utf-8"))
        for event in doc["events"]:
            del event["results_url"]
        if "schema_version" in doc:
            doc["schema_version"] = 3
        path.write_text(json.dumps(doc), encoding="utf-8")
    report = run_all(data_dir, config=ONLY("chessresults_ind"), min_hours_between_fetches=12,
                     now=NOW + timedelta(hours=1))  # not due: only the stored data is used
    assert report["fetched_any"] is False
    doc = load_doc(data_dir)
    assert doc["schema_version"] == be.SCHEMA_VERSION
    assert all(e["results_url"] == e["source_url"] for e in doc["events"])
    assert report["only_timestamps_changed"] is False  # the upgrade is a real change to commit


def test_committed_data_reads_cleanly_as_schema_4():
    doc = json.loads((ROOT / "data" / "events.json").read_text("utf-8"))
    for event in doc["events"]:
        new = be.canonical(event)
        assert list(new) == list(be.EVENT_KEYS)
        if event["source"] == "chessresults_ind":
            assert new["results_url"] == event["source_url"]


# ---- manual links -------------------------------------------------------------------
def test_override_sets_register_and_results_links_and_wins_over_scraped(web, data_dir):
    serve_chessresults(web)
    write_manual(data_dir, OVERRIDES_HEADER
                 + "chessresults_ind-1528935,,,,,,,,https://example.org/register,https://example.org/results\n"
                 + "aicf-none,,,,,,,,,\n", "overrides.csv")
    report = run_all(data_dir, config=ONLY("chessresults_ind"))
    event = by_id(data_dir)["chessresults_ind-1528935"]
    assert event["register_url"] == "https://example.org/register"  # beat the Circle Chess link
    assert event["results_url"] == "https://example.org/results"    # beat the tournament page
    assert event["overridden"]["register_url"] == "https://circlechess.com/registration?id=61557"
    assert any("aicf-none" in w for w in report["warnings"])


def test_removing_the_override_brings_back_the_scraped_links(web, data_dir):
    serve_chessresults(web)
    write_manual(data_dir, OVERRIDES_HEADER
                 + "chessresults_ind-1528935,,,,,,,,,https://example.org/results\n", "overrides.csv")
    run_all(data_dir, config=ONLY("chessresults_ind"))
    write_manual(data_dir, OVERRIDES_HEADER, "overrides.csv")
    run_all(data_dir, config=ONLY("chessresults_ind"), now=NOW + timedelta(hours=1),
            min_hours_between_fetches=12)
    assert by_id(data_dir)["chessresults_ind-1528935"]["results_url"] == CR + "tnr1528935.aspx?lan=1"


@pytest.mark.parametrize("column, value", [("register_url", "www.example.org/x"),
                                           ("results_url", "ftp://example.org/r"),
                                           ("results_url", "results page")])
def test_bad_override_link_stops_with_the_line_number(web, data_dir, column, value):
    serve_aicf(web, [row("Cup", "400001")])
    cells = {"register_url": "", "results_url": ""}
    cells[column] = value
    write_manual(data_dir, OVERRIDES_HEADER + "aicf-400001,,,,,,,,"
                 + f"{cells['register_url']},{cells['results_url']}\n", "overrides.csv")
    with pytest.raises(be.DataFileError) as caught:
        run_all(data_dir, config=ONLY("aicf"))
    assert (f"data/manual/overrides.csv line 2: {column} '{value}' is not a full web address"
            in str(caught.value))
    assert not (data_dir / "events.json").exists()


def test_manual_event_accepts_a_results_link(web, data_dir):
    serve_aicf(web, [row("Cup", "400001")])
    write_manual(data_dir, EVENTS_HEADER + "club-1,Club Cup,05-01-2027,,Goa,,,,,,,,https://example.org/res\n")
    run_all(data_dir, config=ONLY("aicf"))
    assert by_id(data_dir)["club-1"]["results_url"] == "https://example.org/res"
    write_manual(data_dir, EVENTS_HEADER + "club-1,Club Cup,05-01-2027,,Goa,,,,,,,,example.org/res\n")
    with pytest.raises(be.DataFileError, match="events.csv line 2: results_url 'example.org/res'"):
        run_all(data_dir, config=ONLY("aicf"))


def test_the_committed_manual_files_have_the_new_headers():
    events = (ROOT / "data" / "manual" / "events.csv").read_text("utf-8").splitlines()[0]
    overrides = (ROOT / "data" / "manual" / "overrides.csv").read_text("utf-8").splitlines()[0]
    assert events == ",".join(be.EVENTS_CSV_COLUMNS) and events.endswith(",results_url")
    assert "country" in events
    assert overrides == ",".join(be.OVERRIDES_CSV_COLUMNS) and overrides.endswith(",register_url,results_url,fide_rated,format,age,registration_deadline")


# ---- the workflow file --------------------------------------------------------------
WORKFLOW = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")


def test_workflow_runs_every_three_hours_at_minute_17_and_has_a_force_box():
    assert 'cron: "17 */3 * * *"' in WORKFLOW and WORKFLOW.count("cron:") == 1
    assert re.search(r"workflow_dispatch:\n    inputs:\n      force:\n        description: .+\n"
                     r"        type: boolean\n        default: false\n", WORKFLOW)
    assert "cancel-in-progress: false" in WORKFLOW


def test_force_is_only_for_a_manual_run():
    assert "FORCE: ${{ github.event_name == 'workflow_dispatch' && inputs.force == true }}" in WORKFLOW
    assert 'if [ "$FORCE" = "true" ]; then args+=(--force); fi' in WORKFLOW
    assert WORKFLOW.count("--force") == 1  # nowhere else, never for the schedule
