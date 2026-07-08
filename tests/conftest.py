"""Shared test helpers: deterministic ids and the checked-in scan fixture."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import UUID

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


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
