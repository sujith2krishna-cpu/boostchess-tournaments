"""How complete the data is (data/quality.json) and what to fix by hand (data/review.csv).

Pure functions: they take the finished events of a run and return numbers and rows. No
network, no files.

"Shown" events are the ones the website and the app show: not hidden, not cancelled, and not
merged into another site's record of the same tournament (`merged_into` is null). Two windows,
both by start date in Indian time: the next 30 days (today up to today + 30) and all upcoming
(today or later). An event without a usable start date is in neither: unless it is over, the
build hides it from players and review.csv lists it until a person adds its dates.

An event is **fully known** when all of these are known: its format, whether it is FIDE rated
(true or false, not null), its state, good dates (not suspect), and a register link or a
brochure link.

`states` counts the shown upcoming events per Indian state and union territory (every one of
them, so a state with none shows 0), plus `no_state` (an Indian event whose state is not known)
and `abroad` (an event in another country), to show where coverage is thin.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta

from eventlib import (OVERRIDES_CSV_COLUMNS, SOURCE_PRIORITY, STATES, hidden_by_hand, source_rank, status,
                      undated)

WINDOW_DAYS = 30
TARGET_PCT = 95.0  # fully known, for the next 30 days
DROP_POINTS = 10.0  # a source whose fully-known % falls this much (or more) since the last run
MIN_EVENTS_TO_COMPARE = 5  # fewer events than this in a window: too few to raise an alarm
WINDOWS = ("next_30_days", "upcoming")

# (key in quality.json, test: True when the event lacks it)
CHECKS = (
    ("unknown_format", lambda e: not e["tags"]["formats"]),
    ("unknown_fide", lambda e: e["tags"]["fide_rated"] is None),
    ("no_state", lambda e: not e["state"]),
    ("suspect_dates", lambda e: bool(e["flags"]["dates_suspect"]) or not e["start"]),
    ("no_register_link", lambda e: not e["register_url"]),
    ("no_brochure", lambda e: not e["brochure_url"]),
)

# What the review list says is missing, and the overrides.csv column(s) that fix it.
MISSING = (
    ("format", lambda e: not e["tags"]["formats"], ("format",)),
    ("fide", lambda e: e["tags"]["fide_rated"] is None, ("fide_rated",)),
    ("state", lambda e: not e["state"], ("state",)),
    ("dates", lambda e: bool(e["flags"]["dates_suspect"]) or not e["start"], ("start_date", "end_date")),
    ("register or brochure link", lambda e: not e["register_url"] and not e["brochure_url"],
     ("register_url",)),
)

REVIEW_COLUMNS = ("kind", "id", "other_id", "name", "start", "end", "state", "city", "missing",
                  "source_url", "brochure_url", "also_listed_on", "add_to_file", "line_to_add")


def is_shown(event: dict) -> bool:
    return not event["hidden"] and not event["cancelled"] and event["merged_into"] is None


def missing_parts(event: dict) -> list[str]:
    return [label for label, lacks, _ in MISSING if lacks(event)]


def fully_known(event: dict) -> bool:
    return not missing_parts(event)


def in_window(event: dict, window: str, today: date) -> bool:
    start = event.get("start")
    if not start:
        return False
    if window == "next_30_days":
        return today.isoformat() <= start <= (today + timedelta(days=WINDOW_DAYS)).isoformat()
    return start >= today.isoformat()


def _pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 1) if whole else None


def measure(events: list[dict]) -> dict:
    """{"events": n, "fully_known": n, "fully_known_pct": %, "<check>": n, "<check>_pct": %, ...}"""
    total = len(events)
    known = sum(1 for e in events if fully_known(e))
    out = {"events": total, "fully_known": known, "fully_known_pct": _pct(known, total)}
    for key, lacks in CHECKS:
        count = sum(1 for e in events if lacks(e))
        out[key] = count
        out[f"{key}_pct"] = _pct(count, total)
    return out


def state_counts(upcoming: list[dict]) -> dict:
    """Shown upcoming events per Indian state / union territory (all of them, 0 included)."""
    by_state = dict.fromkeys(sorted(STATES), 0)
    no_state = abroad = 0
    for event in upcoming:
        if event["country"] not in (None, "IN"):
            abroad += 1
        elif event["state"]:
            by_state[event["state"]] = by_state.get(event["state"], 0) + 1
        else:
            no_state += 1
    return {"window": "upcoming", "events": len(upcoming), "by_state": by_state,
            "no_state": no_state, "abroad": abroad}


def _alerts(sources: dict, previous: dict | None) -> list[dict]:
    """Compare with the previous run's quality.json: a big drop in fully known, or a halving."""
    alerts = []
    before_sources = (previous or {}).get("sources") or {}
    for name, now in sources.items():
        before = before_sources.get(name) or {}
        for window in WINDOWS:
            a, b = before.get(window) or {}, now[window]
            if (a.get("events") or 0) >= MIN_EVENTS_TO_COMPARE and b["events"] >= MIN_EVENTS_TO_COMPARE \
                    and a.get("fully_known_pct") is not None and b["fully_known_pct"] is not None \
                    and a["fully_known_pct"] - b["fully_known_pct"] >= DROP_POINTS:
                alerts.append({"source": name, "window": window, "what": "fully_known_drop",
                               "message": f"{name}: fully known ({window.replace('_', ' ')}) fell from "
                                          f"{a['fully_known_pct']:g}% to {b['fully_known_pct']:g}%"})
        a, b = (before.get("upcoming") or {}).get("events") or 0, now["upcoming"]["events"]
        if a >= MIN_EVENTS_TO_COMPARE and b * 2 <= a:
            alerts.append({"source": name, "window": "upcoming", "what": "count_halved",
                           "message": f"{name}: upcoming events fell from {a} to {b} (half or fewer)"})
    return alerts


