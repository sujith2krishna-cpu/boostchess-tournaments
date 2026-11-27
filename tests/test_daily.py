"""The daily run: commit message, job summary, heartbeat rule, publish check, workflow file."""
import json
import re
from datetime import date, timedelta

import pytest
import requests

import build_events as be
import daily
import eventlib
import heartbeat
import quality
import verify_published as vp
from conftest import (ALL_SOURCES_ON, NOW, ROOT, build, fx, padding, row, run_all, serve_aicf, serve_chessbase,
                      serve_chessfee, serve_chessresults, serve_kca, serve_ksca, serve_tnsca, web)  # noqa: F401
from sources import chessbase_calendar as cb_source

NEXT_DAY = NOW + timedelta(days=1)


def info(status="ok", found=10, blocked=False, message=None):
    return {"status": status, "found": found, "blocked": blocked, "message": message, "requests": 5,
            "by_status": {"ongoing": 1, "upcoming": 7, "past": 2}, "with_register_url": 3}


def fake_report(**overrides):
    per_source = {n: info() for n in daily.SOURCE_ORDER}
    per_source.update(overrides)
    return {"today": "2026-11-25", "changes": {"new": 3, "changed": 2, "gone": 1},
            "per_source": per_source, "possible_duplicates": 4,
            "status_counts": {"ongoing": 5, "upcoming": 30, "past": 100},
            "meta": {"total": 135, "suspect_dates_count": 9, "missing_state_count": 7},
            "warnings": []}


# ---- the commit message --------------------------------------------------
def test_commit_message_all_sources_ok():
    assert daily.commit_message(fake_report()) == (
        "data: 2026-11-25 (+3 new, 2 changed; sources ok: aicf, kca, tnsca, ksca, chessfee, "
        "chessresults_ind, chessbase_calendar)")


def test_commit_message_names_failed_sources():
    report = fake_report(chessfee=info("failed", message="HTTP 500"))
    assert daily.commit_message(report) == (
        "data: 2026-11-25 (+3 new, 2 changed; sources ok: aicf, kca, tnsca, ksca, chessresults_ind, "
        "chessbase_calendar; failed: chessfee)")


def test_commit_message_counts_a_blocked_source_as_failed_but_not_one_already_fetched_today():
    report = fake_report(aicf=info("skipped", message="already fetched today"),
                         chessbase_calendar=info("skipped", blocked=True, message="robots.txt"))
    message = daily.commit_message(report)
    assert "sources ok: aicf, kca, tnsca, ksca, chessfee, chessresults_ind;" in message and "failed: chessbase_calendar" in message


def test_commit_message_is_one_short_line():
    message = daily.commit_message(fake_report(chessfee=info("failed")))
    assert "\n" not in message and len(message) < 150 and message.startswith("data: ")


def test_commit_message_from_a_real_run(web, data_dir):
    serve_aicf(web, [row("Plain AICF Open", "400001")])
    serve_kca(web)
    serve_tnsca(web)
    serve_ksca(web)
    serve_chessfee(web)
    serve_chessresults(web)
    serve_chessbase(web)
    for html in ("chessbase_calendar.html", "chessbase_calendar_2027.html"):
        for raw in cb_source.parse_events(fx(html)):
            web.add("https://chessbase.in/chess-calendar/event/" + raw["slug"], fx("chessbase_event.html"))
    first = run_all(data_dir)
    assert first["changes"] == {"new": 211, "changed": 0, "gone": 0}  # 21 + 22 KCA + 151 TNSCA + 17 KSCA records
    assert daily.commit_message(first) == (
        "data: 2026-11-24 (+211 new, 0 changed; sources ok: aicf, kca, tnsca, ksca, chessfee, "
        "chessresults_ind, chessbase_calendar)")
    # next day: one AICF event is edited, chessfee fails
    serve_aicf(web, [row("Plain AICF Open", "400001", end="13-12-2026"), row("Another", "400002")])
    web.add("https://www.chessfee.com/tournament_ongoing.php", "down", status=500)
    second = run_all(data_dir, now=NEXT_DAY)
    assert second["changes"] == {"new": 1, "changed": 1, "gone": 0}
    assert daily.commit_message(second) == (
        "data: 2026-11-25 (+1 new, 1 changed; sources ok: aicf, kca, tnsca, ksca, chessresults_ind, "
        "chessbase_calendar; failed: chessfee)")


