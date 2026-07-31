"""The guardrail around the destructive Postgres fixture.

The ``postgres_conn`` fixture drops and re-migrates the whole schema, so the
thing under test here is refusal: which databases it will point that at, and
which it will not. Every case below is a way the fixture could otherwise be
aimed at a database somebody cares about.
"""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from local_postgres import (
    LOCAL_TEST_DATABASE_URL,
    TEST_DATABASE_URL_VAR,
    TargetDatabase,
    UnsafeTestDatabaseError,
    connect,
    resolve_test_database,
)

# A loopback URL on a port nothing listens on, so `connect` fails at once and offline.
UNREACHABLE_URL = "postgresql://plain_sight:plain_sight@127.0.0.1:1/plain_sight_test"

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "compose.yaml"

# The `db` service's published port, as `"<host>:5432"`. Matched out of the raw
# text rather than parsed: one regex beats a YAML dependency for one line.
_PUBLISHED_PORT = re.compile(r'"(\d+):5432"')


@pytest.mark.parametrize(
    "url",
    [
        # The hosted system of record, the URL that was actually on hand.
        "postgresql://postgres:secret@db.abcdefgh.supabase.co:5432/plain_sight_test",
        # Keyword DSN, which a URL-shaped parser would read as a hostless local socket.
        "host=db.abcdefgh.supabase.co dbname=plain_sight_test user=postgres",
        # A prefix match on "localhost" is not a loopback check.
        "postgresql://plain_sight:plain_sight@localhost.attacker.example/plain_sight_test",
        # No host at all: a Unix socket to whatever local cluster is running.
        "postgresql:///plain_sight_test",
        # libpq connects to `hostaddr` and uses `host` only for authentication,
        # so a loopback-looking `host` proves nothing on its own.
        "host=localhost hostaddr=13.55.1.1 dbname=plain_sight_test",
    ],
)
def test_refuses_a_database_that_is_not_on_loopback(url: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        resolve_test_database({TEST_DATABASE_URL_VAR: url})


@pytest.mark.parametrize(
    "url",
    [
        # A local development database, one suffix away from the disposable one.
        "postgresql://plain_sight:plain_sight@localhost:15432/plain_sight",
        "postgresql://plain_sight:plain_sight@127.0.0.1:5432/postgres",
        # Suffix, not substring: a database merely containing "_test".
        "postgresql://plain_sight:plain_sight@localhost:15432/plain_sight_test_archive",
    ],
)
def test_refuses_a_loopback_database_not_named_for_disposal(url: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        resolve_test_database({TEST_DATABASE_URL_VAR: url})


def test_the_refusal_names_the_host_and_the_database() -> None:
    """The operator has to be able to see which database they nearly wiped."""

    with pytest.raises(UnsafeTestDatabaseError) as excinfo:
        resolve_test_database(
            {TEST_DATABASE_URL_VAR: "postgresql://postgres:secret@db.example.supabase.co/live"}
        )

    message = str(excinfo.value)
    assert "db.example.supabase.co" in message
    assert "live" in message
    assert "secret" not in message


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "127.0.0.1", "[::1]"])
def test_accepts_every_loopback_spelling(host: str) -> None:
    url = f"postgresql://plain_sight:plain_sight@{host}:15432/plain_sight_test"

    assert resolve_test_database({TEST_DATABASE_URL_VAR: url}) == TargetDatabase(url, explicit=True)


@pytest.mark.parametrize("environ", [{}, {TEST_DATABASE_URL_VAR: ""}])
def test_falls_back_to_the_compose_url_when_the_variable_is_unset(
    environ: dict[str, str],
) -> None:
    """Unset means "use the local container", not "skip the Postgres tests"."""

    resolved = resolve_test_database(environ)

    assert resolved == TargetDatabase(LOCAL_TEST_DATABASE_URL, explicit=False)


def test_an_unreachable_explicit_url_is_an_error() -> None:
    """Asking for a named database and not getting it is a failure, not a quiet pass."""

    with pytest.raises(psycopg.OperationalError):
        connect(TargetDatabase(UNREACHABLE_URL, explicit=True))


def test_the_fallback_url_names_the_port_compose_publishes() -> None:
    """Drift between the two would make every Postgres test skip, silently.

    Nothing else notices: CI sets the variable explicitly, so it stays green
    while every local run quietly stops exercising the schema. The suite would
    still report success, having tested none of it.
    """

    published = _PUBLISHED_PORT.findall(COMPOSE_FILE.read_text(encoding="utf-8"))

    assert len(published) == 1, f"expected one published port in compose.yaml, got {published}"
    assert conninfo_to_dict(LOCAL_TEST_DATABASE_URL)["port"] == published[0]


def test_an_unreachable_default_skips_and_names_the_fix() -> None:
    with pytest.raises(pytest.skip.Exception) as excinfo:
        connect(TargetDatabase(UNREACHABLE_URL, explicit=False))

    assert "docker compose up -d db" in str(excinfo.value)
