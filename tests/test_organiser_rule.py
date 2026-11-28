"""CR-30: two names that each name their own, different academy (or club, foundation,
association) are not flagged as possible duplicates, unless the venue or the organiser matches.
A code, Chess-Results page or brochure link still proves "same"; pairs.csv still beats it all.

The names, dates and places below are real records from 28 Nov 2026."""
import csv

import pytest

import build_events as be
import dedup
from test_t11 import record

DEC6 = {"start": "2026-12-06", "end": "2026-12-06", "state": "Tamil Nadu"}


def ev(id_, name, source, **fields):
    return record(**{"id": id_, "name": name, "source": source, **DEC6, **fields})


VETRIOUS = ev("chessfee-1867", "VETRIOUS CHESS ACADEMY – TN STATE LEVEL CHILDREN’S CHESS TOURNAMENT – 6 DEC",
              "chessfee", place_text="S.K. Mahal (A/C), Muthukadai, (Ammoor Road), Ranipet District.",
              organiser="M. Vinoth")
DECOYS = {
    "dragon": ev("tnsca-CO-215-TNJ-26-27", "Dragon Chess Academy 4th State Level Children Chess Tournament",
                 "tnsca", city="Thanjavur", place_text="Thanjavur, Tamil Nadu"),
    "anandhan": ev("tnsca-CO-198-CGL-26-27", "Anandhan Chess Academy 12th State Level Children Chess Tournament",
                   "tnsca", city="Chengalpattu", place_text="Chengalpattu, Tamil Nadu"),
    "unique": ev("tnsca-CO-208-TUT-26-27", "Unique Chess Academy 1st Tamil Nadu State Level Children & Open "
                 "Chess Tournament 2026", "tnsca", city="Tuticorin", place_text="Tuticorin, Tamil Nadu"),
    "harshana": ev("tnsca-CO-193-CGL-26-27", "5th Harshana Chess Academy TN State Level Children’s Chess "
                   "Tournament 2026", "tnsca", city="Chengalpattu", place_text="Chengalpattu, Tamil Nadu"),
    "s3": ev("tnsca-CO-205-CGL-26-27", "2nd S3 Chess Academy Children’s TN State Level Chess Tournament",
             "tnsca", city="Chengalpattu", place_text="Chengalpattu, Tamil Nadu"),
    "gd": ev("tnsca-CO-178-CGL-26-27", "G D Chess Academy 1st Tamil Nadu State Level Children’s Tournament 2026",
             "tnsca", city="Chengalpattu", place_text="Chengalpattu, Tamil Nadu"),
}


def compare(a, b):
    return dedup.compare(dedup.Features(a), dedup.Features(b))


@pytest.mark.parametrize("name, found", [
    ("VETRIOUS CHESS ACADEMY – TN STATE LEVEL CHILDREN’S", {"vetrious"}),
    ("MADURAI - Vetri Chess Academy 1st TN State Level", {"vetri"}),          # the town is not part of it
    ("KOVILPATTI - Unique Chess Academy 1st Tamilnadu State Level", {"unique"}),
    ("G D Chess Academy 1st Tamil Nadu State Level", {"gd"}),
    ("Global Sports Foundation 11th TN State Level Children's", {"globalsports"}),
    ("SFA Chess Academy’s 5th Tamil Nadu State Level", {"sfa"}),
    ("En Passant 1st Tamil Nadu State Level Children’s Chess Tournament", set()),
    ("KHANNUR FIDE RAPID RATING CHESS TOURNAMENT 2026", set()),
    ("Tamil Nadu State Chess Association Selection", set()),                 # no organiser word left
])
def test_organiser_words_in_a_name(name, found):
    assert dedup.organisers(name) == frozenset(found)


@pytest.mark.parametrize("key", sorted(DECOYS))
def test_vetrious_is_not_flagged_against_another_academy(key):
    plain = dict(DECOYS[key])
    result = compare(VETRIOUS, plain)
    assert result["decision"] == "different" and "different organisers" in result["reason"]
    assert result["hard"] is False  # pairs.csv "same" can still join them


