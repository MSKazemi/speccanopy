"""AI proposal contracts: fail-closed JSON, provenance, budgets and human approval."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.ai import (
    AIChildrenResponse, AIComponentProposer, AIProposalBundle, AIProposalError,
    OpenAIResponsesClient, ScriptedProposalClient, approve_proposal_bundle,
    brief_digest, draft_architecture,
)
from speccanopy.ai_exporters import export_ai_draft, export_approved
from speccanopy.cli import main
from speccanopy.fixtures import FixtureDesign
from speccanopy.models import ArchitectureSpec, SystemBrief

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def example():
    brief = SystemBrief.model_validate_json((EXAMPLES / "cli-utility.json").read_text())
    responses = json.loads((EXAMPLES / "ai-scripted-cli.json").read_text())
    return brief, responses


def draft(brief=None, responses=None, *, max_model_calls=10):
    b, r = example()
    return draft_architecture(brief or b, ScriptedProposalClient(responses or r), max_model_calls=max_model_calls)


def test_structured_responses_and_extra_fields_rejected():
    _, responses = example()
    AIChildrenResponse.model_validate(responses["system"])
    unsafe = dict(responses["system"])
    unsafe["validation_evidence"] = "AI says verified"
    with pytest.raises(ValidationError):
        AIChildrenResponse.model_validate(unsafe)
    invalid = dict(responses["system"])
    invalid["expand"] = False
    with pytest.raises(ValidationError, match="expand must be true"):
        AIChildrenResponse.model_validate(invalid)


def test_scripted_ai_creates_pending_bundle_with_provenance_and_unverified_status():
    result, bundle = draft()
    assert len(result.architecture.components) == 4
    assert result.stats()["max_depth"] == 1
    assert result.architecture.status == "incomplete_requires_review"
    assert bundle.status == "pending_human_review"
    assert bundle.provider == "scripted"
    assert bundle.model_calls == 4
    assert bundle.coverage.uncovered == sorted(bundle.brief.mandatory_requirement_ids())
    assert all(not c.validation_evidence for c in result.architecture.components)
    assert all(c.status == "requires_review" for c in result.architecture.components)
    assert len(bundle.events) == 4
    assert len({event.prompt_sha256 for event in bundle.events}) == 4
    assert all(event.response_sha256 for event in bundle.events)
    assert any("atomically" in q for q in bundle.open_questions)
    assert set(bundle.fixture.proposals_by_parent) == {"system"}
    AIProposalBundle.model_validate_json(bundle.model_dump_json())


def test_roundtrip_export_and_approved_fixture_stays_review_only(tmp_path):
    result, bundle = draft()
    files = export_ai_draft(result, bundle, tmp_path / "ai")
    assert len(files) == 9
    assert "pending human review" in (files["proposal-review.md"]).read_text()
    assert json.loads(files["generation-trace.json"].read_text())["generator"] == "ai-assisted-draft"
    loaded = AIProposalBundle.model_validate_json(files["ai-proposals.json"].read_text())
    with pytest.raises(AIProposalError, match="acknowledge-review"):
        approve_proposal_bundle(loaded, reviewer="human", acknowledge_review=False)
    fixture, receipt = approve_proposal_bundle(loaded, reviewer="architect-1", acknowledge_review=True)
    assert receipt.reviewer == "architect-1"
    assert receipt.status == "approved_for_further_architecture_review"
    exports = export_approved(fixture, receipt, tmp_path / "approved.design.json")
    spec = FixtureDesign.model_validate_json(exports["approved_fixture"].read_text())
    assert spec.proposals_by_parent["system"][0].name == "File Reader"
    assert receipt.fixture_sha256 == bundle.fixture_sha256


def test_no_claim_of_completion_when_ai_only_and_human_approved():
    result, bundle = draft()
    fixture, _ = approve_proposal_bundle(bundle, reviewer="r", acknowledge_review=True)
    from speccanopy.decomposer import generate_architecture
    subsequent = generate_architecture(bundle.brief, fixture)
    assert subsequent.architecture.status == "incomplete_requires_review"
    assert subsequent.architecture.coverage_report().uncovered
    assert result.architecture.status == subsequent.architecture.status


def test_bundle_integrity_checks_nested_tampering():
    _, bundle = draft()
    data = bundle.model_dump(mode="json")
    data["fixture"]["proposals_by_parent"]["system"][0]["name"] = "Tampered"
    with pytest.raises(ValidationError, match="fixture hash mismatch"):
        AIProposalBundle.model_validate(data)
    data = bundle.model_dump(mode="json")
    data["brief"]["goals"][0] = "Tampered goal"
    with pytest.raises(ValidationError, match="brief hash mismatch"):
        AIProposalBundle.model_validate(data)


def test_reviewer_required():
    _, bundle = draft()
    with pytest.raises(AIProposalError, match="reviewer"):
        approve_proposal_bundle(bundle, reviewer="  ", acknowledge_review=True)


def test_model_call_budget_is_fail_closed_and_flagged():
    result, bundle = draft(max_model_calls=1)
    assert bundle.model_calls == 1
    assert bundle.warnings
    assert result.architecture.status == "incomplete_requires_review"
    assert any(f.id.startswith("AI-BUDGET") for f in result.architecture.findings)
    assert any(e.outcome == "model_budget_exhausted" for e in bundle.events)
    assert len(result.architecture.components) == 4


def test_depth_limit_records_unresolved_instead_of_ready():
    brief, responses = example()
    brief.constraints.max_depth = 1
    result, bundle = draft_architecture(brief, ScriptedProposalClient(responses))
    assert bundle.model_calls == 1
    assert bundle.warnings
    assert all(n.status != "ready" for n in result.architecture.components)
    assert any(f.id.startswith("AI-BUDGET") for f in result.architecture.findings)


def test_node_limit_does_not_silently_drop_candidates():
    brief, responses = example()
    brief.constraints.max_nodes = 1
    result, bundle = draft_architecture(brief, ScriptedProposalClient(responses))
    assert result.architecture.status == "incomplete_requires_review"
    assert bundle.component_count == 1
    assert any("Node budget" in f.description for f in result.architecture.findings)
    assert len(bundle.fixture.proposals_by_parent["system"]) == 3


@pytest.mark.parametrize("change", [
    lambda r: r["system"]["children"][0]["requirement_ids"].append("FR-NOT-REAL"),
    lambda r: r["system"]["children"][0].update({"id": "system"}),
    lambda r: r["system"]["children"][1].update({"id": "read"}),
    lambda r: r["system"]["children"][0].update({"status": "ready"}),
    lambda r: r["system"].update({"children": []}),
])
def test_invalid_model_output_never_admitted(change):
    brief, responses = example()
    change(responses)
    brief.constraints.max_refinement_rounds = 1
    with pytest.raises(AIProposalError, match="bounded repairs"):
        draft_architecture(brief, ScriptedProposalClient(responses))


def test_invalid_child_scope_cannot_reference_requirement_outside_parent():
    brief, responses = example()
    responses["read"]["expand"] = True
    responses["read"]["children"] = [{
        "id": "invalid_child", "name": "Invalid Child", "responsibility": "Wrong scope",
        "boundary": "Invalid", "requirement_ids": ["FR-003"],
        "rationale": "Not allowed", "assumptions": [], "risks": [],
    }]
    brief.constraints.max_refinement_rounds = 0
    with pytest.raises(AIProposalError, match="bounded repairs"):
        draft_architecture(brief, ScriptedProposalClient(responses))


def test_bounded_repair_can_accept_corrected_response():
    brief, responses = example()
    first = json.loads(json.dumps(responses["system"]))
    first["children"][0]["requirement_ids"] = ["NOT-A-REQUIREMENT"]
    class RepairClient(ScriptedProposalClient):
        def __init__(self):
            super().__init__(responses)
            self.count = 0
        def complete(self, parent_id, prompt):
            if parent_id == "system":
                self.count += 1
                if self.count == 1:
                    from speccanopy.ai import ModelCompletion
                    return ModelCompletion(response=first)
            return super().complete(parent_id, prompt)
    result, bundle = draft_architecture(brief, RepairClient())
    assert len(result.architecture.components) == 4
    assert bundle.model_calls == 5
    assert any(e.outcome == "invalid" for e in bundle.events)
    assert any(e.outcome == "accepted" for e in bundle.events)


def test_scripted_runs_are_reproducible_except_approval_timestamp():
    _, a = draft()
    _, b = draft()
    assert a.model_dump() == b.model_dump()


def test_cli_scripted_end_to_end(tmp_path, capsys):
    brief = EXAMPLES / "cli-utility.json"
    outputs = tmp_path / "ai"
    code = main(["propose-ai", str(brief), "--backend", "scripted",
                 "--responses", str(EXAMPLES / "ai-scripted-cli.json"), "--output", str(outputs)])
    assert code == 0
    bundle_file = outputs / "ai-proposals.json"
    assert bundle_file.exists()
    fixture_file = tmp_path / "approved.design.json"
    assert main(["approve-ai", str(bundle_file), "--reviewer", "architect",
                 "--output", str(fixture_file)]) == 1
    assert main(["approve-ai", str(bundle_file), "--reviewer", "architect",
                 "--acknowledge-review", "--output", str(fixture_file)]) == 0
    assert main(["design", str(brief), "--fixture", str(fixture_file),
                 "--output", str(tmp_path / "reviewed")]) == 0
    spec = ArchitectureSpec.model_validate_json((tmp_path / "reviewed" / "architecture.json").read_text())
    assert spec.status == "incomplete_requires_review"
    assert "Human review required" in capsys.readouterr().out
    assert main(["review", str(tmp_path / "reviewed" / "architecture.json"),
                 "--config", str(EXAMPLES / "ai-scripted-cli.review.json"),
                 "--output", str(tmp_path / "quality-review")]) == 0
    assert (tmp_path / "quality-review" / "architecture-review.md").is_file()


def test_cli_rejects_provider_misconfiguration(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    brief = str(EXAMPLES / "cli-utility.json")
    assert main(["propose-ai", brief, "--backend", "scripted", "--output", str(tmp_path)]) == 1
    assert main(["propose-ai", brief, "--backend", "openai", "--output", str(tmp_path)]) == 1
    assert main(["propose-ai", brief, "--model", "any", "--output", str(tmp_path)]) == 1
    assert main(["propose-ai", brief, "--backend", "openai", "--model", "any",
                 "--responses", str(EXAMPLES / "ai-scripted-cli.json"), "--output", str(tmp_path)]) == 1


def test_openai_request_uses_fixed_endpoint_and_strict_schema(monkeypatch):
    import speccanopy.ai as ai
    seen = {}
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            seen["limit"] = limit
            return json.dumps({"id": "resp-test", "status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps({
                    "expand": False, "reason": "Stop", "children": [], "open_questions": []})}]}]}).encode()
    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        seen["timeout"] = timeout
        seen["payload"] = json.loads(req.data)
        return FakeResponse()
    monkeypatch.setattr(ai, "urlopen", fake_urlopen)
    client = OpenAIResponsesClient("model-for-tests", api_key="super-secret")
    out = client.complete("system", "request")
    assert out.response == {"expand": False, "reason": "Stop", "children": [], "open_questions": []}
    assert out.response_id == "resp-test"
    assert seen["url"] == ai.API_ENDPOINT
    assert seen["auth"] == "Bearer super-secret"
    assert seen["payload"]["store"] is False
    assert seen["payload"]["text"]["format"]["strict"] is True
    assert seen["payload"]["text"]["format"]["schema"] == ai.AI_RESPONSE_SCHEMA
    assert seen["limit"] == 2_000_001


def test_openai_refusal_or_failed_status_is_not_silently_accepted(monkeypatch):
    import speccanopy.ai as ai
    class Response:
        def __init__(self, obj): self.obj = obj
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, n): return json.dumps(self.obj).encode()
    for payload in [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": [{"content": [{"type": "refusal", "refusal": "no"}]}]},
        {"status": "completed", "output": [{"content": [{"type": "output_text", "text": "not JSON"}]}]},
    ]:
        monkeypatch.setattr(ai, "urlopen", lambda *a, **kw: Response(payload))
        with pytest.raises(AIProposalError):
            OpenAIResponsesClient("model", api_key="secret").complete("system", "p")


def test_api_error_never_leaks_key(monkeypatch):
    from urllib.error import HTTPError
    import speccanopy.ai as ai
    def bad_request(*args, **kwargs):
        raise HTTPError("https://example.test", 401, "secret-token-in-message", None, None)
    monkeypatch.setattr(ai, "urlopen", bad_request)
    with pytest.raises(AIProposalError) as exc:
        OpenAIResponsesClient("model", api_key="my-key").complete("system", "p")
    assert "my-key" not in str(exc.value)
    assert "secret-token" not in str(exc.value)


def test_refinement_budget_zero_rejects_first_invalid_output():
    brief, responses = example()
    responses["system"]["children"][0]["id"] = "invalid space"
    brief.constraints.max_refinement_rounds = 0
    with pytest.raises(AIProposalError, match="bounded repairs"):
        draft_architecture(brief, ScriptedProposalClient(responses))


def test_partial_approval_is_not_a_completeness_claim():
    _, bundle = draft(max_model_calls=1)
    _, receipt = approve_proposal_bundle(bundle, reviewer="human", acknowledge_review=True)
    assert "further_architecture_review" in receipt.status
    assert bundle.warnings


def test_approved_fixture_cannot_be_replayed_with_changed_brief_or_fixture(tmp_path):
    brief_path = EXAMPLES / "cli-utility.json"
    _, bundle = draft()
    fixture, receipt = approve_proposal_bundle(bundle, reviewer="r", acknowledge_review=True)
    path = tmp_path / "approved.design.json"
    export_approved(fixture, receipt, path)
    manipulated_brief = json.loads(brief_path.read_text())
    manipulated_brief["goals"] = ["Completely different product goal"]
    bad_brief = tmp_path / "other.json"
    bad_brief.write_text(json.dumps(manipulated_brief))
    assert main(["design", str(bad_brief), "--fixture", str(path),
                 "--output", str(tmp_path / "out")]) == 1
    manipulated_fixture = json.loads(path.read_text())
    manipulated_fixture["proposals_by_parent"]["system"][0]["name"] = "Changed after review"
    path.write_text(json.dumps(manipulated_fixture))
    assert main(["design", str(brief_path), "--fixture", str(path),
                 "--output", str(tmp_path / "out")]) == 1


def test_bundle_rejects_child_requirement_escalation_even_with_updated_hash():
    _, bundle = draft()
    content = bundle.model_dump(mode="json")
    content["fixture"]["proposals_by_parent"]["read"] = [{
        "id": "bad", "name": "Bad scope", "responsibility": "Wrong", "boundary": "Wrong",
        "requirement_ids": ["FR-003"], "rationale": "Not permitted",
        "assumptions": [], "risks": [],
    }]
    from speccanopy.ai import sha256_json
    content["fixture_sha256"] = sha256_json(FixtureDesign.model_validate(content["fixture"]).model_dump(mode="json"))
    with pytest.raises(ValidationError, match="outside its parent"):
        AIProposalBundle.model_validate(content)


def test_checked_in_ai_sample_reproduces_exact_bytes(tmp_path):
    result, bundle = draft()
    exported = export_ai_draft(result, bundle, tmp_path)
    golden = EXAMPLES / "ai-drafts" / "cli-utility"
    assert set(exported) == {p.name for p in golden.iterdir()}
    for name, path in exported.items():
        assert path.read_bytes() == (golden / name).read_bytes(), name


def test_scripted_duplicate_id_across_different_parent_is_rejected():
    brief, responses = example()
    responses["read"] = {
        "expand": True, "reason": "Bad reuse", "children": [{
            "id": "write", "name": "Duplicate", "responsibility": "Duplicate",
            "boundary": "bad", "requirement_ids": ["FR-001"],
            "rationale": "Bad reuse", "assumptions": [], "risks": [],
        }], "open_questions": [],
    }
    brief.constraints.max_refinement_rounds = 0
    with pytest.raises(AIProposalError, match="bounded repairs"):
        draft_architecture(brief, ScriptedProposalClient(responses))


def test_live_client_uses_env_key_and_no_key_appears_in_provenance(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "only-in-environment")
    client = OpenAIResponsesClient("test-model")
    assert client.provider == "openai-responses"
    # The public transport adapter is not meant to serialize the secret.
    assert "only-in-environment" not in str(client)


def test_propose_ai_refuses_unusable_output_before_any_model_call(tmp_path, monkeypatch, capsys):
    """A refused output folder must not cost (possibly billed) model requests."""
    from speccanopy import cli

    def no_model_calls(*args, **kwargs):
        raise AssertionError("draft_architecture must not run when output is unusable")

    monkeypatch.setattr(cli, "draft_architecture", no_model_calls)
    examples = Path(__file__).resolve().parents[1] / "examples"
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "notes.md").write_text("OWNER", encoding="utf-8")
    argv = ["propose-ai", str(examples / "cli-utility.json"), "--backend", "scripted",
            "--responses", str(examples / "ai-scripted-cli.json"), "--output"]
    assert cli.main(argv + [str(owned)]) == 1
    assert sorted(p.name for p in owned.iterdir()) == ["notes.md"]
    assert (owned / "notes.md").read_text() == "OWNER"
    assert "existing files not overwritten" in capsys.readouterr().err
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert cli.main(argv + [str(link)]) == 1
    assert not (tmp_path / "elsewhere").exists()
