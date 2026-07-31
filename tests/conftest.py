"""Shared test helpers: deterministic ids and the checked-in scan fixture."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from local_postgres import TargetDatabase, connect, resolve_test_database
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


@pytest.fixture(scope="session")
def postgres_target() -> TargetDatabase:
    """The vetted database the Postgres tests run against, probed once per session.

    Defaults to the ephemeral container in ``compose.yaml``; override with
    ``PLAIN_SIGHT_TEST_DATABASE_URL``. Either way it must be a loopback host with
    a ``*_test`` database, or :mod:`local_postgres` refuses outright. Session
    scope so a container that is not running costs one connect timeout for the
    whole run, not one per test: pytest replays the cached skip.
    """

    database = resolve_test_database(os.environ)
    connect(database).close()
    return database


@pytest.fixture
def postgres_conn(postgres_target: TargetDatabase) -> Iterator[psycopg.Connection[Any]]:
    """A migrated, disposable Postgres connection for the ``postgres`` tests.

    The schema is dropped and re-migrated around each test, so nothing leaks
    between them or is left behind. The connection is yielded open (not used as
    ``with conn:``, which in psycopg 3 would close it); tests scope their own
    transactions with ``conn.transaction()``.
    """

    connection = connect(postgres_target)
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
