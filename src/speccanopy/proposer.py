"""Provider-neutral component proposals with deterministic fixtures.

The engine checks proposed children and their readiness independently. Fixture
proposals are human-authored design input, *not* independently verified facts.
"""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence, runtime_checkable

from pydantic import Field

from .models import Component, Identifier, InterfaceContract, NonEmptyText, SchemaModel, SystemBrief
from .scoring import PriorityFactors


class ComponentProposal(SchemaModel):
    id: Identifier
    name: NonEmptyText
    responsibility: NonEmptyText
    boundary: NonEmptyText
    requirement_ids: list[Identifier] = Field(default_factory=list)
    rationale: NonEmptyText
    priority_factors: PriorityFactors | None = None
    interfaces: list[InterfaceContract] = Field(default_factory=list)
    interfaces_not_applicable_reason: NonEmptyText | None = None
    owned_data: list[NonEmptyText] = Field(default_factory=list)
    data_not_applicable_reason: NonEmptyText | None = None
    quality_targets: dict[Identifier, NonEmptyText] = Field(default_factory=dict)
    assumptions: list[NonEmptyText] = Field(default_factory=list)
    risks: list[NonEmptyText] = Field(default_factory=list)
    validation_evidence: list[NonEmptyText] = Field(default_factory=list)
    stop_reason: NonEmptyText | None = None


@runtime_checkable
class ComponentProposer(Protocol):
    def propose(self, parent: Component, brief: SystemBrief) -> list[ComponentProposal]:
        """Return candidate children without mutating architecture state."""
        ...


class FixtureComponentProposer:
    """Reproducible, non-AI proposer used by the first runnable engine."""

    def __init__(self, proposals_by_parent: Mapping[str, Sequence[ComponentProposal]]) -> None:
        self._proposals = {parent_id: tuple(items) for parent_id, items in proposals_by_parent.items()}
        all_ids = [item.id for items in self._proposals.values() for item in items]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("Fixture proposals must have unique component IDs")

    def propose(self, parent: Component, brief: SystemBrief) -> list[ComponentProposal]:
        result = [item.model_copy(deep=True) for item in self._proposals.get(parent.id, ())]
        allowed = brief.requirement_ids()
        for proposal in result:
            if proposal.id == parent.id:
                raise ValueError("A component cannot propose itself as its child")
            unknown = set(proposal.requirement_ids) - allowed
            if unknown:
                raise ValueError(f"Proposal {proposal.id} has unknown requirements: {sorted(unknown)}")
        return result