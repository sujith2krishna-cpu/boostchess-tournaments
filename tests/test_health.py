"""CR-32: the weekly data health report and the urgent data alerts (no network).

The sample data in tests/fixtures/health/ is made by hand (said so inside the files)."""
import copy
import json
import re
from datetime import datetime, timedelta

import pytest

import build_events as be
import health
from conftest import KSCA, ROOT, run_all, serve_ksca
from eventlib import IST

FIX = ROOT / "tests" / "fixtures" / "health"
META = json.loads((FIX / "meta.json").read_text("utf-8"))
EVENTS = json.loads((FIX / "events.json").read_text("utf-8"))["events"]
NOW = datetime(2026, 11, 30, 7, 0, tzinfo=IST)  # a Monday morning
GOOD_RUNS = [{"status": "completed", "conclusion": "success", "created_at": "2026-11-30T01:10:00Z"}]


def report(meta=META, events=EVENTS, last_week=None, runs=GOOD_RUNS, now=NOW):
    return health.weekly_report(now, meta, events, last_week, runs)


# ---- the weekly report -----------------------------------------------------------------
def test_report_has_warnings_first_then_sources_totals_and_decisions():
    text = report()
    warn, sources, totals, decide = (text.index(s) for s in
                                     ("**Warnings**", "### Sources", "### Totals", "### Needs a decision"))
    assert warn < sources < totals < decide
    assert "- **Karnataka State Chess Association could not be read in 2 runs in a row: Could not fetch" in text
    assert "| All India Chess Federation | OK | 30 Nov 2026 06:40 | 4 | – |" in text
    assert "| Karnataka State Chess Association | failing (2 in a row) | 28 Nov 2026 18:40 | 2 |" in text
    assert "| ChessBase India | off | never | 0 |" in text
    assert "- Records: 6" in text and "- Tournaments shown: 4" in text
    assert "- Upcoming events: 3" in text and "- New events this week: 1" in text


def test_needs_a_decision_counts_and_the_soonest_list_with_reasons():
    text = report()
    assert "- Possible duplicates: 1" in text
    assert "- Upcoming events with no state: 2" in text
    assert "- Events with no date (hidden from players): 1" in text
    assert "- Upcoming events with no register or brochure link: 2" in text
    listed = re.findall(r"^\d+\. (.*)$", text, re.M)
    assert listed == [
        "19 Dec: Bilaspur Open (All India Chess Federation): no state; no register or brochure link; "
        "maybe the same as ksca-9",
        "19 Dec: Bilaspur Open 2026 (Karnataka State Chess Association): no state; no register or brochure link",
        "no date: Undated State Rapid (All India Chess Federation): no date (hidden from players until one "
        "is known); no register or brochure link",
    ]
    assert "Kollam Rapid" not in "\n".join(listed)  # nothing to decide


def test_at_most_20_are_listed_soonest_first():
    many = [dict(EVENTS[2], id=f"aicf-x{n}", name=f"Open {n}", start=f"2026-12-{n:02d}",
                 end=f"2026-12-{n:02d}", flags={"possible_duplicate_of": None}) for n in range(1, 26)]
    text = report(events=many)
    listed = re.findall(r"^\d+\. (\d\d \w+):", text, re.M)
    assert len(listed) == 20 and listed[0] == "01 Dec" and listed[-1] == "20 Dec"
    assert "...and 5 more." in text


def test_no_warnings_when_all_is_well():
    meta = copy.deepcopy(META)
    meta["sources"]["ksca"].update(status="ok", failures_in_a_row=0, message=None)
    events = [dict(e, first_seen="2026-11-29") for e in EVENTS]
    assert "No warnings this week." in report(meta=meta, events=events)


def test_warning_a_source_with_no_new_events_for_14_days():
    events = [dict(e, first_seen="2026-11-01") for e in EVENTS]
    text = report(events=events)
    assert "- **All India Chess Federation has had no new events for 29 days (newest 01 Nov)**" in text


def test_warning_upcoming_events_dropped_by_more_than_a_fifth():
    week_ago = NOW.date() - timedelta(days=7)
    before = [dict(EVENTS[1], id=f"aicf-old{n}") for n in range(5)]  # 5 upcoming last week
    last_week = {"meta": META, "events": before, "today": week_ago}
    text = report(last_week=last_week)
    assert "- **Upcoming events dropped from 5 to 3 since last week (40% fewer)**" in text
    assert "- Upcoming events: 3 (-2 since last week)" in text
    assert "| All India Chess Federation | OK | 30 Nov 2026 06:40 | 4 | no change |" in text
    small = {"meta": META, "events": before[:3], "today": week_ago}
    assert "dropped" not in report(last_week=small)


