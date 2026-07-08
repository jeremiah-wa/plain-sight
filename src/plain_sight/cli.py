"""The crude operator CLI: migrate, ingest, confirm, show.

This stands in for the real verification UI (which comes in a later slice): the
whole point of the walking skeleton is to connect download → store → extract →
confirm → display before any UI investment. ``open_session`` and
``build_extractor`` are module-level seams so the flow can be driven in tests
against an in-memory repository and a stub extractor.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import click
import psycopg

from plain_sight import service
from plain_sight.config import Settings, get_settings
from plain_sight.db import PostgresRepository, Repository, apply_migrations
from plain_sight.extraction import Extractor
from plain_sight.sources import DocumentStore


def _require_database_url(settings: Settings) -> str:
    if not settings.database_url:
        raise click.ClickException("Set PLAIN_SIGHT_DATABASE_URL to a reachable Postgres instance.")
    return settings.database_url


@contextlib.contextmanager
def open_session(settings: Settings) -> Iterator[Repository]:
    """Yield a repository inside a single atomic transaction."""

    conn = psycopg.connect(_require_database_url(settings))
    try:
        with conn:
            yield PostgresRepository(conn)
    finally:
        conn.close()


def build_extractor(settings: Settings) -> Extractor:
    """Construct the live Claude extractor (requires the ``llm`` extra)."""

    from plain_sight.extraction import ClaudeExtractor

    return ClaudeExtractor(settings.model_id)


@click.group()
def cli() -> None:
    """Plain Sight walking-skeleton operator CLI."""


@cli.command()
def migrate() -> None:
    """Apply the hand-authored SQL migrations."""

    settings = get_settings()
    conn = psycopg.connect(_require_database_url(settings))
    try:
        applied = apply_migrations(conn)
    finally:
        conn.close()
    click.echo("Applied: " + ", ".join(applied) if applied else "No migrations to apply.")


@cli.command()
@click.option("--member", required=True, help="Canonical member name.")
@click.option(
    "--pdf",
    "pdf_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="The member's register PDF (downloaded).",
)
@click.option("--url", "source_url", default=None, help="Source URL, recorded as provenance.")
def ingest(member: str, pdf_path: Path, source_url: str | None) -> None:
    """Store a member's PDF, extract it, and record pending claims."""

    settings = get_settings()
    store = DocumentStore(settings.data_dir)
    extractor = build_extractor(settings)
    pdf_bytes = pdf_path.read_bytes()

    with open_session(settings) as repo:
        events = service.ingest(
            repo=repo,
            store=store,
            extractor=extractor,
            member_name=member,
            pdf_bytes=pdf_bytes,
            now=datetime.now(UTC),
            source_url=source_url,
        )

    if not events:
        click.echo("No candidate declarations extracted.")
        return
    click.echo(f"Ingested {len(events)} pending claim(s) for {member}:")
    for event in events:
        click.echo(f"  {event.id}  [{event.category.value}]  (pending)")


@cli.command()
@click.argument("event_id", type=click.UUID)
@click.option("--by", "verified_by", required=True, help="Who confirmed the claim.")
def confirm(event_id: UUID, verified_by: str) -> None:
    """Confirm a pending claim, transitioning it to verified."""

    settings = get_settings()
    with open_session(settings) as repo:
        verified = service.confirm(
            repo=repo,
            event_id=event_id,
            verified_by=verified_by,
            verified_at=datetime.now(UTC),
        )
    if not verified:
        raise click.ClickException(f"No pending claim with id {event_id}.")
    click.echo(f"Verified {event_id}.")


@cli.command()
@click.option("--member", required=True, help="Canonical member name.")
def show(member: str) -> None:
    """Display a member's verified declared interests as plain text."""

    settings = get_settings()
    with open_session(settings) as repo:
        click.echo(service.render_member_interests(repo=repo, member_name=member))
