"""India's districts and sub-districts (taluks, tehsils, mandals) mapped to their state, for
filling an empty state (pure: reads only the files in config/lgd/, no network).

Source: the Local Government Directory (LGD) of the Ministry of Panchayati Raj, Government of
India, as mirrored on GitHub by planemad/india-local-government-directory (files
administrative/1-state.csv, 2-district.csv, 3-subdistrict.csv; retrieved by the mirror from
https://lgdirectory.gov.in/downloadDirectory.do on 11 March 2022; copied here at the mirror's
commit 6d3d839). Licence: Government Open Data License - India (see config/lgd/README.md).

A place name that the files list in more than one state (Bilaspur, Udaipur, Aurangabad,
Puttur, ...) is ambiguous: it never gives a state on its own, it can only agree with a clear
one. Names that are also common words or people's names in tournament titles (North, Nagar,
Anand, Krishna, ...) are not used at all.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from eventlib import (IN_STATE_CODES, _CITY_BY_KEY, _KERALA_DISTRICT_BY_KEY, _ONE_TOWN,
                      _STATE_BY_KEY, _key, lookup_state)

LGD_DIR = Path(__file__).resolve().parent.parent / "config" / "lgd"

# LGD's sub-district names carry a kind or a number ("Aalo HQ", "Bilaspur Sadar", "... Circle",
# "... (M)"): the place is the name without it.
_TAIL = re.compile(r"\b(?:circle|i{1,3}|iv|adc|eac|sdo|hq|pt|sadar|rural|urban|taluk|taluka|"
                   r"tahsil|tehsil|mandal|town|m|block|sub division|subdivision)\b\s*$")
# Place names that in a tournament title, venue or organiser usually mean something else.
NOT_PLACES = frozenset({
    "north", "south", "east", "west", "central", "new", "north east", "north west", "south east",
    "south west", "nagar", "para", "sangram", "sangam", "anand", "krishna", "rohini", "renuka",
    "bhadra", "deo", "hurda", "mandar", "chikhali", "city", "town", "sector", "colony", "bazar",
    "market", "station", "camp", "cantonment", "junction", "road", "industrial", "manasa",
    "bhavani", "dhar", "guna",
})
# A place name followed by one of these words may be part of a venue's own name ("Indore
# Stadium" in Siliguri, "Delhi Public School" in Bhopal): a weak clue, set aside only when at
# least two other, different places agree on one state.
_VENUE_WORDS = frozenset("""
stadium school schools vidyalaya vidyalayam college hall bhavan bhawan auditorium ground grounds
complex hotel mandap mandapam public institute university campus road rd highway bypass street
nagar colony layout cross marg lane mall club
""".split())
_SHORT_FORMS = frozenset({"mp", "up", "wb", "tn", "ap", "hp", "jk", "j and k"})
_STATE_LETTERS = re.compile(r"\(\s*([A-Z]{2})\s*\)")
MAX_WORDS = 4


def _clean(name: str) -> str:
    key = _key(re.sub(r"\(.*?\)|\*", " ", name or ""))
    while True:
        shorter = _TAIL.sub("", key).strip()
        if shorter == key:
            return key
        key = shorter


def _state(lgd_name: str) -> str:
    name = lgd_name.title()
    state = lookup_state(name) or lookup_state(re.sub(r"^The\s+", "", name))
    if state is None:
        raise ValueError(f"config/lgd: unknown state name {lgd_name!r}")
    return state


@lru_cache(maxsize=1)
def place_index() -> dict[str, frozenset[str]]:
    """{place key: states}. Districts and sub-districts from LGD, our own short list of towns
    (eventlib) and Kerala's old district names (Trivandrum, Calicut, ...)."""
    index: dict[str, set[str]] = {}

    def add(key: str, state: str, shortest: int = 4) -> None:
        if key and key not in NOT_PLACES and (len(key) >= shortest or " " in key):
            index.setdefault(key, set()).add(state)

    with open(LGD_DIR / "2-district.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            add(_clean(row["District Name"]), _state(row["State Name"]))
    # A one-word sub-district shorter than 6 letters is too often a plain word ("Bara", "Bass",
    # "Bela"): it counts only when it is also a district or one of our own towns (added either way).
    with open(LGD_DIR / "3-subdistrict.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key, state = _clean(row["Sub-district Name"]), _state(row["State Name"])
            add(key, state, shortest=4 if key in index or key in _CITY_BY_KEY else 6)
    for key, state in _CITY_BY_KEY.items():
        add(key, state)
    for alias, town in _ONE_TOWN.items():
        if town in _CITY_BY_KEY:
            add(alias, _CITY_BY_KEY[town])
    for key in _KERALA_DISTRICT_BY_KEY:
        add(key, "Kerala")
    return {k: frozenset(v) for k, v in index.items()}


def clues_in(text) -> list[tuple[str, frozenset[str], bool]]:
    """[(place, states, weak)] for every known place written in a text, longest names first
    ("new delhi" before "delhi"); weak: followed by a venue word ("Indore Stadium")."""
    index = place_index()
    tokens = _key(text or "").split()
    found, i = [], 0
    while i < len(tokens):
        for n in range(min(MAX_WORDS, len(tokens) - i), 0, -1):
            gram = " ".join(tokens[i:i + n])
            states = _STATE_BY_KEY.get(gram) if gram not in _SHORT_FORMS else None
            if states is None and gram not in index:
                continue
            following = tokens[i + n] if i + n < len(tokens) else ""
            found.append((gram, frozenset({states}) if states else index[gram],
                          following in _VENUE_WORDS))
            i += n
            break
        else:
            i += 1
    for m in _STATE_LETTERS.finditer(text or ""):
        if m.group(1) in IN_STATE_CODES and m.group(1) != "UK":
            found.append((f"({m.group(1)})", frozenset({IN_STATE_CODES[m.group(1)]}), False))
    return found


def state_from_places(*texts) -> tuple[str | None, list]:
    """(state, clues) when the places in the texts point to exactly one state, else (None,
    clues). Unambiguous places must all agree; an ambiguous place only counts when it can be in
    that state too ("Puttur, Dakshina Kannada" -> Karnataka); an ambiguous place alone
    ("Bilaspur") gives nothing. A weak clue (a place followed by a venue word) that says another
    state blocks the answer, unless two or more different places agree on it ("SILIGURI INDORE
    STADIUM" with the "DARJEELING DISTRICT CHESS ASSOCIATION": West Bengal; alone: nothing)."""
    clues = [c for text in texts for c in clues_in(text)]
    strong = [(g, s) for g, s, weak in clues if not weak]
    sure = {next(iter(states)) for _, states in strong if len(states) == 1}
    if len(sure) != 1:
        return None, clues
    state = next(iter(sure))
    if any(state not in states for _, states in strong):
        return None, clues
    agreeing = {g for g, states in strong if states == {state}}
    if any(weak and state not in states for _, states, weak in clues) and len(agreeing) < 2:
        return None, clues
    return state, clues