def test_warning_the_daily_run_has_not_succeeded_for_two_days():
    old = [{"status": "completed", "conclusion": "success", "created_at": "2026-11-27T01:00:00Z"},
           {"status": "completed", "conclusion": "failure", "created_at": "2026-11-29T22:00:00Z"}]
    assert "- **The daily data run has not succeeded for over 2 days (last success: 27 Nov 2026 06:30)**" \
        in report(runs=old)
    assert "has not succeeded" not in report(runs=GOOD_RUNS)
    # without the run list (a local run), the data's own time is used
    assert "has not succeeded" not in report(runs=None)
    stale = dict(META, generated_at="2026-11-27T06:40:00+05:30")
    assert "has not succeeded" in report(meta=stale, runs=None)


# ---- the alerts -------------------------------------------------------------------------
KSCA_TITLE = "Data alert: Karnataka State Chess Association (ksca) could not be read"


def test_alert_problems_a_source_twice_in_a_row_or_a_failed_run():
    problems = health.alert_problems(META, "success", "success")
    assert list(problems) == [KSCA_TITLE] and "2 runs in a row" in problems[KSCA_TITLE]
    one = copy.deepcopy(META)
    one["sources"]["ksca"]["failures_in_a_row"] = 1
    assert health.alert_problems(one, "success", "skipped") == {}
    failed = health.alert_problems(one, "failure", "skipped")
    assert list(failed) == [health.RUN_FAILED_TITLE] and "job: build" in failed[health.RUN_FAILED_TITLE]
    assert "job: deploy" in health.alert_problems(one, "success", "failure")[health.RUN_FAILED_TITLE]
    assert health.alert_problems(one, "cancelled", "skipped") == {health.RUN_FAILED_TITLE: None}


def issue(number, title, state="open", ok=0):
    return {"number": number, "title": title, "state": state,
            "body": f"text\n\n<!-- ok-runs: {ok} -->"}


def test_a_new_problem_opens_one_issue_and_an_open_one_is_not_repeated():
    actions = health.plan_alerts({KSCA_TITLE: "broken"}, [])
    assert actions == [("create", KSCA_TITLE, health.alert_body("broken"))]
    assert "<!-- ok-runs: 0 -->" in actions[0][2]
    assert health.plan_alerts({KSCA_TITLE: "broken"}, [issue(7, KSCA_TITLE)]) == []


def test_a_closed_alert_is_reopened_never_a_second_one():
    actions = health.plan_alerts({KSCA_TITLE: "broken"}, [issue(7, KSCA_TITLE, state="closed", ok=2)])
    assert [a[0] for a in actions] == ["reopen", "edit", "comment"] and actions[0] == ("reopen", 7)
    assert "<!-- ok-runs: 0 -->" in actions[1][2]
    # an open one and an older closed one with the same title: the open one is used
    both = [issue(9, KSCA_TITLE), issue(7, KSCA_TITLE, state="closed")]
    assert health.plan_alerts({KSCA_TITLE: "broken"}, both) == []


def test_an_alert_closes_after_two_runs_without_the_problem():
    first = health.plan_alerts({}, [issue(7, KSCA_TITLE)])
    assert first == [("edit", 7, "text\n\n<!-- ok-runs: 1 -->")]
    second = health.plan_alerts({}, [issue(7, KSCA_TITLE, ok=1)])
    assert [a[0] for a in second] == ["edit", "comment", "close"] and second[-1] == ("close", 7)
    # failing again in between starts the count again
    again = health.plan_alerts({KSCA_TITLE: "broken"}, [issue(7, KSCA_TITLE, ok=1)])
    assert again[0] == ("edit", 7, "text\n\n<!-- ok-runs: 0 -->") and again[1][0] == "comment"
    # a cancelled run says nothing about the run alert
    assert health.plan_alerts({health.RUN_FAILED_TITLE: None},
                              [issue(8, health.RUN_FAILED_TITLE, ok=1)]) == []
    # other issues are never touched
    assert health.plan_alerts({}, [issue(5, "Weekly data health")]) == []


class FakeGitHub:
    def __init__(self, issues=()):
        self.items = [dict(i) for i in issues]
        self.calls = []

    def issues(self, label):
        return [dict(i) for i in self.items]

    def ensure_label(self, name, color, description):
        self.calls.append(("label", name))

    def create(self, title, body, label):
        self.calls.append(("create", title, label))
        self.items.insert(0, {"number": 100 + len(self.items), "title": title, "state": "open", "body": body})
        return {"number": self.items[0]["number"], "url": "u"}

    def comment(self, number, body):
        self.calls.append(("comment", number, body))
        return f"https://github.com/x/y/issues/{number}#c"

    def edit(self, number, **fields):
        self.calls.append(("edit", number, fields))
        for i in self.items:
            if i["number"] == number:
                i.update(fields)


