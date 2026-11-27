#!/usr/bin/env python3
"""Build data/events.json and data/meta.json from the chess tournament sources.

Run from the repository root:

    python scripts/build_events.py

Sources (each its own module in scripts/sources/, switched on or off in
config/sources.json): aicf, kca, tnsca, ksca, chessfee, chessresults_ind, chessbase_calendar. Plus your
own events in data/manual/events.csv and fixes in data/manual/overrides.csv.

What a run does, in short:
  1. reads the manual files and stops with a plain-words message if a row has a mistake;
  2. for every switched-on source: reads robots.txt, fetches politely, parses; a source
     that fails (or returns less than half of last time) keeps its previous events and the
     failure is written to meta.json, while the other sources carry on;
  3. keeps history (events are never deleted), joins entries that share an AICF event
     code, flags look-alikes, applies overrides;
  4. writes events.json and meta.json (and one snapshot per source in data/sources/).

Only `requests` and `beautifulsoup4` are used besides the standard library.
"""
from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import requests  # noqa: F401  (tests patch requests.get through this module)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventlib import *  # noqa: E402,F401,F403
from eventlib import _from_iso, _iso, _key  # noqa: E402,F401
from sources import aicf, chessbase_calendar, chessfee, chessresults_ind, kca, ksca, tnsca  # noqa: E402
from sources.aicf import (MIN_ROWS, check_page_is_sane, event_from_row,  # noqa: E402,F401
                          events_from_rows, parse_html)
from sources.polite import PoliteClient  # noqa: E402
from datetime import timedelta  # noqa: E402
import daily  # noqa: E402
import dedup  # noqa: E402
import quality  # noqa: E402

SOURCE_MODULES = {
    "aicf": aicf,
    "kca": kca,
    "tnsca": tnsca,
    "ksca": ksca,
    "chessfee": chessfee,
    "chessresults_ind": chessresults_ind,
    "chessbase_calendar": chessbase_calendar,
}
CONFIG_PATH = ROOT / "config" / "sources.json"  # noqa: F405


# --------------------------------------------------------------------------
# Configuration: which sources are switched on
# --------------------------------------------------------------------------
def load_config(path: Path = CONFIG_PATH, warnings: list[str] | None = None) -> dict[str, bool]:
    """{source: enabled}. A source missing from the file is switched on."""
    enabled = {name: True for name in SOURCE_MODULES}
    if not Path(path).exists():
        if warnings is not None:
            warnings.append(f"{path} not found; every source is switched on.")
        return enabled
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError(f"config/sources.json cannot be read ({exc}). Fix the file; nothing was run.")
    if not isinstance(raw, dict):
        raise BuildError('config/sources.json must look like {"aicf": {"enabled": true}, ...}.')
    for name, setting in raw.items():
        if name not in SOURCE_MODULES:
            raise BuildError(f"config/sources.json: unknown source '{name}'. "
                             f"Known sources: {', '.join(SOURCE_MODULES)}.")
        flag = setting.get("enabled") if isinstance(setting, dict) else None
        if not isinstance(flag, bool):
            raise BuildError(f'config/sources.json: "{name}" needs {{"enabled": true}} or '
                             '{"enabled": false}.')
        enabled[name] = flag
    return enabled


# --------------------------------------------------------------------------
# History: snapshots (one file per source) and the previous events.json
# --------------------------------------------------------------------------
def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError(
            f"{path.name} exists but cannot be read ({exc}). Not overwriting it; "
            "fix or restore the file first."
        )


def restore_base(event: dict) -> dict:
    """Undo overrides on a stored event, giving the values the source itself reported."""
    event = canonical(event)
    for field, original in (event["overridden"] or {}).items():
        if field in OVERRIDABLE_FIELDS:
            event[field] = original
        elif field.startswith("tags.") and field[5:] in OVERRIDABLE_TAGS:
            event["tags"][field[5:]] = original
    event["hidden"] = False
    event["cancelled"] = False
    event["note"] = None
    event["flags"]["dates_suspect"] = event["raw_dates"] is not None
    event["overridden"] = None
    return event


def load_snapshot(data_dir: Path, name: str, previous_events: list[dict]) -> dict:
    """What we last knew about one source: {'events': [...], 'listing': {...}, 'found': n}."""
    stored = load_json(data_dir / "sources" / f"{name}.json")
    if stored is not None:
        return {"events": [canonical(e) for e in stored.get("events", [])],
                "listing": stored.get("listing", {}), "found": stored.get("found")}
    # Data written before snapshots existed: AICF events live in events.json.
    legacy = [restore_base(e) for e in previous_events if e.get("source") == name]
    return {"events": legacy, "listing": {}, "found": None}


def merge_history(scraped: list[dict], previous: list[dict], today: date) -> list[dict]:
    """Keep every event ever seen. New values win; vanished events are kept as gone."""
    old_by_id = {e["id"]: e for e in previous}
    merged, seen = [], set()
    for event in scraped:
        old = old_by_id.get(event["id"])
        if old and old.get("first_seen"):
            event["first_seen"] = old["first_seen"]
        event["last_seen"] = today.isoformat()
        event["gone_from_source"] = False
        seen.add(event["id"])
        merged.append(event)
    for event_id, old in old_by_id.items():
        if event_id not in seen:
            kept = canonical(old)
            kept["gone_from_source"] = True  # last_seen stays as it was
            merged.append(kept)
    return merged


