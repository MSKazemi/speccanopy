"""Bounded, deterministic priority-first recursive architecture decomposition.

This is a structural generation engine over curated proposals, not an AI
architect. It does not fabricate interface contracts or validation evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush

from .fixtures import FixtureDesign
from .models import ArchitectureSpec, Component, SchemaModel, SystemBrief, ValidationFinding
from pydantic import Field
from .proposer import ComponentProposal, ComponentProposer, FixtureComponentProposer
from .scoring import score_priority


class GenerationEvent(SchemaModel):
    sequence: int
    component_id: str
    depth: int
    action: str
    details: str
    child_ids: list[str] = Field(default_factory=list)
    child_rationales: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResult:
    architecture: ArchitectureSpec
    trace: tuple[GenerationEvent, ...]
    processed_count: int

    def stats(self) -> dict[str, int | str]:
        comps = self.architecture.components
        return {
            "components": len(comps),
            "relationships": len(self.architecture.relationships),
            "max_depth": max(_depth(c, {i.id: i for i in comps}) for c in comps),
            "processed": self.processed_count,
            "status": self.architecture.status,
        }


def _depth(component: Component, by_id: dict[str, Component]) -> int:
    depth = 0
    cursor = component
    while cursor.parent_id is not None:
        depth += 1
        cursor = by_id[cursor.parent_id]
    return depth


def _readiness_missing(component: Component) -> list[str]:
    missing = []
    if not (component.interfaces or component.interfaces_not_applicable_reason):
        missing.append("interface contract or explicit not-applicable reason")
    if not (component.owned_data or component.data_not_applicable_reason):
        missing.append("data ownership or explicit not-applicable reason")
    if not component.validation_evidence:
        missing.append("architectural review evidence")
    if not component.stop_reason:
        missing.append("stop rationale")
    return missing


def _from_proposal(proposal: ComponentProposal, parent_id: str) -> Component:
    return Component(
        id=proposal.id,
        name=proposal.name,
        responsibility=proposal.responsibility,
        boundary=proposal.boundary,
        parent_id=parent_id,
        requirement_ids=proposal.requirement_ids.copy(),
        interfaces=[i.model_copy(deep=True) for i in proposal.interfaces],
        interfaces_not_applicable_reason=proposal.interfaces_not_applicable_reason,
        owned_data=proposal.owned_data.copy(),
        data_not_applicable_reason=proposal.data_not_applicable_reason,
        quality_targets=proposal.quality_targets.copy(),
        assumptions=proposal.assumptions.copy(),
        risks=proposal.risks.copy(),
        validation_evidence=proposal.validation_evidence.copy(),
        stop_reason=proposal.stop_reason,
        priority_score=score_priority(proposal.priority_factors),
        status="proposed",
    )


def generate_architecture(
    brief: SystemBrief, design: FixtureDesign, *, proposer: ComponentProposer | None = None
) -> GenerationResult:
    """Generate a validated draft, preserving gaps instead of declaring success.

    The fixture supplies candidate child components and optional relationships
    and verification plans. The engine controls recursion, priority, integrity,
    stopping criteria and failure reporting.
    """
    root = design.root.model_copy(deep=True)
    if root.status == "ready":
        # Already-reviewed fixture evidence is not a reason to skip exploring
        # this root's proposed child components.
        root.status = "proposed"
    if set(root.requirement_ids) - brief.requirement_ids():
        raise ValueError("Fixture root refers to unknown requirements")
    # Preflight all authored references, including nodes the budget might never
    # materialize; invalid fixture data must not hide behind an early stop.
    known = brief.requirement_ids()
    quality_ids = {req.id for req in brief.quality_requirements}
    authored = [design.root, *(p for group in design.proposals_by_parent.values() for p in group)]
    referenced = [
        *(node.requirement_ids for node in authored),
        *(edge.requirement_ids for edge in design.relationships),
        *(case.requirement_ids for case in design.verification_cases),
        *(decision.requirement_ids for decision in design.decisions),
        *(finding.requirement_ids for finding in design.findings),
    ]
    invalid = set().union(*map(set, referenced)) - known
    if invalid:
        raise ValueError(f"Fixture references unknown requirements: {sorted(invalid)}")
    invalid_targets = set().union(*(set(node.quality_targets) for node in authored)) - quality_ids
    if invalid_targets:
        raise ValueError(f"Fixture contains unknown quality targets: {sorted(invalid_targets)}")

    proposer = proposer if proposer is not None else FixtureComponentProposer(design.proposals_by_parent)
    components = [root]
    by_id = {root.id: root}
    depths = {root.id: 0}
    children: dict[str, list[str]] = {}
    queue: list[tuple[float, int, str]] = []
    serial = 0
    heappush(queue, (-(root.priority_score or 0), serial, root.id))
    visited: set[str] = set()
    events: list[GenerationEvent] = []
    findings = [f.model_copy(deep=True) for f in design.findings]
    claimed_ids = {item.id for group in (design.relationships, design.verification_cases, design.decisions, findings) for item in group}
    claimed_ids |= {component.id for component in components}
    claimed_ids |= {proposal.id for group in design.proposals_by_parent.values() for proposal in group}
    finding_counter = 0

    def record(
        node_id: str, action: str, details: str, child_ids: list[str] | None = None,
        rationales: dict[str, str] | None = None,
    ) -> None:
        events.append(GenerationEvent(
            sequence=len(events) + 1,
            component_id=node_id,
            depth=depths[node_id],
            action=action,
            details=details,
            child_ids=child_ids or [],
            child_rationales=rationales or {},
        ))

    def flag(node_id: str, severity: str, description: str, *, requirement_ids: list[str] | None = None) -> None:
        nonlocal finding_counter
        while True:
            finding_counter += 1
            identifier = f"GEN-FIND-{finding_counter:03d}"
            if identifier not in claimed_ids:
                break
        claimed_ids.add(identifier)
        findings.append(ValidationFinding(
            id=identifier,
            severity=severity,
            description=description,
            requirement_ids=requirement_ids or [],
            component_ids=[node_id],
            status="open",
        ))

    while queue:
        _, _, node_id = heappop(queue)
        if node_id in visited:
            continue
        visited.add(node_id)
        node = by_id[node_id]
        depth = depths[node_id]
        proposed = proposer.propose(node, brief)
        proposed_ids = [c.id for c in proposed]
        if len(proposed_ids) != len(set(proposed_ids)) or any(cid in by_id for cid in proposed_ids):
            raise ValueError(f"Duplicate or cyclic proposed child IDs under {node_id}")
        if not proposed:
            record(node_id, "leaf", "No further components proposed; review readiness evidence")
            continue
        if depth >= brief.constraints.max_depth:
            node.status = "blocked"
            message = f"Depth limit ({brief.constraints.max_depth}) prevents expanding {node_id}; proposed: {proposed_ids}"
            flag(node_id, "high", message, requirement_ids=sorted({rid for p in proposed for rid in p.requirement_ids}))
            record(node_id, "blocked_depth", message, proposed_ids)
            continue
        if len(by_id) + len(proposed) > brief.constraints.max_nodes:
            node.status = "blocked"
            message = f"Node budget ({brief.constraints.max_nodes}) prevents expanding {node_id}; proposed: {proposed_ids}"
            flag(node_id, "high", message, requirement_ids=sorted({rid for p in proposed for rid in p.requirement_ids}))
            record(node_id, "blocked_nodes", message, proposed_ids)
            continue
        if len(proposed) > 10:
            flag(node_id, "medium", f"Node {node_id} has {len(proposed)} children; review grouping/presentation")
        node.status = "needs_decomposition"
        children[node_id] = proposed_ids
        for proposal in proposed:
            child = _from_proposal(proposal, node_id)
            components.append(child)
            by_id[child.id] = child
            depths[child.id] = depth + 1
            serial += 1
            heappush(queue, (-(child.priority_score or 0), serial, child.id))
        record(node_id, "expanded", f"Accepted {len(proposed)} proposed children", proposed_ids,
               {p.id: p.rationale for p in proposed})

    # The fixture may mention descendants which were not materialized when
    # execution hit its depth/node limits. Never silently drop these links.
    relations = []
    for relation in design.relationships:
        if relation.source_id in by_id and relation.target_id in by_id:
            relations.append(relation.model_copy(deep=True))
        else:
            flag(root.id, "high", f"Unmaterialized relationship {relation.id}: {relation.source_id} -> {relation.target_id}", requirement_ids=relation.requirement_ids)
            record(root.id, "unmaterialized_link", f"Relationship {relation.id} cannot be emitted")

    cases = []
    for case in design.verification_cases:
        if set(case.component_ids) <= by_id.keys():
            cases.append(case.model_copy(deep=True))
        else:
            flag(root.id, "high", f"Unmaterialized verification case {case.id}: {case.component_ids}", requirement_ids=case.requirement_ids)
            record(root.id, "unmaterialized_case", f"Verification case {case.id} cannot be emitted")

    for finding in list(findings):
        if not set(finding.component_ids) <= by_id.keys():
            findings.remove(finding)
            flag(root.id, "high", f"Unmaterialized fixture finding {finding.id}", requirement_ids=finding.requirement_ids)

    # Descendants appear after parents in components, allowing reverse
    # traversal to finalize statuses without an additional refinement round.
    for node in reversed(components):
        if node.status == "blocked":
            continue
        missing = _readiness_missing(node)
        unfinished_children = [cid for cid in children.get(node.id, ()) if by_id[cid].status != "ready"]
        if missing or unfinished_children:
            node.status = "requires_review"
            reasons = missing + ([f"children not ready: {unfinished_children}"] if unfinished_children else [])
            record(node.id, "requires_review", "; ".join(reasons))
            flag(node.id, "medium", f"Architecture component {node.id} requires review: {'; '.join(reasons)}", requirement_ids=node.requirement_ids)
        else:
            node.status = "ready"
            record(node.id, "ready", "Authored evidence and all child contracts satisfy the structural readiness gate")

    architecture = ArchitectureSpec(
        brief=brief.model_copy(deep=True),
        selected_style=design.selected_style or brief.constraints.preferred_architecture,
        components=components,
        relationships=relations,
        verification_cases=cases,
        decisions=[d.model_copy(deep=True) for d in design.decisions],
        findings=findings,
        status="draft",
    )
    coverage = architecture.coverage_report()
    if coverage.uncovered:
        flag(root.id, "high", f"Uncovered mandatory requirements: {coverage.uncovered}", requirement_ids=coverage.uncovered)
    if not architecture.selected_style:
        flag(root.id, "medium", "Architecture style requires review and an explicit decision")
    if coverage.uncovered or not architecture.selected_style or any(c.status != "ready" for c in components) or any(
        f.status == "open" and f.severity in {"high", "critical"} for f in findings
    ):
        architecture.status = "incomplete_requires_review"
    architecture.findings = findings
    # A valid generated draft is not equivalent to independently verified
    # architectural quality; this phase never sets validated_for_scope.
    ArchitectureSpec.model_validate(architecture.model_dump())
    record(root.id, "completed", f"Generated {architecture.status}; verified={len(coverage.verified)}, planned={len(coverage.planned_only)}, uncovered={len(coverage.uncovered)}")
    return GenerationResult(architecture=architecture, trace=tuple(events), processed_count=len(visited))