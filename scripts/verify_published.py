#!/usr/bin/env python3
"""Check the data we published on GitHub Pages.

    python scripts/verify_published.py https://<user>.github.io/<repo>/

Fetches events.json, meta.json, quality.json and review.csv from the live site and
checks: the answer is 200, the JSON files are valid JSON, the schema_version is the one
this code writes, quality.json has its target, overall, sources and review parts,
review.csv has the review columns, its counts match quality.json, and the site sends
`Access-Control-Allow-Origin: *` (the website reads the files from the browser).
Prints the headers it saw. Exit code 0 = all good, 1 = something is wrong.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventlib import SCHEMA_VERSION, USER_AGENT  # noqa: E402
from quality import REVIEW_COLUMNS  # noqa: E402

FILES = ("events.json", "meta.json", "quality.json", "review.csv")
QUALITY_PARTS = ("target", "overall", "sources", "review")
REVIEW_KINDS = {"missing": "missing", "possible_duplicate": "possible_duplicates"}
SHOWN_HEADERS = ("content-type", "access-control-allow-origin", "cache-control", "last-modified", "etag")


def fetch(url: str) -> tuple[int, dict, str]:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    return response.status_code, {k.lower(): v for k, v in response.headers.items()}, response.text


def check_file(name: str, status: int, headers: dict, body: str) -> tuple[list[str], list[str], object]:
    """(problems, lines to show, what was read) for one published file."""
    problems = []
    shown = [f"{name}: HTTP {status}"] + [f"  {h}: {headers[h]}" for h in SHOWN_HEADERS if h in headers]
    if status != 200:
        return [f"{name}: HTTP {status} (expected 200)"], shown, None
    if name.endswith(".csv"):
        data = list(csv.reader(io.StringIO(body)))
    else:
        try:
            data = json.loads(body)
        except ValueError as exc:
            return [f"{name}: not valid JSON ({exc})"], shown, None
    if headers.get("access-control-allow-origin") != "*":
        problems.append(f"{name}: Access-Control-Allow-Origin is "
                        f"{headers.get('access-control-allow-origin')!r}, expected '*'")
    if name == "events.json":
        if data.get("schema_version") != SCHEMA_VERSION:
            problems.append(f"{name}: schema_version is {data.get('schema_version')!r}, "
                            f"expected {SCHEMA_VERSION}")
        if not isinstance(data.get("events"), list) or not data["events"]:
            problems.append(f"{name}: has no events")
        else:
            shown.append(f"  schema_version {data.get('schema_version')}, {len(data['events'])} events, "
                         f"generated_at {data.get('generated_at')}")
    elif name == "quality.json":
        missing = [part for part in QUALITY_PARTS if not isinstance(data, dict) or part not in data]
        if missing:
            problems.append(f"{name}: has no {', '.join(missing)}")
            data = None
        else:
            target, review = data["target"], data["review"]
            shown.append(f"  next 30 days: {target.get('now_pct')}% fully known "
                         f"(target {target.get('fully_known_pct')}%), review list: "
                         f"{review.get('missing')} to complete, {review.get('possible_duplicates')} "
                         f"possible duplicates, generated_at {data.get('generated_at')}")
    elif name == "review.csv":
        if not data or tuple(data[0]) != REVIEW_COLUMNS:
            problems.append(f"{name}: the first line is not the review columns "
                            f"({','.join(REVIEW_COLUMNS)})")
            data = None
        else:
            counts = dict.fromkeys(REVIEW_KINDS.values(), 0)
            for number, cells in enumerate(data[1:], start=2):
                kind = cells[0] if cells else ""
                if kind not in REVIEW_KINDS or len(cells) != len(REVIEW_COLUMNS):
                    problems.append(f"{name}: line {number} is not a review line")
                    break
                counts[REVIEW_KINDS[kind]] += 1
            data = counts
            shown.append(f"  {counts['missing']} to complete, {counts['possible_duplicates']} possible duplicates")
    return problems, shown, data


def check_together(read: dict) -> list[str]:
    """Problems that show only when two files are compared: the review counts in
    quality.json must be the lines in review.csv (both come from the same build)."""
    quality, review = read.get("quality.json"), read.get("review.csv")
    if not quality or not review:
        return []
    said = {k: quality["review"].get(k) for k in review}
    if said != review:
        return [f"review.csv has {review['missing']} to complete and {review['possible_duplicates']} "
                f"possible duplicates, but quality.json says {said['missing']} and "
                f"{said['possible_duplicates']}"]
    return []


def verify(base_url: str, getter=None, attempts: int = 6, wait: float = 10.0,
           sleep=None) -> tuple[bool, list[str]]:
    """Check every published file, retrying while a fresh deployment is still spreading."""
    getter = getter or fetch
    sleep = sleep or time.sleep
    base = base_url.rstrip("/") + "/"
    report: list[str] = []
    for attempt in range(1, attempts + 1):
        report, all_problems, read = [], [], {}
        for name in FILES:
            try:
                status, headers, body = getter(base + name)
            except requests.RequestException as exc:
                all_problems.append(f"{name}: could not be fetched ({exc})")
                continue
            problems, shown, read[name] = check_file(name, status, headers, body)
            report += shown
            all_problems += problems
        all_problems += check_together(read)
        if not all_problems:
            return True, report + ["All published files look right."]
        if attempt < attempts:
            sleep(wait)
    return False, report + ["PROBLEMS:"] + [f"- {p}" for p in all_problems]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="base address of the published site")
    parser.add_argument("--summary-file", metavar="FILE")
    args = parser.parse_args(argv)
    ok, lines = verify(args.url)
    text = "\n".join(lines)
    print(text)
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as handle:
            handle.write("\n### Published data check: " + ("ok" if ok else "FAILED")
                         + "\n\n```\n" + text + "\n```\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
