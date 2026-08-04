"""The operator verification UI: a local, server-rendered FastAPI + HTMX app.

This is the trust factory. It shows an operator one pending claim at a time with
the source-scan crop beside the extracted fields, and lets them confirm the claim
as-is or correct a field and confirm. Confirming writes a ``verified`` event;
correcting appends a superseding event carrying who/why/when, so the machine's
original candidate is retained in the log (see docs/ARCHITECTURE.md).

The app is a thin shell over the read/write seam beneath it
(:func:`plain_sight.service.confirm` / :func:`~plain_sight.service.correct` and the
:class:`~plain_sight.db.repository.Repository`); that seam is where behaviour is
tested, not UI snapshots. It is operator-only and meant to run locally against the
system-of-record Postgres; there is no public-facing surface.
"""

from __future__ import annotations

from plain_sight.web.app import SessionFactory, create_app

__all__ = ["SessionFactory", "create_app"]
