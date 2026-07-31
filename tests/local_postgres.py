"""Where the destructive Postgres fixture is allowed to point.

``postgres_conn`` drops and re-migrates every table around each test, so the
only databases it may reach are ones whose whole purpose is to be thrown away:
a loopback host, and a name ending in ``_test``. Anything else is refused,
loudly, with no override. See ``compose.yaml`` for the container this defaults
to, and ``docs/decisions/0002-local-ephemeral-postgres-for-tests.md`` for why
the escape hatch does not exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

#: Set this to point the Postgres tests somewhere other than the local container.
TEST_DATABASE_URL_VAR = "PLAIN_SIGHT_TEST_DATABASE_URL"

#: The ``db`` service in ``compose.yaml``. Used when the variable above is unset.
#: Literal 127.0.0.1 rather than "localhost", which resolves to ::1 as well and
#: costs a second connect timeout when the container is not up.
LOCAL_TEST_DATABASE_URL = "postgresql://plain_sight:plain_sight@127.0.0.1:55432/plain_sight_test"

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_DISPOSABLE_SUFFIX = "_test"

# Only loopback is reachable at all, so anything slower than this is a container
# that is not up. 2 is libpq's effective floor: it clamps smaller values.
_CONNECT_TIMEOUT_SECONDS = 2


class UnsafeTestDatabaseError(RuntimeError):
    """The configured database is not one the destructive fixture may drop."""


class TargetDatabase(NamedTuple):
    """A vetted test database, and whether the operator named it themselves."""

    url: str
    explicit: bool


def resolve_test_database(environ: Mapping[str, str]) -> TargetDatabase:
    """Vet the configured test database, falling back to the local container.

    Raises :class:`UnsafeTestDatabaseError` for anything that is not both loopback
    and disposable. Unset (or empty) is not a skip: it means the container.
    """

    # A refused URL usually carries a password. Keep the frames holding it out of
    # pytest's traceback, which prints locals; the message names host and database.
    __tracebackhide__ = True

    configured = environ.get(TEST_DATABASE_URL_VAR) or ""
    url = configured or LOCAL_TEST_DATABASE_URL
    _refuse_unless_disposable(url)
    return TargetDatabase(url, explicit=bool(configured))


def connect(database: TargetDatabase) -> psycopg.Connection[Any]:
    """Open a connection, distinguishing "yours is down" from "mine is not up".

    An explicitly configured database that cannot be reached is an error: the
    operator asked for it. The implicit local default is a skip, because not
    every run has the container up.
    """

    try:
        return psycopg.connect(database.url, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    except psycopg.OperationalError as exc:
        if database.explicit:
            raise
        pytest.skip(
            f"No local test Postgres at {LOCAL_TEST_DATABASE_URL} "
            f"({' '.join(str(exc).split())}); start it with `docker compose up -d db`"
        )


def _refuse_unless_disposable(url: str) -> None:
    __tracebackhide__ = True

    try:
        parts = conninfo_to_dict(url)
    except psycopg.Error as exc:
        raise UnsafeTestDatabaseError(
            f"{TEST_DATABASE_URL_VAR} is not a connection string psycopg can parse, "
            "so the destructive Postgres fixture cannot tell what it points at."
        ) from exc

    # Both keys, because libpq connects to `hostaddr` when it is present and uses
    # `host` only for authentication: a loopback-looking `host` proves nothing.
    # Fail closed: absent, comma-separated, or unrecognised means refused.
    addresses = [str(parts[key]).lower() for key in ("host", "hostaddr") if parts.get(key)]
    dbname = str(parts.get("dbname") or "")
    on_loopback = bool(addresses) and all(address in _LOOPBACK_HOSTS for address in addresses)
    if on_loopback and dbname.endswith(_DISPOSABLE_SUFFIX):
        return

    raise UnsafeTestDatabaseError(
        f"Refusing to run the destructive Postgres fixture against host "
        f"{' / '.join(addresses) or '(none)'!r}, database {dbname or '(none)'!r}. "
        f"It drops and re-migrates "
        f"every table, so it runs only against a loopback host "
        f"({', '.join(sorted(_LOOPBACK_HOSTS))}) with a database named *{_DISPOSABLE_SUFFIX}. "
        f"There is no override: unset {TEST_DATABASE_URL_VAR} to use the local container "
        f"({LOCAL_TEST_DATABASE_URL}), started with `docker compose up -d db`."
    )
