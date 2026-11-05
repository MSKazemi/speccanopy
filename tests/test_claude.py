"""Mocked Claude Messages API tests; no paid API calls or expert validation."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from speccanopy.ai import AIProposalError, AI_RESPONSE_SCHEMA, INSTRUCTIONS
from speccanopy.claude import (
    CLAUDE_API_ENDPOINT, CLAUDE_API_VERSION, ClaudeMessagesClient,
)
from speccanopy.cli import main


VALID = {
    "expand": False,
    "reason": "The component boundary is sufficient for a draft; review still needed",
    "children": [],
    "open_questions": ["Confirm failure semantics with the application owner"],
}


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.body).encode("utf-8")


def message(result=None, **overrides):
    body = {
        "id": "msg_mock123",
        "type": "message",
        "role": "assistant",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": json.dumps(VALID if result is None else result)}],
    }
    body.update(overrides)
    return body


def test_claude_request_uses_fixed_endpoint_json_schema_and_secret_header(monkeypatch):
    import speccanopy.claude as claude

    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["headers"] = dict(req.header_items())
        seen["payload"] = json.loads(req.data)
        seen["timeout"] = timeout
        return FakeResponse(message())

    monkeypatch.setattr(claude, "urlopen", fake_urlopen)
    client = ClaudeMessagesClient(
        "claude-test-model", api_key="secret-value", workspace_id="wrkspc-test",
        timeout_seconds=15, max_output_tokens=500,
    )
    out = client.complete("system", "This is a requirements brief")
    assert out.response == VALID
    assert out.response_id == "msg_mock123"
    assert seen["url"] == CLAUDE_API_ENDPOINT
    assert seen["method"] == "POST"
    headers = {key.casefold(): val for key, val in seen["headers"].items()}
    assert headers["x-api-key"] == "secret-value"
    assert headers["anthropic-version"] == CLAUDE_API_VERSION
    assert headers["anthropic-workspace-id"] == "wrkspc-test"
    assert seen["payload"] == {
        "model": "claude-test-model",
        "max_tokens": 500,
        "system": INSTRUCTIONS,
        "messages": [{"role": "user", "content": "This is a requirements brief"}],
        "output_config": {
            "format": {"type": "json_schema", "schema": AI_RESPONSE_SCHEMA},
        },
    }
    assert "secret-value" not in json.dumps(seen["payload"])
    assert seen["timeout"] == 15


@pytest.mark.parametrize("field,value", [
    ("type", "error"),
    ("role", "user"),
    ("stop_reason", "max_tokens"),
    ("stop_reason", "refusal"),
    ("stop_reason", "tool_use"),
    ("content", []),
    ("content", [{"type": "text", "text": "{}"}, {"type": "text", "text": "{}"}]),
    ("content", [{"type": "tool_use", "name": "fake", "input": VALID}]),
    ("content", [{"type": "text", "text": "NOT JSON"}]),
    ("content", [{"type": "text", "text": "[]"}]),
])
def test_incomplete_non_schema_and_refused_outputs_are_rejected(monkeypatch, field, value):
    import speccanopy.claude as claude

    monkeypatch.setattr(claude, "urlopen", lambda *args, **kw: FakeResponse(message(**{field: value})))
    with pytest.raises(AIProposalError):
        ClaudeMessagesClient("model", api_key="test-key").complete("system", "prompt")


def test_http_errors_hide_provider_reply_and_secret(monkeypatch):
    import speccanopy.claude as claude

    def fail(req, timeout):
        raise HTTPError(req.full_url, 401, "sensitive provider details", {}, None)

    monkeypatch.setattr(claude, "urlopen", fail)
    with pytest.raises(AIProposalError) as info:
        ClaudeMessagesClient("model", api_key="secret").complete("system", "prompt")
    assert "HTTP 401" in str(info.value)
    assert "sensitive" not in str(info.value)
    assert "secret" not in str(info.value)


def test_network_errors_hide_environment_details(monkeypatch):
    import speccanopy.claude as claude

    def fail(req, timeout):
        raise URLError("token=private-detail")

    monkeypatch.setattr(claude, "urlopen", fail)
    with pytest.raises(AIProposalError) as info:
        ClaudeMessagesClient("model", api_key="secret").complete("system", "prompt")
    assert "private-detail" not in str(info.value)


def test_environment_auth_validation_and_workspace(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AIProposalError, match="ANTHROPIC_API_KEY"):
        ClaudeMessagesClient("model")
    with pytest.raises(ValueError, match="model"):
        ClaudeMessagesClient(" ", api_key="secret")
    with pytest.raises(ValueError, match="timeout"):
        ClaudeMessagesClient("model", api_key="secret", timeout_seconds=0)
    with pytest.raises(ValueError, match="max_output_tokens"):
        ClaudeMessagesClient("model", api_key="secret", max_output_tokens=1)
    with pytest.raises(ValueError, match="ANTHROPIC_WORKSPACE_ID"):
        ClaudeMessagesClient("model", api_key="secret", workspace_id="hello\ninjection")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert ClaudeMessagesClient("model").provider == "anthropic-messages"


def test_oversized_payload_rejected(monkeypatch):
    import speccanopy.claude as claude

    class Huge:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit): return b"x" * limit

    monkeypatch.setattr(claude, "urlopen", lambda *a, **kw: Huge())
    with pytest.raises(AIProposalError, match="maximum size"):
        ClaudeMessagesClient("model", api_key="secret").complete("system", "prompt")


def test_cli_claude_backend_fails_closed_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    source = "examples/cli-utility.json"
    assert main(["propose-ai", source, "--backend", "claude",
                 "--model", "any-model", "--output", str(tmp_path)]) == 1


def test_cli_claude_backend_mocked_end_to_end(tmp_path, monkeypatch):
    import speccanopy.claude as claude
    from speccanopy.ai import ScriptedProposalClient
    from speccanopy.models import SystemBrief
    from pathlib import Path

    base = Path(__file__).resolve().parents[1] / "examples"
    responses = json.loads((base / "ai-scripted-cli.json").read_text())
    # In this mock the provider returns one response per requested parent.
    calls = {"n": 0}
    def fake_urlopen(req, timeout):
        prompt = json.loads(req.data)["messages"][0]["content"]
        calls["n"] += 1
        # AIComponentProposer prompt identifies the parent ID via its JSON payload.
        # Parent order is tested elsewhere; this verifies Claude can feed the full pipeline.
        parent = json.loads(prompt)["parent"]["id"]
        return FakeResponse(message(responses[parent]))
    monkeypatch.setattr(claude, "urlopen", fake_urlopen)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-real")
    code = main(["propose-ai", str(base / "cli-utility.json"), "--backend", "claude",
                 "--model", "mock-claude", "--output", str(tmp_path / "ai")])
    assert code == 0
    from speccanopy.ai import AIProposalBundle
    bundle = AIProposalBundle.model_validate_json((tmp_path / "ai" / "ai-proposals.json").read_text())
    assert bundle.provider == "anthropic-messages"
    assert bundle.status == "pending_human_review"
    assert bundle.component_count == 4
    assert bundle.model_calls == 4
    assert all(e.response_sha256 for e in bundle.events)
