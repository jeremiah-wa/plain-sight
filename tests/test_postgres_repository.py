"""End-to-end against a real Postgres, to validate the migration and raw SQL.

Opt-in: set ``PLAIN_SIGHT_TEST_DATABASE_URL`` to a reachable, disposable
database. The test creates the skeleton schema, drives the pipeline through the
``PostgresRepository``, asserts the verified-only display, and drops the tables.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from plain_sight import service
from plain_sight.db import PostgresRepository, apply_migrations
from plain_sight.domain import CandidateDeclaration, ExtractionResult, InterestCategory
from plain_sight.extraction import StubExtractor
from plain_sight.sources import DocumentStore

pytestmark = pytest.mark.postgres

_TABLES = "declaration_event, source_document, counterparty, person, schema_migrations"
NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection[object]]:
    url = os.environ.get("PLAIN_SIGHT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set PLAIN_SIGHT_TEST_DATABASE_URL to run the Postgres test")
    connection = psycopg.connect(url)
    try:
        connection.execute(f"DROP TABLE IF EXISTS {_TABLES} CASCADE")
        connection.commit()
        apply_migrations(connection)
        yield connection
    finally:
        connection.execute(f"DROP TABLE IF EXISTS {_TABLES} CASCADE")
        connection.commit()
        connection.close()


def test_postgres_pipeline_displays_only_verified(
    conn: psycopg.Connection[object],
    tmp_path: Path,
    sample_pdf_bytes: bytes,
    id_factory: Callable[[], UUID],
) -> None:
    repo = PostgresRepository(conn)
    store = DocumentStore(tmp_path)
    extractor = StubExtractor(
        ExtractionResult(
            method="stub-extractor",
            candidates=[
                CandidateDeclaration(
                    category=InterestCategory.SHAREHOLDING,
                    counterparty_raw="BHP Group Ltd",
                    page=1,
                    confidence=0.9,
                ),
                CandidateDeclaration(
                    category=InterestCategory.REAL_ESTATE,
                    counterparty_raw="Acme Trust",
                    page=2,
                    confidence=0.5,
                ),
            ],
        )
    )

    with conn:
        events = service.ingest(
            repo=repo,
            store=store,
            extractor=extractor,
            member_name="Jane Member",
            pdf_bytes=sample_pdf_bytes,
            now=NOW,
            id_factory=id_factory,
        )

    shareholding = next(e for e in events if e.category is InterestCategory.SHAREHOLDING)
    with conn:
        assert repo.verify_event(shareholding.id, verified_by="operator", verified_at=NOW)

    claims = repo.verified_events_for_member(events[0].member_id)
    assert len(claims) == 1
    event, counterparty = claims[0]
    # Round-trips through raw SQL: provenance and the counterparty-by-UUID link.
    assert event.id == shareholding.id
    assert event.counterparty_id == counterparty.id
    assert counterparty.raw_string == "BHP Group Ltd"
    assert counterparty.resolved is False
    assert event.provenance.document_id == shareholding.provenance.document_id
    assert event.provenance.page == 1
    assert event.verification_status.value == "verified"

    rendered = service.render_member_interests(repo=repo, member_name="Jane Member")
    assert 'as declared: "BHP Group Ltd"' in rendered
    assert "Acme Trust" not in rendered
