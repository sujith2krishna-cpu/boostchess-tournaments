#!/usr/bin/env python3
"""Check the data we published on GitHub Pages.

    python scripts/verify_published.py https://<user>.github.io/<repo>/

Fetches events.json and meta.json from the live site and checks: the answer is 200,
the text is valid JSON, the schema_version is the one this code writes, and the site
sends `Access-Control-Allow-Origin: *` (the website reads the file from the browser).
Prints the headers it saw. Exit code 0 = all good, 1 = something is wrong.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventlib import SCHEMA_VERSION, USER_AGENT  # noqa: E402

FILES = ("events.json", "meta.json")
SHOWN_HEADERS = ("content-type", "access-control-allow-origin", "cache-control", "last-modified", "etag")


def fetch(url: str) -> tuple[int, dict, str]:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    return response.status_code, {k.lower(): v for k, v in response.headers.items()}, response.text


def check_file(name: str, status: int, headers: dict, body: str) -> tuple[list[str], list[str]]:
    """(problems, lines to show) for one published file."""
    problems = []
    shown = [f"{name}: HTTP {status}"] + [f"  {h}: {headers[h]}" for h in SHOWN_HEADERS if h in headers]
    if status != 200:
        return [f"{name}: HTTP {status} (expected 200)"], shown
    try:
        data = json.loads(body)
    except ValueError as exc:
        return [f"{name}: not valid JSON ({exc})"], shown
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
    return problems, shown


def verify(base_url: str, getter=None, attempts: int = 6, wait: float = 10.0,
           sleep=None) -> tuple[bool, list[str]]:
    """Check both files, retrying while a fresh deployment is still spreading."""
    getter = getter or fetch
    sleep = sleep or time.sleep
    base = base_url.rstrip("/") + "/"
    report: list[str] = []
    for attempt in range(1, attempts + 1):
        report, all_problems = [], []
        for name in FILES:
            try:
                status, headers, body = getter(base + name)
            except requests.RequestException as exc:
                all_problems.append(f"{name}: could not be fetched ({exc})")
                continue
            problems, shown = check_file(name, status, headers, body)
            report += shown
            all_problems += problems
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
