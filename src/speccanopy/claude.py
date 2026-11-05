"""Claude Messages API provider for schema-constrained architecture proposals.

This module supplies *unverified proposals*, never human/expert attestations.
No Anthropic credential is stored in the returned architecture or audit trace.
"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai import AIProposalError, AI_RESPONSE_SCHEMA, INSTRUCTIONS, ModelCompletion

CLAUDE_API_ENDPOINT = "https://api.anthropic.com/v1/messages"
CLAUDE_API_VERSION = "2026-10-21"
_MAX_RESPONSE_BYTES = 2_000_000


class ClaudeMessagesClient:
    """Provider-neutral proposal client backed by Anthropic's Messages API.

    Uses output_config.format (schema-constrained JSON), not a text-only
    "please return JSON" prompt. All candidate components still pass through
    Speccanopy's independent Pydantic and requirements-integrity validators.
    """

    provider = "anthropic-messages"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        workspace_id: str | None = None,
        timeout_seconds: int = 45,
        max_output_tokens: int = 2200,
    ) -> None:
        self.model = model.strip()
        if not self.model or any(c in self.model for c in "\r\n"):
            raise ValueError("A valid Claude model identifier is required")
        self._key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._key or any(c in self._key for c in "\r\n"):
            raise AIProposalError("Set ANTHROPIC_API_KEY to use the live Claude Messages API")
        self._workspace_id = (
            workspace_id if workspace_id is not None
            else os.environ.get("ANTHROPIC_WORKSPACE_ID", "")
        ).strip()
        if any(c in self._workspace_id for c in "\r\n"):
            raise ValueError("Invalid ANTHROPIC_WORKSPACE_ID")
        if not 1 <= timeout_seconds <= 180:
            raise ValueError("timeout_seconds must be 1..180")
        if not 128 <= max_output_tokens <= 32000:
            raise ValueError("max_output_tokens must be 128..32000")
        self._timeout = timeout_seconds
        self._token_limit = max_output_tokens

    def complete(self, parent_id: str, prompt: str) -> ModelCompletion:
        payload = {
            "model": self.model,
            "max_tokens": self._token_limit,
            "system": INSTRUCTIONS,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {
                "format": {"type": "json_schema", "schema": AI_RESPONSE_SCHEMA}
            },
        }
        headers = {
            "x-api-key": self._key,
            "anthropic-version": CLAUDE_API_VERSION,
            "content-type": "application/json",
        }
        if self._workspace_id:
            headers["anthropic-workspace-id"] = self._workspace_id
        request = Request(
            CLAUDE_API_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise AIProposalError(
                f"Claude Messages API request failed (HTTP {exc.code}); response details withheld"
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise AIProposalError(
                f"Claude Messages API request failed ({type(exc).__name__}); details withheld"
            ) from None
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise AIProposalError("Claude Messages API response exceeded maximum size")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise AIProposalError("Claude Messages API returned malformed JSON") from None
        if not isinstance(body, dict):
            raise AIProposalError("Claude Messages API returned a non-object payload")
        if body.get("type") != "message" or body.get("role") != "assistant":
            raise AIProposalError("Claude Messages API returned an unexpected message type")
        if body.get("stop_reason") != "end_turn":
            raise AIProposalError("Claude output is incomplete, refused, or requested another action")
        blocks = body.get("content")
        if not isinstance(blocks, list) or len(blocks) != 1:
            raise AIProposalError("Expected exactly one schema-constrained Claude text block")
        block = blocks[0]
        if not isinstance(block, dict) or block.get("type") != "text":
            raise AIProposalError("Claude response did not contain one JSON text block")
        try:
            data = json.loads(block.get("text", ""))
        except (TypeError, ValueError):
            raise AIProposalError("Claude output was not a JSON document") from None
        if not isinstance(data, dict):
            raise AIProposalError("Claude output must be a JSON object")
        # The AIComponentProposer validates data against AIChildrenResponse,
        # requirement scope, duplicate IDs, node budgets and stop conditions.
        response_id = body.get("id")
        return ModelCompletion(
            response=data,
            response_id=response_id if isinstance(response_id, str) else None,
        )
