"""Shared helpers for the offline tests."""
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_events as be  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "aicf_all_events_2026-11-24.html"
NOW = datetime(2026, 11, 24, 10, 30, tzinfo=be.IST)

EVENTS_HEADER = ",".join(be.EVENTS_CSV_COLUMNS) + "\n"
OVERRIDES_HEADER = ",".join(be.OVERRIDES_CSV_COLUMNS) + "\n"


def make_html(rows):
    """A tiny AICF-style page. Each row is (name, code, start, end, place_html, brochure_html)."""
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in r) + "</tr>" for r in rows
    )
    return (
        "<html><body><table><tbody><tr><th>Name of Tournament</th><th>Event Code</th>"
        "<th>Start Date</th><th>End Date</th><th>Place</th><th>Brochure</th></tr>"
        f"{body}</tbody></table></body></html>"
    )


def row(name="Test Open 2026", code="400001", start="10-12-2026", end="12-12-2026",
        place="Chennai", brochure=""):
    return (name, code, start, end, place, brochure)


def padding(n, first=500000):
    """Filler rows so a page passes the 100-row check (when a test uses the real minimum)."""
    return [row(f"Filler {i}", str(first + i), start="01-12-2026", end="02-12-2026")
            for i in range(n)]


@pytest.fixture
def data_dir(tmp_path):
    folder = tmp_path / "data"
    (folder / "manual").mkdir(parents=True)
    (folder / "manual" / "events.csv").write_text(EVENTS_HEADER, encoding="utf-8")
    (folder / "manual" / "overrides.csv").write_text(OVERRIDES_HEADER, encoding="utf-8")
    return folder


def build(folder, rows, now=NOW, min_rows=1, **kwargs):
    return be.run(folder, html=make_html(rows), now=now, min_rows=min_rows, **kwargs)


def load_doc(folder):
    return json.loads((folder / "events.json").read_text(encoding="utf-8"))


def load_events(folder):
    return load_doc(folder)["events"]


def by_id(folder):
    return {e["id"]: e for e in load_events(folder)}


def write_manual(folder, text, name="events.csv"):
    (folder / "manual" / name).write_text(text, encoding="utf-8")