def test_changes_ignore_last_seen_and_count_newly_gone():
    old = [be.canonical({"id": "a", "source": "aicf", "name": "A", "first_seen": "d", "last_seen": "d1"}),
           be.canonical({"id": "b", "source": "aicf", "name": "B", "first_seen": "d", "last_seen": "d1"})]
    new = [dict(old[0], last_seen="d2"), dict(old[1], gone_from_source=True),
           be.canonical({"id": "c", "source": "aicf", "name": "C", "first_seen": "d", "last_seen": "d2"})]
    assert be.count_changes(old, new) == {"new": 1, "changed": 1, "gone": 1}
    assert be.count_changes([], new) == {"new": 3, "changed": 0, "gone": 0}


# ---- the job summary ------------------------------------------------------
def test_summary_has_counts_per_source_and_the_problems():
    text = daily.summary_markdown(fake_report(chessfee=info("failed", message="Could not fetch: HTTP 500")))
    assert "| aicf | ok | yes | 10 | 1 | 7 | 2 | 3 | 5 |" in text
    assert "| chessfee | failed |" in text
    assert "### Problems" in text and "**chessfee**: Could not fetch: HTTP 500" in text
    assert "ongoing 5, upcoming 30, past 100" in text and "+3 new, 2 changed" in text


def test_summary_when_everything_is_fine():
    assert "No source problems." in daily.summary_markdown(fake_report())


def test_failure_summary_and_warning_lines(monkeypatch):
    report = fake_report(chessbase_calendar=info("skipped", blocked=True, message="robots.txt does not allow /x"))
    assert daily.annotations(report) == ["::warning title=chessbase_calendar problem::robots.txt does not allow /x"]
    assert "FAILED" in daily.failure_markdown("boom") and "boom" in daily.failure_markdown("boom")


def test_summary_file_is_appended(tmp_path):
    path = tmp_path / "summary.md"
    daily.write_summary(str(path), "one\n")
    daily.write_summary(str(path), "two\n")
    daily.write_summary(None, "ignored")
    assert path.read_text() == "one\ntwo\n"


def test_main_writes_summary_commit_message_and_warnings(web, data_dir, tmp_path, monkeypatch, capsys):
    serve_aicf(web, padding(150))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(be, "load_config", lambda path=be.CONFIG_PATH, warnings=None:
                        {**{n: False for n in be.SOURCE_MODULES}, "aicf": True, "chessfee": True})
    web.add("https://www.chessfee.com/tournament_ongoing.php", "down", status=500)
    out, summary = tmp_path / "out.txt", tmp_path / "summary.md"
    code = be.main(["--data-dir", str(data_dir), "--github-output", str(out), "--summary-file", str(summary)])
    assert code == 0  # chessfee failed, AICF worked: the run still succeeds
    lines = out.read_text().splitlines()
    assert lines[0] == "real_changes=true" and lines[1].startswith("commit_message=data: ")
    assert "failed: chessfee" in lines[1]
    assert "### Problems" in summary.read_text() and "chessfee" in summary.read_text()
    assert "::warning title=chessfee problem::" in capsys.readouterr().out


