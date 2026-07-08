"""Application services wiring the walking skeleton end to end.

Each function takes its collaborators (repository, document store, extractor)
explicitly, so the whole flow can be driven with an in-memory repository and a
stub extractor in tests, or with Postgres and the live model in the CLI.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from uuid import UUID, uuid4

from plain_sight.db.repository import Repository
from plain_sight.domain import DeclarationEvent, Person
from plain_sight.extraction import Extractor, map_candidates
from plain_sight.sources import DocumentStore


def ingest(
    *,
    repo: Repository,
    store: DocumentStore,
    extractor: Extractor,
    member_name: str,
    pdf_bytes: bytes,
    now: datetime,
    source_url: str | None = None,
    id_factory: Callable[[], UUID] = uuid4,
) -> list[DeclarationEvent]:
    """Store the PDF, extract candidates, and persist them as pending claims.

    Returns the created declaration events (all ``pending``) so the caller can
    surface their ids for the crude confirm step.
    """

    person = repo.get_person_by_canonical_name(member_name)
    if person is None:
        person = Person(id=id_factory(), canonical_name=member_name)
        repo.add_person(person)

    document = store.store(
        pdf_bytes,
        member_id=person.id,
        fetched_at=now,
        source_url=source_url,
        id_factory=id_factory,
    )
    repo.add_source_document(document)

    result = extractor.extract(document, pdf_bytes)
    counterparties, events = map_candidates(
        document, result, ingested_at=now, id_factory=id_factory
    )

    for counterparty in counterparties:
        repo.add_counterparty(counterparty)
    for event in events:
        repo.add_declaration_event(event)

    return events


def confirm(
    *,
    repo: Repository,
    event_id: UUID,
    verified_by: str,
    verified_at: datetime,
) -> bool:
    """Transition one claim from ``pending`` to ``verified``."""

    return repo.verify_event(event_id, verified_by=verified_by, verified_at=verified_at)


def render_member_interests(*, repo: Repository, member_name: str) -> str:
    """Render a member's *verified* declared interests as plain text.

    Unverified claims are physically absent from this output: the repository
    query returns verified rows only.
    """

    person = repo.get_person_by_canonical_name(member_name)
    if person is None:
        return f"No member found: {member_name}"

    claims = repo.verified_events_for_member(person.id)
    if not claims:
        return f"{person.canonical_name} — no verified declared interests yet"

    lines = [f"{person.canonical_name} — verified declared interests", ""]
    for event, counterparty in claims:
        category = event.category.value.replace("_", " ")
        lines.append(f'- [{category}] as declared: "{counterparty.raw_string}"')
        period = _period(event.valid_from, event.valid_to)
        if period:
            lines.append(f"  {period}")
        if event.description:
            lines.append(f"  {event.description}")
        prov = event.provenance
        lines.append(
            f"  source: document {prov.document_id} · page {prov.page} "
            f"· confidence {prov.extraction_confidence:.2f}"
        )
        if event.verified_by and event.verified_at:
            lines.append(f"  verified by {event.verified_by} on {event.verified_at:%Y-%m-%d}")
    return "\n".join(lines)


def _period(valid_from: date | None, valid_to: date | None) -> str:
    if valid_from and valid_to:
        return f"held {valid_from} – {valid_to}"
    if valid_from:
        return f"effective from {valid_from}"
    if valid_to:
        return f"until {valid_to}"
    return ""
