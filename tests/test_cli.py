"""The crude operator CLI wires ingest → confirm → show together.

Exercises the actual click commands, with the Postgres session and live
extractor swapped for an in-memory repository and a stub at the module seams.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from click.testing import CliRunner

from plain_sight import cli as cli_module
from plain_sight.config import Settings
from plain_sight.db import InMemoryRepository, Repository
from plain_sight.domain import CandidateDeclaration, ExtractionResult, InterestCategory
from plain_sight.extraction import StubExtractor

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def wired_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> InMemoryRepository:
    repo = InMemoryRepository()

    @contextmanager
    def fake_session(settings: Settings) -> Iterator[Repository]:
        yield repo

    result = ExtractionResult(
        method="stub-extractor",
        candidates=[
            CandidateDeclaration(
                category=InterestCategory.SHAREHOLDING,
                counterparty_raw="BHP Group Ltd",
                page=1,
                confidence=0.9,
            )
        ],
    )
    monkeypatch.setattr(cli_module, "open_session", fake_session)
    monkeypatch.setattr(cli_module, "build_extractor", lambda settings: StubExtractor(result))
    monkeypatch.setenv("PLAIN_SIGHT_DATA_DIR", str(tmp_path / "documents"))
    return repo


def test_cli_ingest_confirm_show(
    wired_cli: InMemoryRepository, tmp_path: Path, sample_pdf_bytes: bytes
) -> None:
    pdf = tmp_path / "register.pdf"
    pdf.write_bytes(sample_pdf_bytes)
    runner = CliRunner()

    ingest = runner.invoke(cli_module.cli, ["ingest", "--member", "Jane Member", "--pdf", str(pdf)])
    assert ingest.exit_code == 0, ingest.output
    assert "(pending)" in ingest.output
    event_id = _UUID_RE.search(ingest.output).group(0)  # type: ignore[union-attr]

    # Before confirming, the show output has no verified interests.
    show_before = runner.invoke(cli_module.cli, ["show", "--member", "Jane Member"])
    assert "no verified declared interests" in show_before.output
    assert "BHP" not in show_before.output

    confirm = runner.invoke(cli_module.cli, ["confirm", event_id, "--by", "operator"])
    assert confirm.exit_code == 0, confirm.output
    assert "Verified" in confirm.output

    show_after = runner.invoke(cli_module.cli, ["show", "--member", "Jane Member"])
    assert 'as declared: "BHP Group Ltd"' in show_after.output
    assert "verified by operator" in show_after.output


def test_cli_publish_writes_verified_only_html(
    wired_cli: InMemoryRepository, tmp_path: Path, sample_pdf_bytes: bytes
) -> None:
    pdf = tmp_path / "register.pdf"
    pdf.write_bytes(sample_pdf_bytes)
    runner = CliRunner()

    ingest = runner.invoke(
        cli_module.cli,
        ["ingest", "--member", "Jane Member", "--pdf", str(pdf), "--url", "https://x.test/r.pdf"],
    )
    event_id = _UUID_RE.search(ingest.output).group(0)  # type: ignore[union-attr]
    runner.invoke(cli_module.cli, ["confirm", event_id, "--by", "operator"])

    out = tmp_path / "site"
    result = runner.invoke(
        cli_module.cli, ["publish", "--member", "Jane Member", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output

    written = (out / "jane-member.html").read_text()
    assert 'as declared: "BHP Group Ltd"' in written
    assert "mirrors the official record" in written


def test_cli_confirm_unknown_id_errors(wired_cli: InMemoryRepository) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["confirm", "00000000-0000-0000-0000-0000000000ff", "--by", "operator"],
    )
    assert result.exit_code != 0
    assert "No pending claim" in result.output
