"""Build and render the static, verified-only public page for a member.

The flow is deliberately two-staged: :func:`build_member_page` turns repository
rows into a small, fully-sanitised :class:`MemberPage` value object (verified
claims only, source links resolved, freshness computed), and
:func:`render_member_page` renders that value object through the shared Jinja2
templates. Keeping the verified-only filter in the *data* stage is what makes the
guarantee testable: a pending claim never reaches the template context, so it
cannot appear in the artifact even by accident.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from plain_sight.db.repository import Repository
from plain_sight.domain import SourceDocument

_TEMPLATES_DIR = Path(__file__).parent / "templates"

#: The standing statement every published page carries. Plain Sight is a faithful
#: mirror of the official record; it never asserts a connection (PRD story 12).
STANDING_STATEMENT = (
    "Plain Sight mirrors the official record and asserts no connections. "
    "Every entry is shown as declared by the member."
)


@dataclass(frozen=True)
class PublishedClaim:
    """One verified claim, flattened and sanitised for rendering.

    Only fields that are safe to publish are carried here; the raw counterparty
    string is surfaced verbatim as *"as declared"* and the source link points at
    the exact page of the immutable scan the claim was read from.
    """

    category: str
    counterparty_raw: str
    description: str | None
    period: str | None
    confidence: float
    source_url: str | None
    page: int
    verified_by: str | None
    verified_at: datetime | None


@dataclass(frozen=True)
class Freshness:
    """Per-member freshness, surfaced rather than promised (PRD: no SLA).

    The site is as fresh as the last publish run; these dates tell the reader
    exactly how stale each part of the picture is.
    """

    source_last_checked: datetime | None
    source_last_changed: datetime | None
    last_verified: datetime | None


@dataclass(frozen=True)
class MemberPage:
    """Everything the template needs to render one member's public page."""

    member_name: str
    claims: list[PublishedClaim]
    freshness: Freshness
    generated_at: datetime
    standing_statement: str = STANDING_STATEMENT


def build_member_page(
    *, repo: Repository, member_name: str, generated_at: datetime
) -> MemberPage | None:
    """Assemble the verified-only page value object, or ``None`` if unknown member.

    Reads only ``verified`` claims from the repository, resolves each to a source
    link via the member's source documents, and computes the freshness block.
    """

    person = repo.get_person_by_canonical_name(member_name)
    if person is None:
        return None

    documents = {d.id: d for d in repo.source_documents_for_member(person.id)}
    verified = repo.verified_events_for_member(person.id)

    claims = [
        PublishedClaim(
            category=event.category.value.replace("_", " "),
            counterparty_raw=counterparty.raw_string,
            description=event.description,
            period=_period(event.valid_from, event.valid_to),
            confidence=event.provenance.extraction_confidence,
            source_url=_source_link(
                documents.get(event.provenance.document_id), event.provenance.page
            ),
            page=event.provenance.page,
            verified_by=event.verified_by,
            verified_at=event.verified_at,
        )
        for event, counterparty in verified
    ]

    freshness = Freshness(
        source_last_checked=_latest(d.fetched_at for d in documents.values()),
        source_last_changed=_latest(d.fetched_at for d in documents.values()),
        last_verified=_latest(c.verified_at for c in claims if c.verified_at is not None),
    )

    return MemberPage(
        member_name=person.canonical_name,
        claims=claims,
        freshness=freshness,
        generated_at=generated_at,
    )


def render_member_page(*, repo: Repository, member_name: str, generated_at: datetime) -> str:
    """Render a member's verified-only page to a static HTML string."""

    page = build_member_page(repo=repo, member_name=member_name, generated_at=generated_at)
    if page is None:
        return _environment().get_template("not_found.html.j2").render(member_name=member_name)
    return _environment().get_template("member.html.j2").render(page=page)


def publish_member(
    *, repo: Repository, member_name: str, output_dir: Path, generated_at: datetime
) -> Path:
    """Render and write a member's page into ``output_dir``; return the file path."""

    html = render_member_page(repo=repo, member_name=member_name, generated_at=generated_at)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{_slug(member_name)}.html"
    path.write_text(html, encoding="utf-8")
    return path


def _source_link(document: SourceDocument | None, page: int) -> str | None:
    """A link to the exact source page/scan, or ``None`` if no public URL exists."""

    if document is None or not document.source_url:
        return None
    return f"{document.source_url}#page={page}"


def _period(valid_from: date | None, valid_to: date | None) -> str | None:
    if valid_from and valid_to:
        return f"held {valid_from} – {valid_to}"
    if valid_from:
        return f"effective from {valid_from}"
    if valid_to:
        return f"until {valid_to}"
    return None


def _latest(values: Iterable[datetime]) -> datetime | None:
    collected = list(values)
    return max(collected) if collected else None


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "member"


@lru_cache(maxsize=1)
def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["dateonly"] = _dateonly
    return env


def _dateonly(value: datetime | None) -> str:
    return "not yet" if value is None else value.strftime("%Y-%m-%d")
