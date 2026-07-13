"""The repository seam: what the application needs from the system of record.

Two implementations satisfy this Protocol: an in-memory one (used to drive the
walking skeleton deterministically in tests) and a ``psycopg`` v3 + raw SQL one
(the real Postgres system of record). Keeping the contract explicit is what lets
the verified-only display rule be asserted without a live database while the SQL
implementation is checked against the same contract under the ``postgres`` mark.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple, Protocol
from uuid import UUID

from plain_sight.domain import Counterparty, DeclarationEvent, Person, SourceDocument

#: A verified claim paired with the counterparty it was declared against.
VerifiedClaim = tuple[DeclarationEvent, Counterparty]

#: An interest (a declaration event) paired with the counterparty it names, as
#: returned by the bitemporal query views. Unlike :data:`VerifiedClaim` this is not
#: verification-filtered: the views reconstruct temporal state, and the events they
#: return are the current (non-superseded) versions of the record, whatever their
#: verification status.
MemberInterest = tuple[DeclarationEvent, Counterparty]


class ChangeHistoryEntry(NamedTuple):
    """One row of a member's change history: a single change in the timeline.

    Where :data:`MemberInterest` returns only current (non-superseded) versions,
    change history retains *every* version, so a superseded event stays visible
    and is flagged rather than dropped. Both time axes are on the row: valid time
    (effective, via ``event.valid_from`` / ``event.valid_to``) and record time
    (when the fact entered the record, via ``event.ingested_at``).
    """

    event: DeclarationEvent
    counterparty: Counterparty
    #: ``True`` when a later correction superseded this event (``superseded_by``
    #: is set). The row is kept, never removed, so the correction is auditable.
    superseded: bool


class Repository(Protocol):
    """Persistence operations for the walking skeleton."""

    def add_person(self, person: Person) -> None: ...

    def get_person_by_canonical_name(self, canonical_name: str) -> Person | None: ...

    def add_source_document(self, document: SourceDocument) -> None: ...

    def add_counterparty(self, counterparty: Counterparty) -> None: ...

    def add_declaration_event(self, event: DeclarationEvent) -> None: ...

    def verify_event(self, event_id: UUID, *, verified_by: str, verified_at: datetime) -> bool:
        """Transition a ``pending`` claim to ``verified``.

        Returns ``True`` if a pending event was transitioned, ``False`` if the
        event does not exist or was already verified.
        """
        ...

    def verified_events_for_member(self, member_id: UUID) -> list[VerifiedClaim]:
        """Return only ``verified`` claims for a member, oldest first.

        This is the single query behind the text display; the verified-only
        filter lives here so nothing ``pending`` can reach the reader.
        """
        ...
