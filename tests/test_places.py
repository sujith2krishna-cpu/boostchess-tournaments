"""CR-31: India's districts and sub-districts (LGD, config/lgd/) fill an empty state, only when
the name, venue and organiser point to exactly one state."""
import csv

import pytest

import build_events as be
import places
from places import state_from_places
from test_t11 import record



def filled(**fields):
    event = record(**{"id": "chessresults_ind-1", "name": "Open Rapid", "start": "2026-12-06",
                      "source": "chessresults_ind", "place_text": "", **fields})
    be.fill_codes_and_state(event)
    return event["state"]


@pytest.mark.parametrize("name, venue, organiser, state", [
    ("Open Rapid at Kollam", "", "", "Kerala"),
    ("Aurangabad Open", "", "", None),                          # Bihar and Maharashtra
    ("Aurangabad Open", "Maharashtra", "", "Maharashtra"),      # the state is named too
    ("Aurangabad Open", "", "Bihar Chess Association", "Bihar"),
    ("Holi Cup", "Udaipur", "", None),                          # Rajasthan, Tripura, ...
    ("Raisoni Memorial", "Bilaspur", "", None),                 # Chhattisgarh, Himachal, ...
    ("Akkare Trophy", "Puttur", "", None),                      # Karnataka and Andhra Pradesh
    ("Akkare Trophy", "Chinmayi Auditorium, Puttur, Dakshina Kannada", "", "Karnataka"),
    ("Tamil Nadu vs Kerala Challenge", "", "", None),           # two states
    ("Open", "Kollam", "Vizianagaram Chess Club", None),        # Kerala and Andhra Pradesh
    # "Indore Stadium" is a venue's name in Siliguri, not Indore
    ("2nd North Bengal Cup", "SILIGURI INDORE STADIUM", "DARJEELING DISTRICT CHESS ASSOCIATION",
     "West Bengal"),
    ("2nd North Bengal Cup", "SILIGURI, INDORE", "", None),     # two towns, two states
    ("SILIGURI INDORE STADIUM", "", "", None),                  # Siliguri alone does not overrule it
    ("Delhi Public School Open", "DPS, Bhopal", "", None),       # one place against a weak one
    ("Delhi Public School Open", "DPS, Bhopal", "Madhya Pradesh Chess Association", "Madhya Pradesh"),
    ("Shivani Inter School", "Shivani Public School (Kanpur Raod) Lucknow", "", "Uttar Pradesh"),
    ("North East Selection Championship", "", "Manipur State Chess Association", "Manipur"),
    ("Inter Office Sports Meet North Zone", "", "Reserve Bank Of India, New Delhi", "Delhi"),
    ("TCS Maitree Internal", "Technopark Trivandrum", "", "Kerala"),
    ("V. P. Gupta Memorial", "", "BLM ACADEMY SR. SEC. SCHOOL HALDWANI", "Uttarakhand"),
    ("Viswanathan Anand Cup", "", "", None),                    # Anand is a person here
    ("Krishna Memorial Rapid", "", "", None),
    ("Saturday Surprise Edition - 9", "", "", None),
    ("Bara Open", "Bass Hall", "", None),                       # short sub-district names are words
])
def test_state_from_places(name, venue, organiser, state):
    assert state_from_places(name, venue, organiser)[0] == state


def test_the_build_fills_only_an_empty_indian_state_and_never_changes_one():
    assert filled(name="Open Rapid at Kollam") == "Kerala"
    assert filled(name="Open Rapid at Kollam", state="Tamil Nadu") == "Tamil Nadu"
    assert filled(name="Open Rapid at Kollam", country="US") is None
    assert filled(name="Raisoni Memorial", place_text="Bilaspur") is None
    assert filled(name="Open", organiser="FIRE CHESS SCHOOL", place_text="Ring Road, Vizianagaram") \
        == "Andhra Pradesh"


def test_the_earlier_rules_still_come_first():
    # one known town in the venue (eventlib's own list) wins before the place list is read
    assert filled(name="All Goa Blitz", place_text="SGSITS Indore") == "Madhya Pradesh"


def test_the_place_files_are_complete_and_every_state_is_known():
    folder = places.LGD_DIR
    with open(folder / "1-state.csv", encoding="utf-8-sig", newline="") as f:
        states = {places._state(r["State Name"]) for r in csv.DictReader(f)}
    assert len(states) == 36
    with open(folder / "2-district.csv", encoding="utf-8-sig", newline="") as f:
        districts = list(csv.DictReader(f))
    with open(folder / "3-subdistrict.csv", encoding="utf-8-sig", newline="") as f:
        subdistricts = list(csv.DictReader(f))
    assert len(districts) > 700 and len(subdistricts) > 6000
    index = places.place_index()
    assert index["kollam"] == {"Kerala"} and len(index["aurangabad"]) == 2
    assert "anand" not in index and "north east" not in index and "bara" not in index
    readme = (folder / "README.md").read_text("utf-8")
    assert "Local Government Directory" in readme and "Government Open Data License - India" in readme
    assert "planemad/india-local-government-directory" in readme
