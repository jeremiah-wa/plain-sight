"""The temporal integrity constraint, asserted directly against Postgres.

This is PRD seam 2's foundation: overlapping validity for the same member +
interest (counterparty + category) must be impossible at the database level, not
merely discouraged in application code. The behaviour lives at the DB boundary,
so these tests exercise the ``EXCLUDE USING GIST`` constraint from 0002 through
raw SQL rather than through any application logic.

Runs against the ephemeral container in ``compose.yaml`` via the shared
``postgres_conn`` fixture (see ``conftest.py``); ``docker compose up -d db``, and
it skips if that is not up.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import ExclusionViolation

from plain_sight.db import PostgresRepository
from plain_sight.domain import (
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    Person,
    Provenance,
    SourceDocument,
)

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

MEMBER_ID = UUID(int=0xA1)
DOCUMENT_ID = UUID(int=0xD0)
# Two counterparties so a test can prove the constraint is keyed on interest
# identity, not on the member alone.
BHP_ID = UUID(int=0xC1)
ACME_ID = UUID(int=0xC2)


@pytest.fixture
def repo(postgres_conn: psycopg.Connection[Any]) -> PostgresRepository:
    """A repository over a seeded schema: one member, one document, two counterparties."""

    repository = PostgresRepository(postgres_conn)
    repository.add_person(Person(id=MEMBER_ID, canonical_name="Jane Member"))
    repository.add_source_document(
        SourceDocument(
            id=DOCUMENT_ID,
            member_id=MEMBER_ID,
            content_sha256="0" * 64,
            storage_path="documents/jane.pdf",
            page_count=1,
            fetched_at=NOW,
        )
    )
    for cid, raw in ((BHP_ID, "BHP Group Ltd"), (ACME_ID, "Acme Trust")):
        repository.add_counterparty(Counterparty(id=cid, raw_string=raw, normalised_label=raw))
    postgres_conn.commit()
    return repository


def _event(
    *,
    valid_from: date | None,
    valid_to: date | None,
    counterparty_id: UUID = BHP_ID,
    category: InterestCategory = InterestCategory.SHAREHOLDING,
) -> DeclarationEvent:
    return DeclarationEvent(
        id=uuid4(),
        member_id=MEMBER_ID,
        counterparty_id=counterparty_id,
        category=category,
        valid_from=valid_from,
        valid_to=valid_to,
        provenance=Provenance(
            document_id=DOCUMENT_ID,
            page=1,
            extraction_method="stub-extractor",
            extraction_confidence=0.9,
            fetch_timestamp=NOW,
        ),
        ingested_at=NOW,
    )


def test_overlapping_active_validity_is_rejected(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    repo.add_declaration_event(_event(valid_from=date(2020, 1, 1), valid_to=date(2021, 1, 1)))
    postgres_conn.commit()

    # Same member + counterparty + category, validity overlaps the first.
    with pytest.raises(ExclusionViolation):
        repo.add_declaration_event(_event(valid_from=date(2020, 6, 1), valid_to=date(2020, 9, 1)))
    postgres_conn.rollback()


def test_adjacent_validity_is_accepted(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    repo.add_declaration_event(_event(valid_from=date(2020, 1, 1), valid_to=date(2021, 1, 1)))
    # Half-open [) means the upper bound is exclusive: these meet but do not overlap.
    repo.add_declaration_event(_event(valid_from=date(2021, 1, 1), valid_to=date(2022, 1, 1)))
    postgres_conn.commit()

    assert _active_count(postgres_conn) == 2


def test_overlap_on_different_interest_is_accepted(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    # Same member and dates, but a different counterparty and a different category:
    # three distinct interests, so none overlaps another.
    repo.add_declaration_event(_event(valid_from=date(2020, 1, 1), valid_to=date(2021, 1, 1)))
    repo.add_declaration_event(
        _event(valid_from=date(2020, 1, 1), valid_to=date(2021, 1, 1), counterparty_id=ACME_ID)
    )
    repo.add_declaration_event(
        _event(
            valid_from=date(2020, 1, 1),
            valid_to=date(2021, 1, 1),
            category=InterestCategory.DIRECTORSHIP,
        )
    )
    postgres_conn.commit()

    assert _active_count(postgres_conn) == 3


def test_new_event_overlapping_an_already_superseded_prior_is_accepted(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    """The spec's literal scenario: a prior version is *already* superseded, then a
    new active event overlapping it is accepted immediately, because the partial
    index excludes the superseded row. No deferral is involved."""

    original = _event(valid_from=date(2020, 1, 1), valid_to=date(2021, 1, 1))
    successor = _event(valid_from=date(2021, 1, 1), valid_to=date(2022, 1, 1))  # adjacent, active
    repo.add_declaration_event(original)
    repo.add_declaration_event(successor)
    _mark_superseded(postgres_conn, original.id, by=successor.id)
    postgres_conn.commit()

    # Overlaps only the now-superseded original, so it is accepted immediately.
    repo.add_declaration_event(_event(valid_from=date(2020, 6, 1), valid_to=date(2020, 9, 1)))
    postgres_conn.commit()

    assert _active_count(postgres_conn) == 2  # successor + the new overlapping event
    assert _total_count(postgres_conn) == 3  # the superseded original is retained


def test_supersession_within_one_transaction_is_accepted(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    """The real correction path: append a successor that overlaps its predecessor
    and mark the predecessor superseded atomically. The constraint is deferred to
    the end of the transaction, by which point only one of the two is active."""

    original = _event(valid_from=date(2020, 1, 1), valid_to=date(2021, 1, 1))
    repo.add_declaration_event(original)
    postgres_conn.commit()

    correction = _event(valid_from=date(2020, 6, 1), valid_to=date(2020, 9, 1))  # overlaps original
    with postgres_conn.transaction():
        postgres_conn.execute("SET CONSTRAINTS declaration_event_no_active_overlap DEFERRED")
        repo.add_declaration_event(correction)
        _mark_superseded(postgres_conn, original.id, by=correction.id)

    assert _active_count(postgres_conn) == 1  # only the correction
    assert _total_count(postgres_conn) == 2  # the superseded original is retained


def _mark_superseded(conn: psycopg.Connection[Any], event_id: UUID, *, by: UUID) -> None:
    conn.execute(
        "UPDATE declaration_event SET superseded_by = %s WHERE id = %s",
        (by, event_id),
    )


def _active_count(conn: psycopg.Connection[Any]) -> int:
    row = conn.execute(
        "SELECT count(*) FROM declaration_event WHERE superseded_by IS NULL"
    ).fetchone()
    assert row is not None
    return int(row[0])


def _total_count(conn: psycopg.Connection[Any]) -> int:
    row = conn.execute("SELECT count(*) FROM declaration_event").fetchone()
    assert row is not None
    return int(row[0])
