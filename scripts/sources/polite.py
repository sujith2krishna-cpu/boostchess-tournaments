"""Polite web access shared by every source.

Rules (see CLAUDE.md): robots.txt is read at the start of every run and respected,
a clear User-Agent, a timeout, one retry, at least 3 seconds between requests to
the same site, and a cap of 60 requests per site per run.
"""
from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from eventlib import (REQUEST_TIMEOUT_SECONDS, RETRY_WAIT_SECONDS, USER_AGENT, RequestCapReached,
                      RobotsDisallowed, SourceError, SourceSkipped)

MAX_REQUESTS_PER_SITE = 60
MIN_SECONDS_BETWEEN_REQUESTS = 3.0
ROBOTS_TOKEN = "BoostchessBot"


def _decode(raw: bytes) -> str:
    """UTF-8, or Windows-1252 for old pages that mix encodings (broken characters stay visible)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


class PoliteClient:
    """One instance per site per run. Counts every request it makes, robots.txt included."""

    def __init__(self, site_url: str, *, max_requests: int = MAX_REQUESTS_PER_SITE,
                 min_interval: float = MIN_SECONDS_BETWEEN_REQUESTS):
        parsed = urlparse(site_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.max_requests = max_requests
        self.min_interval = min_interval
        self.requests_made = 0
        self.robots_checked = False
        self.last_url = site_url
        self._last_request_at: float | None = None
        self._robots: urllib.robotparser.RobotFileParser | None = None  # None = allow everything

    # -- robots.txt ---------------------------------------------------------
    def load_robots(self) -> None:
        """Read robots.txt once per run. Cannot be read at all = skip the site (safe side)."""
        if self.robots_checked:
            return
        url = f"{self.origin}/robots.txt"
        try:
            status_code, body = self._request("GET", url, allow_4xx=True)
        except SourceError as exc:
            raise SourceSkipped(f"robots.txt of {self.origin} could not be read ({exc}); "
                                "skipping the site to be safe.") from exc
        self.robots_checked = True
        # A missing robots.txt means "no rules". Some sites answer 200 with their home
        # page instead; that is not a robots file either.
        if status_code != 200 or "<html" in body[:2000].lower() or "<!doctype" in body[:200].lower():
            self._robots = None
            return
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(body.splitlines())
        self._robots = parser

    def check(self, url: str) -> None:
        """Raise RobotsDisallowed if robots.txt forbids this URL."""
        self.load_robots()
        if self._robots is not None and not self._robots.can_fetch(ROBOTS_TOKEN, url):
            raise RobotsDisallowed(f"robots.txt of {self.origin} does not allow {urlparse(url).path}")

    # -- requests -----------------------------------------------------------
    def get(self, url: str) -> str:
        self.check(url)
        return self._request("GET", url)[1]

    def post(self, url: str, data: dict) -> str:
        self.check(url)
        return self._request("POST", url, data=data)[1]

    def _request(self, method: str, url: str, data: dict | None = None,
                 allow_4xx: bool = False) -> tuple[int, str]:
        """Send one request (plus one retry after a network error or a 5xx answer)."""
        problem = "unknown problem"
        for attempt in (1, 2):
            if self.requests_made >= self.max_requests:
                raise RequestCapReached(
                    f"request cap of {self.max_requests} per run reached for {self.origin}")
            if self._last_request_at is not None:
                wait = self.min_interval - (time.monotonic() - self._last_request_at)
                if wait > 0:
                    time.sleep(wait)
            self.requests_made += 1
            self._last_request_at = time.monotonic()
            headers = {"User-Agent": USER_AGENT}
            try:
                if method == "POST":
                    response = requests.post(url, data=data, headers=headers,
                                             timeout=REQUEST_TIMEOUT_SECONDS)
                else:
                    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                problem = f"network problem: {exc}"
            else:
                code = response.status_code
                if code == 200 or (allow_4xx and 400 <= code < 500):
                    self.last_url = str(getattr(response, "url", url) or url)
                    return code, _decode(response.content)
                problem = f"the server answered HTTP {code}"
                if code < 500:
                    break  # a 4xx will not get better by asking again
            if attempt == 1:
                time.sleep(RETRY_WAIT_SECONDS)
        raise SourceError(f"Could not fetch {url}: {problem}.")
