"""Query-time counterparty similarity over pgvector, asserted against Postgres.

This is issue #11 / PRD story 2: "find declarations related to company X" served
by **pgvector similarity at query time**, never by a materialised cluster entity
or a clustering pipeline. Counterparties carry an embedding; the search ranks the
reconstructed interests by how near their counterparty's embedding is to a query
vector, and that ranking composes with structured (category) and temporal
(as-of-date) filters in a single SQL query.

Embeddings are seeded directly with known near/far vectors so the ranking is a
pure pgvector computation with no live embedding model in the loop. The vectors
are deliberately axis-aligned: "near" counterparties point along the query's
dominant axis, "far" ones point orthogonally, so cosine distance separates them
cleanly.

Opt-in via the shared ``postgres_conn`` fixture (see ``conftest.py``): set
``PLAIN_SIGHT_TEST_DATABASE_URL`` to a reachable, disposable database with the
``vector`` extension available.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from plain_sight.db import PostgresRepository
from plain_sight.db.postgres import EMBEDDING_DIMENSIONS
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

JANE_ID = UUID(int=0xA1)
DOCUMENT_ID = UUID(int=0xD0)
BHP_ID = UUID(int=0xC1)  # near the "mining company" query
RIO_ID = UUID(int=0xC2)  # also near, a second mining company
WOODSIDE_ID = UUID(int=0xC3)  # far: an unrelated counterparty


def _axis(index: int, *, blend: float = 0.0) -> list[float]:
    """A unit-ish embedding pointing along ``index`` (with a little ``blend`` on 0).

    Axis-aligned vectors make cosine distance interpretable: two vectors on the
    same axis are near (distance ~0), on orthogonal axes far (distance ~1).
    """

    vec = [0.0] * EMBEDDING_DIMENSIONS
    vec[index] = 1.0
    if blend:
        vec[0] += blend
    return vec


# The query vector points along axis 0: the "mining company" concept.
QUERY = _axis(0)
# BHP is dead-on the query axis; Rio is close (mostly axis 0, a little axis 1);
# Woodside is orthogonal (axis 5), the far case.
BHP_EMBEDDING = _axis(0)
RIO_EMBEDDING = [1.0, 0.15, *([0.0] * (EMBEDDING_DIMENSIONS - 2))]
WOODSIDE_EMBEDDING = _axis(5)


@pytest.fixture
def repo(postgres_conn: psycopg.Connection[Any]) -> PostgresRepository:
    """One member, one document, three counterparties carrying known embeddings."""

    repository = PostgresRepository(postgres_conn)
    repository.add_person(Person(id=JANE_ID, canonical_name="Jane Member"))
    repository.add_source_document(
        SourceDocument(
            id=DOCUMENT_ID,
            member_id=JANE_ID,
            content_sha256="0" * 64,
            storage_path="documents/jane.pdf",
            page_count=1,
            fetched_at=NOW,
        )
    )
    for cid, raw, embedding in (
        (BHP_ID, "BHP Group Ltd", BHP_EMBEDDING),
        (RIO_ID, "Rio Tinto Ltd", RIO_EMBEDDING),
        (WOODSIDE_ID, "Woodside Energy", WOODSIDE_EMBEDDING),
    ):
        repository.add_counterparty(Counterparty(id=cid, raw_string=raw, normalised_label=raw))
        repository.set_counterparty_embedding(cid, embedding)
    postgres_conn.commit()
    return repository


def _event(
    *,
    counterparty_id: UUID,
    category: InterestCategory = InterestCategory.SHAREHOLDING,
    valid_from: date | None = date(2020, 1, 1),
    valid_to: date | None = None,
) -> DeclarationEvent:
    return DeclarationEvent(
        id=uuid4(),
        member_id=JANE_ID,
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


def _labels(results: Sequence[tuple[DeclarationEvent, Counterparty, float]]) -> list[str]:
    return [counterparty.raw_string for _, counterparty, _ in results]


def test_near_counterparties_rank_above_far(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    repo.add_declaration_event(_event(counterparty_id=BHP_ID))
    repo.add_declaration_event(_event(counterparty_id=RIO_ID))
    repo.add_declaration_event(_event(counterparty_id=WOODSIDE_ID))
    postgres_conn.commit()

    results = repo.similar_counterparty_interests(QUERY)

    # All three surface, ordered nearest-first: BHP (on-axis) then Rio (near) then
    # Woodside (orthogonal, far).
    assert _labels(results) == ["BHP Group Ltd", "Rio Tinto Ltd", "Woodside Energy"]
    distances = [distance for _, _, distance in results]
    assert distances == sorted(distances)
    assert distances[0] < distances[-1]  # near strictly nearer than far

    # Results are cited records, not resolved legal identities: provenance points
    # back at the source, and the counterparty stays explicitly provisional. No ACN
    # is asserted (there is no such field to assert).
    for event, counterparty, _ in results:
        assert event.provenance.document_id == DOCUMENT_ID
        assert counterparty.resolved is False


def test_similarity_composes_with_structured_and_temporal_filters(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    # BHP: a shareholding held 2020 onward (near the query).
    repo.add_declaration_event(
        _event(counterparty_id=BHP_ID, category=InterestCategory.SHAREHOLDING)
    )
    # Rio: also near the query, but a *directorship* — excluded by the category filter.
    repo.add_declaration_event(
        _event(counterparty_id=RIO_ID, category=InterestCategory.DIRECTORSHIP)
    )
    # Woodside: a shareholding, but sold in 2021 — excluded by the as-of filter.
    repo.add_declaration_event(
        _event(
            counterparty_id=WOODSIDE_ID,
            category=InterestCategory.SHAREHOLDING,
            valid_from=date(2019, 1, 1),
            valid_to=date(2021, 1, 1),
        )
    )
    postgres_conn.commit()

    # Similarity + structured (category) + temporal (as-of) in a single query.
    results = repo.similar_counterparty_interests(
        QUERY,
        category=InterestCategory.SHAREHOLDING,
        as_of=date(2022, 6, 1),
    )

    # Only BHP satisfies all three: near, a shareholding, and still held in 2022.
    # Rio is filtered by category; Woodside by the as-of date, even though both are
    # otherwise near the query. Filtering composes with, does not bypass, ranking.
    assert _labels(results) == ["BHP Group Ltd"]