# --------------------------------------------------------------------------
# Manual CSV files
# --------------------------------------------------------------------------
def read_csv_file(path: Path, rel: str, allowed: tuple, required: tuple,
                  errors: list[str], warnings: list[str]) -> list[tuple[int, dict]]:
    """Rows as (line number, {column: text}). Problems are appended to `errors`."""
    if not path.exists():
        warnings.append(f"{rel} not found; treated as empty.")
        return []
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        errors.append(f"{rel} line 1: the file is not UTF-8 text. In Excel use "
                      "'Save as' > 'CSV UTF-8'; on GitHub just edit it in the browser.")
        return []
    reader = csv.reader(io.StringIO(text, newline=""))
    header = None
    rows: list[tuple[int, dict]] = []
    while True:
        start_line = reader.line_num + 1
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            errors.append(f"{rel} line {start_line}: the row cannot be read ({exc}). "
                          "Check for a missing closing quote.")
            break
        if header is None:
            header = [re.sub(r"\s+", "_", c.strip().lower()) for c in cells]
            bad = [h for h in header if h not in allowed]
            missing = [c for c in required if c not in header]
            if bad:
                errors.append(f"{rel} line {start_line}: unknown column name(s): "
                              f"{', '.join(repr(h) for h in bad)}. Allowed: {', '.join(allowed)}.")
            if missing:
                errors.append(f"{rel} line {start_line}: the header row is missing the "
                              f"column(s): {', '.join(missing)}.")
            if bad or missing:
                return []
            continue
        if not any(c.strip() for c in cells):
            continue
        if len(cells) > len(header) and any(c.strip() for c in cells[len(header):]):
            errors.append(f"{rel} line {start_line}: the row has more values than the header "
                          f"has columns ({len(cells)} vs {len(header)}). If a value contains "
                          "a comma, put the value in double quotes.")
            continue
        row = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(header)}
        rows.append((start_line, row))
    if header is None:
        errors.append(f"{rel} line 1: the file is empty; it needs the header row "
                      f"({','.join(allowed)}).")
    return rows


def _date_problem(text: str, what: str) -> str:
    return (f"{what} '{text}' is not a date. Write it as DD-MM-YYYY (like 25-12-2026) "
            "or YYYY-MM-DD.")


def event_from_manual_row(line: int, row: dict, rel: str, today: date,
                          errors: list[str]) -> dict | None:
    problems: list[str] = []
    name = clean_name(strip_phones(row.get("name", "")))
    if not name:
        problems.append("the name is empty.")
    start = end = None
    if not row.get("start_date"):
        problems.append("start_date is empty.")
    else:
        start = parse_date(row["start_date"], allow_iso=True)
        if start is None:
            problems.append(_date_problem(row["start_date"], "start_date"))
    if row.get("end_date"):
        end = parse_date(row["end_date"], allow_iso=True)
        if end is None:
            problems.append(_date_problem(row["end_date"], "end_date"))
    elif start is not None:
        end = start  # no end date means a one-day event
    if start and end and end < start:
        problems.append(f"end_date {end.isoformat()} is before start_date {start.isoformat()}.")
    event_id = row.get("id", "").strip()
    if event_id:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", event_id):
            problems.append(f"id '{event_id}' may only use letters, digits, dash, "
                            "underscore and dot, without spaces.")
        elif event_id.lower().startswith("aicf-"):
            problems.append(f"id '{event_id}' starts with 'aicf-', which is reserved for AICF events.")
    elif name and start:
        event_id = "manual-" + short_hash(f"{normalise_name(name)}|{start.isoformat()}")
    country = (row.get("country") or "IN").strip().upper()
    if country not in ISO_COUNTRIES:
        problems.append(f"country '{row['country']}' is not a two-letter country code. Use IN for "
                        "India, or for example US, GB, CA, AU; leave it empty for India.")
        country = "IN"
    place_text = strip_phones(row.get("place", ""))
    place = parse_place(place_text) if country == "IN" else parse_place_abroad(country, place_text)
    state = None
    if row.get("state"):
        state, problem = resolve_state(country, row["state"])
        if problem:
            problems.append(problem)
    else:
        state = place["state"]
    tags = derive_tags(name)
    if row.get("format"):
        wanted = [t for t in re.split(r"[\s/,;&+]+", row["format"].lower()) if t]
        unknown = [t for t in wanted if t not in FORMAT_ORDER]
        if unknown:
            problems.append(f"format '{row['format']}' is not understood. Use rapid, blitz "
                            "and/or classical.")
        tags["formats"] = [f for f in FORMAT_ORDER if f in wanted or f in tags["formats"]]
    if row.get("age"):
        ages = [] if re.fullmatch(r"[\d\s,/&]+", row["age"]) else ages_from_text(row["age"])
        if not ages:
            problems.append(f"age '{row['age']}' is not understood. Write it like U11, Under-11 "
                            "or, for several groups, U12/U18.")
        else:
            tags["age"] = ages
    urls = {}
    for column, field in (("link", "register_url"), ("brochure_url", "brochure_url"),
                          ("results_url", "results_url")):
        if row.get(column):
            url = valid_url(row[column])
            if url is None or not re.match(r"https?://", row[column].strip(), re.I):
                problems.append(f"{column} '{row[column]}' is not a full web address "
                                "(it must start with http:// or https://).")
            else:
                urls[field] = url
    if problems:
        errors.extend(f"{rel} line {line}: {p}" for p in problems)
        return None
    return canonical({
        "id": event_id,
        "codes": [],
        "name": name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "place_text": place["place_text"],
        "state": state,
        "city": place["city"],
        "country": country,
        "brochure_url": urls.get("brochure_url"),
        "source": "manual",
        "register_url": urls.get("register_url"),
        "results_url": urls.get("results_url"),
        "tags": tags,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
        "note": strip_phones(row.get("note", "")) or None,
    })


