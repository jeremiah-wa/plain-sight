"""The Postgres system of record: ``psycopg`` v3 + hand-written SQL, no ORM.

Domain objects are validated with Pydantic at this boundary as rows cross back
into the application. Temporal/provenance behaviour is expressed directly in SQL
so the tests can assert it without an ORM obscuring it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from plain_sight.db.repository import VerifiedClaim
from plain_sight.domain import (
    BBox,
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    Person,
    Provenance,
    SourceDocument,
    VerificationStatus,
)


class PostgresRepository:
    """A :class:`~plain_sight.db.repository.Repository` backed by Postgres.

    Does not manage transactions itself: the caller wraps a unit of work in
    ``with conn:`` so an ingest is atomic. Reads and single-row writes work the
    same either way.
    """

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add_person(self, person: Person) -> None:
        self._conn.execute(
            """
            INSERT INTO person
                (id, canonical_name, name_variants, external_ids, chamber, jurisdiction)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                person.id,
                person.canonical_name,
                person.name_variants,
                Jsonb(person.external_ids),
                person.chamber,
                person.jurisdiction,
            ),
        )

    def get_person_by_canonical_name(self, canonical_name: str) -> Person | None:
        row = self._conn.execute(
            """
            SELECT id, canonical_name, name_variants, external_ids, chamber, jurisdiction
            FROM person
            WHERE canonical_name = %s
            """,
            (canonical_name,),
        ).fetchone()
        return None if row is None else _person(row)

    def add_source_document(self, document: SourceDocument) -> None:
        self._conn.execute(
            """
            INSERT INTO source_document
                (id, member_id, content_sha256, storage_path, page_count,
                 source_url, fetched_at, jurisdiction)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document.id,
                document.member_id,
                document.content_sha256,
                document.storage_path,
                document.page_count,
                document.source_url,
                document.fetched_at,
                document.jurisdiction,
            ),
        )

    def add_counterparty(self, counterparty: Counterparty) -> None:
        self._conn.execute(
            """
            INSERT INTO counterparty (id, raw_string, normalised_label, resolved)
            VALUES (%s, %s, %s, %s)
            """,
            (
                counterparty.id,
                counterparty.raw_string,
                counterparty.normalised_label,
                counterparty.resolved,
            ),
        )

    def add_declaration_event(self, event: DeclarationEvent) -> None:
        provenance = event.provenance
        self._conn.execute(
            """
            INSERT INTO declaration_event
                (id, member_id, counterparty_id, category, description,
                 valid_from, valid_to,
                 document_id, page, extraction_method, extraction_confidence,
                 fetch_timestamp, bbox,
                 verification_status, verified_by, verified_at, ingested_at)
            VALUES (%s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s)
            """,
            (
                event.id,
                event.member_id,
                event.counterparty_id,
                event.category.value,
                event.description,
                event.valid_from,
                event.valid_to,
                provenance.document_id,
                provenance.page,
                provenance.extraction_method,
                provenance.extraction_confidence,
                provenance.fetch_timestamp,
                list(provenance.bbox) if provenance.bbox is not None else None,
                event.verification_status.value,
                event.verified_by,
                event.verified_at,
                event.ingested_at,
            ),
        )

    def verify_event(
        self, event_id: UUID, *, verified_by: str, verified_at: datetime
    ) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE declaration_event
            SET verification_status = 'verified',
                verified_by = %s,
                verified_at = %s
            WHERE id = %s AND verification_status = 'pending'
            """,
            (verified_by, verified_at, event_id),
        )
        return cursor.rowcount == 1

    def verified_events_for_member(self, member_id: UUID) -> list[VerifiedClaim]:
        rows = self._conn.execute(
            """
            SELECT de.id, de.member_id, de.counterparty_id, de.category, de.description,
                   de.valid_from, de.valid_to,
                   de.document_id, de.page, de.extraction_method, de.extraction_confidence,
                   de.fetch_timestamp, de.bbox,
                   de.verification_status, de.verified_by, de.verified_at, de.ingested_at,
                   c.raw_string, c.normalised_label, c.resolved
            FROM declaration_event de
            JOIN counterparty c ON c.id = de.counterparty_id
            WHERE de.member_id = %s AND de.verification_status = 'verified'
            ORDER BY de.ingested_at, de.id
            """,
            (member_id,),
        ).fetchall()
        return [(_event(row), _counterparty(row)) for row in rows]


def _person(row: tuple[Any, ...]) -> Person:
    return Person(
        id=row[0],
        canonical_name=row[1],
        name_variants=list(row[2]),
        external_ids=dict(row[3]),
        chamber=row[4],
        jurisdiction=row[5],
    )


def _event(row: tuple[Any, ...]) -> DeclarationEvent:
    bbox = row[12]
    return DeclarationEvent(
        id=row[0],
        member_id=row[1],
        counterparty_id=row[2],
        category=InterestCategory(row[3]),
        description=row[4],
        valid_from=row[5],
        valid_to=row[6],
        provenance=Provenance(
            document_id=row[7],
            page=row[8],
            extraction_method=row[9],
            extraction_confidence=row[10],
            fetch_timestamp=row[11],
            bbox=_bbox(bbox),
        ),
        verification_status=VerificationStatus(row[13]),
        verified_by=row[14],
        verified_at=row[15],
        ingested_at=row[16],
    )


def _counterparty(row: tuple[Any, ...]) -> Counterparty:
    return Counterparty(id=row[2], raw_string=row[17], normalised_label=row[18], resolved=row[19])


def _bbox(value: list[float] | None) -> BBox | None:
    if value is None:
        return None
    x0, y0, x1, y1 = value
    return (x0, y0, x1, y1)
