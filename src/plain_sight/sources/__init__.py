"""Source ingestion: fetch and immutably store the official register PDFs.

v1 builds only the ``AU:federal`` adapter. The skeleton stores whatever bytes the
operator supplies (standing in for the download) and anchors provenance to them.
"""

from __future__ import annotations

from plain_sight.sources.store import DocumentStore

__all__ = ["DocumentStore"]