def load_manual_events(data_dir: Path, today: date, errors: list[str],
                       warnings: list[str]) -> list[dict]:
    rel = "data/manual/events.csv"
    rows = read_csv_file(data_dir / "manual" / "events.csv", rel, EVENTS_CSV_COLUMNS,
                         ("name", "start_date"), errors, warnings)
    events, line_of = [], {}
    for line, row in rows:
        event = event_from_manual_row(line, row, rel, today, errors)
        if event is None:
            continue
        if event["id"] in line_of:
            errors.append(f"{rel} line {line}: id '{event['id']}' is already used on line "
                          f"{line_of[event['id']]}. Every event needs its own id.")
            continue
        line_of[event["id"]] = line
        events.append(event)
    return events


def _yes(value: str, column: str, line: int, rel: str, errors: list[str]) -> bool:
    value = value.strip().lower()
    if value in ("", "no", "n", "false", "0"):
        return False
    if value in ("yes", "y", "true", "1"):
        return True
    errors.append(f"{rel} line {line}: {column} must be 'yes' or empty, not '{value}'.")
    return False


NOT_FILLED = "?"  # review.csv's ready-made lines put "?" where a value is still to be filled in


def _yes_no(value: str, column: str, line: int, rel: str, errors: list[str]) -> bool | None:
    """'yes' -> True, 'no' -> False, empty -> None; anything else is a mistake."""
    value = value.strip().lower()
    if not value:
        return None
    if value in ("yes", "y"):
        return True
    if value in ("no", "n"):
        return False
    errors.append(f"{rel} line {line}: {column} must be 'yes' or 'no' (or empty), not '{value}'.")
    return None


def _formats_value(value: str, line: int, rel: str, errors: list[str]) -> list[str] | None:
    wanted = [t for t in re.split(r"[\s|/,;&+]+", value.strip().lower()) if t]
    unknown = [t for t in wanted if t not in FORMAT_ORDER]
    if unknown or not wanted:
        errors.append(f"{rel} line {line}: format '{value}' is not understood. Write classical, "
                      "rapid or blitz; for several, put | between them (like rapid|blitz).")
        return None
    return [f for f in FORMAT_ORDER if f in wanted]


def _ages_value(value: str, line: int, rel: str, errors: list[str]) -> list[str] | None:
    ages = []
    for part in (p.strip() for p in re.split(r"[|/,;]+", value)):
        found = ages_from_text(part) if part else []
        if len(found) != 1:
            errors.append(f"{rel} line {line}: age '{value}' is not understood. Write it like "
                          "U-9, or for several groups U-9|U-11.")
            return None
        ages.append(found[0])
    return sorted(set(ages), key=lambda a: int(a[1:]))


def load_overrides(data_dir: Path, errors: list[str], warnings: list[str]) -> list[dict]:
    rel = "data/manual/overrides.csv"
    rows = read_csv_file(data_dir / "manual" / "overrides.csv", rel, OVERRIDES_CSV_COLUMNS,
                         ("key",), errors, warnings)
    overrides = []
    for line, row in rows:
        unfilled = [c for c, v in row.items() if c != "key" and v.strip() == NOT_FILLED]
        if unfilled:
            warnings.append(f"{rel} line {line}: {', '.join(unfilled)} still "
                            f"{'has' if len(unfilled) == 1 else 'have'} '{NOT_FILLED}'; fill in the "
                            "value or leave it empty. Until then it is ignored.")
            row = {c: ("" if c in unfilled else v) for c, v in row.items()}
        item = {"line": line, "key": row.get("key", "").strip()}
        if not item["key"]:
            errors.append(f"{rel} line {line}: key is empty. Put the event id or the 6-digit "
                          "AICF code there.")
            continue
        for column in ("start_date", "end_date"):
            item[column] = None
            if row.get(column):
                item[column] = parse_date(row[column], allow_iso=True)
                if item[column] is None:
                    errors.append(f"{rel} line {line}: " + _date_problem(row[column], column))
        item["place"] = row.get("place") or None
        item["state"] = row.get("state") or None  # checked against each event's country later
        item["hide"] = _yes(row.get("hide", ""), "hide", line, rel, errors)
        item["cancelled"] = _yes(row.get("cancelled", ""), "cancelled", line, rel, errors)
        item["note"] = row.get("note") or None
        for column in ("register_url", "results_url"):
            item[column] = None
            value = (row.get(column) or "").strip()
            if value:
                url = valid_url(value)
                if url is None or not re.match(r"https?://", value, re.I):
                    errors.append(f"{rel} line {line}: {column} '{value}' is not a full web address "
                                  "(it must start with http:// or https://).")
                else:
                    item[column] = url
        item["fide_rated"] = _yes_no(row.get("fide_rated", ""), "fide_rated", line, rel, errors)
        item["formats"] = (_formats_value(row["format"], line, rel, errors)
                           if (row.get("format") or "").strip() else None)
        item["age"] = _ages_value(row["age"], line, rel, errors) if (row.get("age") or "").strip() else None
        item["registration_deadline"] = None
        if (row.get("registration_deadline") or "").strip():
            deadline = parse_date(row["registration_deadline"], allow_iso=True)
            if deadline is None:
                errors.append(f"{rel} line {line}: "
                              + _date_problem(row["registration_deadline"], "registration_deadline"))
            else:
                item["registration_deadline"] = deadline.isoformat()
        overrides.append(item)
    return overrides


