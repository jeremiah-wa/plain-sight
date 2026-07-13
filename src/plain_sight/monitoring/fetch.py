"""Source-respectful fetching: the polite half of the monitoring loop.

Plain Sight polls government sites it does not own, so it must not behave like an
abusive crawler and get itself blocked (PRD "Source-respectful fetching": cache,
backoff, identify the bot, honour robots.txt). :class:`RespectfulFetcher` layers
those four behaviours over a pluggable transport:

* **identify the bot** - every request carries an honest ``User-Agent`` naming
  the project and a contact URL, never a spoofed browser string;
* **honour robots.txt** - the origin's rules are fetched once per host and a
  disallowed URL is refused before any content request goes out;
* **rate limit + back off** - at most one request per host per ``min_interval``,
  and transient ``429``/``5xx`` responses are retried with exponential backoff;
* **cache** - ``ETag``/``Last-Modified`` are remembered so a re-poll issues a
  conditional request and a ``304 Not Modified`` returns the cached bytes.

The actual socket work lives behind the :class:`Opener` seam, so the whole policy
is driven and asserted with a stub transport and injected clock/sleep, no live
network (the change-detection tests do exactly this).
"""

from __future__ import annotations

import time
import urllib.robotparser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

#: The honest, identifying bot string sent on every request. It names the project
#: and a contact URL so a site operator can see who we are and reach us, rather
#: than us masquerading as a browser.
DEFAULT_USER_AGENT = (
    "PlainSightBot/0.1 (+https://github.com/jeremiah-wa/plain-sight; civic transparency)"
)


@dataclass(frozen=True)
class FetchResponse:
    """One transport response. ``headers`` are treated case-insensitively."""

    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str | None:
        """Case-insensitive header lookup."""

        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None


class Opener(Protocol):
    """The transport seam: turn a URL + request headers into a response.

    Real code wraps ``urllib``/``httpx``; tests pass a stub that records the
    requests (so the identifying user agent and conditional headers can be
    asserted) and returns canned responses (so robots, backoff, and caching can
    be driven deterministically).
    """

    def open(self, url: str, headers: Mapping[str, str]) -> FetchResponse: ...


class FetchNotPermitted(Exception):
    """Raised when robots.txt disallows fetching a URL for our user agent."""


class FetchError(Exception):
    """Raised when a URL cannot be fetched after exhausting retries."""


# Statuses worth retrying with backoff: explicit rate limiting and transient
# server errors. Anything else (e.g. 404) is a hard result, not retried.
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


class RespectfulFetcher:
    """Fetch URLs politely: identify, honour robots, rate-limit/back off, cache."""

    def __init__(
        self,
        opener: Opener,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval: float = 1.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._opener = opener
        self._user_agent = user_agent
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._monotonic = monotonic
        # Per-host robots parsers and last-request times; per-URL conditional cache.
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_fetch: dict[str, float] = {}
        self._cache: dict[str, _CacheEntry] = {}

    def fetch(self, url: str) -> FetchResponse:
        """Fetch ``url`` respectfully, returning the (possibly cached) response.

        Raises :class:`FetchNotPermitted` if robots.txt disallows it, or
        :class:`FetchError` if it keeps failing after ``max_retries``.
        """

        host = _host(url)
        if not self._robots_for(host).can_fetch(self._user_agent, url):
            raise FetchNotPermitted(url)
        self._respect_rate_limit(host)
        return self._get_with_backoff(url)

    # -- robots.txt -----------------------------------------------------------

    def _robots_for(self, host: str) -> urllib.robotparser.RobotFileParser:
        """Fetch and cache the origin's robots rules, once per host.

        A robots.txt that is missing or errors is treated as "allow all", the
        conventional default; the robots fetch itself is not throttled or
        rate-limit-recursive.
        """

        parser = self._robots.get(host)
        if parser is not None:
            return parser

        parser = urllib.robotparser.RobotFileParser()
        try:
            response = self._opener.open(f"{host}/robots.txt", {"User-Agent": self._user_agent})
        except Exception:
            # An empty ruleset is the conventional "allow all" default; parsing
            # it (rather than leaving the parser unread) also marks it checked so
            # ``can_fetch`` permits requests.
            parser.parse([])
        else:
            if response.status == 200:
                parser.parse(response.body.decode("utf-8", "replace").splitlines())
            else:
                parser.parse([])
        self._robots[host] = parser
        return parser

    # -- rate limiting --------------------------------------------------------

    def _respect_rate_limit(self, host: str) -> None:
        """Sleep so consecutive requests to one host are >= ``min_interval`` apart."""

        now = self._monotonic()
        last = self._last_fetch.get(host)
        if last is not None:
            elapsed = now - last
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last_fetch[host] = now

    # -- conditional GET + backoff -------------------------------------------

    def _get_with_backoff(self, url: str) -> FetchResponse:
        cached = self._cache.get(url)
        headers = {"User-Agent": self._user_agent}
        if cached is not None:
            if cached.etag is not None:
                headers["If-None-Match"] = cached.etag
            if cached.last_modified is not None:
                headers["If-Modified-Since"] = cached.last_modified

        for attempt in range(self._max_retries + 1):
            response = self._opener.open(url, headers)
            if response.status == 304 and cached is not None:
                # Not modified: hand back the bytes we already hold.
                return FetchResponse(status=200, body=cached.body, headers=response.headers)
            if response.status == 200:
                self._cache[url] = _CacheEntry(
                    body=response.body,
                    etag=response.header("ETag"),
                    last_modified=response.header("Last-Modified"),
                )
                return response
            if response.status in _RETRYABLE and attempt < self._max_retries:
                self._sleep(self._backoff_base * (2**attempt))
                continue
            raise FetchError(f"{url} returned HTTP {response.status}")

        raise FetchError(
            f"{url} exhausted retries"
        )  # pragma: no cover - loop always returns/raises


@dataclass(frozen=True)
class _CacheEntry:
    """A remembered response, keyed by URL, for conditional re-fetching."""

    body: bytes
    etag: str | None
    last_modified: str | None


def _host(url: str) -> str:
    """The scheme+authority origin of ``url`` (where robots.txt and throttling live)."""

    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))
