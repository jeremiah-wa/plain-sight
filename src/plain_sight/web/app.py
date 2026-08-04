"""The FastAPI application: routes over the verification seam, rendered with Jinja2.

The app owns no business logic. Every route opens a unit of work through the
injected ``session_factory`` (one atomic transaction per request, exactly like the
CLI's ``open_session``), reads or writes through the :class:`Repository`, and
delegates confirm/correct to :mod:`plain_sight.service`. Collaborators are injected
so the whole HTTP surface can be driven against an in-memory repository in tests,
without Postgres, a document store, or a real clock.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from plain_sight import service
from plain_sight.db.repository import Repository
from plain_sight.domain import (
    ClaimCorrection,
    Counterparty,
    DeclarationEvent,
    InterestCategory,
    SourceDocument,
    VerificationStatus,
)

#: Opens one unit of work: a context manager yielding a repository whose writes are
#: committed when the block exits cleanly. In production this wraps a psycopg
#: transaction; in tests it yields a shared in-memory repository.
SessionFactory = Callable[[], AbstractContextManager[Repository]]

#: Reads the immutable bytes of a stored scan, so the operator sees the exact
#: source a claim was extracted from.
DocumentReader = Callable[[SourceDocument], bytes]

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _read_from_disk(document: SourceDocument) -> bytes:
    return Path(document.storage_path).read_bytes()


def _parse_date(raw: str | None) -> date | None:
    raw = (raw or "").strip()
    return date.fromisoformat(raw) if raw else None


def _optional_text(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    return raw or None


def create_app(
    *,
    session_factory: SessionFactory,
    read_document: DocumentReader = _read_from_disk,
    operator: str = "operator",
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    """Build the verification UI over the given seam.

    ``operator`` is the identity stamped as ``verified_by`` on every confirm and
    correct: this is a local, single-operator tool, so the person running it is who
    settled the claim. ``clock`` supplies ``verified_at`` and is injectable so tests
    assert an exact timestamp.
    """

    app = FastAPI(title="Plain Sight verification")
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    def _load_claim(
        repo: Repository, event_id: UUID
    ) -> tuple[DeclarationEvent, Counterparty, SourceDocument] | None:
        event = repo.get_declaration_event(event_id)
        if event is None:
            return None
        counterparty = repo.get_counterparty(event.counterparty_id)
        document = repo.get_source_document(event.provenance.document_id)
        if counterparty is None or document is None:
            return None
        return event, counterparty, document

    def _after_write(request: Request, member_name: str, message: str) -> Response:
        """Return an HTMX result fragment, or fall back to a plain redirect."""

        if request.headers.get("HX-Request"):
            return templates.TemplateResponse(
                request,
                "partials/result.html",
                {"message": message, "member_name": member_name},
            )
        return RedirectResponse(url=f"/members/{member_name}", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Response:
        return templates.TemplateResponse(request, "index.html", {})

    @app.get("/members/{member_name}", response_class=HTMLResponse)
    def queue(request: Request, member_name: str) -> Response:
        with session_factory() as repo:
            person = repo.get_person_by_canonical_name(member_name)
            claims = repo.pending_claims_for_member(person.id) if person is not None else []
        return templates.TemplateResponse(
            request,
            "queue.html",
            {"member_name": member_name, "claims": claims, "known": person is not None},
        )

    @app.get("/members/{member_name}/claims/{event_id}", response_class=HTMLResponse)
    def claim_detail(request: Request, member_name: str, event_id: UUID) -> Response:
        with session_factory() as repo:
            loaded = _load_claim(repo, event_id)
        if loaded is None:
            return templates.TemplateResponse(
                request, "not_found.html", {"member_name": member_name}, status_code=404
            )
        event, counterparty, document = loaded
        return templates.TemplateResponse(
            request,
            "claim.html",
            {
                "member_name": member_name,
                "event": event,
                "counterparty": counterparty,
                "document": document,
                "categories": list(InterestCategory),
                "is_pending": event.verification_status is VerificationStatus.PENDING,
                "scan_url": f"/documents/{document.id}#page={event.provenance.page}",
            },
        )

    @app.post("/members/{member_name}/claims/{event_id}/confirm")
    def confirm(request: Request, member_name: str, event_id: UUID) -> Response:
        with session_factory() as repo:
            settled = service.confirm(
                repo=repo,
                event_id=event_id,
                verified_by=operator,
                verified_at=clock(),
            )
        message = (
            f"Confirmed as declared, verified by {operator}."
            if settled
            else "This claim was already settled; nothing was written."
        )
        return _after_write(request, member_name, message)

    @app.post("/members/{member_name}/claims/{event_id}/correct")
    def correct(
        request: Request,
        member_name: str,
        event_id: UUID,
        category: str = Form(...),
        counterparty_raw: str = Form(...),
        reason: str = Form(...),
        description: str | None = Form(None),
        valid_from: str | None = Form(None),
        valid_to: str | None = Form(None),
    ) -> Response:
        correction = ClaimCorrection(
            category=InterestCategory(category),
            counterparty_raw=counterparty_raw.strip(),
            description=_optional_text(description),
            valid_from=_parse_date(valid_from),
            valid_to=_parse_date(valid_to),
        )
        with session_factory() as repo:
            successor = service.correct(
                repo=repo,
                event_id=event_id,
                correction=correction,
                corrected_by=operator,
                corrected_at=clock(),
                reason=reason.strip(),
            )
        message = (
            f"Corrected and verified by {operator}; the original candidate is retained."
            if successor is not None
            else "This claim was already settled; nothing was written."
        )
        return _after_write(request, member_name, message)

    @app.get("/documents/{document_id}")
    def document_scan(document_id: UUID) -> Response:
        with session_factory() as repo:
            document = repo.get_source_document(document_id)
        if document is None:
            return Response(status_code=404)
        return Response(
            content=read_document(document),
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )

    return app
