"""Turning AICF rows into clean events: codes, places, dates, tags, links."""
from datetime import date, datetime, timezone

import pytest

import build_events as be
from conftest import FIXTURE, NOW, build, by_id, load_events, row

TODAY = NOW.date()


def one(folder, **kwargs):
    build(folder, [row(**kwargs)])
    return next(iter(by_id(folder).values()))


# ---- codes --------------------------------------------------------------
def test_two_codes_and_under_11_open_girls_fide_rated(data_dir):
    event = one(data_dir,
                name="WB State Under – 11 Open/Girls FIDE Rated Chess Championship 2026",
                code="472290/472291")
    assert event["id"] == "aicf-472290"
    assert event["codes"] == ["472290", "472291"]
    assert event["tags"] == {"formats": [], "fide_rated": True, "fide_how": "stated", "age": ["U11"],
                             "open": True, "girls": True, "categories": []}


def test_abbreviated_second_code_is_expanded(data_dir):
    event = one(data_dir, code="472175/76")
    assert event["codes"] == ["472175", "472176"]
    assert event["flags"]["code_expanded"] is True


def test_messy_code_cell_with_many_codes(data_dir):
    event = one(data_dir, code="502253 | 502251 | 502249I 502254")
    assert event["codes"] == ["502253", "502251", "502249", "502254"]


def test_missing_code_gets_stable_hash_id():
    def make(name, start):
        return be.event_from_row(
            {"name": name, "code": "", "start": start, "end": start, "place": "", "hrefs": []}, TODAY)

    first = make("No Code Open", "01-12-2026")
    assert first["codes"] == []
    assert first["id"].startswith("aicf-") and len(first["id"]) == 13
    assert make("No  code OPEN", "01-12-2026")["id"] == first["id"]  # spacing, capitals: same id
    assert make("No Code Open", "02-12-2026")["id"] != first["id"]


# ---- brochure -----------------------------------------------------------
def test_brochure_link_is_absolute_even_when_the_word_is_split(data_dir):
    event = one(data_dir, brochure='D<a href="/wp-content/uploads/x.pdf">ownload</a>')
    assert event["brochure_url"] == "https://aicf.in/wp-content/uploads/x.pdf"


def test_missing_brochure_is_null(data_dir):
    assert one(data_dir, brochure="")["brochure_url"] is None


@pytest.mark.parametrize("href", ["http://475826", "http://Visakhapatnam", "#", ""])
def test_junk_brochure_links_are_dropped(data_dir, href):
    assert one(data_dir, brochure=f'<a href="{href}">Download</a>')["brochure_url"] is None


# ---- places -------------------------------------------------------------
def test_place_on_a_second_line(data_dir):
    event = one(data_dir, place="Banka,<br>Bihar")
    assert (event["place_text"], event["city"], event["state"]) == ("Banka, Bihar", "Banka", "Bihar")


def test_state_only_place(data_dir):
    event = one(data_dir, place="Karnataka")
    assert (event["place_text"], event["city"], event["state"]) == ("Karnataka", None, "Karnataka")


@pytest.mark.parametrize("raw, city, state", [
    ("Jabalpur\xa0,\nMP", "Jabalpur", "Madhya Pradesh"),
    ("Chennai\n,\nTamil Nadu", "Chennai", "Tamil Nadu"),
    ("Chennai", "Chennai", "Tamil Nadu"),            # well-known city
    ("Miyapur,\nHyderabad", "Miyapur", "Telangana"),
    ("Bilaspur", "Bilaspur", None),                  # two states have a Bilaspur: stay null
    ("Udaipur", "Udaipur", None),
    ("Jammu", None, "Jammu and Kashmir"),
    ("", None, None),
])
def test_place_best_effort(raw, city, state):
    parsed = be.parse_place(raw)
    assert (parsed["city"], parsed["state"]) == (city, state)


# ---- dates --------------------------------------------------------------
def test_one_day_event(data_dir):
    event = one(data_dir, start="05-04-2026", end="05-04-2026")
    assert (event["start"], event["end"]) == ("2026-04-05", "2026-04-05")
    assert event["flags"]["dates_suspect"] is False and event["raw_dates"] is None


def test_unpadded_date_is_read_normally(data_dir):
    event = one(data_dir, start="12-4-2026", end="12-4-2026")
    assert event["start"] == "2026-04-12" and event["flags"]["dates_suspect"] is False


def test_end_before_start_is_kept_and_flagged_not_fixed(data_dir):
    event = one(data_dir, start="29-04-2026", end="03-04-2026")
    assert (event["start"], event["end"]) == ("2026-04-29", "2026-04-03")
    assert event["flags"]["dates_suspect"] is True
    assert event["raw_dates"] == {"start": "29-04-2026", "end": "03-04-2026"}


def test_malformed_year_keeps_event_and_raw_text(data_dir):
    event = one(data_dir, start="18-09-2026", end="20-092-2026")
    assert event["start"] == "2026-09-18" and event["end"] is None
    assert event["flags"]["dates_suspect"] is True
    assert event["raw_dates"] == {"start": "18-09-2026", "end": "20-092-2026"}


