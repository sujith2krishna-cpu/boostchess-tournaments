"""Data health: the weekly report and the urgent alerts, posted as GitHub issues.

    python scripts/health.py weekly [--post]        the "Weekly data health" report
    python scripts/health.py alerts --build R --deploy R   after every daily data run

Everything that decides what to say is pure (tests/test_health.py). The command line reads
data/ (the files Pages publishes), last week's data/ from git, and the daily workflow's runs,
and posts with the built-in GITHUB_TOKEN. It never writes data or publishes anything.

Alerts ("Data alert: <what failed>", label data-alert), one issue per problem:
- a source failed or was blocked FAILURES_TO_ALERT fetch attempts in a row
  (meta.json `failures_in_a_row`), or
- the daily data run itself failed (its build or deploy job).
An alert is opened (or reopened) at once, and closed by itself after OK_RUNS_TO_CLOSE daily
runs in a row without the problem; how many is kept in the issue body (`<!-- ok-runs: N -->`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from eventlib import IST, SOURCE_LABELS, hidden_by_hand, undated
from quality import in_window, is_shown

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEEKLY_TITLE = "Weekly data health"
WEEKLY_LABEL = "data-health"
ALERT_PREFIX = "Data alert: "
ALERT_LABEL = "data-alert"
RUN_FAILED_TITLE = ALERT_PREFIX + "the daily data run failed"
FAILURES_TO_ALERT = 2
OK_RUNS_TO_CLOSE = 2
QUIET_DAYS = 14
DROP_SHARE = 0.20
RUN_STALE_HOURS = 48
MAX_LISTED = 20
_OK_RUNS = re.compile(r"<!-- ok-runs: (\d+) -->")


# ---- small helpers --------------------------------------------------------------------
def _when(iso: str | None) -> str:
    if not iso:
        return "never"
    moment = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IST)
    return moment.strftime("%d %b %Y %H:%M")


def _day(iso: str | None) -> str:
    return datetime.fromisoformat(iso).strftime("%d %b") if iso else "no date"


def _change(now: int, before: int | None) -> str:
    if before is None:
        return "–"
    diff = now - before
    return "no change" if diff == 0 else f"{diff:+d}"


def _label(name: str) -> str:
    return SOURCE_LABELS.get(name, name)


def upcoming(events: list[dict], today: date) -> list[dict]:
    return [e for e in events if is_shown(e) and in_window(e, "upcoming", today)]


def reasons(event: dict) -> list[str]:
    out = []
    if not event.get("start"):
        out.append("no date (hidden from players until one is known)")
    if not event.get("state"):
        out.append("no state")
    if not event.get("register_url") and not event.get("brochure_url"):
        out.append("no register or brochure link")
    if (event.get("flags") or {}).get("possible_duplicate_of"):
        out.append(f"maybe the same as {event['flags']['possible_duplicate_of']}")
    return out


def needs_decision(events: list[dict], today: date) -> dict:
    coming = upcoming(events, today)
    hidden_undated = [e for e in events if undated(e, today) and e["merged_into"] is None
                      and not hidden_by_hand(e)
                      and not e.get("cancelled") and not e.get("gone_from_source")]
    listed = sorted((e for e in coming + hidden_undated if reasons(e)),
                    key=lambda e: (e.get("start") or "9999", e["id"]))
    return {
        "possible_duplicates": sum(1 for e in events if (e.get("flags") or {}).get("possible_duplicate_of")),
        "no_state": sum(1 for e in coming if not e.get("state")),
        "no_date": len(hidden_undated),
        "no_link": sum(1 for e in coming if not e.get("register_url") and not e.get("brochure_url")),
        "listed": listed[:MAX_LISTED], "more": max(0, len(listed) - MAX_LISTED),
    }


def last_run_success(runs: list[dict] | None) -> str | None:
    done = [r for r in runs or [] if r.get("conclusion") == "success"]
    return max((r["created_at"] for r in done), default=None)


# ---- the weekly report ------------------------------------------------------------------
def warnings(now: datetime, meta: dict, events: list[dict], last_week: dict | None,
             runs: list[dict] | None) -> list[str]:
    today = now.astimezone(IST).date()
    out = []
    for name, info in meta.get("sources", {}).items():
        if info.get("enabled") and int(info.get("failures_in_a_row") or 0) >= FAILURES_TO_ALERT:
            out.append(f"{_label(name)} could not be read in {info['failures_in_a_row']} runs in a "
                       f"row: {info.get('message') or 'see meta.json'}")
    for name, info in meta.get("sources", {}).items():
        if not info.get("enabled"):
            continue
        seen = [e["first_seen"] for e in events if e["source"] == name and e.get("first_seen")]
        newest = max(seen, default=None)
        if newest and date.fromisoformat(newest) < today - timedelta(days=QUIET_DAYS):
            days = (today - date.fromisoformat(newest)).days
            out.append(f"{_label(name)} has had no new events for {days} days (newest {_day(newest)})")
    if last_week:
        before = len(upcoming(last_week["events"], last_week["today"]))
        now_count = len(upcoming(events, today))
        if before and now_count < before * (1 - DROP_SHARE):
            out.append(f"Upcoming events dropped from {before} to {now_count} since last week "
                       f"({100 * (before - now_count) / before:.0f}% fewer)")
    success = last_run_success(runs) if runs is not None else meta.get("generated_at")
    if success is None or now - datetime.fromisoformat(success.replace("Z", "+00:00")) \
            > timedelta(hours=RUN_STALE_HOURS):
        out.append(f"The daily data run has not succeeded for over {RUN_STALE_HOURS // 24} days "
                   f"(last success: {_when(success)})")
    return out


def weekly_report(now: datetime, meta: dict, events: list[dict], last_week: dict | None = None,
                  runs: list[dict] | None = None) -> str:
    """The report, in plain English (GitHub Markdown)."""
    today = now.astimezone(IST).date()
    lines = [f"## Data health, week of {today.strftime('%d %b %Y')}", ""]
    found = warnings(now, meta, events, last_week, runs)
    if found:
        lines += ["**Warnings**", ""] + [f"- **{w}**" for w in found]
    else:
        lines += ["No warnings this week."]
    lines += ["", "### Sources", "",
              "| Source | Status | Last good read | Events | Change since last week |",
              "|---|---|---|---|---|"]
    before_sources = (last_week or {}).get("meta", {}).get("sources", {})
    for name, info in meta.get("sources", {}).items():
        failures = int(info.get("failures_in_a_row") or 0)
        if not info.get("enabled"):
            state = "off"
        elif info.get("status") in ("failed", "skipped"):
            state = f"failing ({failures} in a row)" if failures else "failing"
        else:
            state = "OK"
        count = int(info.get("count") or 0)
        old = before_sources.get(name, {}).get("count") if last_week else None
        lines.append(f"| {_label(name)} | {state} | {_when(info.get('last_success'))} | {count} | "
                     f"{_change(count, old)} |")
    coming = upcoming(events, today)
    shown = sum(1 for e in events if e["merged_into"] is None and not e.get("hidden"))
    new = sum(1 for e in events if is_shown(e) and e.get("first_seen")
              and e["first_seen"] >= (today - timedelta(days=7)).isoformat())
    lw = last_week or {}
    lw_events = lw.get("events")
    lines += ["", "### Totals", "",
              f"- Records: {len(events)} ({_change(len(events), len(lw_events) if lw_events is not None else None)} since last week)",
              f"- Tournaments shown: {shown}",
              f"- Upcoming events: {len(coming)} ({_change(len(coming), len(upcoming(lw_events, lw['today'])) if lw_events is not None else None)} since last week)",
              f"- New events this week: {new}"]
    need = needs_decision(events, today)
    lines += ["", "### Needs a decision", "",
              f"- Possible duplicates: {need['possible_duplicates']}",
              f"- Upcoming events with no state: {need['no_state']}",
              f"- Events with no date (hidden from players): {need['no_date']}",
              f"- Upcoming events with no register or brochure link: {need['no_link']}"]
    if need["listed"]:
        lines += ["", f"The {len(need['listed'])} soonest:", ""]
        for n, e in enumerate(need["listed"], 1):
            name = e["name"] if len(e["name"]) <= 90 else e["name"][:87].rstrip() + "..."
            lines.append(f"{n}. {_day(e.get('start'))}: {name} ({_label(e['source'])}): "
                         f"{'; '.join(reasons(e))}")
        if need["more"]:
            lines.append(f"\n...and {need['more']} more.")
    lines += ["", f"<sub>Made from `data/` on main ({_when(meta.get('generated_at'))} India time) "
                  f"by the Weekly data health workflow.</sub>"]
    return "\n".join(lines) + "\n"


# ---- alerts ------------------------------------------------------------------------------
def alert_problems(meta: dict, build_result: str | None, deploy_result: str | None) -> dict:
    """{issue title: what is wrong} for every problem that needs an alert now; None as a value
    means "cannot tell this run" (a cancelled run): that alert is left as it is."""
    problems: dict[str, str | None] = {}
    for name, info in meta.get("sources", {}).items():
        failures = int(info.get("failures_in_a_row") or 0)
        if info.get("enabled") and failures >= FAILURES_TO_ALERT:
            problems[f"{ALERT_PREFIX}{_label(name)} ({name}) could not be read"] = (
                f"{_label(name)} could not be read in {failures} runs in a row. Its previous events "
                f"are kept and shown. Last error: {info.get('message') or 'see data/meta.json'}")
    results = {"build": build_result, "deploy": deploy_result}
    failed = [job for job, result in results.items() if result == "failure"]
    if failed:
        problems[RUN_FAILED_TITLE] = (f"The daily data run failed (job: {', '.join(failed)}). Open "
                                      "the Actions tab, Daily tournament data, for the log.")
    elif "cancelled" in results.values():
        problems[RUN_FAILED_TITLE] = None
    return problems


def ok_runs(body: str) -> int:
    match = _OK_RUNS.search(body or "")
    return int(match.group(1)) if match else 0


def _with_ok_runs(body: str, count: int) -> str:
    if _OK_RUNS.search(body or ""):
        return _OK_RUNS.sub(f"<!-- ok-runs: {count} -->", body)
    return (body or "").rstrip() + f"\n\n<!-- ok-runs: {count} -->"


def alert_body(text: str) -> str:
    return (f"{text}\n\nOpened by the daily data run. It closes by itself after "
            f"{OK_RUNS_TO_CLOSE} runs in a row without this problem.\n\n<!-- ok-runs: 0 -->")


def plan_alerts(problems: dict, issues: list[dict]) -> list[tuple]:
    """What to do with the alert issues: ('create', title, body), ('reopen', number),
    ('comment', number, text), ('edit', number, body), ('close', number). One issue per
    problem: an open one is reused, else the newest closed one is reopened."""
    actions = []
    by_title: dict[str, dict] = {}
    for issue in issues:  # newest first; an open issue wins over closed ones
        if not issue["title"].startswith(ALERT_PREFIX):
            continue
        known = by_title.get(issue["title"])
        if known is None or (known["state"] != "open" and issue["state"] == "open"):
            by_title[issue["title"]] = issue
    for title, text in problems.items():
        issue = by_title.get(title)
        if text is None:
            continue  # cannot tell this run
        if issue is None:
            actions.append(("create", title, alert_body(text)))
        elif issue["state"] != "open":
            actions += [("reopen", issue["number"]),
                        ("edit", issue["number"], _with_ok_runs(issue["body"], 0)),
                        ("comment", issue["number"], f"The problem is back. {text}")]
        elif ok_runs(issue["body"]) > 0:
            actions += [("edit", issue["number"], _with_ok_runs(issue["body"], 0)),
                        ("comment", issue["number"], f"It failed again. {text}")]
    for title, issue in by_title.items():
        if issue["state"] != "open" or title in problems:
            continue
        count = ok_runs(issue["body"]) + 1
        if count >= OK_RUNS_TO_CLOSE:
            actions += [("edit", issue["number"], _with_ok_runs(issue["body"], count)),
                        ("comment", issue["number"],
                         f"Fixed: {count} runs in a row without this problem. Closing."),
                        ("close", issue["number"])]
        else:
            actions.append(("edit", issue["number"], _with_ok_runs(issue["body"], count)))
    return actions


def apply_alerts(client, actions: list[tuple]) -> list[str]:
    done = []
    if any(a[0] == "create" for a in actions):
        client.ensure_label(ALERT_LABEL, "d73a4a", "Opened by the daily data run when data goes wrong")
    for action in actions:
        kind = action[0]
        if kind == "create":
            issue = client.create(action[1], action[2], ALERT_LABEL)
            done.append(f"opened #{issue['number']}: {action[1]}")
        elif kind == "reopen":
            client.edit(action[1], state="open")
            done.append(f"reopened #{action[1]}")
        elif kind == "comment":
            client.comment(action[1], action[2])
        elif kind == "edit":
            client.edit(action[1], body=action[2])
        elif kind == "close":
            client.edit(action[1], state="closed", state_reason="completed")
            done.append(f"closed #{action[1]}")
    return done


def post_weekly(client, report: str) -> str | None:
    """Comment on the one "Weekly data health" issue (made the first time, reopened if closed)."""
    client.ensure_label(WEEKLY_LABEL, "0e8a16", "The weekly data health report")
    found = [i for i in client.issues(WEEKLY_LABEL) if i["title"] == WEEKLY_TITLE]
    issue = next((i for i in found if i["state"] == "open"), found[0] if found else None)
    if issue is None:
        issue = client.create(WEEKLY_TITLE, "Every Monday morning (India time) the Weekly data "
                              "health workflow adds the week's report here as a comment, so "
                              "GitHub e-mails it. It only reads the data; it never changes it.",
                              WEEKLY_LABEL)
    elif issue["state"] != "open":
        client.edit(issue["number"], state="open")
    return client.comment(issue["number"], report)


# ---- command line --------------------------------------------------------------------------
def _load(folder: Path) -> tuple[dict, list[dict]]:
    meta = json.loads((folder / "meta.json").read_text("utf-8"))
    events = json.loads((folder / "events.json").read_text("utf-8"))["events"]
    return meta, events


def last_week_from_git(now: datetime) -> dict | None:
    """data/meta.json and data/events.json as they were on main a week ago (git history)."""
    before = (now - timedelta(days=7)).isoformat()
    try:
        sha = subprocess.run(["git", "log", "-1", "--format=%H", f"--before={before}", "--",
                              "data/events.json"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        if not sha:
            return None
        show = lambda path: subprocess.run(["git", "show", f"{sha}:{path}"], cwd=ROOT,  # noqa: E731
                                           capture_output=True, text=True, check=True,
                                           encoding="utf-8").stdout
        meta = json.loads(show("data/meta.json"))
        events = json.loads(show("data/events.json"))["events"]
    except (subprocess.CalledProcessError, ValueError, KeyError, FileNotFoundError):
        return None
    when = datetime.fromisoformat(meta["generated_at"]).astimezone(IST).date()
    return {"meta": meta, "events": events, "today": when}


def _client():
    from github_issues import GitHub
    token, repository = os.environ.get("GITHUB_TOKEN"), os.environ.get("REPOSITORY")
    if not token or not repository:
        raise SystemExit("GITHUB_TOKEN and REPOSITORY must be set to post (the workflow sets them).")
    return GitHub(repository, token)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    weekly = sub.add_parser("weekly")
    weekly.add_argument("--post", action="store_true", help="comment on the GitHub issue")
    alerts = sub.add_parser("alerts")
    alerts.add_argument("--build", default=None)
    alerts.add_argument("--deploy", default=None)
    args = parser.parse_args(argv)
    meta, events = _load(DATA_DIR)
    now = datetime.now(IST)
    if args.command == "weekly":
        client = _client() if args.post else None
        runs = client.runs("daily.yml") if client else None
        report = weekly_report(now, meta, events, last_week_from_git(now), runs)
        print(report)
        if client:
            print("Posted:", post_weekly(client, report))
        return 0
    client = _client()
    actions = plan_alerts(alert_problems(meta, args.build, args.deploy), client.issues(ALERT_LABEL))
    for line in apply_alerts(client, actions) or ["no alert changes"]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
