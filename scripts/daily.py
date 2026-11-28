"""Text for the daily GitHub Action: commit message, job summary, warnings.

Pure functions that turn the report of build_events.run() into short text. No network,
no files (except write_summary, which appends to the file GitHub gives us).
"""
from __future__ import annotations

import os
from pathlib import Path

import quality

SOURCE_ORDER = ("aicf", "kca", "tnsca", "ksca", "upcsa", "chessfee", "chessresults_ind", "chessbase_calendar")


def _names(report: dict, wanted: tuple[str, ...]) -> list[str]:
    return [n for n in SOURCE_ORDER if report["per_source"].get(n, {}).get("status") in wanted]


def commit_message(report: dict) -> str:
    """One short line, e.g.
    data: 2026-11-25 (+3 new, 2 changed; sources ok: aicf, chessfee, chessresults_ind, chessbase_calendar)
    """
    changes = report.get("changes", {})
    blocked = [n for n in SOURCE_ORDER if report["per_source"].get(n, {}).get("blocked")]
    ok = [n for n in _names(report, ("ok", "skipped")) if n not in blocked]
    failed = _names(report, ("failed",)) + blocked
    text = f"+{changes.get('new', 0)} new, {changes.get('changed', 0)} changed"
    text += "; sources ok: " + (", ".join(ok) if ok else "none")
    if failed:
        text += "; failed: " + ", ".join(failed)
    return f"data: {report['today']} ({text})"


def problems(report: dict) -> list[tuple[str, str]]:
    """(source, message) for every source that failed or was blocked this run."""
    found = []
    for name in SOURCE_ORDER:
        info = report["per_source"].get(name, {})
        if info.get("status") == "failed" or info.get("blocked"):
            found.append((name, info.get("message") or "unknown problem"))
    return found


def summary_markdown(report: dict) -> str:
    """The job summary: per-source counts, ongoing/upcoming/past, failures."""
    meta = report["meta"]
    changes = report.get("changes", {})
    lines = [f"## Tournament data, {report['today']}", "",
             "| Source | Status | Fetched this run | Events | Ongoing | Upcoming | Past | Register links | Requests |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for name in SOURCE_ORDER:
        info = report["per_source"].get(name)
        if not info:
            continue
        by = info["by_status"]
        fetched = "yes" if info.get("due", True) else f"no, next due {(info.get('next_due') or '?')[:16]}"
        lines.append(f"| {name} | {info['status']} | {fetched} | {info['found']} | {by.get('ongoing', 0)} | "
                     f"{by.get('upcoming', 0)} | {by.get('past', 0)} | "
                     f"{info['with_register_url']} | {info['requests']} |")
    counts = report["status_counts"]
    if not report.get("fetched_any", True):
        lines += ["", "**No source was due** (each source is fetched at most once every 12 hours), "
                  "so nothing was fetched this run."]
    lines += ["", f"**All events:** {meta['total']} "
              f"(ongoing {counts.get('ongoing', 0)}, upcoming {counts.get('upcoming', 0)}, "
              f"past {counts.get('past', 0)}, no usable date {counts.get('unknown', 0)}); "
              f"suspect dates {meta['suspect_dates_count']}, missing state {meta['missing_state_count']}, "
              f"records grouped under another site's record {report.get('merged', 0)}, "
              f"possible duplicates {report.get('possible_duplicates', 0)} "
              "(see data/review/dedup_review.csv).",
              f"**Since the last run:** +{changes.get('new', 0)} new, {changes.get('changed', 0)} changed, "
              f"{changes.get('gone', 0)} no longer listed."]
    bad = problems(report)
    if bad:
        lines += ["", "### Problems"]
        lines += [f"- **{name}**: {message}" for name, message in bad]
        lines.append("")
        lines.append("The other sources were read normally and the failed source kept its previous events.")
    else:
        lines += ["", "No source problems."]
    for warning in report.get("warnings", []):
        lines.append(f"- warning: {warning}")
    text = "\n".join(lines) + "\n"
    if report.get("quality"):
        text += quality.summary_markdown(report["quality"])
    return text


def failure_markdown(message: str) -> str:
    return f"## Tournament data: the run FAILED\n\n{message}\n\nNothing was written or committed.\n"


def annotations(report: dict) -> list[str]:
    """GitHub warning lines (they show up on the run page) for failed or blocked sources."""
    lines = [f"::warning title={name} problem::{message.replace(chr(10), ' ')}"
             for name, message in problems(report)]
    lines += [f"::warning title=Quality alert::{alert['message']}"
              for alert in (report.get("quality") or {}).get("alerts", [])]
    return lines


def write_summary(path: str | None, text: str) -> None:
    """Append to the job summary file (the GITHUB_STEP_SUMMARY path), if there is one."""
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


def running_in_github() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"
