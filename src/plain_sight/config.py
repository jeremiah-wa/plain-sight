"""Runtime configuration, resolved from the environment.

The one place the live extractor's model id and the Postgres URL are read, so the
``Extractor`` boundary and the database stay config-driven. Tests never touch
this: they inject a stub extractor and either an in-memory repository or the
ephemeral local Postgres, which they resolve themselves (``tests/local_postgres.py``,
defaulting to the ``compose.yaml`` container rather than to anything set here).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Default extraction model. The live multimodal call lives only behind the
#: ``Extractor`` seam; this id is what :class:`~plain_sight.extraction.ClaudeExtractor`
#: passes to the Anthropic SDK. Overridable via ``PLAIN_SIGHT_MODEL_ID``.
DEFAULT_MODEL_ID = "claude-opus-4-8"

#: Where immutable source PDFs are written (content-addressed). Overridable via
#: ``PLAIN_SIGHT_DATA_DIR``.
DEFAULT_DATA_DIR = "data/documents"


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for one process."""

    database_url: str | None
    model_id: str
    data_dir: Path


def get_settings() -> Settings:
    """Read :class:`Settings` from the environment."""

    return Settings(
        database_url=os.environ.get("PLAIN_SIGHT_DATABASE_URL"),
        model_id=os.environ.get("PLAIN_SIGHT_MODEL_ID", DEFAULT_MODEL_ID),
        data_dir=Path(os.environ.get("PLAIN_SIGHT_DATA_DIR", DEFAULT_DATA_DIR)),
    )