def quality_report(events: list[dict], today: date, generated_at: str,
                   previous: dict | None = None, review_counts: dict | None = None) -> dict:
    """The content of data/quality.json."""
    shown = [e for e in events if is_shown(e)]
    by_window = {w: [e for e in shown if in_window(e, w, today)] for w in WINDOWS}
    overall = {w: measure(by_window[w]) for w in WINDOWS}
    sources = {name: {w: measure([e for e in by_window[w] if e["source"] == name]) for w in WINDOWS}
               for name in SOURCE_PRIORITY}
    now_pct = overall["next_30_days"]["fully_known_pct"]
    return {
        "generated_at": generated_at,
        "today": today.isoformat(),
        "windows": {"next_30_days": {"from": today.isoformat(),
                                     "to": (today + timedelta(days=WINDOW_DAYS)).isoformat()},
                    "upcoming": {"from": today.isoformat(), "to": None}},
        "target": {"window": "next_30_days", "fully_known_pct": TARGET_PCT,
                   "now_pct": now_pct, "met": now_pct is not None and now_pct >= TARGET_PCT},
        "overall": overall,
        "sources": sources,
        "alerts": _alerts(sources, previous),
        "review": review_counts or {"missing": 0, "dates_disagree": 0, "possible_duplicates": 0},
        "states": state_counts(by_window["upcoming"]),
    }


def comparable(quality: dict | None):
    """The numbers only (no times, dates or alerts): has anything changed since the last run?"""
    if not quality:
        return None
    return {k: quality.get(k) for k in ("target", "overall", "sources", "review", "states")}


# --------------------------------------------------------------------------
# data/review.csv
# --------------------------------------------------------------------------
def _csv_line(cells: list[str]) -> str:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="").writerow(cells)
    return buffer.getvalue()


def override_line(event: dict, missing: list[str]) -> str:
    """A ready overrides.csv line: the key, and '?' in each column to fill in."""
    to_fill = {c for label, _, columns in MISSING if label in missing for c in columns}
    return _csv_line([event["id"] if c == "key" else ("?" if c in to_fill else "")
                      for c in OVERRIDES_CSV_COLUMNS])


