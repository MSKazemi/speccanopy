"""Contract tests for architecture modeling and validation invariants."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.models import ArchitectureSpec, Component, SystemBrief

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_json(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def spec_data() -> dict:
    return load_json("cli-utility-architecture.json")


def test_input_brief_validates() -> None:
    brief = SystemBrief.model_validate(load_json("cli-utility.json"))
    assert brief.system == "Text normalization CLI utility"
    assert brief.mandatory_requirement_ids() == {"FR-001", "FR-002", "FR-003", "NFR-001"}
    assert brief.constraints.max_depth == 4


def test_example_architecture_valid_and_json_serializable() -> None:
    spec = ArchitectureSpec.model_validate(spec_data())
    round_trip = ArchitectureSpec.model_validate_json(spec.model_dump_json())
    assert len(round_trip.components) == 4
    assert len(round_trip.relationships) == 2
    assert round_trip.status == "draft"


def test_coverage_distinguishes_verified_planned_and_uncovered() -> None:
    spec = ArchitectureSpec.model_validate(spec_data())
    report = spec.coverage_report()
    assert report.verified == ["FR-001", "NFR-001"]
    assert report.planned_only == ["FR-002", "FR-003"]
    assert report.uncovered == []


def test_requirement_without_matching_case_is_uncovered() -> None:
    data = spec_data()
    data["verification_cases"] = [data["verification_cases"][0]]
    report = ArchitectureSpec.model_validate(data).coverage_report()
    assert report.uncovered == ["FR-002", "FR-003"]


def test_verified_case_must_link_to_component_responsible_for_requirement() -> None:
    data = spec_data()
    data["verification_cases"][0]["component_ids"] = ["normalize"]
    report = ArchitectureSpec.model_validate(data).coverage_report()
    assert "FR-001" in report.uncovered
    # NFR-001 can still be in planned_only via output.
    assert "NFR-001" in report.planned_only


@pytest.mark.parametrize("change", [
    lambda d: d.update({"surprise": True}),
    lambda d: d.update({"goals": []}),
    lambda d: d["constraints"].update({"max_nodes": 0}),
    lambda d: d["functional_requirements"].append({"id": "NFR-001", "statement": "Clashing ID"}),
])
def test_invalid_brief_rejected(change) -> None:
    data = load_json("cli-utility.json")
    change(data)
    with pytest.raises(ValidationError):
        SystemBrief.model_validate(data)


def test_ready_component_requires_positive_evidence() -> None:
    with pytest.raises(ValidationError, match="Ready component requires evidence"):
        Component(id="unit", name="Unit", responsibility="Do work", boundary="Module", status="ready")


def test_verified_case_requires_evidence() -> None:
    data = spec_data()
    del data["verification_cases"][0]["evidence"]
    with pytest.raises(ValidationError, match="verified case must include evidence"):
        ArchitectureSpec.model_validate(data)


def test_duplicate_component_ids_rejected() -> None:
    data = spec_data()
    data["components"][1]["id"] = "system"
    with pytest.raises(ValidationError, match="globally unique"):
        ArchitectureSpec.model_validate(data)


def test_missing_parent_rejected() -> None:
    data = spec_data()
    data["components"][1]["parent_id"] = "nonexistent"
    with pytest.raises(ValidationError, match="Missing parent"):
        ArchitectureSpec.model_validate(data)


def test_containment_cycle_rejected() -> None:
    data = spec_data()
    data["components"][0]["parent_id"] = "normalize"
    with pytest.raises(ValidationError, match="root component"):
        ArchitectureSpec.model_validate(data)


def test_relationship_to_unknown_component_rejected() -> None:
    data = spec_data()
    data["relationships"][0]["target_id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown component"):
        ArchitectureSpec.model_validate(data)


def test_self_relationship_rejected() -> None:
    data = spec_data()
    data["relationships"][0]["target_id"] = "input"
    with pytest.raises(ValidationError, match="cannot reference itself"):
        ArchitectureSpec.model_validate(data)


def test_unknown_requirement_reference_rejected() -> None:
    data = spec_data()
    data["components"][1]["requirement_ids"].append("FR-MISSING")
    with pytest.raises(ValidationError, match="Unknown requirement"):
        ArchitectureSpec.model_validate(data)


def test_verification_missing_component_rejected() -> None:
    data = spec_data()
    data["verification_cases"][0]["component_ids"] = ["unknown"]
    with pytest.raises(ValidationError, match="unknown component"):
        ArchitectureSpec.model_validate(data)


def test_max_nodes_enforced() -> None:
    data = spec_data()
    data["brief"]["constraints"]["max_nodes"] = 3
    with pytest.raises(ValidationError, match="max_nodes"):
        ArchitectureSpec.model_validate(data)


def test_max_depth_enforced() -> None:
    data = spec_data()
    data["brief"]["constraints"]["max_depth"] = 0
    with pytest.raises(ValidationError, match="max_depth"):
        ArchitectureSpec.model_validate(data)


def test_validated_status_requires_evidence_and_ready_components() -> None:
    data = spec_data()
    data["status"] = "validated_for_scope"
    with pytest.raises(ValidationError, match="All components must be ready"):
        ArchitectureSpec.model_validate(data)


def test_validated_status_rejects_unverified_mandatory_requirement() -> None:
    data = spec_data()
    data["status"] = "validated_for_scope"
    # Make root ready without claiming this example is actually validated.
    root = data["components"][0]
    root["status"] = "ready"
    root["interfaces_not_applicable_reason"] = "Orchestrator is internal"
    root["data_not_applicable_reason"] = "Stateless orchestrator"
    root["validation_evidence"] = ["Reviewed integration boundary"]
    root["stop_reason"] = "All operations delegated"
    with pytest.raises(ValidationError, match="verified coverage"):
        ArchitectureSpec.model_validate(data)


def test_validated_status_rejects_open_critical_finding() -> None:
    data = spec_data()
    data["status"] = "validated_for_scope"
    for component in data["components"]:
        if component["id"] == "system":
            component["status"] = "ready"
            component["interfaces_not_applicable_reason"] = "Internal orchestrator"
            component["data_not_applicable_reason"] = "Stateless"
            component["validation_evidence"] = ["Reviewed integration boundaries"]
            component["stop_reason"] = "No further architectural decomposition needed"
    for case in data["verification_cases"]:
        case["status"] = "verified"
        case["evidence"] = "Architecture contract reviewed"
    data["findings"][0]["severity"] = "critical"
    with pytest.raises(ValidationError, match="Open high/critical"):
        ArchitectureSpec.model_validate(data)


def test_validation_can_pass_when_all_explicit_gates_pass() -> None:
    data = spec_data()
    data["status"] = "validated_for_scope"
    root = data["components"][0]
    root.update(status="ready", interfaces_not_applicable_reason="Internal orchestrator",
                data_not_applicable_reason="Stateless", validation_evidence=["Reviewed interactions"],
                stop_reason="Responsibilities assigned")
    for case in data["verification_cases"]:
        case.update(status="verified", evidence="Architecture review evidence")
    data["findings"][0]["status"] = "resolved"
    spec = ArchitectureSpec.model_validate(data)
    assert spec.coverage_report().uncovered == []
    assert spec.status == "validated_for_scope"


def test_quality_target_cannot_point_to_functional_requirement() -> None:
    data = spec_data()
    data["components"][1]["quality_targets"] = {"FR-001": "Wrong target"}
    with pytest.raises(ValidationError, match="Quality target must reference a quality requirement"):
        ArchitectureSpec.model_validate(data)


def test_disconnected_containment_cycle_rejected() -> None:
    data = spec_data()
    data["components"].append({"id": "cycle_a", "name": "Cycle A", "responsibility": "A", "boundary": "A", "parent_id": "cycle_b"})
    data["components"].append({"id": "cycle_b", "name": "Cycle B", "responsibility": "B", "boundary": "B", "parent_id": "cycle_a"})
    with pytest.raises(ValidationError, match="Containment cycle"):
        ArchitectureSpec.model_validate(data)


def test_validated_status_requires_mandatory_quality_target() -> None:
    data = spec_data()
    data["status"] = "validated_for_scope"
    root = data["components"][0]
    root.update(status="ready", interfaces_not_applicable_reason="Orchestrator is internal",
                data_not_applicable_reason="Stateless", validation_evidence=["Reviewed interactions"],
                stop_reason="Responsibilities assigned")
    for component in data["components"]:
        component["quality_targets"] = {}
    for case in data["verification_cases"]:
        case.update(status="verified", evidence="Reviewed interface")
    data["findings"][0]["status"] = "resolved"
    with pytest.raises(ValidationError, match="Mandatory quality requirement needs a quality target"):
        ArchitectureSpec.model_validate(data)
