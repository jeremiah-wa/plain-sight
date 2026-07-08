"""A tiny forward-only migration runner for hand-authored SQL files.

No autogenerate: the bitemporal core this schema grows into (range types, GIST
exclusion constraints, "state as of D" views) is exactly what an ORM's
autogenerate cannot see, so migrations are authored by hand and applied in order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_BOOKKEEPING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def apply_migrations(conn: psycopg.Connection[Any]) -> list[str]:
    """Apply any unapplied ``*.sql`` files in order; return the ones applied."""

    conn.execute(_BOOKKEEPING)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    newly_applied: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.stem
        if version in applied:
            continue
        conn.execute(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        newly_applied.append(version)

    conn.commit()
    return newly_applied
