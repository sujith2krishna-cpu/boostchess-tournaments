#!/usr/bin/env python3
"""One-time refresh of the stored Chess-Results tournament pages (run by hand, never by the schedule).

The daily run reads a tournament's details page only when the tournament is new or its line in
the list changed, so new reading rules (the "Rating calculation" row, the brochure rule) reach
stored events only through a refresh like this one. Two steps:

    python scripts/refresh_chessresults.py fetch CACHE_DIR   # polite: robots.txt, 3 s apart
    python scripts/refresh_chessresults.py apply CACHE_DIR   # offline: rebuilds the records

`fetch` reads each stored event's details page once into CACHE_DIR (keep it outside the
repository; the pages are not ours to publish). It stops before the first request when more
than MAX_PAGES pages would be needed. `apply` rebuilds each stored record from its saved page
with the current rules and keeps its history (first_seen, last_seen, gone_from_source). A page
that could not be fetched or read keeps the old record unchanged. Then run build_events.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventlib import DATA_DIR, SourceError, canonical, sort_key, today_in_india  # noqa: E402
from sources import chessresults_ind as cr  # noqa: E402
from sources.polite import PoliteClient  # noqa: E402

MAX_PAGES = 400  # the agreed limit for this one-time refresh
SNAPSHOT = DATA_DIR / "sources" / f"{cr.NAME}.json"
HISTORY_FIELDS = ("first_seen", "last_seen", "gone_from_source")


def _load(snapshot: Path) -> dict:
    return json.loads(snapshot.read_text(encoding="utf-8"))


def _number(event: dict) -> str:
    return event["id"].split("-", 1)[1]


def fetch(cache: Path, snapshot: Path = SNAPSHOT, client=None) -> int:
    events = _load(snapshot)["events"]
    cache.mkdir(parents=True, exist_ok=True)
    todo = [e for e in events if not (cache / f"{_number(e)}.html").exists()]
    if len(todo) > MAX_PAGES:
        print(f"{len(todo)} pages would be needed, more than {MAX_PAGES}. Nothing was fetched.")
        return 2
    if client is None:  # pages + retries + robots.txt; the agreed limit was checked above
        client = PoliteClient(cr.SITE_URL, max_requests=len(todo) * 2 + 1)
    client.load_robots()
    failed = []
    for i, event in enumerate(todo, 1):
        try:
            html = client.get(event["source_url"] + "&turdet=YES")
        except SourceError as exc:
            failed.append(f"{event['id']}: {exc}")
            continue
        (cache / f"{_number(event)}.html").write_text(html, encoding="utf-8")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} pages", flush=True)
    print(f"Fetched {len(todo) - len(failed)} of {len(todo)} pages "
          f"({client.requests_made} requests, robots.txt included).")
    for line in failed:
        print("  not fetched:", line)
    return 0


def refreshed(old: dict, details: dict, today: date) -> dict:
    """The record rebuilt from a fresh details page, with its history kept."""
    item = {"id": _number(old), "title": old["name"], "url": old["source_url"]}
    new = cr.build_event(item, details, today)
    for field in HISTORY_FIELDS:
        new[field] = old[field]
    # The old record's register link came from the list line's title, which we did not re-read.
    new["register_url"] = new["register_url"] or old.get("register_url")
    return canonical(new)


def apply(cache: Path, today: date | None = None, snapshot: Path = SNAPSHOT) -> int:
    today = today or today_in_india()
    doc = _load(snapshot)
    changed, kept, fields = 0, [], Counter()
    events = []
    for old in doc["events"]:
        old = canonical(old)
        page = cache / f"{_number(old)}.html"
        try:
            details = cr.parse_details(page.read_text(encoding="utf-8"), old["source_url"])
        except (OSError, SourceError) as exc:
            kept.append(f"{old['id']}: {exc}")
            events.append(old)
            continue
        new = refreshed(old, details, today)
        if new["start"] is None and old["start"] is not None:
            kept.append(f"{old['id']}: the page has no readable dates now")
            events.append(old)  # never overwrite good data with a bad read
            continue
        diff = [k for k in new if new[k] != old[k]]
        diff += [f"tags.{k}" for k in new["tags"] if new["tags"][k] != old["tags"][k]]
        fields.update(diff)
        changed += bool(diff)
        events.append(new)
    doc["events"] = [canonical(e) for e in sorted(events, key=sort_key)]
    snapshot.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                        newline="\n")
    print(f"{changed} of {len(events)} records changed; {len(kept)} kept as they were.")
    for field, n in sorted(fields.items()):
        print(f"  {field}: {n}")
    for line in kept:
        print("  kept:", line)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=("fetch", "apply"))
    parser.add_argument("cache", type=Path, help="folder for the saved pages (outside the repo)")
    args = parser.parse_args(argv)
    return fetch(args.cache) if args.step == "fetch" else apply(args.cache)


if __name__ == "__main__":
    raise SystemExit(main())
