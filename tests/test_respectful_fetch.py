"""Source-respectful fetching, asserted through a stub transport (no live network).

Drives :class:`RespectfulFetcher` with a recording stub opener and injected
clock/sleep to assert the four PRD behaviours directly: it sends an identifying
user agent, honours robots.txt, rate-limits and backs off, and caches via
conditional requests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from plain_sight.monitoring import (
    DEFAULT_USER_AGENT,
    FetchError,
    FetchNotPermitted,
    FetchResponse,
    RespectfulFetcher,
)

Handler = Callable[[str, Mapping[str, str]], FetchResponse]


class RecordingOpener:
    """A stub transport that records every request and serves canned responses."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.requests: list[tuple[str, dict[str, str]]] = []

    def open(self, url: str, headers: Mapping[str, str]) -> FetchResponse:
        self.requests.append((url, dict(headers)))
        return self._handler(url, dict(headers))


def _allow_all_robots(body: bytes = b"200 ok") -> Handler:
    """A handler that permits everything via robots.txt and returns ``body``."""

    def handler(url: str, headers: Mapping[str, str]) -> FetchResponse:
        if url.endswith("/robots.txt"):
            return FetchResponse(status=200, body=b"User-agent: *\nAllow: /\n")
        return FetchResponse(status=200, body=body, headers={"ETag": '"v1"'})

    return handler


def test_sends_an_identifying_user_agent() -> None:
    opener = RecordingOpener(_allow_all_robots())
    fetcher = RespectfulFetcher(opener, min_interval=0.0)

    fetcher.fetch("https://www.aph.gov.au/register.pdf")

    # Every request, robots.txt included, carries the honest bot string.
    assert opener.requests, "expected at least one request"
    for _url, headers in opener.requests:
        assert headers["User-Agent"] == DEFAULT_USER_AGENT
    assert "PlainSightBot" in DEFAULT_USER_AGENT
    assert "https://" in DEFAULT_USER_AGENT  # a contact URL, not a spoofed browser


def test_honours_robots_txt_disallow() -> None:
    def handler(url: str, headers: Mapping[str, str]) -> FetchResponse:
        if url.endswith("/robots.txt"):
            return FetchResponse(status=200, body=b"User-agent: *\nDisallow: /private/\n")
        return FetchResponse(status=200, body=b"secret")

    opener = RecordingOpener(handler)
    fetcher = RespectfulFetcher(opener, min_interval=0.0)

    with pytest.raises(FetchNotPermitted):
        fetcher.fetch("https://www.aph.gov.au/private/register.pdf")

    # Refused before any content request: only robots.txt was ever fetched.
    assert [url for url, _ in opener.requests] == ["https://www.aph.gov.au/robots.txt"]
    # An allowed path on the same host still works (robots is cached, not re-fetched).
    assert fetcher.fetch("https://www.aph.gov.au/public/register.pdf").status == 200


def test_rate_limits_consecutive_requests_to_a_host() -> None:
    clock = _StubClock([100.0, 101.5])
    slept: list[float] = []
    opener = RecordingOpener(_allow_all_robots())
    fetcher = RespectfulFetcher(
        opener,
        min_interval=5.0,
        sleep=slept.append,
        monotonic=clock,
    )

    fetcher.fetch("https://www.aph.gov.au/a.pdf")  # first: no wait
    fetcher.fetch("https://www.aph.gov.au/b.pdf")  # 1.5s later: must wait the rest

    assert slept == [3.5]


def test_backs_off_and_retries_on_transient_errors() -> None:
    statuses = iter([429, 503, 200])

    def handler(url: str, headers: Mapping[str, str]) -> FetchResponse:
        if url.endswith("/robots.txt"):
            return FetchResponse(status=200, body=b"User-agent: *\nAllow: /\n")
        return FetchResponse(status=next(statuses), body=b"finally")

    slept: list[float] = []
    opener = RecordingOpener(handler)
    fetcher = RespectfulFetcher(opener, min_interval=0.0, backoff_base=1.0, sleep=slept.append)

    response = fetcher.fetch("https://www.aph.gov.au/register.pdf")

    assert response.status == 200
    assert response.body == b"finally"
    # Exponential backoff between the two failed attempts.
    assert slept == [1.0, 2.0]


def test_gives_up_after_max_retries() -> None:
    def handler(url: str, headers: Mapping[str, str]) -> FetchResponse:
        if url.endswith("/robots.txt"):
            return FetchResponse(status=200, body=b"User-agent: *\nAllow: /\n")
        return FetchResponse(status=503, body=b"")

    fetcher = RespectfulFetcher(
        RecordingOpener(handler), min_interval=0.0, max_retries=2, sleep=lambda _: None
    )

    with pytest.raises(FetchError):
        fetcher.fetch("https://www.aph.gov.au/register.pdf")


def test_caches_via_conditional_request_and_returns_cached_bytes() -> None:
    calls = {"n": 0}

    def handler(url: str, headers: Mapping[str, str]) -> FetchResponse:
        if url.endswith("/robots.txt"):
            return FetchResponse(status=200, body=b"User-agent: *\nAllow: /\n")
        calls["n"] += 1
        if calls["n"] == 1:
            return FetchResponse(status=200, body=b"payload", headers={"ETag": '"abc"'})
        # Second time: the client should have sent the validator, so we can 304.
        assert headers.get("If-None-Match") == '"abc"'
        return FetchResponse(status=304, body=b"")

    opener = RecordingOpener(handler)
    fetcher = RespectfulFetcher(opener, min_interval=0.0)

    first = fetcher.fetch("https://www.aph.gov.au/register.pdf")
    second = fetcher.fetch("https://www.aph.gov.au/register.pdf")

    assert first.body == b"payload"
    # A 304 hands back the cached bytes, not an empty body.
    assert second.status == 200
    assert second.body == b"payload"


class _StubClock:
    """A monotonic clock returning a fixed sequence of values, one per call."""

    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)
        self._last = 0.0

    def __call__(self) -> float:
        try:
            self._last = next(self._values)
        except StopIteration:
            pass
        return self._last