def test_the_rule_only_stops_a_possible_flag_never_a_strong_proof():
    shared = dict(DECOYS["dragon"], brochure_url="https://example.org/same.pdf")
    assert compare(dict(VETRIOUS, brochure_url="https://example.org/same.pdf"), shared)["decision"] == "same"
    coded = dict(DECOYS["dragon"], codes=["123456"])
    assert compare(dict(VETRIOUS, codes=["123456"]), coded)["decision"] == "same"


def test_the_same_venue_or_organiser_keeps_the_flag():
    venue = "S.K. Mahal (A/C), Muthukadai, Ranipet"
    other = dict(DECOYS["dragon"], place_text=venue, city=None)
    assert compare(dict(VETRIOUS, place_text=venue), other)["decision"] == "possible"
    other = dict(DECOYS["dragon"], organiser="Vetrious Chess Academy", city=None)
    assert compare(VETRIOUS, other)["decision"] == "possible"


# Real duplicates (all settled as "same" in pairs.csv) are still caught by the algorithm alone.
@pytest.mark.parametrize("a, b", [
    (ev("chessfee-1853", "ENPASSANT 1st TAMIL NADU STATE LEVEL CHILDREN'S CHESS TOURNAMENT – 29 NOV", "chessfee",
        city="Chennai", start="2026-11-29", end="2026-11-29"),
     ev("tnsca-CO-210-CHE-26-27", "En Passant 1st Tamil Nadu State Level Children’s Chess Tournament", "tnsca",
        city="Chennai", start="2026-11-29", end="2026-11-29")),
    (ev("chessfee-1869", "GENIUS CHESS ACADEMY - 4th TN STATE LEVEL OPEN & CHILDREN'S CHESS TOURNAMENT 2026 – 29 NOV",
        "chessfee", place_text="APTSMPS MATRICULATION SCHOOL, ARUPPUKOTTAI.", start="2026-11-29", end="2026-11-29"),
     ev("tnsca-CO-139-VNR-26-27", "Genius Chess Academy State Level Chess Tournament", "tnsca",
        city="Virudhunagar", start="2026-11-29", end="2026-11-29")),
    (record(id="ksca-6939", name="KHANNUR FIDE RAPID RATING CHESS TOURNAMENT 2026", source="ksca",
            start="2026-11-29", end="2026-11-29", state="Karnataka", city="Bengaluru"),
     record(id="aicf-501318", name="Khannur Rapid Rated Chess Tournament – Bengaluru", source="aicf",
            start="2026-11-29", end="2026-11-29", state="Karnataka", city="Bengaluru", codes=["501318"])),
    (ev("chessfee-1850", "MADURAI - Vetri Chess Academy 1st TN State Level Children’s Cycle & Open Chess "
        "Tournament 2026 – 6 DEC", "chessfee", city="Madurai"),
     ev("tnsca-CO-195-MDU-26-27", "Veteri Chess Academy 1st TN State Level Cycle & Open Chess Tournament",
        "tnsca", city="Madurai")),                                          # Vetri / Veteri: one academy
    (ev("chessfee-1863", "KOVILPATTI - Unique Chess Academy 1st Tamilnadu State Level Children & Open Chess "
        "Tournament 2026 – 6 DEC", "chessfee"), DECOYS["unique"]),
])
def test_real_duplicates_are_still_caught(a, b):
    assert compare(a, b)["decision"] in ("same", "possible")


def test_no_same_line_in_pairs_csv_has_different_organisers():
    """The rule never argues with a decision made by hand."""
    with open(be.DATA_DIR / "manual" / "pairs.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    events = {e["id"]: e for e in be.load_json(be.DATA_DIR / "events.json")["events"]}
    for row in rows:
        if row["decision"] == "same" and row["id_a"] in events and row["id_b"] in events:
            a, b = (dedup.Features(events[row[k]]) for k in ("id_a", "id_b"))
            assert not dedup.different_organisers(a.organisers, b.organisers), row
