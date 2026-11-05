"""Human-authored, finding-bound architectural refinements with bounded simulation.

Planning NEVER approves a design. Applying requires explicit human acknowledgement,
revalidates source/config/plan hashes, preserves mandatory coverage and invalidates
stale evidence affected by edits. Neither step can assert architectural correctness.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from .ai import sha256_json
from .models import (
    ArchitectureSpec, Component, Identifier, InterfaceContract, NonEmptyText,
    Relationship, SchemaModel, VerificationCase,
)
from .review import ArchitectureReview, ReviewConfig, ReviewFinding, assess_architecture

PatchKind = Literal[
    "add_interface", "add_relationship", "set_quality_target",
    "remove_duplicate_data_owner", "add_requirement_link", "add_verification_plan",
]

_PATCH_FIELDS: dict[str, set[str]] = {
    "add_interface": {"component_id", "interface"},
    "add_relationship": {"relationship"},
    "set_quality_target": {"component_id", "requirement_id", "target_text"},
    "remove_duplicate_data_owner": {"component_id", "data_name"},
    "add_requirement_link": {"component_id", "requirement_id"},
    "add_verification_plan": {"verification_case"},
}


class RefinementPatch(SchemaModel):
    id: Identifier
    round: int = Field(ge=1, le=100)
    finding_id: Identifier
    finding_category: NonEmptyText
    kind: PatchKind
    rationale: NonEmptyText
    component_id: Identifier | None = None
    requirement_id: Identifier | None = None
    interface: InterfaceContract | None = None
    relationship: Relationship | None = None
    target_text: NonEmptyText | None = None
    data_name: NonEmptyText | None = None
    verification_case: VerificationCase | None = None

    @model_validator(mode="after")
    def exact_payload(self) -> RefinementPatch:
        fields = {
            "component_id", "requirement_id", "interface", "relationship",
            "target_text", "data_name", "verification_case",
        }
        active = {name for name in fields if getattr(self, name) is not None}
        expected = _PATCH_FIELDS[self.kind]
        if active != expected:
            raise ValueError(f"{self.kind} requires exactly {sorted(expected)}; supplied {sorted(active)}")
        if self.kind == "add_verification_plan":
            if self.verification_case.status != "planned" or self.verification_case.evidence:
                raise ValueError("Refinement cannot add verified evidence; verification must remain planned")
        return self


class RefinementEdits(SchemaModel):
    author: NonEmptyText
    patches: list[RefinementPatch] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def valid_order(self) -> RefinementEdits:
        ids = [p.id for p in self.patches]
        if len(ids) != len(set(ids)):
            raise ValueError("Patch IDs must be unique")
        rounds = sorted({p.round for p in self.patches})
        if rounds != list(range(1, len(rounds) + 1)):
            raise ValueError("Refinement rounds must start at one and be contiguous")
        return self


class RefinementRound(SchemaModel):
    round: int
    patch_ids: list[Identifier]
    before_counts: dict[str, int]
    after_counts: dict[str, int]
    before_high_or_critical: int
    after_high_or_critical: int
    invalidated_verification_cases: list[Identifier]
    unresolved_categories: list[str]


class RefinementPlan(SchemaModel):
    version: Literal[1] = 1
    status: Literal["pending_human_review"] = "pending_human_review"
    source_sha256: NonEmptyText
    config_sha256: NonEmptyText
    candidate_sha256: NonEmptyText
    edits: RefinementEdits
    rounds: list[RefinementRound]
    caveat: NonEmptyText = (
        "This is a human-authored design change proposal. Preview and approval do not prove "
        "architectural correctness or verify quality scenarios; domain review remains required."
    )


class RefinementReceipt(SchemaModel):
    status: Literal["acknowledged_for_architecture_review"] = "acknowledged_for_architecture_review"
    reviewer: NonEmptyText
    plan_sha256: NonEmptyText
    source_sha256: NonEmptyText
    config_sha256: NonEmptyText
    candidate_sha256: NonEmptyText
    rounds_applied: int = Field(ge=1)
    caveat: NonEmptyText = (
        "Reviewer identifier is self-declared, not authenticated. Approval permits further "
        "architecture review; it is not an architectural signoff or verified evidence."
    )


def _review_counts(review: ArchitectureReview) -> dict[str, int]:
    return dict(sorted(Counter(x.category for x in review.quality_review.findings).items()))


def _severe_count(review: ArchitectureReview) -> int:
    return sum(f.severity in {"critical", "high"} for f in review.quality_review.findings)


def _severe_signatures(review: ArchitectureReview) -> set[tuple[object, ...]]:
    """Independent of generated finding numbers; catch newly introduced high risks."""
    return {
        (f.category, f.severity, f.description, tuple(f.requirement_ids), tuple(f.component_ids))
        for f in review.quality_review.findings if f.severity in {"critical", "high"}
    }


def _related(patch: RefinementPatch) -> tuple[set[str], set[str]]:
    components = {patch.component_id} if patch.component_id else set()
    requirements = {patch.requirement_id} if patch.requirement_id else set()
    if patch.relationship:
        components |= {patch.relationship.source_id, patch.relationship.target_id}
        requirements.update(patch.relationship.requirement_ids)
    if patch.verification_case:
        components.update(patch.verification_case.component_ids)
        requirements.update(patch.verification_case.requirement_ids)
    return components, requirements


def _check_finding(patch: RefinementPatch, review: ArchitectureReview) -> None:
    finding = next((f for f in review.quality_review.findings if f.id == patch.finding_id), None)
    if not finding or finding.category != patch.finding_category:
        raise ValueError(f"Patch {patch.id} must cite a current, matching review finding")
    comps, reqs = _related(patch)
    if finding.component_ids and not set(finding.component_ids).intersection(comps):
        raise ValueError(f"Patch {patch.id} does not touch the finding's components")
    if finding.requirement_ids and reqs and not set(finding.requirement_ids).intersection(reqs):
        raise ValueError(f"Patch {patch.id} does not address the finding's requirements")
    allowed: dict[str, set[str]] = {
        "add_interface": {"interaction_contract", "scenario_design"},
        "add_relationship": {"scenario_design"},
        "set_quality_target": {"quality_target", "scenario_design"},
        "remove_duplicate_data_owner": {"data_ownership"},
        "add_requirement_link": {"requirement_coverage", "quality_ownership", "scenario_design"},
        "add_verification_plan": {"requirement_coverage", "verification_pending", "scenario_evidence"},
    }
    if patch.finding_category not in allowed[patch.kind]:
        raise ValueError(f"Patch {patch.id} action {patch.kind} cannot address {patch.finding_category}")


def _apply_patch(spec: ArchitectureSpec, patch: RefinementPatch) -> set[str]:
    by_id = {component.id: component for component in spec.components}
    affected: set[str] = set()
    if patch.kind == "add_interface":
        if patch.component_id not in by_id:
            raise ValueError(f"Unknown component {patch.component_id}")
        c = by_id[patch.component_id]
        if c.interfaces_not_applicable_reason:
            raise ValueError(f"Component {c.id} explicitly states interfaces are not applicable")
        if any(x.name == patch.interface.name and x.direction == patch.interface.direction for x in c.interfaces):
            raise ValueError("Duplicate interface name and direction")
        c.interfaces.append(patch.interface)
        affected.add(c.id)
    elif patch.kind == "add_relationship":
        edge = patch.relationship
        if edge.source_id not in by_id or edge.target_id not in by_id:
            raise ValueError("New relationship references unknown component")
        if edge.source_id == edge.target_id:
            raise ValueError("Self-relationship is forbidden")
        if any(x.id == edge.id for x in spec.relationships):
            raise ValueError("Duplicate relationship ID")
        if any((x.source_id, x.target_id, x.kind) == (edge.source_id, edge.target_id, edge.kind)
               for x in spec.relationships):
            raise ValueError("Equivalent typed relationship already exists")
        spec.relationships.append(edge)
        affected.update((edge.source_id, edge.target_id))
    elif patch.kind == "set_quality_target":
        if patch.component_id not in by_id:
            raise ValueError("Unknown component")
        comp = by_id[patch.component_id]
        if patch.requirement_id not in {q.id for q in spec.brief.quality_requirements}:
            raise ValueError("Quality target must reference a quality requirement")
        if patch.requirement_id not in comp.requirement_ids:
            raise ValueError("Component must own the quality requirement before setting its target")
        if patch.requirement_id in comp.quality_targets:
            raise ValueError("Cannot silently overwrite an existing quality target")
        comp.quality_targets[patch.requirement_id] = patch.target_text
        affected.add(comp.id)
    elif patch.kind == "remove_duplicate_data_owner":
        if patch.component_id not in by_id:
            raise ValueError("Unknown component")
        comp = by_id[patch.component_id]
        matches = [datum for datum in comp.owned_data if datum.strip().casefold() == patch.data_name.strip().casefold()]
        if len(matches) != 1:
            raise ValueError("Duplicate owner removal requires one exact owned data item")
        peer_owners = [other for other in spec.components if other.id != comp.id
                       and other.parent_id == comp.parent_id and any(
                           data.strip().casefold() == patch.data_name.strip().casefold()
                           for data in other.owned_data)]
        if len(peer_owners) != 1:
            raise ValueError("Specify only a true sibling ownership conflict with exactly one remaining owner")
        comp.owned_data.remove(matches[0])
        if not comp.owned_data:
            comp.data_not_applicable_reason = (
                f"Canonical owner: {peer_owners[0].id}; no local ownership of {matches[0]}"
            )
        affected.add(comp.id)
    elif patch.kind == "add_requirement_link":
        if patch.component_id not in by_id:
            raise ValueError("Unknown component")
        if patch.requirement_id not in spec.brief.requirement_ids():
            raise ValueError("Unknown requirement")
        comp = by_id[patch.component_id]
        if patch.requirement_id in comp.requirement_ids:
            raise ValueError("Requirement is already linked to this component")
        comp.requirement_ids.append(patch.requirement_id)
        affected.add(comp.id)
    elif patch.kind == "add_verification_plan":
        case = patch.verification_case
        if case.status != "planned" or case.evidence:
            raise ValueError("Cannot invent or add verified evidence")
        ids = {c.id for c in spec.components}
        if set(case.component_ids) - ids or set(case.requirement_ids) - spec.brief.requirement_ids():
            raise ValueError("Verification plan references unknown items")
        for rid in case.requirement_ids:
            if not any(rid in by_id[cid].requirement_ids for cid in case.component_ids):
                raise ValueError("Verification plan must link a responsible component")
        if any(x.id == case.id for x in spec.verification_cases):
            raise ValueError("Duplicate verification case ID")
        spec.verification_cases.append(case)
        affected.update(case.component_ids)
    else:
        raise ValueError(f"Unsupported operation {patch.kind}")
    return affected


def _invalidate(spec: ArchitectureSpec, affected: set[str]) -> list[str]:
    """Reopen changed components and ancestors; invalidate stale verified case evidence."""
    by_id = {c.id: c for c in spec.components}
    closure = set(affected)
    for component_id in tuple(affected):
        parent = by_id[component_id].parent_id
        while parent is not None:
            closure.add(parent)
            parent = by_id[parent].parent_id
    for component_id in closure:
        c = by_id[component_id]
        c.status = "requires_review"
        c.validation_evidence = []
        c.stop_reason = None
    invalidated: list[str] = []
    for case in spec.verification_cases:
        if case.status == "verified" and set(case.component_ids).intersection(closure):
            invalidated.append(case.id)
            case.status = "planned"
            case.evidence = None
    spec.status = "incomplete_requires_review"
    return sorted(invalidated)


def simulate_refinement(spec: ArchitectureSpec, config: ReviewConfig, edits: RefinementEdits) -> tuple[ArchitectureSpec, list[RefinementRound]]:
    """Pure simulation; refuses growing high/critical risks or lost required coverage."""
    candidate = spec.model_copy(deep=True)
    rounds = sorted({p.round for p in edits.patches})
    if len(rounds) > spec.brief.constraints.max_refinement_rounds:
        raise ValueError("Refinement exceeds brief max_refinement_rounds")
    if rounds != list(range(1, len(rounds) + 1)):
        raise ValueError("Refinement rounds must be contiguous")
    summaries: list[RefinementRound] = []
    for round_num in rounds:
        current = assess_architecture(candidate, config)
        selected = [patch for patch in edits.patches if patch.round == round_num]
        for patch in selected:
            _check_finding(patch, current)
        affected: set[str] = set()
        for patch in selected:
            affected.update(_apply_patch(candidate, patch))
        invalidated = _invalidate(candidate, affected)
        # Re-parse the complete model: assignment validation cannot check cross-object references.
        candidate = ArchitectureSpec.model_validate(candidate.model_dump(mode="json"))
        new_review = assess_architecture(candidate, config)
        old_uncovered = set(current.quality_review.coverage.uncovered)
        if set(new_review.quality_review.coverage.uncovered) - old_uncovered:
            raise ValueError("Refinement would create new uncovered mandatory requirements")
        if _severe_signatures(new_review) - _severe_signatures(current):
            raise ValueError("Refinement would introduce new high/critical review findings")
        summaries.append(RefinementRound(
            round=round_num, patch_ids=[p.id for p in selected],
            before_counts=_review_counts(current), after_counts=_review_counts(new_review),
            before_high_or_critical=_severe_count(current),
            after_high_or_critical=_severe_count(new_review),
            invalidated_verification_cases=invalidated,
            unresolved_categories=sorted({f.category for f in new_review.quality_review.findings}),
        ))
    return candidate, summaries


def plan_refinement(spec: ArchitectureSpec, config: ReviewConfig, edits: RefinementEdits) -> tuple[RefinementPlan, ArchitectureSpec]:
    candidate, summaries = simulate_refinement(spec, config, edits)
    plan = RefinementPlan(
        source_sha256=sha256_json(spec.model_dump(mode="json")),
        config_sha256=sha256_json(config.model_dump(mode="json")),
        candidate_sha256=sha256_json(candidate.model_dump(mode="json")),
        edits=edits, rounds=summaries,
    )
    return plan, candidate


def apply_refinement(spec: ArchitectureSpec, config: ReviewConfig, plan: RefinementPlan,
                     *, reviewer: str, acknowledge_review: bool) -> tuple[ArchitectureSpec, RefinementReceipt]:
    if not acknowledge_review:
        raise ValueError("Explicit --acknowledge-review is required")
    if not reviewer.strip():
        raise ValueError("A reviewer identifier is required")
    if plan.source_sha256 != sha256_json(spec.model_dump(mode="json")):
        raise ValueError("Source architecture changed after refinement planning")
    if plan.config_sha256 != sha256_json(config.model_dump(mode="json")):
        raise ValueError("Review configuration changed after refinement planning")
    candidate, rounds = simulate_refinement(spec, config, plan.edits)
    if candidate.status != "incomplete_requires_review":
        raise ValueError("Refined architecture may not assert validated_for_scope")
    if sha256_json(candidate.model_dump(mode="json")) != plan.candidate_sha256 or rounds != plan.rounds:
        raise ValueError("Refinement plan preview no longer matches deterministic simulation")
    receipt = RefinementReceipt(
        reviewer=reviewer.strip(), plan_sha256=sha256_json(plan.model_dump(mode="json")),
        source_sha256=plan.source_sha256, config_sha256=plan.config_sha256,
        candidate_sha256=plan.candidate_sha256, rounds_applied=len(rounds),
    )
    return candidate, receipt
