"""The bitemporal query views, asserted directly against Postgres.

This is PRD seam 2: the append-only event log, reconstructed into queryable state
through SQL views over the log (never stored/materialised snapshots). Two shapes
are exercised:

- **current state**: the active, non-superseded interests a member holds *now*
  (record-time current *and* valid-time current), and
- **state as of date D**: what a member held as of an arbitrary valid-time date,
  which is what lets a researcher check holdings at the time of a relevant vote.

The whole point is raw SQL temporal reconstruction, so these tests seed a sequence
of declaration + alteration (supersession) events and query the views directly.
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
OTHER_ID = UUID(int=0xA2)
DOCUMENT_ID = UUID(int=0xD0)
BHP_ID = UUID(int=0xC1)  # a stable, still-held holding
SUNRISE_ID = UUID(int=0xC2)  # held then sold: an alteration closes the period
OTHER_HOLDING_ID = UUID(int=0xC3)  # belongs to the other member, must not leak


@pytest.fixture
def repo(postgres_conn: psycopg.Connection[Any]) -> PostgresRepository:
    """A repository seeded with two members, one document, three counterparties."""

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
            fetched_at=NOW,
        )
    )
    for cid, raw in (
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
    member_id: UUID = JANE_ID,
    counterparty_id: UUID = BHP_ID,
    category: InterestCategory = InterestCategory.SHAREHOLDING,
    ingested_at: datetime = NOW,
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
            fetch_timestamp=NOW,
        ),
        ingested_at=ingested_at,
    )


def _seed_history(
    repo: PostgresRepository, conn: psycopg.Connection[Any]
) -> tuple[DeclarationEvent, DeclarationEvent, DeclarationEvent]:
    """Seed the event log Jane's interests are reconstructed from.

    - ``bhp``: shareholding held from 2019, open-ended and never altered.
    - ``sunrise_original``: real estate declared held from 2020, open-ended.
    - ``sunrise_closed``: an *alteration* superseding the original: the property
      was sold, so the period is closed at 2022-06-01. The original is retained,
      marked superseded, never deleted.

    Returns ``(bhp, sunrise_original, sunrise_closed)``.
    """

    bhp = _event(valid_from=date(2019, 1, 1), valid_to=None)
    sunrise_original = _event(
        valid_from=date(2020, 1, 1),
        valid_to=None,
        counterparty_id=SUNRISE_ID,
        category=InterestCategory.REAL_ESTATE,
    )
    repo.add_declaration_event(bhp)
    repo.add_declaration_event(sunrise_original)
    conn.commit()

    # The alteration overlaps the version it corrects, so append the successor and
    # mark the predecessor superseded atomically with the constraint deferred.
    sunrise_closed = _event(
        valid_from=date(2020, 1, 1),
        valid_to=date(2022, 6, 1),
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

    # An unrelated current holding for the other member, to prove per-member scoping.
    repo.add_declaration_event(
        _event(
            valid_from=date(2018, 1, 1),
            valid_to=None,
            member_id=OTHER_ID,
            counterparty_id=OTHER_HOLDING_ID,
        )
    )
    conn.commit()
    return bhp, sunrise_original, sunrise_closed


def _labels(claims: list[tuple[DeclarationEvent, Counterparty]]) -> set[str]:
    return {counterparty.raw_string for _, counterparty in claims}


def _ids(claims: list[tuple[DeclarationEvent, Counterparty]]) -> set[UUID]:
    return {event.id for event, _ in claims}


def test_current_state_returns_only_active_non_superseded_holdings(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    bhp, sunrise_original, sunrise_closed = _seed_history(repo, postgres_conn)

    current = repo.current_interests_for_member(JANE_ID)

    # BHP is open-ended and unaltered, so it is current. Sunrise was sold in 2022,
    # so it is no longer held; the superseded original is invisible either way.
    assert _labels(current) == {"BHP Group Ltd"}
    assert _ids(current) == {bhp.id}
    assert sunrise_original.id not in _ids(current)  # superseded, honoured
    assert sunrise_closed.id not in _ids(current)  # active but validity has ended
    # The other member's current holding does not leak in.
    assert "Wattle Holdings" not in _labels(current)


def test_state_as_of_date_returns_the_historically_correct_set(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    _bhp, _sunrise_original, _sunrise_closed = _seed_history(repo, postgres_conn)

    # 2019: only BHP had begun.
    assert _labels(repo.interests_as_of(JANE_ID, date(2019, 6, 1))) == {"BHP Group Ltd"}
    # 2021: both BHP and Sunrise were held.
    assert _labels(repo.interests_as_of(JANE_ID, date(2021, 1, 1))) == {
        "BHP Group Ltd",
        "Sunrise Pty Ltd",
    }
    # 2023: Sunrise had been sold (period closed 2022-06-01); BHP remains.
    assert _labels(repo.interests_as_of(JANE_ID, date(2023, 1, 1))) == {"BHP Group Ltd"}


def test_superseded_event_is_absent_but_prior_state_is_recoverable(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    _bhp, sunrise_original, sunrise_closed = _seed_history(repo, postgres_conn)

    # The superseded original (which claimed Sunrise was held open-endedly) never
    # surfaces, neither in current state nor at any valid-time date.
    for claims in (
        repo.current_interests_for_member(JANE_ID),
        repo.interests_as_of(JANE_ID, date(2021, 1, 1)),
        repo.interests_as_of(JANE_ID, date(2025, 1, 1)),
    ):
        assert sunrise_original.id not in _ids(claims)

    # Yet the prior state is still recoverable as of the date it was valid: Sunrise
    # *was* held in 2021, reconstructed through the surviving (corrected) event.
    as_of_2021 = repo.interests_as_of(JANE_ID, date(2021, 1, 1))
    sunrise_claim = next((e for e, c in as_of_2021 if c.raw_string == "Sunrise Pty Ltd"), None)
    assert sunrise_claim is not None
    assert sunrise_claim.id == sunrise_closed.id


def _seed_change_history(
    repo: PostgresRepository, conn: psycopg.Connection[Any]
) -> tuple[DeclarationEvent, DeclarationEvent, DeclarationEvent]:
    """Seed an acquire -> divest-via-correction sequence with distinct record times.

    Unlike :func:`_seed_history`, each event carries its own ``ingested_at`` so the
    change history has a genuine record-time order to assert:

    - ``bhp``: shareholding acquired 2019, recorded 2019, never altered.
    - ``sunrise_original``: real estate acquired 2020, recorded 2020, open-ended;
      later superseded (retained, never deleted).
    - ``sunrise_closed``: the correction recorded 2022 that divests Sunrise by
      closing its period at 2022-06-01 and supersedes the open-ended original.

    Returns ``(bhp, sunrise_original, sunrise_closed)``.
    """

    bhp = _event(
        valid_from=date(2019, 1, 1),
        valid_to=None,
        ingested_at=datetime(2019, 2, 1, 12, 0, tzinfo=UTC),
    )
    sunrise_original = _event(
        valid_from=date(2020, 1, 1),
        valid_to=None,
        counterparty_id=SUNRISE_ID,
        category=InterestCategory.REAL_ESTATE,
        ingested_at=datetime(2020, 2, 1, 12, 0, tzinfo=UTC),
    )
    repo.add_declaration_event(bhp)
    repo.add_declaration_event(sunrise_original)
    conn.commit()

    sunrise_closed = _event(
        valid_from=date(2020, 1, 1),
        valid_to=date(2022, 6, 1),
        counterparty_id=SUNRISE_ID,
        category=InterestCategory.REAL_ESTATE,
        ingested_at=datetime(2022, 7, 1, 12, 0, tzinfo=UTC),
    )
    with conn.transaction():
        conn.execute("SET CONSTRAINTS declaration_event_no_active_overlap DEFERRED")
        repo.add_declaration_event(sunrise_closed)
        conn.execute(
            "UPDATE declaration_event SET superseded_by = %s WHERE id = %s",
            (sunrise_closed.id, sunrise_original.id),
        )

    # A holding for the other member, to prove per-member scoping of the history.
    repo.add_declaration_event(
        _event(
            valid_from=date(2018, 1, 1),
            valid_to=None,
            member_id=OTHER_ID,
            counterparty_id=OTHER_HOLDING_ID,
            ingested_at=datetime(2018, 2, 1, 12, 0, tzinfo=UTC),
        )
    )
    conn.commit()
    return bhp, sunrise_original, sunrise_closed


def test_change_history_orders_by_record_time_and_keeps_superseded_marked(
    repo: PostgresRepository, postgres_conn: psycopg.Connection[Any]
) -> None:
    bhp, sunrise_original, sunrise_closed = _seed_change_history(repo, postgres_conn)

    history = repo.change_history_for_member(JANE_ID)

    # The full chronological sequence of changes, ordered by record time (when each
    # fact entered the record): acquire BHP, acquire Sunrise, then the correction
    # that divests it. The superseded original is present, never dropped.
    assert [change.event.id for change in history] == [
        bhp.id,
        sunrise_original.id,
        sunrise_closed.id,
    ]

    # The other member's holding does not leak into Jane's history.
    assert OTHER_HOLDING_ID not in {change.counterparty.id for change in history}

    # Supersession is surfaced as a marker, not by dropping the row: the corrected
    # original stays visible, marked superseded; the acquisitions/correction do not.
    by_id = {change.event.id: change for change in history}
    assert by_id[sunrise_original.id].superseded is True
    assert by_id[sunrise_closed.id].superseded is False
    assert by_id[bhp.id].superseded is False

    # Each row surfaces both axes: valid time (effective) and record time (ingested).
    divest = by_id[sunrise_closed.id]
    assert divest.event.valid_from == date(2020, 1, 1)  # acquired (valid time)
    assert divest.event.valid_to == date(2022, 6, 1)  # divested (valid time)
    assert divest.event.ingested_at == datetime(2022, 7, 1, 12, 0, tzinfo=UTC)  # record time
