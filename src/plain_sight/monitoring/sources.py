"""Register sources and the documented, attributed OpenAustralia fallback.

The authoritative sources are on aph.gov.au: the House per-member register index
and the Senate tabled volumes. When the official site is unreachable, Plain Sight
falls back to OpenAustralia's mirror of the same scans, but only as a *documented*
source, carrying its own attribution so a claim sourced from the mirror is never
silently presented as coming straight from Parliament (PRD "Sources").

:func:`fetch_register` walks an ordered list of candidate sources, returning the
first that yields bytes together with which source it was and that source's
attribution, so provenance and any required credit are recorded downstream.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from plain_sight.monitoring.fetch import FetchError, FetchNotPermitted, RespectfulFetcher


@dataclass(frozen=True)
class RegisterSource:
    """A place a member's register PDF can be fetched from, with its attribution."""

    name: str
    homepage: str
    #: Human-readable credit line recorded whenever bytes come from this source.
    #: Authoritative sources need none; the mirror requires one.
    attribution: str | None = None
    #: Whether this is the official record or a mirror used only as a fallback.
    is_authoritative: bool = True


#: The House of Representatives per-member register index (authoritative).
APH_HOUSE = RegisterSource(
    name="APH House register",
    homepage="https://www.aph.gov.au/Senators_and_Members/Members/Register",
)

#: The Senate tabled register volumes (authoritative).
APH_SENATE = RegisterSource(
    name="APH Senate register",
    homepage="https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Senators_Interests",
)

#: OpenAustralia's mirror of the register scans. A documented fallback only, and
#: attributed: content taken from here credits OpenAustralia and is never passed
#: off as coming directly from Parliament.
OPENAUSTRALIA = RegisterSource(
    name="OpenAustralia",
    homepage="https://www.openaustralia.org.au/",
    attribution=(
        "Register scan mirrored from OpenAustralia (openaustralia.org.au), "
        "used as a documented fallback and reproduced with attribution."
    ),
    is_authoritative=False,
)


@dataclass(frozen=True)
class SourceCandidate:
    """A source paired with the concrete URL to try for one member."""

    source: RegisterSource
    url: str


@dataclass(frozen=True)
class RegisterFetch:
    """A successful register fetch: the bytes, which source served them, and where."""

    source: RegisterSource
    url: str
    content: bytes

    @property
    def attribution(self) -> str | None:
        """The credit line to record for this fetch, if the source requires one."""

        return self.source.attribution


def fetch_register(
    fetcher: RespectfulFetcher,
    candidates: Sequence[SourceCandidate],
) -> RegisterFetch:
    """Fetch a member's register from the first working source, in order.

    Tries the authoritative aph.gov.au source(s) first and only falls through to
    the OpenAustralia mirror when an earlier candidate is unreachable or refused,
    so the fallback is genuinely a fallback. Raises :class:`FetchError` if every
    candidate fails.
    """

    if not candidates:
        raise FetchError("no register sources supplied")

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            response = fetcher.fetch(candidate.url)
        except (FetchError, FetchNotPermitted) as error:
            last_error = error
            continue
        return RegisterFetch(source=candidate.source, url=candidate.url, content=response.body)

    raise FetchError(f"all register sources failed; last error: {last_error}")
