"""Manual events: the country column (default IN) and the state checks that depend on it."""
import pytest

import build_events as be
from conftest import EVENTS_HEADER, OVERRIDES_HEADER, build, by_id, row, write_manual


def manual(folder, line):
    write_manual(folder, EVENTS_HEADER + line + "\n")
    build(folder, [row()])
    return next(e for e in by_id(folder).values() if e["source"] == "manual")


def test_empty_country_means_india_and_the_indian_list_is_used(data_dir):
    e = manual(data_dir, "x1,Pune Cup,05-01-2027,,\"Pune, Maharashtra\",,,,,,,")
    assert (e["country"], e["state"], e["city"]) == ("IN", "Maharashtra", "Pune")
    e = manual(data_dir, "x1,Pune Cup,05-01-2027,,Pune,Tamilnadu,,,,,,")
    assert (e["country"], e["state"]) == ("IN", "Tamil Nadu")


@pytest.mark.parametrize("country, state, expected", [
    ("US", "North Carolina", "North Carolina"), ("us", "NC", "North Carolina"),
    ("GB", "Scotland", "Scotland"), ("CA", "Ontario", "Ontario"), ("AU", "VIC", "Victoria"),
    ("DE", "Bayern", "Bayern"),          # no built-in list: free text
    ("FR", "  Ile-de-France ", "Ile-de-France"),
])
def test_state_is_checked_against_the_countrys_list(data_dir, country, state, expected):
    e = manual(data_dir, f"x1,Open,05-01-2027,,Somewhere,{state},{country},,,,,")
    assert (e["country"], e["state"]) == (country.upper(), expected)


def test_abroad_place_gives_city_and_state(data_dir):
    e = manual(data_dir, "x1,US Masters,25-11-2027,,\"Charlotte, North Carolina\",,US,,,,,")
    assert (e["country"], e["state"], e["city"]) == ("US", "North Carolina", "Charlotte")
    e = manual(data_dir, "x1,Berlin Open,25-11-2027,,\"Berlin, Germany\",,DE,,,,,")
    assert (e["country"], e["state"], e["city"]) == ("DE", None, "Berlin")


@pytest.mark.parametrize("line, expected", [
    ("x1,Cup,05-01-2027,,Goa,Tamil Nadu,US,,,,,", "state 'Tamil Nadu' is not a known state or region of US"),
    ("x1,Cup,05-01-2027,,Goa,Texas,,,,,,", "state 'Texas' is not an Indian state"),
    ("x1,Cup,05-01-2027,,Goa,Wales,IN,,,,,", "state 'Wales' is not an Indian state"),
    ("x1,Cup,05-01-2027,,Goa,,ZZ,,,,,", "country 'ZZ' is not a two-letter country code"),
    ("x1,Cup,05-01-2027,,Goa,,India,,,,,", "country 'India' is not a two-letter country code"),
])
def test_country_and_state_mistakes_name_the_line(data_dir, line, expected):
    write_manual(data_dir, EVENTS_HEADER + line + "\n")
    with pytest.raises(be.DataFileError) as caught:
        build(data_dir, [row()])
    assert "data/manual/events.csv line 2:" in str(caught.value) and expected in str(caught.value)


def test_header_without_the_country_column_still_works(data_dir):
    write_manual(data_dir, "name,start_date,place\nOld style cup,05-01-2027,Goa\n")
    build(data_dir, [row()])
    e = next(e for e in by_id(data_dir).values() if e["source"] == "manual")
    assert (e["country"], e["state"]) == ("IN", "Goa")


def test_override_state_is_checked_against_the_events_country(data_dir):
    write_manual(data_dir, EVENTS_HEADER + "us1,US Open,05-01-2027,,Austin,,US,,,,,\n")
    write_manual(data_dir, OVERRIDES_HEADER + "us1,,,,Texas,,,\n", "overrides.csv")
    build(data_dir, [row()])
    assert by_id(data_dir)["us1"]["state"] == "Texas"
    write_manual(data_dir, OVERRIDES_HEADER + "us1,,,,Tamil Nadu,,,\n", "overrides.csv")
    with pytest.raises(be.DataFileError, match="overrides.csv line 2: state 'Tamil Nadu' is not a known"):
        build(data_dir, [row()])


def test_phone_numbers_in_manual_rows_are_dropped(data_dir):
    e = manual(data_dir, "x1,Club Cup call 98765 43210,05-01-2027,,Goa,,,,,,,Ph: 98765 43210 ask for Ravi")
    assert e["name"] == "Club Cup" and e["note"] == "ask for Ravi"