def _row(event: dict, kind: str, **extra) -> dict:
    return {"kind": kind, "id": event["id"], "other_id": "", "name": event["name"] or "",
            "start": event["start"] or "", "end": event["end"] or "", "state": event["state"] or "",
            "city": event["city"] or "", "missing": "", "source_url": event["source_url"] or "",
            "brochure_url": event["brochure_url"] or "",
            "also_listed_on": " | ".join(x["source_url"] for x in event["also_listed_on"]
                                         if x.get("source_url")),
            "add_to_file": "", "line_to_add": "", **extra}


DATES_APART_DAYS = 1  # grouped records whose start dates are further apart than this disagree


def dates_disagree(events: list[dict], today: date) -> list[tuple[dict, list[dict]]]:
    """[(primary, members)] for each group of records (not past, not hidden) whose start dates
    are more than a day apart: the sites disagree about when the tournament starts."""
    groups = defaultdict(list)
    for event in events:
        if not event["hidden"]:
            groups[event["group_id"]].append(event)
    found = []
    for members in groups.values():
        primary = next((m for m in members if m["merged_into"] is None), None)
        starts = [date.fromisoformat(m["start"]) for m in members if m["start"]]
        if primary is None or len(starts) < 2 or not is_shown(primary)                 or status(primary, today) == "past":
            continue
        if (max(starts) - min(starts)).days > DATES_APART_DAYS:
            found.append((primary, sorted(members, key=lambda m: (source_rank(m["source"]), m["id"]))))
    return sorted(found, key=lambda pm: (pm[0]["start"] or "9999", pm[0]["id"]))


def _dates_text(members: list[dict]) -> str:
    """'aicf 2027-02-08 to 2027-02-13 (aicf-1); tnsca, chessbase_calendar 2027-01-30 to ...'"""
    by_dates: dict[str, list[dict]] = {}
    for m in members:
        when = (m["start"] or "no date") + (f" to {m['end']}" if m["end"] and m["end"] != m["start"] else "")
        by_dates.setdefault(when, []).append(m)
    return "; ".join(f"{', '.join(dict.fromkeys(m['source'] for m in ms))} {when} "
                     f"({', '.join(m['id'] for m in ms)})" for when, ms in by_dates.items())


def review_rows(events: list[dict], today: date) -> list[dict]:
    """Shown events starting in the next 30 days that miss anything (by start date), then shown
    events with no start date that are not past (by id), then grouped records whose start dates disagree by more than a day (not past events), then
    every remaining possible duplicate (with both ids and a ready pairs.csv line)."""
    rows = []
    for event in sorted((e for e in events if is_shown(e) and in_window(e, "next_30_days", today)),
                        key=lambda e: (e["start"], e["end"] or "", e["id"])):
        missing = missing_parts(event)
        if missing:
            rows.append(_row(event, "missing", missing=", ".join(missing),
                             add_to_file="data/manual/overrides.csv",
                             line_to_add=override_line(event, missing)))
    # Events with no start date that are not over (a page that gives "12-13 December" and no
    # year): the build hides them from players, so they are listed here until a person adds the
    # dates. Not the ones a person hid (overrides.csv), cancelled, merged or gone.
    for event in sorted((e for e in events if undated(e, today) and not hidden_by_hand(e)
                         and not e["cancelled"] and e["merged_into"] is None
                         and not e["gone_from_source"]), key=lambda e: e["id"]):
        missing = missing_parts(event)
        said = (event["raw_dates"] or {}).get("start") or ""
        rows.append(_row(event, "missing",
                         missing=", ".join(missing) + "; no start date: the page says "
                                 + (f"'{said}'" if said else "nothing")
                                 + ", so it is hidden from players; check the event's own circular "
                                 "or brochure",
                         add_to_file="data/manual/overrides.csv",
                         line_to_add=override_line(event, missing)))
    for primary, members in dates_disagree(events, today):
        others = [m["id"] for m in members if m is not primary and m["start"] != primary["start"]]
        rows.append(_row(primary, "dates_disagree", other_id=" ".join(others),
                         missing="start dates disagree: " + _dates_text(members)
                                 + "; check the organiser's page, then set the right dates here",
                         add_to_file="data/manual/overrides.csv",
                         line_to_add=override_line(primary, ["dates"])))
    by_id = {e["id"]: e for e in events}
    dups = [e for e in events if e["flags"]["possible_duplicate_of"] and not e["hidden"]]
    for event in sorted(dups, key=lambda e: (e["start"] or "9999", e["id"])):
        other = event["flags"]["possible_duplicate_of"]
        other_event = by_id.get(other)
        rows.append(_row(event, "possible_duplicate", other_id=other,
                         missing=f"maybe the same tournament as {other}"
                                 + (f" ({other_event['name']})" if other_event else "")
                                 + "; check both, then keep 'same' or change it to 'not_same'",
                         add_to_file="data/manual/pairs.csv",
                         line_to_add=_csv_line([other, event["id"], "same", ""])))
    return rows


