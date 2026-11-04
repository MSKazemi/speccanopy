"""Typed, style-independent contracts for Speccanopy architecture documents.

Models validate *structural* integrity, not that a design is correct in reality.
Coverage distinguishes verified design evidence from a verification plan.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_.:-]*$")]
NonEmptyText = Annotated[str, StringConstraints(min_length=1)]


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class FunctionalRequirement(SchemaModel):
    id: Identifier
    statement: NonEmptyText
    mandatory: bool = True


class QualityRequirement(SchemaModel):
    id: Identifier
    attribute: NonEmptyText
    statement: NonEmptyText
    mandatory: bool = True


class DesignConstraints(SchemaModel):
    preferred_architecture: NonEmptyText | None = None
    max_depth: int = Field(default=6, ge=0, le=50)
    max_nodes: int = Field(default=150, ge=1, le=100_000)
    max_refinement_rounds: int = Field(default=3, ge=0, le=100)


class SystemBrief(SchemaModel):
    system: NonEmptyText
    goals: list[NonEmptyText] = Field(min_length=1)
    actors: list[NonEmptyText] = Field(default_factory=list)
    functional_requirements: list[FunctionalRequirement] = Field(min_length=1)
    quality_requirements: list[QualityRequirement] = Field(default_factory=list)
    constraints: DesignConstraints = Field(default_factory=DesignConstraints)

    @model_validator(mode="after")
    def unique_requirement_ids(self) -> SystemBrief:
        ids = [req.id for req in (*self.functional_requirements, *self.quality_requirements)]
        if len(ids) != len(set(ids)):
            raise ValueError("Requirement IDs must be unique across functional and quality requirements")
        return self

    def requirement_ids(self) -> set[str]:
        return {req.id for req in (*self.functional_requirements, *self.quality_requirements)}

    def mandatory_requirement_ids(self) -> set[str]:
        return {
            req.id
            for req in (*self.functional_requirements, *self.quality_requirements)
            if req.mandatory
        }


class InterfaceContract(SchemaModel):
    name: NonEmptyText
    direction: Literal["inbound", "outbound"]
    kind: Literal["api", "event", "cli", "file", "function", "other"]
    description: NonEmptyText
    failure_behavior: NonEmptyText | None = None


class Component(SchemaModel):
    id: Identifier
    name: NonEmptyText
    responsibility: NonEmptyText
    boundary: NonEmptyText
    parent_id: Identifier | None = None
    requirement_ids: list[Identifier] = Field(default_factory=list)
    interfaces: list[InterfaceContract] = Field(default_factory=list)
    interfaces_not_applicable_reason: NonEmptyText | None = None
    owned_data: list[NonEmptyText] = Field(default_factory=list)
    data_not_applicable_reason: NonEmptyText | None = None
    quality_targets: dict[str, NonEmptyText] = Field(default_factory=dict)
    assumptions: list[NonEmptyText] = Field(default_factory=list)
    risks: list[NonEmptyText] = Field(default_factory=list)
    validation_evidence: list[NonEmptyText] = Field(default_factory=list)
    stop_reason: NonEmptyText | None = None
    priority_score: float | None = Field(default=None, ge=0, le=10)
    status: Literal["proposed", "needs_decomposition", "ready", "blocked", "requires_review"] = "proposed"

    @model_validator(mode="after")
    def ready_requires_evidence(self) -> Component:
        if self.status == "ready":
            missing = []
            if not (self.interfaces or self.interfaces_not_applicable_reason):
                missing.append("interfaces or interfaces_not_applicable_reason")
            if not (self.owned_data or self.data_not_applicable_reason):
                missing.append("owned_data or data_not_applicable_reason")
            if not self.validation_evidence:
                missing.append("validation_evidence")
            if not self.stop_reason:
                missing.append("stop_reason")
            if missing:
                raise ValueError("Ready component requires evidence: " + ", ".join(missing))
        return self


class Relationship(SchemaModel):
    id: Identifier
    source_id: Identifier
    target_id: Identifier
    kind: Literal["dependency", "synchronous_call", "event", "data_flow", "shared_resource", "trust_boundary", "deployment", "other"]
    description: NonEmptyText
    requirement_ids: list[Identifier] = Field(default_factory=list)


class ArchitectureDecision(SchemaModel):
    id: Identifier
    title: NonEmptyText
    choice: NonEmptyText
    rationale: NonEmptyText
    alternatives: list[NonEmptyText] = Field(default_factory=list)
    tradeoffs: list[NonEmptyText] = Field(default_factory=list)
    requirement_ids: list[Identifier] = Field(default_factory=list)
    status: Literal["proposed", "accepted", "superseded"] = "proposed"


class ValidationFinding(SchemaModel):
    id: Identifier
    severity: Literal["critical", "high", "medium", "low"]
    description: NonEmptyText
    requirement_ids: list[Identifier] = Field(default_factory=list)
    component_ids: list[Identifier] = Field(default_factory=list)
    status: Literal["open", "accepted", "resolved"] = "open"


class VerificationCase(SchemaModel):
    id: Identifier
    description: NonEmptyText
    method: Literal["design_review", "analysis", "simulation", "test_plan", "other"]
    requirement_ids: list[Identifier] = Field(min_length=1)
    component_ids: list[Identifier] = Field(min_length=1)
    status: Literal["planned", "verified"] = "planned"
    evidence: NonEmptyText | None = None

    @model_validator(mode="after")
    def verified_requires_evidence(self) -> VerificationCase:
        if self.status == "verified" and not self.evidence:
            raise ValueError("A verified case must include evidence")
        return self


class CoverageReport(SchemaModel):
    """Status for mandatory requirements only, based on component and verification links."""

    verified: list[str]
    planned_only: list[str]
    uncovered: list[str]


class ArchitectureSpec(SchemaModel):
    brief: SystemBrief
    selected_style: NonEmptyText | None = None
    components: list[Component] = Field(min_length=1)
    relationships: list[Relationship] = Field(default_factory=list)
    verification_cases: list[VerificationCase] = Field(default_factory=list)
    decisions: list[ArchitectureDecision] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)
    status: Literal["draft", "incomplete_requires_review", "validated_for_scope"] = "draft"

    def coverage_report(self) -> CoverageReport:
        mapped = {rid for component in self.components for rid in component.requirement_ids}
        planned: set[str] = set()
        verified: set[str] = set()
        for case in self.verification_cases:
            # Only count verification linked to a component that owns that requirement.
            linked = {
                rid
                for rid in case.requirement_ids
                if any(
                    rid in component.requirement_ids and component.id in case.component_ids
                    for component in self.components
                )
            }
            if case.status == "verified":
                verified.update(linked)
            else:
                planned.update(linked)
        mandatory = self.brief.mandatory_requirement_ids()
        return CoverageReport(
            verified=sorted(mandatory & verified),
            planned_only=sorted((mandatory & mapped & planned) - verified),
            uncovered=sorted(mandatory - verified - planned),
        )

    @model_validator(mode="after")
    def check_integrity(self) -> ArchitectureSpec:
        groups = (self.components, self.relationships, self.verification_cases, self.decisions, self.findings)
        ids = [record.id for group in groups for record in group]
        if len(ids) != len(set(ids)):
            raise ValueError("Architecture element IDs must be globally unique")

        by_id = {component.id: component for component in self.components}
        if len(by_id) > self.brief.constraints.max_nodes:
            raise ValueError("Component count exceeds max_nodes")
        roots = [component for component in self.components if component.parent_id is None]
        if len(roots) != 1:
            raise ValueError("Architecture requires exactly one root component")

        for component in self.components:
            depth = 0
            seen: set[str] = set()
            current: Component | None = component
            while current is not None:
                if current.id in seen:
                    raise ValueError("Containment cycle detected")
                seen.add(current.id)
                if current.parent_id is None:
                    break
                if current.parent_id not in by_id:
                    raise ValueError(f"Missing parent component: {current.parent_id}")
                depth += 1
                current = by_id[current.parent_id]
            if depth > self.brief.constraints.max_depth:
                raise ValueError("Architecture exceeds max_depth")

        valid_requirement_ids = self.brief.requirement_ids()
        quality_requirement_ids = {requirement.id for requirement in self.brief.quality_requirements}

        def check_requirements(references: list[str], location: str) -> None:
            unknown = set(references) - valid_requirement_ids
            if unknown:
                raise ValueError(f"Unknown requirement IDs in {location}: {sorted(unknown)}")

        for component in self.components:
            check_requirements(component.requirement_ids, component.id)
            for requirement_id in component.quality_targets:
                if requirement_id not in quality_requirement_ids:
                    raise ValueError(f"Quality target must reference a quality requirement: {requirement_id}")

        for relation in self.relationships:
            if relation.source_id not in by_id or relation.target_id not in by_id:
                raise ValueError(f"Relationship {relation.id} references an unknown component")
            if relation.source_id == relation.target_id:
                raise ValueError(f"Relationship {relation.id} cannot reference itself")
            check_requirements(relation.requirement_ids, relation.id)

        for case in self.verification_cases:
            if set(case.component_ids) - by_id.keys():
                raise ValueError(f"Verification case {case.id} references an unknown component")
            check_requirements(case.requirement_ids, case.id)
        for decision in self.decisions:
            check_requirements(decision.requirement_ids, decision.id)
        for finding in self.findings:
            if set(finding.component_ids) - by_id.keys():
                raise ValueError(f"Finding {finding.id} references an unknown component")
            check_requirements(finding.requirement_ids, finding.id)

        if self.status == "validated_for_scope":
            if not self.selected_style:
                raise ValueError("Validated architecture requires a selected style")
            if any(component.status != "ready" for component in self.components):
                raise ValueError("All components must be ready for validated_for_scope")
            coverage = self.coverage_report()
            for quality in self.brief.quality_requirements:
                if quality.mandatory and not any(
                    quality.id in component.quality_targets
                    for component in self.components
                    if quality.id in component.requirement_ids
                ):
                    raise ValueError(f"Mandatory quality requirement needs a quality target: {quality.id}")
            if coverage.planned_only or coverage.uncovered:
                raise ValueError("All mandatory requirements require verified coverage")
            if any(f.status == "open" and f.severity in {"critical", "high"} for f in self.findings):
                raise ValueError("Open high/critical findings prevent validated_for_scope")
        return self
