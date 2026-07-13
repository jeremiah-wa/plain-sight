"""Database access: hand-written SQL over ``psycopg`` v3, no ORM."""

from __future__ import annotations

from plain_sight.db.memory import InMemoryRepository
from plain_sight.db.migrate import apply_migrations
from plain_sight.db.postgres import EMBEDDING_DIMENSIONS, PostgresRepository
from plain_sight.db.repository import (
    MemberInterest,
    Repository,
    SimilarInterest,
    VerifiedClaim,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "InMemoryRepository",
    "MemberInterest",
    "PostgresRepository",
    "Repository",
    "SimilarInterest",
    "VerifiedClaim",
    "apply_migrations",
]