def _change(event: dict, field: str, value) -> None:
    """Set a field (or "tags.<name>"), remembering the value it replaced in `overridden`."""
    if field.startswith("tags."):
        holder, name = event["tags"], field[5:]
    else:
        holder, name = event, field
    if holder[name] != value:
        if event["overridden"] is None:
            event["overridden"] = {}
        event["overridden"].setdefault(field, copy.deepcopy(holder[name]))
        holder[name] = copy.deepcopy(value)


def _override_targets(events: list[dict]):
    """(targets(key) -> the events an overrides.csv key names, {id: event})."""
    by_id = {e["id"]: e for e in events}
    by_code = defaultdict(list)
    for event in events:
        for code in event["codes"]:
            by_code[code].append(event)

    def targets(key: str) -> list[dict]:
        found = [by_id[key]] if key in by_id else list(by_code.get(key, []))
        if len(found) > 1 and any(e["source"] == "aicf" for e in found):
            found = [e for e in found if e["source"] == "aicf"]  # the code is AICF's own
        return found
    return targets, by_id


def _apply_manual_values(event: dict, item: dict) -> None:
    """format / fide_rated / age / registration_deadline from overrides.csv: they win over all."""
    if item.get("formats") is not None:
        _change(event, "tags.formats", item["formats"])
    if item.get("fide_rated") is not None:
        _change(event, "tags.fide_rated", item["fide_rated"])
        _change(event, "tags.fide_how", "manual")
    if item.get("age") is not None:
        _change(event, "tags.age", item["age"])
    if item.get("registration_deadline"):
        _change(event, "registration_deadline", item["registration_deadline"])


def reapply_manual_values(events: list[dict], overrides: list[dict]) -> None:
    """After grouping: put the manual values back (grouping may have joined other records' tags
    into a primary), on the event the line names and on the primary of its group."""
    targets, by_id = _override_targets(events)
    for item in overrides:
        for event in targets(item["key"]):
            _apply_manual_values(event, item)
            primary = by_id.get(event["merged_into"]) if event["merged_into"] else None
            if primary is not None:
                _apply_manual_values(primary, item)


def apply_overrides(events: list[dict], overrides: list[dict], errors: list[str],
                    warnings: list[str]) -> None:
    """Override > manual > scraped. Changes `events` in place."""
    rel = "data/manual/overrides.csv"
    targets_for, _ = _override_targets(events)
    change = _change

    for item in overrides:
        key = item["key"]
        targets = targets_for(key)
        if not targets:
            warnings.append(f"{rel} line {item['line']}: no event has the id or code '{key}'; "
                            "this row was ignored.")
            continue
        if len(targets) > 1:
            warnings.append(f"{rel} line {item['line']}: the code '{key}' belongs to "
                            f"{len(targets)} events, so the row was applied to all of them. "
                            "Use the event id to pick one.")
        for event in targets:
            country = event["country"] or "IN"
            state_value = None
            if item["state"]:
                state_value, problem = resolve_state(country, item["state"])
                if problem:
                    errors.append(f"{rel} line {item['line']}: {problem}")
                    continue
            if item["start_date"] or item["end_date"]:
                new_start = item["start_date"].isoformat() if item["start_date"] else event["start"]
                new_end = item["end_date"].isoformat() if item["end_date"] else event["end"]
                if new_start and new_end and new_end < new_start:
                    errors.append(f"{rel} line {item['line']}: these dates would put the end "
                                  f"({new_end}) before the start ({new_start}) for event "
                                  f"'{event['id']}'.")
                    continue
                change(event, "start", new_start)
                change(event, "end", new_end)
                event["flags"]["dates_suspect"] = not (
                    event["start"] and event["end"] and event["end"] >= event["start"]
                )
            if item["place"]:
                place = (parse_place(item["place"]) if country == "IN"
                         else parse_place_abroad(country, item["place"]))
                change(event, "place_text", place["place_text"])
                change(event, "city", place["city"])
                change(event, "state", state_value or place["state"])
            elif state_value:
                change(event, "state", state_value)
            if item["hide"]:
                event["hidden"] = True
            if item["cancelled"]:
                event["cancelled"] = True
            if item["note"]:
                event["note"] = item["note"]
            for field in ("register_url", "results_url"):
                if item[field]:
                    change(event, field, item[field])
            _apply_manual_values(event, item)



# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def dump_json(obj) -> bytes:
    """Same data always gives the same bytes: fixed key order, 2 spaces, UTF-8, LF."""
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_files(data_dir: Path, payloads: dict[str, bytes]) -> None:
    """Write every file to a temporary name first, then swap them in."""
    data_dir.mkdir(parents=True, exist_ok=True)
    temporary = {}
    try:
        for name, payload in payloads.items():
            target = data_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.name}.tmp")
            tmp.write_bytes(payload)
            temporary[name] = tmp
        for name, tmp in temporary.items():
            os.replace(tmp, data_dir / name)
    finally:
        for tmp in temporary.values():
            if tmp.exists():
                tmp.unlink()



# --------------------------------------------------------------------------
# Duplicates across sources: pairs.csv, tags, the review file
# --------------------------------------------------------------------------
_PAIR_DECISIONS = {"same": "same", "not_same": "not_same", "not same": "not_same",
                   "notsame": "not_same", "different": "not_same",
                   # a pair someone still has to check: kept in the file, changes nothing
                   "undecided": "undecided"}


def load_pairs(data_dir: Path, errors: list[str], warnings: list[str]) -> list[dict]:
    """data/manual/pairs.csv: force two event ids to be the same tournament, or not. Optional."""
    rel = "data/manual/pairs.csv"
    path = data_dir / "manual" / "pairs.csv"
    if not path.exists():
        return []
    rows = read_csv_file(path, rel, PAIRS_CSV_COLUMNS, ("id_a", "id_b", "decision"), errors, warnings)
    pairs, seen = [], {}
    for line, row in rows:
        a, b = row.get("id_a", "").strip(), row.get("id_b", "").strip()
        decision = _PAIR_DECISIONS.get(re.sub(r"\s+", " ", row.get("decision", "").strip().lower()))
        problems = []
        if not a or not b:
            problems.append("id_a and id_b both need an event id (like aicf-502180 and chessfee-1800).")
        elif a == b:
            problems.append(f"id_a and id_b are the same id ('{a}'); a pair needs two different events.")
        if decision is None:
            problems.append(f"decision '{row.get('decision', '')}' is not understood. Write 'same', "
                            "'not_same' or 'undecided'.")
        if problems:
            errors.extend(f"{rel} line {line}: {p}" for p in problems)
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            errors.append(f"{rel} line {line}: the pair {a} / {b} is already on line {seen[key]}. "
                          "Keep one line per pair.")
            continue
        seen[key] = line
        pairs.append({"line": line, "a": a, "b": b, "decision": decision,
                      "note": (row.get("note") or "").strip() or None})
    return pairs


def fill_tags(event: dict) -> None:
    """Fill format / FIDE gaps from the name and the source's category labels (evidence only)."""
    text = " ".join([event["name"] or ""] + list(event["tags"]["categories"] or []))
    if not event["tags"]["formats"]:
        event["tags"]["formats"] = formats_in(text)
    # A KCA "STATE" event is rated by the state association; its name alone says nothing more.
    if event["tags"]["fide_rated"] is None and kca.STATE_CATEGORY not in event["tags"]["categories"]:
        event["tags"]["fide_rated"], event["tags"]["fide_how"] = fide_evidence(text)
    # AICF's national / state / Asian championships are rated, though their names never say so.
    if event["tags"]["fide_rated"] is None and event["source"] == "aicf" \
            and aicf_championship_rated(event["name"] or ""):
        event["tags"]["fide_rated"], event["tags"]["fide_how"] = True, "inferred"
    # "FIDE Open / Chess / Tournament" in the name: an inferred yes is a stated yes (label only).
    if event["tags"]["fide_rated"] is True and event["tags"]["fide_how"] == "inferred" \
            and fide_named(event["name"] or ""):
        event["tags"]["fide_how"] = "stated"


# Sources whose `codes` are AICF codes read from their own titles (the state associations keep
# their own codes there).
CODES_FROM_NAME_SOURCES = frozenset({"chessfee", "chessresults_ind", "chessbase_calendar"})
_TN_STATE_LEVEL = re.compile(r"(?i)\btamil\s*nadu\s+state\s+level\b")  # chessfee's category label