def test_apply_alerts_runs_the_plan():
    gh = FakeGitHub()
    done = health.apply_alerts(gh, health.plan_alerts({KSCA_TITLE: "broken"}, []))
    assert done == [f"opened #100: {KSCA_TITLE}"] and gh.calls[:2] == [("label", "data-alert"),
                                                                       ("create", KSCA_TITLE, "data-alert")]
    gh = FakeGitHub([issue(7, KSCA_TITLE, ok=1)])
    assert health.apply_alerts(gh, health.plan_alerts({}, gh.issues("data-alert"))) == ["closed #7"]


def test_the_weekly_report_goes_to_one_issue_reopened_when_closed():
    gh = FakeGitHub()
    url = health.post_weekly(gh, "report 1")
    assert [c[0] for c in gh.calls] == ["label", "create", "comment"] and url.endswith("#c")
    gh.calls.clear()
    health.post_weekly(gh, "report 2")
    assert [c[0] for c in gh.calls] == ["label", "comment"]  # the same issue, no second one
    gh = FakeGitHub([{"number": 3, "title": "Weekly data health", "state": "closed", "body": ""}])
    health.post_weekly(gh, "report 3")
    assert gh.calls[1] == ("edit", 3, {"state": "open"}) and gh.calls[2][:2] == ("comment", 3)


# ---- failures in a row, in meta.json ----------------------------------------------------
ONLY_KSCA = {n: n == "ksca" for n in be.SOURCE_MODULES}


def test_meta_counts_failed_fetches_in_a_row_and_a_success_resets_it(web, data_dir):
    serve_ksca(web)
    run_all(data_dir, config=ONLY_KSCA)
    meta = lambda: json.loads((data_dir / "meta.json").read_text("utf-8"))["sources"]["ksca"]  # noqa: E731
    assert meta()["failures_in_a_row"] == 0
    web.add(KSCA + "tournaments/", "down", status=500)
    with pytest.raises(be.SourceError):
        run_all(data_dir, config=ONLY_KSCA)
    # the only source failed, so nothing was written (the run fails: that is the run alert)
    assert meta()["failures_in_a_row"] == 0
    serve_ksca(web)
    run_all(data_dir, config=dict(ONLY_KSCA, aicf=True))
    assert meta()["failures_in_a_row"] == 0


def test_failures_in_a_row_go_up_while_other_sources_carry_on(web, data_dir):
    from conftest import fx, serve_tnsca
    serve_tnsca(web)
    web.add(KSCA + "tournaments/", "down", status=500)
    both = {n: n in ("ksca", "tnsca") for n in be.SOURCE_MODULES}
    run_all(data_dir, config=both)
    run_all(data_dir, config=both)
    sources = json.loads((data_dir / "meta.json").read_text("utf-8"))["sources"]
    assert sources["ksca"]["failures_in_a_row"] == 2 and sources["tnsca"]["failures_in_a_row"] == 0
    problems = health.alert_problems(json.loads((data_dir / "meta.json").read_text("utf-8")), "success", "success")
    assert list(problems) == [KSCA_TITLE]
    assert fx  # imported for the fake web


# ---- the workflow files -----------------------------------------------------------------
WEEKLY = (ROOT / ".github" / "workflows" / "weekly.yml").read_text("utf-8")
DAILY = (ROOT / ".github" / "workflows" / "daily.yml").read_text("utf-8")


def test_weekly_workflow_runs_monday_morning_india_time_and_by_hand_and_only_writes_issues():
    assert re.search(r'cron: "30 1 \* \* 1"', WEEKLY)  # 01:30 UTC = 07:00 India time, Monday
    assert "workflow_dispatch:" in WEEKLY
    top = WEEKLY.split("jobs:")[0]
    assert re.search(r"^permissions:\n  contents: read\n  issues: write\n  actions: read\n", top, re.M)
    assert len(re.findall(r": write\b", WEEKLY)) == 1  # issues only
    for word in ("secrets.", "GH_TOKEN", "git push", "git commit", "pages", "deploy",
                 "build_events.py", "upload-"):
        assert word not in WEEKLY, word
    assert "python scripts/health.py weekly --post" in WEEKLY and "fetch-depth: 0" in WEEKLY
    assert "group: weekly-data-health" in WEEKLY and "group: weekly-data-health" not in DAILY


def test_daily_workflow_alerts_job_runs_after_every_run_and_only_writes_issues():
    alerts = DAILY.split("\n  alerts:\n")[1]
    assert "needs: [build, deploy]" in alerts and "if: ${{ always() }}" in alerts
    assert re.search(r"permissions:\n      contents: read\n      issues: write\n", alerts)
    assert "git push" not in alerts and "secrets." not in alerts and "pages" not in alerts
    assert 'python scripts/health.py alerts --build "$BUILD_RESULT" --deploy "$DEPLOY_RESULT"' in alerts
    assert "ref: main" in alerts