def review_counts(rows: list[dict]) -> dict:
    return {"missing": sum(1 for r in rows if r["kind"] == "missing"),
            "dates_disagree": sum(1 for r in rows if r["kind"] == "dates_disagree"),
            "possible_duplicates": sum(1 for r in rows if r["kind"] == "possible_duplicate")}


def review_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def summary_markdown(quality: dict) -> str:
    """The quality part of the job summary."""
    labels = (("fully_known_pct", "Fully known"), ("unknown_format_pct", "Unknown format"),
              ("unknown_fide_pct", "Unknown FIDE"), ("no_state_pct", "No state"),
              ("suspect_dates_pct", "Suspect dates"), ("no_register_link_pct", "No register link"),
              ("no_brochure_pct", "No brochure"))

    def cells(m: dict) -> str:
        return " | ".join("–" if m[k] is None else f"{m[k]:g}%" for k, _ in labels)

    target = quality["target"]
    now = target["now_pct"]
    lines = ["", "### Data quality (shown events starting in the next 30 days)", "",
             f"**Target:** {target['fully_known_pct']:g}% fully known (format, FIDE, state, dates, "
             f"register or brochure link). **Now:** {'–' if now is None else f'{now:g}%'} "
             f"({'met' if target['met'] else 'not met yet'}).", "",
             "| Source | Events | " + " | ".join(label for _, label in labels) + " |",
             "|---|---:|" + "---:|" * len(labels)]
    for name, windows in quality["sources"].items():
        m = windows["next_30_days"]
        if m["events"]:
            lines.append(f"| {name} | {m['events']} | {cells(m)} |")
    m = quality["overall"]["next_30_days"]
    lines.append(f"| **all** | **{m['events']}** | {cells(m)} |")
    up = quality["overall"]["upcoming"]
    lines += ["", f"All upcoming: {up['events']} events, "
              f"{'–' if up['fully_known_pct'] is None else format(up['fully_known_pct'], 'g') + '%'} fully known."]
    review = quality["review"]
    lines.append(f"**Review list** (`data/review.csv`): {review['missing']} events to complete, "
                 f"{review.get('dates_disagree', 0)} with dates that disagree, "
                 f"{review['possible_duplicates']} possible duplicates.")
    states = quality.get("states")
    if states:
        ranked = sorted(states["by_state"].items(), key=lambda kv: (-kv[1], kv[0]))
        lines.append("**Upcoming by state:** " + ", ".join(f"{s} {n}" for s, n in ranked if n)
                     + f"; no state {states['no_state']}; abroad {states['abroad']}. "
                     + "None yet: " + (", ".join(s for s, n in ranked if not n) or "–") + ".")
    if quality["alerts"]:
        lines += ["", "**Quality alerts** (compared with the previous run):"]
        lines += [f"- {a['message']}" for a in quality["alerts"]]
    return "\n".join(lines) + "\n"