@pytest.mark.parametrize("start", ["12-04-26", "-03-10-2026", "", "31-02-2026"])
def test_unusable_start_is_never_dropped(data_dir, start):
    event = one(data_dir, start=start, end="04-10-2026")
    assert event["start"] is None and event["flags"]["dates_suspect"] is True
    assert event["raw_dates"]["start"] == start


def test_valid_date_with_an_impossible_year_is_flagged_but_kept(data_dir):
    event = one(data_dir, start="10-12-2062", end="11-12-2062")
    assert event["start"] == "2062-12-10" and event["flags"]["dates_suspect"] is True


def test_sorted_by_start_with_unusable_dates_last(data_dir):
    build(data_dir, [
        row("A", "400001", start="", end=""),
        row("B", "400002", start="20-12-2026", end="21-12-2026"),
        row("C", "400003", start="10-12-2026", end="garbage"),
    ])
    assert [e["name"] for e in load_events(data_dir)] == ["C", "B", "A"]


# ---- tags ---------------------------------------------------------------
@pytest.mark.parametrize("name, age", [
    ("Under-11 Open", ["U11"]), ("U-11 Open", ["U11"]), ("U11 Open", ["U11"]),
    ("Under 11 Open", ["U11"]), ("UNDER – 11 Girls", ["U11"]), ("under-9", ["U9"]),
    ("4th National School Team Chess (Under 12 & 18)", ["U12", "U18"]),
    ("UNDER-12 & UNDER-18 Championship", ["U12", "U18"]),
    ("U-9, 11 and 13 Open", ["U9", "U11", "U13"]),
    ("Under 15/U17 Girls", ["U15", "U17"]),
    ("U-18 & U-12 Open", ["U12", "U18"]),                  # always sorted, no repeats
    ("Under 13, 14 Oct Open", ["U13"]),                    # "14 Oct" is a date, not an age
    ("Below 1700 FIDE Rated Open", []),                    # a rating, not an age
    ("Under 1600 Open", []),
    ("Under 40 Veterans", []),
    ("Cup Tournament 2026", []),
])
def test_age_tag(name, age):
    assert be.derive_tags(name)["age"] == age


@pytest.mark.parametrize("name, formats", [
    ("FIDE Rapid Rating Chess Tournament", ["rapid"]),
    ("International FIDE Rated BLITZ Open", ["blitz"]),
    ("Rapid & Blitz Open", ["rapid", "blitz"]),
    ("Classical Open", ["classical"]),
    ("2nd International FIDE Rated Open Chess Tournament", []),   # never guess
    ("Rapidly Growing Academy Cup", []),                         # whole words only
])
def test_format_tags(name, formats):
    assert be.derive_tags(name)["formats"] == formats


def test_other_tags_are_true_or_null():
    tags = be.derive_tags("Girls Chess Championship")
    assert tags == {"formats": [], "fide_rated": None, "fide_how": None, "age": [], "open": None, "girls": True,
                    "categories": []}
    assert be.derive_tags("FIDE Open Rapid Rating Chess")["fide_rated"] is True
    assert be.derive_tags("Unrated Open")["fide_rated"] is False  # schema 5: said non-rated
    assert be.derive_tags("FIDE Master Memorial Cup")["fide_rated"] is None


# ---- status -------------------------------------------------------------
@pytest.mark.parametrize("start, end, expected", [
    ("2026-11-25", "2026-11-27", "upcoming"),
    ("2026-11-24", "2026-11-26", "ongoing"),   # first day
    ("2026-11-20", "2026-11-24", "ongoing"),   # last day
    ("2026-11-24", "2026-11-24", "ongoing"),   # one-day event today
    ("2026-11-22", "2026-11-23", "past"),
    ("2026-11-23", None, "past"),              # unusable end counts as end = start
    ("2026-11-24", None, "ongoing"),
    ("2026-11-26", "2026-11-20", "upcoming"),  # end before start: end = start
    (None, None, "unknown"),
    (None, "2026-11-01", "past"),
    (None, "2026-12-01", "unknown"),
])
def test_status(start, end, expected):
    assert be.status({"start": start, "end": end}, TODAY) == expected


def test_today_is_the_indian_date_not_the_utc_date():
    late_utc = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)  # already the 24th in India
    assert be.today_in_india(late_utc) == date(2026, 11, 24)


# ---- the real saved page ------------------------------------------------
def test_real_page_snapshot(data_dir):
    html = FIXTURE.read_text(encoding="utf-8")
    report = be.run(data_dir, html=html, now=NOW)
    events = by_id(data_dir)
    assert report["rows_on_page"] == 443
    assert report["duplicate_rows_collapsed"] == 1            # the Baderia row listed twice
    assert len(events) == 442 and len({e["id"] for e in events.values()}) == 442
    assert report["meta"]["suspect_dates_count"] == 9
    # same code on two different events: both kept, the second gets a suffix
    assert "aicf-499113" in events
    assert [i for i in events if i.startswith("aicf-499113-")]
    assert events["aicf-472290"]["codes"] == ["472290", "472291"]
    assert events["aicf-472175"]["codes"] == ["472175", "472176"]
    assert "�" not in events["aicf-471848"]["name"]
    starts = [e["start"] or e["end"] or "9999" for e in load_events(data_dir)]
    assert starts == sorted(starts)
