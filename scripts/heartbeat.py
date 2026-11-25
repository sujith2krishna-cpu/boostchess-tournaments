#!/usr/bin/env python3
"""Heartbeat: fail loudly when a source has not been fetched successfully for 3 days.

    python scripts/heartbeat.py [--data-dir data] [--days 3]

Reads data/meta.json (written by build_events.py). Sources switched off in
config/sources.json are not checked. Exit code 0 = fine, 1 = a source has gone quiet.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventlib import DATA_DIR, IST  # noqa: E402

DEFAULT_DAYS = 3  # was 7; a healthy source is fetched every 12 hours
STALE_DATA_HOURS = 30


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
    if not stale and not old_data:
        print(f"Heartbeat ok: every source has a successful fetch within the last {args.days} days, "
              f"and the newest fetch is less than {args.stale_hours:g} hours old.")
        return 0
    text = chr(10).join(t for t in (old_data, message(stale) if stale else "") if t)
    print(text, file=sys.stderr)
    if old_data:
        print(f"::error title=Stale data::{old_data}")
    for item in stale:
        print(f"::error title=Source gone quiet::{item['source']}: no successful fetch for "
              f"{args.days}+ days")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as handle:
            handle.write("\n### Heartbeat FAILED\n\n" + text.replace("\n", "\n\n") + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
