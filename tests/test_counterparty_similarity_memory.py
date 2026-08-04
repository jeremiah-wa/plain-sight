"""Query-time counterparty similarity, unit-tested against the in-memory repo.

The postgres-marked ``test_counterparty_similarity`` asserts the same behaviour
against a live pgvector database (and auto-skips without one). This file is the
always-on unit coverage: it drives the identical ranking + filter-composition
contract through :class:`~plain_sight.db.InMemoryRepository`, whose cosine
distance mirrors pgvector's ``<=>``, and exercises the mockable embedding seam so
"near a query string" is verified with no live model and no database.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from plain_sight import service
from plain_sight.db import EMBEDDING_DIMENSIONS, InMemoryRepository, SimilarInterest
from plain_sight.domain import (
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    Provenance,
)
from plain_sight.embedding import StubEmbeddingProvider

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

JANE_ID = UUID(int=0xA1)
DOCUMENT_ID = UUID(int=0xD0)
BHP_ID = UUID(int=0xC1)
RIO_ID = UUID(int=0xC2)
WOODSIDE_ID = UUID(int=0xC3)


def _axis(index: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIMENSIONS
    vec[index] = 1.0
    return vec


# The query points along axis 0 ("mining company"). BHP is dead-on it, Rio is
# close (mostly axis 0, a little axis 1), Woodside is orthogonal (axis 5, far).
QUERY = _axis(0)
BHP_EMBEDDING = _axis(0)
RIO_EMBEDDING = [1.0, 0.15, *([0.0] * (EMBEDDING_DIMENSIONS - 2))]
WOODSIDE_EMBEDDING = _axis(5)


def _repo() -> InMemoryRepository:
    repo = InMemoryRepository()
    for cid, raw, embedding in (
        (BHP_ID, "BHP Group Ltd", BHP_EMBEDDING),
        (RIO_ID, "Rio Tinto Ltd", RIO_EMBEDDING),
        (WOODSIDE_ID, "Woodside Energy", WOODSIDE_EMBEDDING),
    ):
        repo.add_counterparty(Counterparty(id=cid, raw_string=raw, normalised_label=raw))
        repo.set_counterparty_embedding(cid, embedding)
    return repo


def _event(
    *,
    counterparty_id: UUID,
    category: InterestCategory = InterestCategory.SHAREHOLDING,
    valid_from: date | None = date(2020, 1, 1),
    valid_to: date | None = None,
    ingested_at: datetime = NOW,
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
        ingested_at=ingested_at,
    )


def _labels(results: Sequence[SimilarInterest]) -> list[str]:
    return [counterparty.raw_string for _, counterparty, _ in results]


def test_near_counterparties_rank_above_far() -> None:
    repo = _repo()
    # Distinct ingested_at so the ordering under test is similarity, not a tie-break.
    repo.add_declaration_event(
        _event(counterparty_id=BHP_ID, ingested_at=datetime(2026, 1, 3, tzinfo=UTC))
    )
    repo.add_declaration_event(
        _event(counterparty_id=RIO_ID, ingested_at=datetime(2026, 1, 2, tzinfo=UTC))
    )
    repo.add_declaration_event(
        _event(counterparty_id=WOODSIDE_ID, ingested_at=datetime(2026, 1, 1, tzinfo=UTC))
    )

    results = repo.similar_counterparty_interests(QUERY)

    assert _labels(results) == ["BHP Group Ltd", "Rio Tinto Ltd", "Woodside Energy"]
    distances = [distance for _, _, distance in results]
    assert distances == sorted(distances)
    assert distances[0] < distances[-1]

    # Cited records, not resolved identities: provenance survives, the
    # counterparty stays provisional, and there is no ACN field to assert.
    for event, counterparty, _ in results:
        assert event.provenance.document_id == DOCUMENT_ID
        assert counterparty.resolved is False


def test_similarity_composes_with_structured_and_temporal_filters() -> None:
    repo = _repo()
    # BHP: a shareholding held 2020 onward (near the query).
    repo.add_declaration_event(
        _event(counterparty_id=BHP_ID, category=InterestCategory.SHAREHOLDING)
    )
    # Rio: near, but a directorship, so excluded by the category filter.
    repo.add_declaration_event(
        _event(counterparty_id=RIO_ID, category=InterestCategory.DIRECTORSHIP)
    )
    # Woodside: a shareholding, but sold in 2021, so excluded by the as-of filter.
    repo.add_declaration_event(
        _event(
            counterparty_id=WOODSIDE_ID,
            category=InterestCategory.SHAREHOLDING,
            valid_from=date(2019, 1, 1),
            valid_to=date(2021, 1, 1),
        )
    )

    results = repo.similar_counterparty_interests(
        QUERY,
        category=InterestCategory.SHAREHOLDING,
        as_of=date(2022, 6, 1),
    )

    # Only BHP is near, a shareholding, and still held in 2022. Filtering composes
    # with, does not bypass, the ranking.
    assert _labels(results) == ["BHP Group Ltd"]


def test_counterparties_without_an_embedding_are_absent() -> None:
    repo = _repo()
    # A fourth counterparty that never gets embedded must not surface at all.
    unranked = UUID(int=0xC9)
    repo.add_counterparty(
        Counterparty(id=unranked, raw_string="No Vector Pty", normalised_label="No Vector Pty")
    )
    repo.add_declaration_event(_event(counterparty_id=BHP_ID))
    repo.add_declaration_event(_event(counterparty_id=unranked))

    results = repo.similar_counterparty_interests(QUERY)

    assert _labels(results) == ["BHP Group Ltd"]


def test_find_similar_interests_embeds_the_query_string_through_the_seam() -> None:
    """The service embeds a *string* via the seam, then ranks by that vector."""

    repo = _repo()
    repo.add_declaration_event(_event(counterparty_id=BHP_ID))
    repo.add_declaration_event(_event(counterparty_id=WOODSIDE_ID))

    # The stub pins the query string to the on-axis vector, so "mining company"
    # embeds to BHP's neighbourhood without any live model.
    embedder = StubEmbeddingProvider(vectors={"mining company": QUERY})

    results = service.find_similar_interests(repo=repo, embedder=embedder, query="mining company")

    assert _labels(results) == ["BHP Group Ltd", "Woodside Energy"]
    assert results[0][2] < results[1][2]


def test_ingest_embeds_counterparties_so_they_become_searchable() -> None:
    """With an embedder wired in, ingest gives counterparties a retrieval vector."""

    repo = InMemoryRepository()
    embedder = StubEmbeddingProvider(vectors={"BHP Group Ltd": QUERY, "query": QUERY})
    repo.add_counterparty(
        Counterparty(id=BHP_ID, raw_string="BHP Group Ltd", normalised_label="BHP Group Ltd")
    )
    repo.set_counterparty_embedding(BHP_ID, embedder.embed("BHP Group Ltd"))
    repo.add_declaration_event(_event(counterparty_id=BHP_ID))

    results = service.find_similar_interests(repo=repo, embedder=embedder, query="query")

    assert _labels(results) == ["BHP Group Ltd"]
