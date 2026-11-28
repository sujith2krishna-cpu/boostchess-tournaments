"""CR-27: an empty Indian state is filled from the event's own name, on evidence only."""
import pytest

import build_events as be
from eventlib import name_state_in, town_state_in
from test_t11 import record


@pytest.mark.parametrize("name, venue, state", [
    # real Chess-Results titles from 28-29 Nov 2026
    ("14th LCCA UNDER 06 CHESS TOURNAMENT at Kanyakumari (TN) on 28/11/2026", "", "Tamil Nadu"),
    ("9th Inter Academies Chess Tournament at Nizampet, Hyderabad on 28th Nov, 2026", "", "Telangana"),
    ("WMA Presents All Assam Inter School Rapid Rating Chess Championship 2026", "", "Assam"),
    ("70th PUNJAB STATE SCHOOL GAMES U-17 (GIRLS) 2026 GSS SCHOOL SANGRUR", "", "Punjab"),
    ("All Goa Blitz Chess Tournament 2026", "Ravi Naik Sports Complex, Indoor Stadium, Ponda", "Goa"),
    ("2nd SGCA PRAYAGRAJ OPEN RAPID CHESS TOURNAMENT 29th November 2026", None, "Uttar Pradesh"),
    ("Nagercoil, Kanyakumari Open", "", "Tamil Nadu"),        # two towns, one state
    ("Tamil Nadu vs Kerala Challenge", "", None),             # two states
    ("Open Rapid at Kanyakumari (KA)", "", None),            # the town and the letters disagree
    ("Warm Up Blitz", "", None),                              # "Up" is not Uttar Pradesh
    ("Open (up) Rapid", "", None),                            # letters count only in capitals
    ("Summer Open (UK)", "", None),                           # (UK) is not read as Uttarakhand
    ("All Goa Blitz", "SILIGURI INDORE STADIUM", None),       # venue towns in other states
    ("All Goa Blitz", "SGSITS Indore", None),                 # a venue town in another state
    ("Saturday Surprise Edition - 9", "", None),               # nothing to go on
    ("", None, None),
    (None, None, None),
])
def test_state_from_the_name(name, venue, state):
    assert name_state_in(name, venue) == state


@pytest.mark.parametrize("venue, state", [
    ("Criminal Bar Library, Barasat", "West Bengal"),
    ("AUKERI SPORTS (OFFICES) MANAITAND DHANBAD", "Jharkhand"),
    ("Skanda Residency, Near SS Temple, Payyannur", "Kerala"),
    ("Vivbekananda Public School, Kalahandi", "Odisha"),
    ("Calicut Beach Hall, Kozhikode", "Kerala"),               # two spellings of one town
])
def test_new_towns(venue, state):
    assert town_state_in(venue) == state


def filled(**fields):
    event = record(**{"id": "chessresults_ind-1", "start": "2026-11-29", "source": "chessresults_ind",
                      **fields})
    be.fill_codes_and_state(event)
    return event


def test_the_name_is_read_only_after_the_venue_and_only_for_an_empty_indian_state():
    assert filled(name="14th LCCA UNDER 08 at Kanyakumari (TN)", place_text="")["state"] == "Tamil Nadu"
    # the venue still comes first
    assert filled(name="All Goa Blitz", place_text="SGSITS Indore")["state"] == "Madhya Pradesh"
    assert filled(name="All Goa Blitz", place_text="", state="Kerala")["state"] == "Kerala"
    assert filled(name="All Goa Blitz", place_text="", country="US")["state"] is None
    assert filled(name="Velocity 42nd Tournament 28/11/2026 SATURDAY", place_text="")["state"] is None
