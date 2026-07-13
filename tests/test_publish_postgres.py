"""The publish gate against a real Postgres: verified-only, physically absent.

Opt-in via the shared ``postgres_conn`` fixture. Seeds mixed verified/pending
rows into the actual system of record, runs the publish gate, and asserts
against the *emitted HTML* (not a live query) that the pending claim is
physically absent from the artifact. This is the faithful, seam-level form of
the dedicated verified-only test the PRD mandates (PRD seam 3).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from plain_sight import publish, service
from plain_sight.db import PostgresRepository
from plain_sight.domain import CandidateDeclaration, ExtractionResult, InterestCategory
from plain_sight.extraction import StubExtractor
from plain_sight.sources import DocumentStore

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)


def test_publish_from_postgres_omits_pending_rows(
    postgres_conn: psycopg.Connection[Any],
    tmp_path: Path,
    sample_pdf_bytes: bytes,
    id_factory: Callable[[], UUID],
) -> None:
    conn = postgres_conn
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

    with conn.transaction():
        events = service.ingest(
            repo=repo,
            store=store,
            extractor=extractor,
            member_name="Jane Member",
            pdf_bytes=sample_pdf_bytes,
            now=NOW,
            source_url="https://example.test/register.pdf",
            id_factory=id_factory,
        )

    # Verify exactly one of the two pending claims.
    shareholding = next(e for e in events if e.category is InterestCategory.SHAREHOLDING)
    with conn.transaction():
        assert repo.verify_event(shareholding.id, verified_by="operator", verified_at=NOW)

    html = publish.render_member_page(
        repo=repo, member_name="Jane Member", generated_at=GENERATED_AT
    )

    # The verified row is present with its source link; the pending row is
    # physically absent from the artifact, not merely filtered.
    assert 'as declared: "BHP Group Ltd"' in html
    assert 'href="https://example.test/register.pdf#page=1"' in html
    assert "Acme Trust" not in html
    assert "mirrors the official record" in html
