"""Transparent, reviewer-authored structural architecture evaluation rubrics.

A rubric is *not* a universal quality oracle. Scores indicate the fraction of
explicitly authored structural criteria observable in the architecture draft;
expert validity and operational effectiveness are outside the evaluation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import ArchitectureSpec, Identifier, NonEmptyText, SchemaModel
from .review import ArchitectureReview, RelationshipKind, ReviewConfig, assess_architecture

CriterionKind = Literal[
    "component_present", "relationship_present", "interface_present",
    "quality_target_present", "scenario_design_complete", "verification_planned",
]


class ReferenceCriterion(SchemaModel):
    id: Identifier
    kind: CriterionKind
    description: NonEmptyText
    weight: int = Field(default=1, ge=1, le=5)
    component_id: Identifier | None = None
    source_id: Identifier | None = None
    target_id: Identifier | None = None
    relationship_kind: RelationshipKind | None = None
    direction: Literal["inbound", "outbound"] | None = None
    interface_kind: Literal["api", "event", "cli", "file", "function", "other"] | None = None
    requirement_id: Identifier | None = None
    scenario_id: Identifier | None = None

    @model_validator(mode="after")
    def exact_target(self) -> ReferenceCriterion:
        payload = {name for name in (
            "component_id", "source_id", "target_id", "relationship_kind", "direction",
            "interface_kind", "requirement_id", "scenario_id"
        ) if getattr(self, name) is not None}
        expected = {
            "component_present": {"component_id"},
            "relationship_present": {"source_id", "target_id", "relationship_kind"},
            "interface_present": {"component_id", "direction", "interface_kind"},
            "quality_target_present": {"component_id", "requirement_id"},
            "scenario_design_complete": {"scenario_id"},
            "verification_planned": {"requirement_id"},
        }[self.kind]
        if payload != expected:
            raise ValueError(f"{self.kind} requires exactly {sorted(expected)}")
        return self


class ReferenceRubric(SchemaModel):
    name: NonEmptyText
    source: NonEmptyText
    status: Literal["curated_unreviewed", "reviewer_attested"] = "curated_unreviewed"
    reviewer: NonEmptyText | None = None
    criteria: list[ReferenceCriterion] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def review_metadata(self) -> ReferenceRubric:
        ids = [x.id for x in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("Rubric criterion IDs must be unique")
        if self.status == "reviewer_attested" and not self.reviewer:
            raise ValueError("A reviewer-attested rubric requires a reviewer identifier")
        if self.status == "curated_unreviewed" and self.reviewer:
            raise ValueError("Do not label a rubric unreviewed while claiming a reviewer")
        return self


class CriterionResult(SchemaModel):
    id: Identifier
    kind: CriterionKind
    description: NonEmptyText
    weight: int
    present: bool
    reason: NonEmptyText


class BenchmarkAssessment(SchemaModel):
    system: NonEmptyText
    rubric_name: NonEmptyText
    rubric_status: str
    score: float = Field(ge=0, le=100)
    satisfied: int
    total: int
    missing_criteria: list[Identifier]
    results: list[CriterionResult]
    high_or_critical_findings: int
    uncovered_mandatory: list[str]
    caveat: NonEmptyText = (
        "This score is criterion presence under a human-authored rubric, NOT independent "
        "architecture correctness, expert certification, performance or security validation."
    )


class BenchmarkComparison(SchemaModel):
    before: BenchmarkAssessment
    after: BenchmarkAssessment
    delta_points: float
    reduced_high_or_critical: int
    introduced_missing_criteria: list[Identifier]
    caveat: NonEmptyText = (
        "A positive rubric score delta only means more authored structural checks match; "
        "human domain review and real-world architectural validation remain necessary."
    )


def _criterion_present(spec: ArchitectureSpec, review: ArchitectureReview,
                       config: ReviewConfig, criterion: ReferenceCriterion) -> tuple[bool, str]:
    components = {component.id: component for component in spec.components}
    if criterion.kind == "component_present":
        present = criterion.component_id in components
        return present, "Component is represented in the hierarchy" if present else "Missing expected component"
    if criterion.kind == "relationship_present":
        present = any((x.source_id, x.target_id, x.kind) == (
            criterion.source_id, criterion.target_id, criterion.relationship_kind
        ) for x in spec.relationships)
        return present, "Typed interaction is represented" if present else "Expected typed interaction is missing"
    if criterion.kind == "interface_present":
        component = components.get(criterion.component_id)
        present = bool(component and any((i.direction, i.kind) == (
            criterion.direction, criterion.interface_kind
        ) for i in component.interfaces))
        return present, "Directional contract is specified" if present else "Required directional contract is missing"
    if criterion.kind == "quality_target_present":
        component = components.get(criterion.component_id)
        present = bool(component and criterion.requirement_id in component.quality_targets)
        return present, "Quality target is recorded" if present else "Quality target is missing"
    if criterion.kind == "scenario_design_complete":
        assessment = next((x for x in review.quality_review.scenario_assessments if x.scenario_id == criterion.scenario_id), None)
        if not any(s.id == criterion.scenario_id for s in config.scenarios):
            raise ValueError(f"Rubric scenario {criterion.scenario_id} not in review configuration")
        present = bool(assessment and not assessment.missing_design_elements)
        return present, "No rule-based scenario design gaps" if present else "Scenario still has rule-based design gaps"
    if criterion.kind == "verification_planned":
        if criterion.requirement_id not in spec.brief.requirement_ids():
            raise ValueError(f"Unknown criterion requirement: {criterion.requirement_id}")
        report = spec.coverage_report()
        present = criterion.requirement_id in set(report.verified + report.planned_only)
        return present, "Requirement has a linked verification case" if present else "Missing linked verification case"
    raise ValueError(f"Unsupported criterion {criterion.kind}")


def evaluate_reference(spec: ArchitectureSpec, config: ReviewConfig,
                       rubric: ReferenceRubric) -> BenchmarkAssessment:
    review = assess_architecture(spec, config)
    results: list[CriterionResult] = []
    for criterion in rubric.criteria:
        present, reason = _criterion_present(spec, review, config, criterion)
        results.append(CriterionResult(
            id=criterion.id, kind=criterion.kind, description=criterion.description,
            weight=criterion.weight, present=present, reason=reason,
        ))
    weight = sum(x.weight for x in results)
    score = round(100 * sum(x.weight for x in results if x.present) / weight, 2)
    return BenchmarkAssessment(
        system=spec.brief.system, rubric_name=rubric.name, rubric_status=rubric.status,
        score=score, satisfied=sum(x.present for x in results), total=len(results),
        missing_criteria=[x.id for x in results if not x.present], results=results,
        high_or_critical_findings=sum(x.severity in {"critical", "high"} for x in review.quality_review.findings),
        uncovered_mandatory=review.quality_review.coverage.uncovered,
    )


def compare_reference(before: ArchitectureSpec, after: ArchitectureSpec, config: ReviewConfig,
                      rubric: ReferenceRubric) -> BenchmarkComparison:
    if before.brief.model_dump(mode="json") != after.brief.model_dump(mode="json"):
        raise ValueError("Benchmark comparison requires the same original system brief")
    b = evaluate_reference(before, config, rubric)
    a = evaluate_reference(after, config, rubric)
    added_missing = sorted(set(a.missing_criteria) - set(b.missing_criteria))
    return BenchmarkComparison(
        before=b, after=a, delta_points=round(a.score - b.score, 2),
        reduced_high_or_critical=b.high_or_critical_findings - a.high_or_critical_findings,
        introduced_missing_criteria=added_missing,
    )
