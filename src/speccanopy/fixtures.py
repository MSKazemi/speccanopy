"""Machine-readable curated architecture proposals for deterministic testing.

FixtureDesign is a design *proposal*: it is not a solution oracle and its
verification cases need human-reviewed evidence before becoming verified.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .models import (
    ArchitectureDecision,
    Component,
    Identifier,
    NonEmptyText,
    Relationship,
    SchemaModel,
    ValidationFinding,
    VerificationCase,
)
from .proposer import ComponentProposal


class FixtureDesign(SchemaModel):
    root: Component
    selected_style: NonEmptyText | None = None
    proposals_by_parent: dict[Identifier, list[ComponentProposal]] = Field(default_factory=dict)
    relationships: list[Relationship] = Field(default_factory=list)
    verification_cases: list[VerificationCase] = Field(default_factory=list)
    decisions: list[ArchitectureDecision] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fixture_topology(self) -> FixtureDesign:
        if self.root.parent_id is not None:
            raise ValueError("Fixture root must not have parent_id")
        child_ids = [c.id for group in self.proposals_by_parent.values() for c in group]
        if self.root.id in child_ids or len(child_ids) != len(set(child_ids)):
            raise ValueError("Fixture children must have unique IDs distinct from the root")
        all_ids = set(child_ids) | {self.root.id}
        unknown_parents = set(self.proposals_by_parent) - all_ids
        if unknown_parents:
            raise ValueError(f"Fixture has unknown parent IDs: {sorted(unknown_parents)}")

        reachable: set[str] = set()
        stack = [self.root.id]
        while stack:
            parent_id = stack.pop()
            if parent_id in reachable:
                raise ValueError("Fixture has a containment cycle")
            reachable.add(parent_id)
            stack.extend(p.id for p in self.proposals_by_parent.get(parent_id, []))
        if reachable != all_ids:
            raise ValueError(f"Fixture has unreachable proposals: {sorted(all_ids - reachable)}")

        for relation in self.relationships:
            if relation.source_id not in all_ids or relation.target_id not in all_ids:
                raise ValueError(f"Fixture relation {relation.id} references unknown component")
        for case in self.verification_cases:
            if set(case.component_ids) - all_ids:
                raise ValueError(f"Fixture case {case.id} references unknown component")
        for finding in self.findings:
            if set(finding.component_ids) - all_ids:
                raise ValueError(f"Fixture finding {finding.id} references unknown component")
        return self