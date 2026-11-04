"""Phase 3 advisory style comparison and independent quality review tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.cli import main
from speccanopy.models import ArchitectureSpec, ValidationFinding
from speccanopy.review import (
    ExpectedInteraction, QualityScenario, ReviewConfig, StyleDriver,
    assess_architecture, compare_styles, review_quality,
)
from speccanopy.review_exporters import export_review, review_markdown

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def example(name: str) -> tuple[ArchitectureSpec, ReviewConfig]:
    spec = ArchitectureSpec.model_validate_json((EXAMPLES / "generated" / name / "architecture.json").read_text())
    config = ReviewConfig.model_validate_json((EXAMPLES / f"{name}.review.json").read_text())
    return spec, config


@pytest.mark.parametrize("name,expected_style,scenarios", [
    ("cli-utility", "single_process", 1),
    ("ecommerce", "modular_monolith", 2),
    ("file-transfer", "event_driven", 1),
])
def test_three_domains_assessed_without_claim_of_validation(name, expected_style, scenarios):
    spec, config = example(name)
    report = assess_architecture(spec, config)
    assert report.style_comparison.recommendation == expected_style
    assert report.style_comparison.status == "recommendation"
    assert report.style_comparison.declared_style_family == expected_style
    assert report.overall_status == "requires_review"
    assert len(report.quality_review.scenario_assessments) == scenarios
    assert all(a.status == "verification_pending" for a in report.quality_review.scenario_assessments)
    assert report.quality_review.coverage.verified == []
    assert len(report.style_comparison.candidates) == 5
    assert all(c.score is not None and c.tradeoff for c in report.style_comparison.candidates)
    assert all(c.driver_fits for c in report.style_comparison.candidates)
    assert "not measured" in report.style_comparison.methodology


def test_absent_drivers_refuse_to_invent_style_selection():
    spec, _ = example("ecommerce")
    result = assess_architecture(spec)
    assert result.style_comparison.status == "insufficient_drivers"
    assert result.style_comparison.recommendation is None
    assert all(c.score is None for c in result.style_comparison.candidates)
    assert any(f.category == "quality_scenario" for f in result.quality_review.findings)


def test_ambiguous_score_abstains_without_arbitrary_tiebreak():
    spec, _ = example("cli-utility")
    config = ReviewConfig(
        candidates=["single_process", "modular_monolith"],
        drivers=[StyleDriver(key="strong_consistency", importance=4, desired=5, rationale="Consistent local writes")],
    )
    result = compare_styles(spec, config)
    assert result.status == "ambiguous"
    assert result.recommendation is None
    assert result.candidates[0].score == result.candidates[1].score


def test_driver_changes_recommendation_without_mutating_authored_style():
    spec, _ = example("ecommerce")
    config = ReviewConfig(drivers=[
        StyleDriver(key="independent_deployment", importance=5, desired=5, rationale="Teams must ship independently"),
        StyleDriver(key="fault_isolation", importance=5, desired=5, rationale="Faults isolated by service"),
    ])
    report = assess_architecture(spec, config)
    assert report.style_comparison.recommendation == "microservices"
    assert spec.selected_style == "modular monolith"
    assert report.style_comparison.declared_style == spec.selected_style
    assert any(f.category == "style_tradeoff" for f in report.quality_review.findings)


@pytest.mark.parametrize("mutation,match", [
    (lambda d: d["drivers"].append(d["drivers"][0]), "Duplicate driver"),
    (lambda d: d.update({"candidates": ["microservices"]}), "At least two"),
    (lambda d: d["scenarios"].append(d["scenarios"][0]), "Duplicate scenario"),
    (lambda d: d["drivers"][0].update({"desired": 6}), "less than or equal to 5"),
    (lambda d: d["drivers"][0].update({"key": "magic_style"}), "Input should be"),
])
def test_invalid_config_rejected(mutation, match):
    _, config = example("ecommerce")
    data = config.model_dump()
    mutation(data)
    with pytest.raises(ValidationError, match=match):
        ReviewConfig.model_validate(data)


def test_duplicate_scenario_components_rejected():
    with pytest.raises(ValidationError, match="must be unique"):
        QualityScenario(id="SC-A", requirement_id="NFR-001", stimulus="An error", expected_response="Fail safely",
                        measure="Document recovery", component_ids=["payments", "payments"])


def test_rejects_unknown_quality_requirement_even_if_functional_exists():
    spec, config = example("ecommerce")
    config.scenarios[0].requirement_id = "FR-001"
    with pytest.raises(ValueError, match="quality requirement"):
        assess_architecture(spec, config)


def test_rejects_scenario_unknown_component_and_edge():
    spec, config = example("ecommerce")
    config.scenarios[0].component_ids = ["ghost"]
    with pytest.raises(ValueError, match="unknown components"):
        review_quality(spec, config)
    config.scenarios[0].component_ids = ["payments"]
    config.scenarios[0].expected_interactions = [ExpectedInteraction(
        source_id="payments", target_id="ghost", kind="trust_boundary"
    )]
    with pytest.raises(ValueError, match="interaction references unknown"):
        review_quality(spec, config)


def test_missing_expected_interaction_detected_as_quality_gap():
    spec, config = example("ecommerce")
    config.scenarios[0].expected_interactions = [ExpectedInteraction(
        source_id="payments", target_id="identity", kind="event"
    )]
    report = review_quality(spec, config)
    scenario = report.scenario_assessments[0]
    assert scenario.status == "design_gap"
    assert any("Missing expected event" in i for i in scenario.missing_design_elements)
    assert any(f.category == "scenario_design" and f.severity == "high" for f in report.findings)


def test_existing_edge_without_scenario_requirement_trace_is_not_credited():
    spec, config = example("ecommerce")
    spec.relationships[3].requirement_ids = ["FR-003"]
    assessment = review_quality(spec, config).scenario_assessments[0]
    assert assessment.status == "design_gap"
    assert any("does not trace" in reason for reason in assessment.missing_design_elements)


def test_missing_quality_target_detected_independently():
    spec, config = example("cli-utility")
    for comp in spec.components:
        comp.quality_targets = {}
    review = review_quality(spec, config)
    assert any(f.category == "quality_target" and f.severity == "high" for f in review.findings)
    assert review.scenario_assessments[0].status == "design_gap"


def test_duplicate_sibling_data_ownership_requires_review():
    spec, config = example("cli-utility")
    c1 = next(c for c in spec.components if c.id == "input")
    c2 = next(c for c in spec.components if c.id == "output")
    c1.owned_data = ["Shared file"]
    c2.owned_data = ["shared file"]
    review = review_quality(spec, config)
    assert any(f.category == "data_ownership" for f in review.findings)


def test_open_source_high_risk_is_not_suppressed():
    spec, config = example("cli-utility")
    spec.findings.append(ValidationFinding(
        id="OPEN-HIGH-001", severity="high", status="open",
        description="No safe rollback path for failed output writing", component_ids=["output"],
        requirement_ids=["NFR-001"],
    ))
    report = assess_architecture(spec, config)
    risks = [f for f in report.quality_review.findings if f.category == "source_architecture_risk"]
    assert len(risks) == 1
    assert risks[0].severity == "high"
    assert "OPEN-HIGH-001" in risks[0].description
    assert report.overall_status == "requires_review"


def test_missing_architecture_style_is_flagged():
    spec, config = example("cli-utility")
    spec.selected_style = None
    result = assess_architecture(spec, config)
    assert any(f.category == "style_decision" for f in result.quality_review.findings)


def test_call_and_event_contract_gaps_are_detected():
    spec, config = example("ecommerce")
    review = review_quality(spec, config)
    assert any(f.category == "interaction_contract" for f in review.findings)
    assert all(f.component_ids for f in review.findings if f.category == "interaction_contract")


def test_missing_planned_verification_does_not_become_verified():
    spec, config = example("file-transfer")
    spec.verification_cases = []
    review = review_quality(spec, config)
    assert review.scenario_assessments[0].verification_status == "missing"
    assert review.scenario_assessments[0].status == "verification_pending"
    assert review.coverage.uncovered


def test_authored_verified_evidence_is_not_independent_signoff():
    spec, config = example("cli-utility")
    for case in spec.verification_cases:
        case.evidence = "Architecture reviewer confirms explicit control"
        case.status = "verified"
    review = assess_architecture(spec, config)
    assert review.quality_review.scenario_assessments[0].status == "evidence_documented"
    assert review.source_architecture_status == "draft"
    assert review.overall_status == "requires_review"
    assert "No LLM inference" in review.provenance


def test_no_mutation_and_determinism():
    spec, config = example("ecommerce")
    before_spec, before_config = spec.model_dump_json(), config.model_dump_json()
    a, b = assess_architecture(spec, config), assess_architecture(spec, config)
    assert a.model_dump_json() == b.model_dump_json()
    assert spec.model_dump_json() == before_spec
    assert config.model_dump_json() == before_config


def test_markdown_report_explains_caveats():
    spec, config = example("file-transfer")
    report = assess_architecture(spec, config)
    text = review_markdown(report)
    assert "Architecture review" in text
    assert "event_driven" in text
    assert "not measured benchmarks" in text
    assert "verification_pending" in text


@pytest.mark.parametrize("name", ["cli-utility", "ecommerce", "file-transfer"])
def test_cli_review_emits_reviewable_artifacts(name, tmp_path, capsys):
    dest = tmp_path / name
    code = main(["review", str(EXAMPLES / "generated" / name / "architecture.json"),
                 "--config", str(EXAMPLES / f"{name}.review.json"), "--output", str(dest)])
    assert code == 0
    assert sorted(f.name for f in dest.iterdir()) == [
        "architecture-review.json", "architecture-review.md", "quality-review.json", "style-comparison.json"
    ]
    report = json.loads((dest / "architecture-review.json").read_text())
    assert report["overall_status"] == "requires_review"
    assert report["style_comparison"]["recommendation"]
    assert json.loads((dest / "quality-review.json").read_text())["coverage"]["uncovered"] == []
    assert "Quality findings:" in capsys.readouterr().out


def test_cli_review_strict_requires_human_approval(tmp_path):
    spec = EXAMPLES / "generated/ecommerce/architecture.json"
    assert main(["review", str(spec), "--config", str(EXAMPLES / "ecommerce.review.json"),
                 "--output", str(tmp_path), "--strict"]) == 2


def test_cli_review_no_config_abstains(tmp_path):
    spec = EXAMPLES / "generated/ecommerce/architecture.json"
    assert main(["review", str(spec), "--output", str(tmp_path)]) == 0
    result = json.loads((tmp_path / "architecture-review.json").read_text())
    assert result["style_comparison"]["recommendation"] is None


def test_cli_review_rejects_bad_config(tmp_path, capsys):
    invalid = tmp_path / "bad.json"
    invalid.write_text('{"drivers": [{"key": "nonexistent"}]}')
    spec = EXAMPLES / "generated/cli-utility/architecture.json"
    assert main(["review", str(spec), "--config", str(invalid), "--output", str(tmp_path / "out")]) == 1
    assert "Error reviewing architecture" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["cli-utility", "ecommerce", "file-transfer"])
def test_review_snapshots_match_committed_examples(name, tmp_path):
    spec, config = example(name)
    paths = export_review(assess_architecture(spec, config), tmp_path)
    reference = EXAMPLES / "reviews" / name
    assert sorted(p.name for p in paths.values()) == sorted(p.name for p in reference.iterdir())
    for path in paths.values():
        assert path.read_bytes() == (reference / path.name).read_bytes()
