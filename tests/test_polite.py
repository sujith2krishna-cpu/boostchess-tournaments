"""The polite web client: robots.txt, spacing, request cap, timeout, one retry."""
import pytest
import requests

import build_events as be
from conftest import FakeResponse
from sources.polite import PoliteClient

SITE = "https://example.test/"


def client(**kwargs):
    return PoliteClient(SITE, **kwargs)


def test_sends_clear_user_agent_and_timeout(web):
    web.add(SITE + "robots.txt", "User-agent: *\nAllow: /\n")
    web.add(SITE + "page", "café")
    assert client().get(SITE + "page") == "café"
    page_call = web.calls[-1]
    assert page_call["headers"]["User-Agent"] == be.USER_AGENT
    assert page_call["headers"]["User-Agent"].startswith("BoostchessBot (+https://github.com/")


def test_robots_txt_is_read_first_and_only_once(web):
    web.add(SITE + "robots.txt", "User-agent: *\nAllow: /\n")
    web.add(SITE + "a", "A")
    web.add(SITE + "b", "B")
    c = client()
    c.get(SITE + "a")
    c.get(SITE + "b")
    assert web.urls() == [SITE + "robots.txt", SITE + "a", SITE + "b"]


def test_robots_disallow_stops_the_request(web):
    web.add(SITE + "robots.txt", "User-agent: *\nDisallow: /private/\n")
    web.add(SITE + "private/page", "secret")
    with pytest.raises(be.RobotsDisallowed, match="does not allow /private/page"):
        client().get(SITE + "private/page")
    assert SITE + "private/page" not in web.urls()


def test_robots_rule_for_our_bot_name_is_respected(web):
    web.add(SITE + "robots.txt", "User-agent: BoostchessBot\nDisallow: /\n")
    with pytest.raises(be.RobotsDisallowed):
        client().get(SITE + "anything")


def test_a_missing_robots_txt_means_no_rules(web):
    web.add(SITE + "robots.txt", "nope", status=404)
    web.add(SITE + "page", "ok")
    assert client().get(SITE + "page") == "ok"


def test_a_home_page_served_as_robots_txt_means_no_rules(web):
    web.add(SITE + "robots.txt", "<!DOCTYPE html><html><body>Disallow: /page</body></html>")
    web.add(SITE + "page", "ok")
    assert client().get(SITE + "page") == "ok"


def test_robots_txt_that_cannot_be_read_skips_the_site(web, monkeypatch):
    web.add(SITE + "robots.txt", "oops", status=503)
    with pytest.raises(be.SourceSkipped, match="robots.txt .* could not be read"):
        client().get(SITE + "page")
    assert SITE + "page" not in web.urls()


def test_at_least_three_seconds_between_requests(web):
    for name in "abc":
        web.add(SITE + name, name)
    c = client()
    for name in "abc":
        c.get(SITE + name)
    # robots.txt + 3 pages = 4 requests, so 3 waits of (about) 3 seconds
    assert len(web.sleeps) == 3 and all(2.9 <= wait <= 3.0 for wait in web.sleeps)


def test_request_cap_per_site(web):
    for n in range(10):
        web.add(SITE + f"p{n}", "x")
    c = client(max_requests=4)  # robots.txt counts too
    for n in range(3):
        c.get(SITE + f"p{n}")
    with pytest.raises(be.RequestCapReached, match="cap of 4"):
        c.get(SITE + "p3")
    assert len(web.calls) == 4 and c.requests_made == 4


def test_cap_default_is_60_and_gap_is_3_seconds():
    from sources import polite
    assert polite.MAX_REQUESTS_PER_SITE == 60 and polite.MIN_SECONDS_BETWEEN_REQUESTS == 3.0


def test_one_retry_after_a_network_error(monkeypatch, web):
    calls = []

    def flaky(url, headers=None, timeout=None):
        calls.append(url)
        if url.endswith("page") and calls.count(url) == 1:
            raise requests.ConnectionError("down")
        return FakeResponse(200, "fine", url)

    monkeypatch.setattr(be.requests, "get", flaky)
    assert client().get(SITE + "page") == "fine"
    assert calls.count(SITE + "page") == 2 and be.RETRY_WAIT_SECONDS in web.sleeps


def test_gives_up_after_one_retry_on_server_errors(web):
    web.add(SITE + "page", "boom", status=503)
    with pytest.raises(be.SourceError, match="HTTP 503"):
        client().get(SITE + "page")
    assert web.urls().count(SITE + "page") == 2


def test_a_404_is_not_retried(web):
    with pytest.raises(be.SourceError, match="HTTP 404"):
        client().get(SITE + "missing")
    assert web.urls().count(SITE + "missing") == 1


def test_old_pages_in_windows_1252_are_still_readable(web):
    web.add(SITE + "page", "Academy’s cup".encode("cp1252"))
    assert client().get(SITE + "page") == "Academy’s cup"