def test_main_fails_and_says_why_when_every_source_fails(web, data_dir, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(be, "load_config", lambda path=be.CONFIG_PATH, warnings=None:
                        {**{n: False for n in be.SOURCE_MODULES}, "aicf": True})
    web.add("https://aicf.in/all-events/", "down", status=500)
    summary = tmp_path / "summary.md"
    assert be.main(["--data-dir", str(data_dir), "--summary-file", str(summary)]) == 2
    assert "run FAILED" in summary.read_text()
    assert "::error title=Tournament data run failed::" in capsys.readouterr().out
    assert not (data_dir / "events.json").exists()


# ---- the heartbeat (3 days per source) -------------------------------------------------
def meta_with(**sources):
    return {"sources": {name: {"enabled": True, "status": "ok", "last_success": stamp}
                        for name, stamp in sources.items()}}


TODAY = date(2026, 11, 25)


def test_a_source_silent_for_three_days_is_stale_but_two_days_is_fine():
    assert heartbeat.DEFAULT_DAYS == 3
    meta = meta_with(aicf="2026-11-25T03:10:00+05:30", chessfee="2026-11-23T03:10:00+05:30",
                     chessresults_ind="2026-11-22T03:10:00+05:30", chessbase_calendar="2026-11-01T03:10:00+05:30")
    stale = heartbeat.stale_sources(meta, TODAY)
    assert [(s["source"], s["days"]) for s in stale] == [("chessresults_ind", 3), ("chessbase_calendar", 24)]


def test_days_are_counted_in_indian_dates():
    # 22:00 UTC on the 21st is already the 22nd in India: 3 days before the 25th
    meta = meta_with(chessfee="2026-11-21T22:00:00+00:00")
    assert heartbeat.stale_sources(meta, TODAY)[0]["days"] == 3
    # 19:00 UTC on the 22nd is 00:30 on the 23rd in India: only 2 days, still fine
    assert heartbeat.stale_sources(meta_with(chessfee="2026-11-22T19:00:00+00:00"), TODAY) == []


def test_a_source_that_never_worked_is_stale_and_a_switched_off_one_is_ignored():
    meta = {"sources": {"chessfee": {"enabled": True, "status": "failed", "last_success": None},
                        "aicf": {"enabled": False, "status": "disabled", "last_success": None}}}
    stale = heartbeat.stale_sources(meta, TODAY)
    assert [s["source"] for s in stale] == ["chessfee"] and stale[0]["days"] is None
    assert "never been fetched successfully" in heartbeat.message(stale)


def test_message_names_the_source_and_the_days():
    text = heartbeat.message(heartbeat.stale_sources(meta_with(chessfee="2026-11-10T03:10:00+05:30"), TODAY))
    assert text.startswith("Source 'chessfee' has had no successful fetch for 15 days")
    assert "last_error" in text


def test_heartbeat_command_exit_codes(tmp_path, capsys):
    from datetime import datetime
    now = datetime.now(be.IST)
    good = meta_with(aicf=now.isoformat(), chessfee=(now - timedelta(days=2)).isoformat())
    # chessfee failed an hour ago: tried (no missed fetch), and 2 days is not yet "gone quiet"
    good["sources"]["chessfee"]["last_error"] = {"at": (now - timedelta(hours=1)).isoformat(), "message": "x"}
    (tmp_path / "meta.json").write_text(json.dumps(good), encoding="utf-8")
    assert heartbeat.main(["--data-dir", str(tmp_path)]) == 0
    assert "Heartbeat ok" in capsys.readouterr().out
    bad = meta_with(aicf=now.isoformat(), chessfee=(now - timedelta(days=9)).isoformat())
    (tmp_path / "meta.json").write_text(json.dumps(bad), encoding="utf-8")
    summary = tmp_path / "summary.md"
    assert heartbeat.main(["--data-dir", str(tmp_path), "--summary-file", str(summary)]) == 1
    captured = capsys.readouterr()
    assert "Source 'chessfee' has had no successful fetch for 9 days" in captured.err
    assert "::error title=Source gone quiet::chessfee" in captured.out
    assert "Heartbeat FAILED" in summary.read_text()
    assert heartbeat.main(["--data-dir", str(tmp_path / "nowhere")]) == 1


def test_meta_from_a_real_run_passes_then_fails_after_three_days_of_failures(web, data_dir):
    serve_aicf(web, [row("Plain AICF Open", "400001")])
    config = {**{n: False for n in be.SOURCE_MODULES}, "aicf": True}
    be.run(data_dir, config=config, now=NOW, min_rows=1)
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert heartbeat.stale_sources(meta, NOW.date()) == []
    web.add("https://aicf.in/all-events/", "down", status=500)
    # days of failing: the source keeps its old data but last_success is stuck
    for day in range(1, 4):
        with pytest.raises(be.SourceError):
            be.run(data_dir, config=config, now=NOW + timedelta(days=day), min_rows=1)
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    assert heartbeat.stale_sources(meta, (NOW + timedelta(days=2)).date()) == []
    assert heartbeat.stale_sources(meta, (NOW + timedelta(days=3)).date())[0]["source"] == "aicf"


def test_partial_failures_move_the_heartbeat_forward_only_for_the_failing_source(web, data_dir):
    serve_aicf(web, [row("Plain AICF Open", "400001")])
    serve_chessfee(web)
    config = {**{n: False for n in be.SOURCE_MODULES}, "aicf": True, "chessfee": True}
    be.run(data_dir, config=config, now=NOW, min_rows=1)
    web.add("https://www.chessfee.com/tournament_ongoing.php", "down", status=500)
    for day in range(1, 9):
        be.run(data_dir, config=config, now=NOW + timedelta(days=day), min_rows=1)
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    stale = heartbeat.stale_sources(meta, (NOW + timedelta(days=8)).date())
    assert [(s["source"], s["days"]) for s in stale] == [("chessfee", 8)]


# ---- checking the published files ----------------------------------------
GOOD_EVENTS = json.dumps({"schema_version": be.SCHEMA_VERSION, "generated_at": "t", "events": [{"id": "x"}]})
CORS = {"content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*"}
CSV_CORS = {"content-type": "text/csv; charset=utf-8", "access-control-allow-origin": "*"}


def quality_json(missing=1, duplicates=1, **change):
    data = {"generated_at": "t", "target": {"fully_known_pct": 95.0, "now_pct": 20.0}, "overall": {},
            "sources": {}, "review": {"missing": missing, "possible_duplicates": duplicates}, **change}
    return json.dumps(data)


def review_csv(*kinds):
    lines = [",".join(quality.REVIEW_COLUMNS)]
    lines += [kind + "," * (len(quality.REVIEW_COLUMNS) - 1) for kind in kinds]
    return "\n".join(lines) + "\n"


GOOD_QUALITY = quality_json()
GOOD_REVIEW = review_csv("missing", "possible_duplicate")


def getter(events=(200, CORS, GOOD_EVENTS), meta=(200, CORS, "{}"), quality_file=(200, CORS, GOOD_QUALITY),
           review=(200, CSV_CORS, GOOD_REVIEW)):
    answers = {"https://site.test/repo/events.json": events, "https://site.test/repo/meta.json": meta,
               "https://site.test/repo/quality.json": quality_file, "https://site.test/repo/review.csv": review}
    return lambda url: answers[url]


def test_published_files_that_are_right_pass_and_the_headers_are_shown():
    ok, lines = vp.verify("https://site.test/repo", getter(), sleep=lambda s: None)
    text = "\n".join(lines)
    assert ok and "access-control-allow-origin: *" in text and "content-type: application/json" in text
    assert f"schema_version {be.SCHEMA_VERSION}, 1 events" in text
    assert "quality.json: HTTP 200" in text and "20.0% fully known (target 95.0%)" in text
    assert "review.csv: HTTP 200" in text and "1 to complete, 1 possible duplicates" in text
    assert "content-type: text/csv" in text


@pytest.mark.parametrize("changes, expected", [
    ({"quality_file": (404, {}, "")}, "quality.json: HTTP 404"),
    ({"quality_file": (200, CORS, "{ not json")}, "quality.json: not valid JSON"),
    ({"quality_file": (200, CORS, json.dumps({"target": {}, "overall": {}}))}, "quality.json: has no sources, review"),
    ({"quality_file": (200, {}, GOOD_QUALITY)}, "quality.json: Access-Control-Allow-Origin is None"),
    ({"review": (404, {}, "")}, "review.csv: HTTP 404"),
    ({"review": (200, CSV_CORS, "id,name\nx,y\n")}, "review.csv: the first line is not the review columns"),
    ({"review": (200, CSV_CORS, "")}, "review.csv: the first line is not the review columns"),
    ({"review": (200, CSV_CORS, review_csv("missing", "something_else"))}, "review.csv: line 3 is not a review line"),
    ({"review": (200, CSV_CORS, GOOD_REVIEW + "missing,too,short\n")}, "review.csv: line 4 is not a review line"),
    ({"review": (200, {"content-type": "text/csv"}, GOOD_REVIEW)}, "review.csv: Access-Control-Allow-Origin is None"),
    ({"review": (200, CSV_CORS, review_csv("missing", "missing", "possible_duplicate"))},
     "review.csv has 2 to complete and 1 possible duplicates, but quality.json says 1 and 1"),
    ({"quality_file": (200, CORS, quality_json(missing=0, duplicates=0))},
     "review.csv has 1 to complete and 1 possible duplicates, but quality.json says 0 and 0"),
])
def test_a_wrong_quality_report_or_review_list_fails_with_a_reason(changes, expected):
    ok, lines = vp.verify("https://site.test/repo/", getter(**changes), attempts=2, sleep=lambda s: None)
    assert not ok and expected in "\n".join(lines)


def test_an_empty_review_list_with_matching_counts_passes():
    files = getter(quality_file=(200, CORS, quality_json(missing=0, duplicates=0)), review=(200, CSV_CORS, review_csv()))
    ok, lines = vp.verify("https://site.test/repo/", files, sleep=lambda s: None)
    assert ok and "0 to complete, 0 possible duplicates" in "\n".join(lines)


def test_the_check_reads_the_review_list_the_build_writes():
    def event(eid, name):
        return eventlib.canonical({"id": eid, "name": name, "start": "2026-12-01", "end": "2026-12-01",
                                   "first_seen": "2026-11-01", "last_seen": "2026-11-25", "source": "aicf"})
    first, second = event("aicf-1", "Open, with a comma"), event("aicf-2", 'A "quoted" Open')
    second["flags"]["possible_duplicate_of"] = "aicf-1"
    rows = quality.review_rows([first, second], date(2026, 11, 25))
    problems, _, read = vp.check_file("review.csv", 200, CSV_CORS, quality.review_csv(rows).decode("utf-8"))
    assert problems == [] and read == quality.review_counts(rows) == {"missing": 2, "dates_disagree": 0, "possible_duplicates": 1}


@pytest.mark.parametrize("events, expected", [
    ((200, CORS, "{ not json"), "not valid JSON"),
    ((200, CORS, json.dumps({"schema_version": 2, "events": [{"id": "x"}]})), "schema_version is 2"),
    ((200, {"content-type": "application/json"}, GOOD_EVENTS), "Access-Control-Allow-Origin is None"),
    ((404, {}, "nope"), "HTTP 404"),
    ((200, CORS, json.dumps({"schema_version": be.SCHEMA_VERSION, "events": []})), "has no events"),
])
def test_published_files_with_a_problem_fail_with_a_reason(events, expected):
    sleeps = []
    ok, lines = vp.verify("https://site.test/repo/", getter(events=events), attempts=3, sleep=sleeps.append)
    assert not ok and expected in "\n".join(lines) and len(sleeps) == 2  # it retried


def test_a_fresh_deployment_that_is_not_there_yet_is_retried():
    calls = []

    def slow(url):
        calls.append(url)
        if len(calls) <= 2:
            return 404, {}, ""
        return getter()(url)

    ok, _ = vp.verify("https://site.test/repo/", slow, attempts=4, sleep=lambda s: None)
    assert ok


def test_network_trouble_while_checking_is_a_failure_not_a_crash():
    def broken(url):
        raise requests.ConnectionError("down")

    ok, lines = vp.verify("https://site.test/repo/", broken, attempts=2, sleep=lambda s: None)
    assert not ok and "could not be fetched" in "\n".join(lines)


def test_verify_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(vp, "fetch", getter())
    monkeypatch.setattr(vp.time, "sleep", lambda s: None)
    summary = tmp_path / "s.md"
    assert vp.main(["https://site.test/repo/", "--summary-file", str(summary)]) == 0
    assert "Published data check: ok" in summary.read_text()
    monkeypatch.setattr(vp, "fetch", getter(events=(200, {}, "{")))
    assert vp.main(["https://site.test/repo/"]) == 1


# ---- the workflow file itself --------------------------------------------
WORKFLOW = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")


def step_position(marker):
    assert marker in WORKFLOW, marker
    return WORKFLOW.index(marker)


def test_workflow_triggers_and_concurrency():
    assert re.search(r'cron: "17 \*/3 \* \* \*"', WORKFLOW)  # every 3 hours at minute 17
    assert "workflow_dispatch:" in WORKFLOW
    assert re.search(r"concurrency:\n  group: \S+\n  cancel-in-progress: false", WORKFLOW)


def test_workflow_tests_run_before_anything_is_fetched_or_committed():
    assert step_position("python -m pytest -q") < step_position("scripts/build_events.py") \
        < step_position("git commit") < step_position("scripts/heartbeat.py")
    assert step_position("python -m pip install -r requirements.txt -r requirements-dev.txt") \
        < step_position("python -m pytest -q")


def test_workflow_commits_only_data_and_only_when_something_really_changed():
    assert "if: steps.build.outputs.real_changes == 'true'" in WORKFLOW
    assert WORKFLOW.count("git add ") == 1 and "git add data\n" in WORKFLOW
    assert "git diff --cached --name-only | grep -qv '^data/'" in WORKFLOW
    assert "push --force" not in WORKFLOW and "push -f" not in WORKFLOW and "-f origin" not in WORKFLOW
    assert 'git config user.name "github-actions[bot]"' in WORKFLOW
    assert "--github-output \"$GITHUB_OUTPUT\"" in WORKFLOW and "--summary-file \"$GITHUB_STEP_SUMMARY\"" in WORKFLOW


def test_workflow_has_no_secrets_and_least_permissions():
    assert "secrets." not in WORKFLOW and "personal" not in WORKFLOW.lower()
    assert "GH_TOKEN" not in WORKFLOW and "PAT" not in re.findall(r"\b[A-Z_]{3,}\b", WORKFLOW)
    top = WORKFLOW.split("jobs:")[0]
    assert re.search(r"^permissions:\n  contents: write\n", top, re.M)
    assert WORKFLOW.count("id-token: write") == 1  # only the deploy job
    assert "contents: read" in WORKFLOW.split("deploy:")[1]


def test_workflow_uses_pinned_python_and_the_official_pages_actions():
    assert 'python-version: "3.13"' in WORKFLOW
    for action in ("actions/checkout", "actions/setup-python", "actions/configure-pages",
                   "actions/upload-pages-artifact", "actions/deploy-pages"):
        assert re.search(rf"uses: {action}@v\d+", WORKFLOW), action
    assert re.search(r"upload-pages-artifact@v\d+\n        with:\n          path: data\n", WORKFLOW)
    assert "name: github-pages" in WORKFLOW
    assert "verify_published.py" in WORKFLOW


def test_the_data_is_published_even_when_nothing_was_committed_and_the_heartbeat_comes_last():
    upload = WORKFLOW[step_position("id: upload"):]
    assert "real_changes" not in upload.split("heartbeat")[0]  # upload is not conditional on a commit
    assert WORKFLOW.index("scripts/heartbeat.py") > WORKFLOW.index("id: upload")
    assert "needs.build.outputs.published == 'true'" in WORKFLOW and "!cancelled()" in WORKFLOW
