"""Shared test helpers: deterministic ids and the checked-in scan fixture."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from plain_sight.db import apply_migrations

FIXTURES = Path(__file__).parent / "fixtures"

# Every table the Postgres tests own, dropped around each test so a run starts
# from a known-empty schema and leaves nothing behind.
_POSTGRES_TABLES = "declaration_event, source_document, counterparty, person, schema_migrations"


def sequential_uuids(start: int = 1) -> Callable[[], UUID]:
    """A deterministic ``uuid4``-shaped factory: ``00000000-...-0001``, ``...0002``.

    Injected wherever production code takes an ``id_factory`` so a whole
    extract → map → store flow is reproducible and its ids can be asserted.
    """

    counter: Iterator[int] = iter(range(start, 1_000_000))

    def factory() -> UUID:
        return UUID(int=next(counter))

    return factory


@pytest.fixture
def id_factory() -> Callable[[], UUID]:
    """A fresh deterministic id factory per test."""

    return sequential_uuids()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """The checked-in one-page register scan the extraction tests run against."""

    return (FIXTURES / "sample_register_page.pdf").read_bytes()


@pytest.fixture
def postgres_conn() -> Iterator[psycopg.Connection[Any]]:
    """A migrated, disposable Postgres connection for the opt-in ``postgres`` tests.

    Opt-in: set ``PLAIN_SIGHT_TEST_DATABASE_URL`` to a reachable, disposable
    database, or the test skips. The schema is dropped and re-migrated around each
    test so nothing leaks between them or is left behind. The connection is
    yielded open (not used as ``with conn:``, which in psycopg 3 would close it);
    tests scope their own transactions with ``conn.transaction()``.
    """

    url = os.environ.get("PLAIN_SIGHT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set PLAIN_SIGHT_TEST_DATABASE_URL to run the Postgres tests")
    connection = psycopg.connect(url)
    try:
        connection.execute(f"DROP TABLE IF EXISTS {_POSTGRES_TABLES} CASCADE")
        connection.commit()
        apply_migrations(connection)
        yield connection
    finally:
        connection.rollback()
        connection.execute(f"DROP TABLE IF EXISTS {_POSTGRES_TABLES} CASCADE")
        connection.commit()
        connection.close()