def fill_codes_and_state(event: dict) -> None:
    """AICF codes in the name, and a missing Indian state from what the pages say (evidence only).

    The state is filled only when it is empty, in this order: chessfee's category
    "TAMILNADU STATE LEVEL ..." (the site says so); the state letters of a full-form AICF code
    in the name ("499268/KA(R)/2026"); exactly one known town in the venue text.
    """
    if event["source"] in CODES_FROM_NAME_SOURCES:
        codes = list(event["codes"] or [])
        event["codes"] = codes + [c for c in aicf_codes_in(event["name"]) if c not in codes]
    if event["state"] is not None or event["country"] != "IN":
        return
    if event["source"] == "chessfee" and any(_TN_STATE_LEVEL.search(c or "")
                                             for c in event["tags"]["categories"]):
        event["state"] = "Tamil Nadu"
        return
    event["state"] = aicf_code_state_in(event["name"]) or town_state_in(event["place_text"])


def review_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=dedup.REVIEW_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


# --------------------------------------------------------------------------
# The whole run
# --------------------------------------------------------------------------
def _source_meta(previous: dict | None, now_iso: str) -> dict:
    previous = previous or {}
    return {"last_success": previous.get("last_success"), "last_error": previous.get("last_error")}


def fetch_due_at(last_success: str | None, hours: float | None) -> datetime | None:
    """When a source may be fetched again (None = right away)."""
    if not hours or not last_success:
        return None
    try:
        return datetime.fromisoformat(last_success).astimezone(IST) + timedelta(hours=hours)
    except ValueError:
        return None


def _count(snapshot: dict) -> int:
    return sum(1 for e in snapshot["events"] if not e["gone_from_source"])


