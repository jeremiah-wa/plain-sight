"""The per-member change-history view, asserted directly against Postgres.

This is PRD seam 2 in its *timeline* shape: the append-only event log
reconstructed into a member's ordered change history through a SQL view over the
log (never a stored snapshot). Where ``test_bitemporal_views`` exercises the
point-in-time state views ("what did the member hold as of date D"), this
exercises the timeline question ("what was acquired and divested and when, in
sequence") over the same log.

The defining behaviour under test is that a *superseded* event stays visible in
history (marked by its ``superseded_by`` pointer), never dropped: a reader must
see that a fact was declared and later corrected. Both time axes are surfaced per
row: valid time (effective acquire/divest dates) and record time
(ingested/verified stamps).

Opt-in via the shared ``postgres_conn`` fixture (see ``conftest.py``): set
``PLAIN_SIGHT_TEST_DATABASE_URL`` to a reachable, disposable database.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from plain_sight.db import PostgresRepository
from plain_sight.db.repository import ChangeHistoryEntry
from plain_sight.domain import (
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    Person,
    Provenance,
    SourceDocument,
    VerificationStatus,
)

pytestmark = pytest.mark.postgres

FETCHED = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

JANE_ID = UUID(int=0xA1)
OTHER_ID = UUID(int=0xA2)
DOCUMENT_ID = UUID(int=0xD0)
IRONBARK_ID = UUID(int=0xC0)  # a directorship acquired then divested, recorded once
BHP_ID = UUID(int=0xC1)  # a stable, still-held shareholding
SUNRISE_ID = UUID(int=0xC2)  # declared open-ended, then corrected to a closed period
OTHER_HOLDING_ID = UUID(int=0xC3)  # belongs to the other member, must not leak

# Distinct record-time stamps so the timeline order is deterministic and so a
# correction provably sorts *after* the version it supersedes.
INGEST_IRONBARK = datetime(2026, 1, 1, tzinfo=UTC)
INGEST_BHP = datetime(2026, 1, 2, tzinfo=UTC)
INGEST_SUNRISE_ORIGINAL = datetime(2026, 1, 3, tzinfo=UTC)
INGEST_SUNRISE_CLOSED = datetime(2026, 1, 4, tzinfo=UTC)
VERIFIED_AT = datetime(2026, 2, 1, tzinfo=UTC)


@pytest.fixture
def repo(postgres_conn: psycopg.Connection[Any]) -> PostgresRepository:
    """A repository seeded with two members, one document, four counterparties."""

    repository = PostgresRepository(postgres_conn)
    repository.add_person(Person(id=JANE_ID, canonical_name="Jane Member"))
    repository.add_person(Person(id=OTHER_ID, canonical_name="Other Member"))
    repository.add_source_document(
        SourceDocument(
            id=DOCUMENT_ID,
            member_id=JANE_ID,
            content_sha256="0" * 64,
            storage_path="documents/jane.pdf",
            page_count=1,
            fetched_at=FETCHED,
        )
    )
    for cid, raw in (
        (IRONBARK_ID, "Ironbark Consulting"),
        (BHP_ID, "BHP Group Ltd"),
        (SUNRISE_ID, "Sunrise Pty Ltd"),
        (OTHER_HOLDING_ID, "Wattle Holdings"),
    ):
        repository.add_counterparty(Counterparty(id=cid, raw_string=raw, normalised_label=raw))
    postgres_conn.commit()
    return repository


def _event(
    *,
    valid_from: date | None,
    valid_to: date | None,
    ingested_at: datetime,
    member_id: UUID = JANE_ID,
    counterparty_id: UUID = BHP_ID,
    category: InterestCategory = InterestCategory.SHAREHOLDING,
) -> DeclarationEvent:
    return DeclarationEvent(
        id=uuid4(),
        member_id=member_id,
        counterparty_id=counterparty_id,
        category=category,
        valid_from=valid_from,
        valid_to=valid_to,
        provenance=Provenance(
            document_id=DOCUMENT_ID,
            page=1,
            extraction_method="stub-extractor",
            extraction_confidence=0.9,
            fetch_timestamp=FETCHED,
        ),
        ingested_at=ingested_at,
    )


def _seed_history(
    repo: PostgresRepository, conn: psycopg.Connection[Any]
) -> dict[str, DeclarationEvent]:
    """Seed the event log Jane's change history is reconstructed from.

    Three shapes, spanning both a clean acquire-then-divest and a correction:

    - ``ironbark``: a directorship acquired 2018 and divested 2021, recorded
      correctly the first time as a single bounded period (both endpoints in one
      row). Never superseded.
    - ``bhp``: a shareholding held from 2019, open-ended and never altered; later
      *verified*, to exercise record-time verification surfacing. Still current.
    - ``sunrise_original`` then ``sunrise_closed``: a correction. The property was
      first declared held open-endedly (2020, open-ended), then an alteration
      superseded that with a closed period (sold 2022-06-01). The original is
      retained, marked superseded, and must still appear in history.

    Returns the events keyed by name.
    """

    ironbark = _event(
        valid_from=date(2018, 1, 1),
        valid_to=date(2021, 1, 1),
        ingested_at=INGEST_IRONBARK,
        counterparty_id=IRONBARK_ID,
        category=InterestCategory.DIRECTORSHIP,
    )
    bhp = _event(valid_from=date(2019, 1, 1), valid_to=None, ingested_at=INGEST_BHP)
    sunrise_original = _event(
        valid_from=date(2020, 1, 1),
        valid_to=None,
        ingested_at=INGEST_SUNRISE_ORIGINAL,
        counterparty_id=SUNRISE_ID,
        category=InterestCategory.REAL_ESTATE,
    )
    repo.add_declaration_event(ironbark)
    repo.add_declaration_event(bhp)
    repo.add_declaration_event(sunrise_original)
    repo.verify_event(bhp.id, verified_by="clerk", verified_at=VERIFIED_AT)
    conn.commit()

    # The alteration overlaps the version it corrects, so append the successor and
    # mark the predecessor superseded atomically with the constraint deferred.
    sunrise_closed = _event(
        valid_from=date(2020, 1, 1),
        valid_to=date(2022, 6, 1),
        ingested_at=INGEST_SUNRISE_CLOSED,
        counterparty_id=SUNRISE_ID,
        category=InterestCategory.REAL_ESTATE,
    )
    with conn.transaction():
        conn.execute("SET CONSTRAINTS declaration_event_no_active_overlap DEFERRED")
        repo.add_declaration_event(sunrise_closed)
        conn.execute(
            "UPDATE declaration_event SET superseded_by = %s WHERE id = %s",
            (sunrise_closed.id, sunrise_original.id),
        )

    # An unrelated holding for the other member, to prove per-member scoping.
    repo.add_declaration_event(
        _event(
            valid_from=date(2017, 1, 1),
            valid_to=None,
            ingested_at=INGEST_IRONBARK,
            member_id=OTHER_ID,
            counterparty_id=OTHER_HOLDING_ID,
        )
    )
    conn.commit()
    return {
        "ironbark": ironbark,
        "bhp": bhp,
        "sunrise_original": sunrise_original,
        "sunrise_closed": sunrise_closed,
    }


def _by_id(history: list[ChangeHistoryEntry], event_id: UUID) -> ChangeHistoryEntry:
    return next(entry for entry in history if entry.event.id == event_id)


def test_history_lists_every_event_in_chronological_sequence(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    events = _seed_history(repo, postgres_conn)

    history = repo.change_history_for_member(JANE_ID)

    # Ordered by valid-time acquisition, then record time: the divested directorship
    # (2018) first, then the still-held shareholding (2019), then the Sunrise pair
    # (both 2020, the correction sorting after the original it supersedes).
    assert [entry.event.id for entry in history] == [
        events["ironbark"].id,
        events["bhp"].id,
        events["sunrise_original"].id,
        events["sunrise_closed"].id,
    ]
    assert [entry.counterparty.raw_string for entry in history] == [
        "Ironbark Consulting",
        "BHP Group Ltd",
        "Sunrise Pty Ltd",
        "Sunrise Pty Ltd",
    ]


def test_superseded_events_remain_visible_and_marked(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    events = _seed_history(repo, postgres_conn)

    history = repo.change_history_for_member(JANE_ID)

    # The superseded original is NOT dropped: it is present, and marked by a pointer
    # to the successor that replaced it.
    superseded = _by_id(history, events["sunrise_original"].id)
    assert superseded.superseded_by == events["sunrise_closed"].id

    # Every other row is a current version of its record: no marker.
    assert _by_id(history, events["sunrise_closed"].id).superseded_by is None
    assert _by_id(history, events["bhp"].id).superseded_by is None
    assert _by_id(history, events["ironbark"].id).superseded_by is None


def test_each_row_surfaces_both_valid_time_and_record_time(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    events = _seed_history(repo, postgres_conn)

    history = repo.change_history_for_member(JANE_ID)

    # Valid time: acquisition and divestment endpoints are both readable. The
    # directorship carries both (acquired 2018, divested 2021); the correction
    # carries the divestment date (sold 2022-06-01); BHP is still held (open upper).
    ironbark = _by_id(history, events["ironbark"].id).event
    assert (ironbark.valid_from, ironbark.valid_to) == (date(2018, 1, 1), date(2021, 1, 1))
    assert _by_id(history, events["sunrise_closed"].id).event.valid_to == date(2022, 6, 1)
    assert _by_id(history, events["bhp"].id).event.valid_to is None

    # Record time is present on every row (when the fact entered the record) ...
    for entry in history:
        assert entry.event.ingested_at is not None
        assert entry.event.provenance.fetch_timestamp == FETCHED

    # ... and a verified row surfaces its verification record time and status.
    bhp = _by_id(history, events["bhp"].id).event
    assert bhp.verification_status is VerificationStatus.VERIFIED
    assert bhp.verified_at == VERIFIED_AT
    assert bhp.verified_by == "clerk"


def test_history_is_scoped_to_the_member(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    _seed_history(repo, postgres_conn)

    jane_labels = {e.counterparty.raw_string for e in repo.change_history_for_member(JANE_ID)}
    assert "Wattle Holdings" not in jane_labels

    other = repo.change_history_for_member(OTHER_ID)
    assert {e.counterparty.raw_string for e in other} == {"Wattle Holdings"}
