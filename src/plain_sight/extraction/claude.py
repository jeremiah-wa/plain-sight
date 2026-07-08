"""The live multimodal extractor: Claude Opus over the scanned register page.

This is the only code that calls the Anthropic SDK, and it is never imported by
the test suite (the ``Extractor`` seam is mocked). It is behind the ``llm`` extra.
Extraction is forced through a tool schema (structured output, no free-text
parsing); the model returns the page it read each claim from and its own
confidence, and is instructed never to fabricate bounding boxes.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

from plain_sight.domain import (
    CandidateDeclaration,
    ExtractionResult,
    InterestCategory,
    SourceDocument,
)

if TYPE_CHECKING:
    from anthropic import Anthropic

_TOOL_NAME = "record_declarations"

_INSTRUCTION = (
    "This is a scanned page from an Australian federal parliamentarian's register "
    "of interests, often handwritten. Transcribe every declared interest on the "
    "page faithfully, exactly as written. Do not infer, resolve, or correct the "
    "named companies/trusts/assets. For each interest call the record_declarations "
    "tool with: the interest category; the counterparty string exactly as it "
    "appears; an optional short description; effective dates if legibly present "
    "(ISO-8601); the 1-indexed page you read it from; and your confidence (0-1). "
    "Omit any field you cannot read. Never guess."
)


def _tool_schema() -> dict[str, Any]:
    return {
        "name": _TOOL_NAME,
        "description": "Record the declared interests transcribed from the page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "declarations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": [c.value for c in InterestCategory],
                            },
                            "counterparty_raw": {"type": "string"},
                            "description": {"type": "string"},
                            "valid_from": {"type": "string", "format": "date"},
                            "valid_to": {"type": "string", "format": "date"},
                            "page": {"type": "integer", "minimum": 1},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["category", "counterparty_raw", "page", "confidence"],
                    },
                }
            },
            "required": ["declarations"],
        },
    }


class ClaudeExtractor:
    """Extracts candidate declarations from a source PDF with Claude Opus."""

    def __init__(
        self,
        model_id: str,
        *,
        client: Anthropic | None = None,
        max_tokens: int = 8000,
    ) -> None:
        if client is None:
            from anthropic import Anthropic

            client = Anthropic()
        self._model_id = model_id
        self._client = client
        self._max_tokens = max_tokens

    def extract(self, document: SourceDocument, content: bytes) -> ExtractionResult:
        pdf_b64 = base64.standard_b64encode(content).decode("ascii")
        message = self._client.messages.create(
            model=self._model_id,
            max_tokens=self._max_tokens,
            tools=[_tool_schema()],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {"type": "text", "text": _INSTRUCTION},
                    ],
                }
            ],
        )

        raw = self._tool_input(message)
        candidates = [
            CandidateDeclaration.model_validate(item) for item in raw.get("declarations", [])
        ]
        return ExtractionResult(method=self._model_id, candidates=candidates)

    @staticmethod
    def _tool_input(message: Any) -> dict[str, Any]:
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _TOOL_NAME:
                return dict(block.input)
        raise ValueError("Claude did not return a record_declarations tool call")