def run(data_dir=DATA_DIR, *, html: str | None = None, now: datetime | None = None,
        min_rows: int = MIN_ROWS, config: dict | None = None,
        min_hours_between_fetches: float | None = None) -> dict:
    """Do a full build. Returns a report; raises BuildError (and writes nothing) on trouble.

    `html` is a saved AICF page (offline use); with it, only AICF is read unless `config` says more.
    `min_hours_between_fetches` (12 for the command line) skips a source fetched more recently
    than that; None fetches every switched-on source.
    """
    data_dir = Path(data_dir)
    now = (now or datetime.now(IST)).astimezone(IST).replace(microsecond=0)
    today = now.date()
    now_iso = now.isoformat()
    warnings: list[str] = []
    offline = config is None and html is not None
    if config is None:
        config = ({"aicf": True, **{n: False for n in SOURCE_MODULES if n != "aicf"}}
                  if offline else load_config(warnings=warnings))

    previous_doc = load_json(data_dir / "events.json") or {}
    previous_meta = load_json(data_dir / "meta.json") or {}
    previous_events = previous_doc.get("events", [])
    previous_sources = previous_meta.get("sources") or {}
    previous_quality = load_json(data_dir / "quality.json")
    previous_review = (data_dir / "review.csv").read_bytes() if (data_dir / "review.csv").exists() else None

    # Hand-edited files first: a typo there should stop us before we fetch anything.
    errors: list[str] = []
    manual_events = load_manual_events(data_dir, today, errors, warnings)
    overrides = load_overrides(data_dir, errors, warnings)
    pairs = load_pairs(data_dir, errors, warnings)
    if errors:
        raise DataFileError("Nothing was written. Please fix:\n  " + "\n  ".join(errors))

    snapshots, source_meta, source_stats = {}, {}, {}
    blocked: set[str] = set()
    problems: list[str] = []
    attempted = succeeded = 0
    for name in AUTOMATIC_SOURCES:
        module = SOURCE_MODULES[name]
        snapshot = load_snapshot(data_dir, name, previous_events)
        before = previous_sources.get(name)
        if before is None and name == "aicf" and previous_meta.get("generated_at"):
            before = {"last_success": previous_meta["generated_at"]}  # data from before sources[]
        meta = {"enabled": bool(config.get(name, False)), "status": "ok", "message": None,
                **_source_meta(before, now_iso)}
        stats = {"requests": 0, "due": True}
        due_at = fetch_due_at(meta["last_success"], min_hours_between_fetches)
        if not meta["enabled"]:
            meta.update(status="disabled", message=("not read in offline mode (--html)" if offline
                                                    else "switched off in config/sources.json"))
            stats["due"] = False
        elif due_at is not None and due_at > now:
            # Not due yet: nothing is fetched and what meta.json says about it stays as it was.
            before = before or {}
            meta.update(status=before.get("status", "ok"), message=before.get("message"))
            stats["due"] = False
            succeeded += 1
        else:
            attempted += 1
            client = PoliteClient(module.SITE_URL)
            options = {"html": html, "min_rows": min_rows} if name == "aicf" else {}
            try:
                if not (name == "aicf" and html is not None):
                    client.load_robots()  # robots.txt first, at the start of every run
                scraped, listing, found_stats = module.fetch(client, snapshot, today, **options)
                found = found_stats.get("found", len(scraped))
                known = snapshot.get("found") or _count(snapshot)
                if known >= 5 and found < known * MIN_FRACTION_OF_PREVIOUS:  # noqa: F405
                    raise SourceError(f"{name} returned {found} events, fewer than half of the "
                                      f"{known} from the previous run. Its previous events were kept.")
                snapshot = {"events": merge_history(scraped, snapshot["events"], today),
                            "listing": listing, "found": found}
                stats.update(found_stats)
                meta["last_success"] = now_iso
                succeeded += 1
            except SourceSkipped as exc:
                blocked.add(name)
                meta.update(status="skipped", message=str(exc))
                meta["last_error"] = {"at": now_iso, "message": str(exc)}
                problems.append(f"{name}: {exc}")
            except Exception as exc:  # one broken site must never stop the others
                text = str(exc) if isinstance(exc, BuildError) else f"{type(exc).__name__}: {exc}"
                meta.update(status="failed", message=text)
                meta["last_error"] = {"at": now_iso, "message": text}
                problems.append(f"{name}: {text}")
            stats["requests"] = client.requests_made
        meta["count"] = _count(snapshot)
        next_due = fetch_due_at(meta["last_success"], min_hours_between_fetches or FETCH_INTERVAL_HOURS)
        meta["next_due"] = (None if not meta["enabled"]
                            else (max(next_due, now) if next_due else now).isoformat())
        snapshots[name], source_meta[name], source_stats[name] = snapshot, meta, stats

    if attempted and succeeded == 0:
        raise SourceError("No source could be read, so nothing was written. "
                          + " | ".join(problems))

    # ---- tags, overrides, then grouping ---------------------------------------------
    entries = [e for name in AUTOMATIC_SOURCES for e in snapshots[name]["events"]]
    entries.extend(manual_events)
    previous_manual = {e["id"]: e for e in previous_events if e.get("source") == "manual"}
    for event in manual_events:
        old = previous_manual.get(event["id"])
        if old and old.get("first_seen"):
            event["first_seen"] = old["first_seen"]
    # Every record stays; the records of one tournament are grouped, never removed.
    events = [canonical({**e, "sources": None}) for e in entries]
    for event in events:
        fill_tags(event)
        fill_codes_and_state(event)
    apply_overrides(events, overrides, errors, warnings)
    if errors:
        raise DataFileError("Nothing was written. Please fix:\n  " + "\n  ".join(errors))
    grouping = dedup.group_events(events, pairs, warnings)
    reapply_manual_values(events, overrides)
    in_groups = Counter(e["group_id"] for e in events)
    joined = Counter(e["source"] for e in events if in_groups[e["group_id"]] > 1)
    duplicates = grouping["possible"]

    events = sorted((canonical(e) for e in events), key=sort_key)
    meta = {
        "generated_at": now_iso,
        "last_run_at": now_iso,
        "scraped_count": sum(1 for e in events if e["source"] != "manual" and not e["gone_from_source"]),
        "manual_count": sum(1 for e in events if e["source"] == "manual"),
        "total": len(events),
        "suspect_dates_count": sum(1 for e in events if e["flags"]["dates_suspect"]),
        "missing_state_count": sum(1 for e in events if e["state"] is None),
        "gone_from_source_count": sum(1 for e in events if e["gone_from_source"]),
        "groups_count": grouping["groups"],
        "merged_count": grouping["merged"],
        "possible_duplicates_count": duplicates,
        "sources": source_meta,
    }
    document = {"schema_version": SCHEMA_VERSION, "generated_at": now_iso, "events": events}
    review_rows = quality.review_rows(events, today)
    review_bytes = quality.review_csv(review_rows)
    quality_doc = quality.quality_report(events, today, now_iso, previous_quality,
                                         quality.review_counts(review_rows))
    # The review list and the quality numbers count as real changes (a new day can change
    # them); their times, dates and the comparison with the run before do not.
    timestamps_only = (only_timestamps_changed(previous_doc, previous_meta, document, meta)
                       and quality.comparable(previous_quality) == quality.comparable(quality_doc)
                       and previous_review == review_bytes)
    payloads = {"events.json": dump_json(document), "meta.json": dump_json(meta),
                "review/dedup_review.csv": review_csv(grouping["review"]),
                "quality.json": dump_json(quality_doc), "review.csv": review_bytes}
    for name, snapshot in snapshots.items():
        if snapshot["events"] or (data_dir / "sources" / f"{name}.json").exists():
            payloads[f"sources/{name}.json"] = dump_json({
                "source": name, "found": snapshot["found"], "listing": snapshot["listing"],
                "events": [canonical(e) for e in sorted(snapshot["events"], key=sort_key)]})
    write_files(data_dir, payloads)

    visible = [e for e in events if not e["hidden"]]
    per_source = {}
    for name in AUTOMATIC_SOURCES:
        live = [e for e in snapshots[name]["events"] if not e["gone_from_source"]]
        per_source[name] = {
            "status": source_meta[name]["status"], "message": source_meta[name]["message"],
            "blocked": name in blocked, "due": source_stats[name].get("due", True),
            "next_due": source_meta[name]["next_due"],
            "requests": source_stats[name].get("requests", 0), "found": len(live),
            "by_status": dict(Counter(status(e, today) for e in live)),
            "with_register_url": sum(1 for e in live if e["register_url"]),
            "joined": joined[name], "stats": source_stats[name],
            "possible_duplicates": sum(1 for e in events
                                       if e["source"] == name and e["flags"]["possible_duplicate_of"]),
        }
    aicf_stats = source_stats.get("aicf", {})
    return {
        "meta": meta,
        "today": today.isoformat(),
        "rows_on_page": aicf_stats.get("rows_on_page", 0),
        "rows_skipped": aicf_stats.get("rows_skipped", 0),
        "duplicate_rows_collapsed": aicf_stats.get("duplicate_rows_collapsed", 0),
        "new_events": sum(1 for e in events if e["first_seen"] == today.isoformat()
                          and e["source"] != "manual"),
        "status_counts": dict(Counter(status(e, today) for e in visible)),
        "hidden_count": len(events) - len(visible),
        "cancelled_count": sum(1 for e in events if e["cancelled"]),
        "missing_brochure_count": sum(1 for e in events if e["brochure_url"] is None),
        "possible_duplicates": duplicates,
        "groups": grouping["groups"],
        "multi_groups": grouping["multi_groups"],
        "merged": grouping["merged"],
        "per_source": per_source,
        "only_timestamps_changed": timestamps_only,
        "fetched_any": any(source_stats[n].get("due") for n in AUTOMATIC_SOURCES),
        "changes": count_changes(previous_events, events),
        "warnings": warnings,
        "quality": quality_doc,
        "events": events,
    }


