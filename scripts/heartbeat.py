#!/usr/bin/env python3
"""Heartbeat: fail loudly when a source has gone quiet, the data is stale, or a fetch was missed.

    python scripts/heartbeat.py [--data-dir data] [--days 3] [--before FILE --started TIME]

Reads data/meta.json (written by build_events.py). Three alarms:
  * a source has had no successful fetch for 3 days;
  * the newest successful fetch of any source is over 30 hours old (stale data);
  * missed fetch: a source has been due (12 hours after its last good fetch) for more than
    6 hours without any fetch attempt. With --before (meta.json as it was before this run's
    build) and --started (when this run started), the waiting time counted is the time up to
    this run, so a run that comes after GitHub skipped scheduled runs fails and says so.
Sources switched off in config/sources.json are not checked. Exit code 0 = fine, 1 = alarm.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventlib import DATA_DIR, FETCH_INTERVAL_HOURS, IST  # noqa: E402

DEFAULT_DAYS = 3  # was 7; a healthy source is fetched every 12 hours
STALE_DATA_HOURS = 30
MISSED_FETCH_HOURS = 6  # due for longer than this with no attempt at all = a missed fetch


def _time(text) -> datetime | None:
    try:
        return datetime.fromisoformat(text).astimezone(IST) if text else None
    except (TypeError, ValueError):
        return None


def missed_fetches(meta: dict, now: datetime, grace_hours: float = MISSED_FETCH_HOURS,
                   interval_hours: float = FETCH_INTERVAL_HOURS) -> list[dict]:
    """Switched-on sources that have waited more than `grace_hours` for a fetch attempt.

    A source is due `interval_hours` after its last success. A failed attempt counts as an
    attempt (the source is due again straight away, so the wait starts again from that
    attempt; failures themselves are the 3-day alarm's job). A source that has never been
    tried at all is left to the 3-day alarm ("never fetched").
    Returns [{"source", "due_since", "waiting_hours"}].
    """
    now = now.astimezone(IST)
    found = []
    for name, info in (meta.get("sources") or {}).items():
        if not info.get("enabled", True) or info.get("status") == "disabled":
            continue
        success = _time(info.get("last_success"))
        error = info.get("last_error") or {}
        failed = _time(error.get("at")) if isinstance(error, dict) else None
        attempts = [t for t in (success, failed) if t is not None]
        if not attempts:
            continue
        due = success + timedelta(hours=interval_hours) if success else None
        waiting_since = max([t for t in (due, max(attempts)) if t is not None])
        waiting = (now - waiting_since).total_seconds() / 3600
        if waiting > grace_hours:
            found.append({"source": name, "due_since": waiting_since.isoformat(),
                          "waiting_hours": round(waiting, 1)})
    return found


def missed_message(missed: list[dict], grace_hours: float = MISSED_FETCH_HOURS) -> str:
    return "\n".join(
        f"Missed fetch: source '{m['source']}' has been due since "
        f"{m['due_since'][:16].replace('T', ' ')} (Indian time) and waited {m['waiting_hours']:g} "
        f"hours for a fetch, more than {grace_hours:g}. Usually this means GitHub skipped "
        "scheduled runs: open the Actions tab and check that a run happens every 3 hours. If "
        "runs did happen but fetched nothing, the 12-hour rule has a bug." for m in missed)


def stale_sources(meta: dict, today: date, days: int = DEFAULT_DAYS) -> list[dict]:
    """Enabled sources whose last successful fetch is `days` or more days (Indian dates) ago.

    A source that has never succeeded counts as stale. Returns
    [{"source", "last_success", "days"}], with days None for "never".
    """
    stale = []
    for name, info in (meta.get("sources") or {}).items():
        if not info.get("enabled", True) or info.get("status") == "disabled":
            continue
        last = info.get("last_success")
        if not last:
            stale.append({"source": name, "last_success": None, "days": None})
            continue
        try:
            last_day = datetime.fromisoformat(last).astimezone(IST).date()
        except ValueError:
            stale.append({"source": name, "last_success": last, "days": None})
            continue
        age = (today - last_day).days
        if age >= days:
            stale.append({"source": name, "last_success": last, "days": age})
    return stale


def stale_data(meta: dict, now: datetime, hours: float = STALE_DATA_HOURS) -> str | None:
    """A message when even the newest successful fetch of any switched-on source is older than
    `hours` (the whole robot has stopped bringing in data); None when data is fresh."""
    newest = None
    for info in (meta.get("sources") or {}).values():
        if not info.get("enabled", True) or info.get("status") == "disabled" or not info.get("last_success"):
            continue
        try:
            when = datetime.fromisoformat(info["last_success"])
        except ValueError:
            continue
        newest = when if newest is None or when > newest else newest
    if newest is None:
        return "Stale data: no switched-on source has ever been fetched successfully."
    age = (now - newest).total_seconds() / 3600
    if age > hours:
        return (f"Stale data: the newest successful fetch of any source was {age:.1f} hours ago "
                f"({newest.isoformat()}), more than {hours:g} hours. The scheduled runs may have "
                "stopped, or every source is failing; see data/meta.json and the Actions tab.")
    return None


def message(stale: list[dict]) -> str:
    lines = []
    for item in stale:
        if item["days"] is None:
            when = "has never been fetched successfully" if not item["last_success"] \
                else f"has an unreadable last-success time ({item['last_success']})"
        else:
            when = (f"has had no successful fetch for {item['days']} days "
                    f"(last success {item['last_success']})")
        lines.append(f"Source '{item['source']}' {when}. Look at its last_error in data/meta.json; "
                     "the site may have changed or may be blocking us.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--stale-hours", type=float, default=STALE_DATA_HOURS)
    parser.add_argument("--missed-hours", type=float, default=MISSED_FETCH_HOURS)
    parser.add_argument("--before", metavar="FILE",
                        help="meta.json as it was before this run's build (for the missed-fetch alarm)")
    parser.add_argument("--started", metavar="TIME",
                        help="when this run started (ISO time; default: now)")
    parser.add_argument("--summary-file", metavar="FILE", help="append the result to the job summary")
    args = parser.parse_args(argv)
    path = Path(args.data_dir) / "meta.json"
    if not path.exists():
        print(f"ERROR: {path} not found; nothing to check.", file=sys.stderr)
        return 1
    meta = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(IST)
    stale = stale_sources(meta, now.date(), args.days)
    old_data = stale_data(meta, now, args.stale_hours)
    missed = missed_fetches(meta, now, args.missed_hours)
    before = Path(args.before) if args.before else None
    if before is not None and before.exists():
        started = _time(args.started) or now
        earlier = missed_fetches(json.loads(before.read_text(encoding="utf-8")), started,
                                 args.missed_hours)
        missed = earlier + [m for m in missed if m["source"] not in {e["source"] for e in earlier}]
    if not stale and not old_data and not missed:
        print(f"Heartbeat ok: every source has a successful fetch within the last {args.days} days, "
              f"the newest fetch is less than {args.stale_hours:g} hours old, and no source waited "
              f"more than {args.missed_hours:g} hours past its due time.")
        return 0
    text = chr(10).join(t for t in (old_data, message(stale) if stale else "",
                                    missed_message(missed, args.missed_hours) if missed else "") if t)
    print(text, file=sys.stderr)
    if old_data:
        print(f"::error title=Stale data::{old_data}")
    for item in missed:
        print(f"::error title=Missed fetch::{item['source']}: due for {item['waiting_hours']:g} hours "
              "without a fetch attempt")
    for item in stale:
        print(f"::error title=Source gone quiet::{item['source']}: no successful fetch for "
              f"{args.days}+ days")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as handle:
            handle.write("\n### Heartbeat FAILED\n\n" + text.replace("\n", "\n\n") + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
