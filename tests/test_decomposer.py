"""Cross-domain recursion, prioritization, coverage and fail-safe budget tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.decomposer import generate_architecture
from speccanopy.fixtures import FixtureDesign
from speccanopy.models import ArchitectureSpec, SystemBrief
from speccanopy.scoring import PriorityFactors, score_priority

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def example(stem):
    brief = SystemBrief.model_validate_json((EXAMPLES / f"{stem}.json").read_text())
    fixture = FixtureDesign.model_validate_json((EXAMPLES / f"{stem}.design.json").read_text())
    return brief, fixture


@pytest.mark.parametrize("stem,depth,count,breadth", [
    ("cli-utility", 1, 4, {"system": 3}),
    ("ecommerce", 3, 13, {"system": 5, "orders": 3, "payments": 2, "order_lifecycle": 2}),
    ("file-transfer", 4, 13, {"system": 4, "engine": 3, "adapters": 3, "s3": 2}),
])
def test_three_domains_vary_depth_and_breadth(stem, depth, count, breadth):
    brief, fixture = example(stem)
    run = generate_architecture(brief, fixture)
    assert run.stats()["max_depth"] == depth
    assert len(run.architecture.components) == count
    assert run.architecture.status == "draft"
    assert all(component.status == "ready" for component in run.architecture.components)
    assert all(case.status == "planned" for case in run.architecture.verification_cases)
    assert run.architecture.coverage_report().uncovered == []
    assert set(run.architecture.coverage_report().planned_only) == brief.mandatory_requirement_ids()
    assert run.architecture.coverage_report().verified == []
    graph = {component.id: component.parent_id for component in run.architecture.components}
    assert graph["system"] is None
    for parent, n in breadth.items():
        assert sum(component.parent_id == parent for component in run.architecture.components) == n
    assert ArchitectureSpec.model_validate_json(run.architecture.model_dump_json()) == run.architecture
    assert all(edge.source_id in graph and edge.target_id in graph for edge in run.architecture.relationships)
    assert any(e.action == "completed" for e in run.trace)


def test_priority_frontier_prefers_explicit_high_priority_nodes():
    brief, fixture = example("ecommerce")
    run = generate_architecture(brief, fixture)
    order = [e.component_id for e in run.trace if e.action in {"expanded", "leaf"}]
    assert order[:4] == ["system", "payments", "payment_gateway", "orders"]
    assert next(c.priority_score for c in run.architecture.components if c.id == "payments") > next(
        c.priority_score for c in run.architecture.components if c.id == "catalog"
    )


def test_scoring_formula_and_bounds():
    assert score_priority(PriorityFactors(value=10, risk=10, dependency=10, quality_impact=10, uncertainty=10)) == 10
    assert score_priority(PriorityFactors(value=10)) == 3
    assert score_priority(None) == 0
    with pytest.raises(ValidationError):
        PriorityFactors(uncertainty=11)


def test_generation_is_bitwise_deterministic_and_does_not_mutate_fixtures():
    brief, design = example("file-transfer")
    saved = design.model_dump_json()
    first = generate_architecture(brief, design)
    second = generate_architecture(brief, design)
    assert first.architecture.model_dump_json() == second.architecture.model_dump_json()
    assert [e.model_dump() for e in first.trace] == [e.model_dump() for e in second.trace]
    assert design.model_dump_json() == saved


def test_depth_limit_marks_incomplete_and_preserves_uncovered_requirements():
    brief, fixture = example("file-transfer")
    brief.constraints.max_depth = 1
    run = generate_architecture(brief, fixture)
    assert run.architecture.status == "incomplete_requires_review"
    blocked = {c.id for c in run.architecture.components if c.status == "blocked"}
    assert "engine" in blocked
    assert any(event.action == "blocked_depth" for event in run.trace)
    assert "FR-003" in run.architecture.coverage_report().uncovered
    assert any(f.severity == "high" and "Depth limit" in f.description for f in run.architecture.findings)
    assert all(edge.source_id in {c.id for c in run.architecture.components} for edge in run.architecture.relationships)


def test_node_budget_never_silently_discards_proposed_components():
    brief, fixture = example("ecommerce")
    brief.constraints.max_nodes = 5
    run = generate_architecture(brief, fixture)
    assert run.architecture.status == "incomplete_requires_review"
    assert len(run.architecture.components) == 1
    assert run.architecture.components[0].status == "blocked"
    assert any("Node budget" in f.description for f in run.architecture.findings)
    assert run.architecture.coverage_report().uncovered == sorted(brief.mandatory_requirement_ids())
    assert any(e.action == "unmaterialized_link" for e in run.trace)


def test_empty_decomposition_without_readiness_evidence_requires_review():
    brief, fixture = example("cli-utility")
    fixture.proposals_by_parent.pop("system")
    # A fixture with no proposal entries may still be a deliberate root-only design.
    fixture.root.validation_evidence = []
    fixture.root.stop_reason = None
    run = generate_architecture(brief, fixture)
    assert run.architecture.status == "incomplete_requires_review"
    assert run.architecture.components[0].status == "requires_review"
    assert any(e.action == "requires_review" for e in run.trace)


def test_missing_architectural_verification_case_is_reported_as_uncovered():
    brief, fixture = example("cli-utility")
    fixture.verification_cases = [case for case in fixture.verification_cases if "FR-002" not in case.requirement_ids]
    run = generate_architecture(brief, fixture)
    assert run.architecture.status == "incomplete_requires_review"
    assert "FR-002" in run.architecture.coverage_report().uncovered
    assert any("Uncovered mandatory" in f.description for f in run.architecture.findings)


def test_bad_fixture_references_are_rejected_before_generation():
    _, fixture = example("cli-utility")
    data = fixture.model_dump()
    data["relationships"][0]["target_id"] = "ghost"
    with pytest.raises(ValidationError, match="unknown component"):
        FixtureDesign.model_validate(data)


def test_orphaned_proposals_cannot_be_silently_skipped():
    _, fixture = example("cli-utility")
    data = fixture.model_dump()
    data["proposals_by_parent"]["unexpected"] = []
    with pytest.raises(ValidationError, match="unknown parent"):
        FixtureDesign.model_validate(data)


def test_invalid_proposer_output_is_rejected():
    brief, fixture = example("cli-utility")
    class BrokenProposer:
        def propose(self, parent, brief):
            return list(fixture.proposals_by_parent.get("system", []))  # duplicates for every node
    with pytest.raises(ValueError, match="Duplicate or cyclic"):
        generate_architecture(brief, fixture, proposer=BrokenProposer())


def test_no_unsupported_claim_of_validated_for_scope():
    brief, fixture = example("cli-utility")
    for case in fixture.verification_cases:
        case.evidence = "Fixture author says reviewed; no independent verification by generator"
        case.status = "verified"
    run = generate_architecture(brief, fixture)
    assert run.architecture.status == "draft"
    assert run.architecture.coverage_report().uncovered == []


def test_unmaterialized_author_input_still_must_reference_known_requirements():
    brief, fixture = example("ecommerce")
    brief.constraints.max_nodes = 1  # deeper proposals would never be visited
    fixture.proposals_by_parent["payments"][0].requirement_ids.append("FR-FAKE")
    with pytest.raises(ValueError, match="unknown requirements"):
        generate_architecture(brief, fixture)


def test_expansion_trace_preserves_authored_child_rationale():
    brief, fixture = example("ecommerce")
    event = next(e for e in generate_architecture(brief, fixture).trace if e.action == "expanded")
    assert set(event.child_rationales) == set(event.child_ids)
    assert event.child_rationales["orders"].startswith("Explicit responsibility")
