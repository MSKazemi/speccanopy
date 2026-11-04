"""Provider-neutral component proposals; the first proposer is deterministic.

This does not recursively design an architecture yet. The future decomposition
engine consumes this protocol and independently checks all proposals.
"""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence, runtime_checkable

from pydantic import Field

from .models import Component, Identifier, NonEmptyText, SchemaModel, SystemBrief


class ComponentProposal(SchemaModel):
    id: Identifier
    name: NonEmptyText
    responsibility: NonEmptyText
    boundary: NonEmptyText
    requirement_ids: list[Identifier] = Field(default_factory=list)
    rationale: NonEmptyText


@runtime_checkable
class ComponentProposer(Protocol):
    def propose(self, parent: Component, brief: SystemBrief) -> list[ComponentProposal]:
        """Return candidate children, without mutating architecture state."""
        ...


class FixtureComponentProposer:
    """Reproducible, non-AI proposer for schema and recursion tests."""

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