def print_summary(report: dict) -> None:
    meta = report["meta"]
    counts = report["status_counts"]
    print(f"Done. Today in India: {report['today']}")
    for name, info in report["per_source"].items():
        by = info["by_status"]
        line = (f"  {name:<19}: {info['status']:<8} {info['found']:>4} events "
                f"(ongoing {by.get('ongoing', 0)}, upcoming {by.get('upcoming', 0)}, "
                f"past {by.get('past', 0)}), {info['with_register_url']} with a register link, "
                f"{info['requests']} requests")
        print(line + (f" -- {info['message']}" if info["message"] else ""))
    print(f"  Total events          : {meta['total']} "
          f"(automatic {meta['scraped_count']}, manual {meta['manual_count']}, "
          f"gone from source {meta['gone_from_source_count']})")
    print(f"  Same tournament       : {report['multi_groups']} groups of 2 or more, "
          f"{report['merged']} records merged into another (all kept); "
          f"possible duplicates flagged: {report['possible_duplicates']}")
    print(f"  Suspect dates         : {meta['suspect_dates_count']}")
    print(f"  Missing state         : {meta['missing_state_count']}")
    print(f"  Missing brochure      : {report['missing_brochure_count']}")
    print(f"  Hidden / cancelled    : {report['hidden_count']} / {report['cancelled_count']}")
    print("  By status (not hidden): "
          + ", ".join(f"{name} {counts.get(name, 0)}"
                      for name in ("ongoing", "upcoming", "past", "unknown")))
    q = report.get("quality")
    if q:
        m = q["overall"]["next_30_days"]
        print(f"  Quality, next 30 days : {m['events']} shown events, "
              f"{'-' if m['fully_known_pct'] is None else m['fully_known_pct']}% fully known "
              f"(target {q['target']['fully_known_pct']:g}%); review list: "
              f"{q['review']['missing']} to complete, {q['review'].get('dates_disagree', 0)} dates "
              f"disagree, {q['review']['possible_duplicates']} possible duplicates (data/review.csv)")
        for alert in q["alerts"]:
            print(f"  QUALITY ALERT: {alert['message']}")
    print("  Changes vs last run   : "
          + ("none, only last_seen/generated_at differ" if report["only_timestamps_changed"]
             else "real changes"))
    for warning in report["warnings"]:
        print(f"  WARNING: {warning}")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Build data/events.json from the chess sources.")
    parser.add_argument("--html", help="read this saved AICF page instead of fetching (offline; "
                                       "only AICF is read)")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="where data/ lives")
    parser.add_argument("--force", action="store_true",
                        help=f"fetch every source now, even if it was fetched less than "
                             f"{FETCH_INTERVAL_HOURS} hours ago (a deliberate manual refresh)")
    parser.add_argument("--github-output", metavar="FILE",
                        help="append 'real_changes=true|false' and 'commit_message=...' to FILE "
                             "(for a GitHub Action)")
    parser.add_argument("--summary-file", metavar="FILE",
                        help="append a markdown summary of the run to FILE (the job summary)")
    args = parser.parse_args(argv)
    try:
        html = Path(args.html).read_text(encoding="utf-8") if args.html else None
        interval = None if args.force or html is not None else FETCH_INTERVAL_HOURS
        report = run(args.data_dir, html=html, min_hours_between_fetches=interval)
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        daily.write_summary(args.summary_file, daily.failure_markdown(str(exc)))
        if daily.running_in_github():
            print(f"::error title=Tournament data run failed::{str(exc).splitlines()[0]}")
        if not isinstance(exc, DataFileError):
            print("Existing data was left untouched.", file=sys.stderr)
        return exc.exit_code
    print_summary(report)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"real_changes={'false' if report['only_timestamps_changed'] else 'true'}\n")
            handle.write(f"commit_message={daily.commit_message(report)}\n")
    daily.write_summary(args.summary_file, daily.summary_markdown(report))
    if daily.running_in_github():
        for line in daily.annotations(report):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
