#!/usr/bin/env python3
"""Weekly heartbeat: fail loudly when a source has not been fetched successfully for 7 days.

    python scripts/heartbeat.py [--data-dir data] [--days 7]

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

DEFAULT_DAYS = 7


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
    parser.add_argument("--summary-file", metavar="FILE", help="append the result to the job summary")
    args = parser.parse_args(argv)
    path = Path(args.data_dir) / "meta.json"
    if not path.exists():
        print(f"ERROR: {path} not found; nothing to check.", file=sys.stderr)
        return 1
    meta = json.loads(path.read_text(encoding="utf-8"))
    stale = stale_sources(meta, datetime.now(IST).date(), args.days)
    if not stale:
        print(f"Heartbeat ok: every source has a successful fetch within the last {args.days} days.")
        return 0
    text = message(stale)
    print(text, file=sys.stderr)
    for item in stale:
        print(f"::error title=Source gone quiet::{item['source']}: no successful fetch for "
              f"{args.days}+ days")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as handle:
            handle.write("\n### Heartbeat FAILED\n\n" + text.replace("\n", "\n\n") + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
