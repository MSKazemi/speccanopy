"""Phase 6: reference-case evaluation supporting multiple architectural alternatives.

These checks are explainable, requirement-linked *signals*, not semantic proof,
expert attestation verification, or a substitute for independent review.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import Field, HttpUrl, StringConstraints, model_validator
from typing import Annotated

from .models import ArchitectureSpec, Identifier, NonEmptyText, SchemaModel, SystemBrief
from .review import RelationshipKind, StyleId, _style_family

CriterionKind = Literal[
    "requirement_mapped", "verification_link", "quality_target",
    "failure_contract", "interface_contract", "typed_interaction",
    "single_data_owner",
]
CaseOrigin = Literal["synthetic_curated", "published_source", "contributed"]
CaseSplit = Literal["development", "public_holdout"]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def digest(value: object) -> str:
    """Content digest from canonical JSON for integrity comparisons (not signatures)."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResearchCriterion(SchemaModel):
    id: Identifier
    kind: CriterionKind
    description: NonEmptyText
    requirement_id: Identifier
    weight: int = Field(default=1, ge=1, le=5)
    required: bool = True
    relationship_kind: RelationshipKind | None = None
    direction: Literal["inbound", "outbound"] | None = None
    interface_kind: Literal["api", "event", "cli", "file", "function", "other"] | None = None
    data_label: NonEmptyText | None = None

    @model_validator(mode="after")
    def exact_fields(self) -> ResearchCriterion:
        supplied = {key for key in ("relationship_kind", "direction", "interface_kind", "data_label")
                    if getattr(self, key) is not None}
        expected = {
            "requirement_mapped": set(), "verification_link": set(),
            "quality_target": set(), "failure_contract": set(),
            "interface_contract": {"direction", "interface_kind"},
            "typed_interaction": {"relationship_kind"},
            "single_data_owner": {"data_label"},
        }[self.kind]
        if supplied != expected:
            raise ValueError(f"{self.kind} requires exactly {sorted(expected)} fields")
        return self


class AcceptableAlternative(SchemaModel):
    id: Identifier
    name: NonEmptyText
    rationale: NonEmptyText
    style_families: list[StyleId] = Field(min_length=1, max_length=5)
    criteria: list[ResearchCriterion] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_styles(self) -> AcceptableAlternative:
        if len(set(self.style_families)) != len(self.style_families):
            raise ValueError("Style families within an alternative must be unique")
        return self


class ReviewClaim(SchemaModel):
    """A self-declared review record, NOT verified identity or expertise."""

    reviewer: NonEmptyText
    expertise: NonEmptyText
    reviewed_on: date
    method: Literal["scenario_walkthrough", "tradeoff_review", "architecture_review"]
    report_url: HttpUrl
    subject_sha256: Sha256
    declares_independence: bool
    summary: NonEmptyText


class CaseProvenance(SchemaModel):
    origin: CaseOrigin
    curator: NonEmptyText
    source_url: HttpUrl | None = None
    usage_rights: NonEmptyText
    limitations: NonEmptyText
    review_claims: list[ReviewClaim] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def source_required_for_non_synthetic(self) -> CaseProvenance:
        if self.origin != "synthetic_curated" and self.source_url is None:
            raise ValueError("External/contributed case must cite its source_url")
        return self


class ResearchCase(SchemaModel):
    id: Identifier
    title: NonEmptyText
    split: CaseSplit
    brief: SystemBrief
    provenance: CaseProvenance
    common_criteria: list[ResearchCriterion] = Field(min_length=1, max_length=100)
    alternatives: list[AcceptableAlternative] = Field(min_length=1, max_length=12)

    def subject_digest(self) -> str:
        """Bind claims to the evaluated case, excluding review claims themselves."""
        raw = self.model_dump(mode="json")
        raw["provenance"]["review_claims"] = []
        return digest(raw)

    @model_validator(mode="after")
    def validate_references(self) -> ResearchCase:
        alternatives = [a.id for a in self.alternatives]
        if len(alternatives) != len(set(alternatives)):
            raise ValueError("Alternative IDs must be unique")
        criteria = self.common_criteria + [c for a in self.alternatives for c in a.criteria]
        ids = [c.id for c in criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("Research criterion IDs must be globally unique within a case")
        unknown = {c.requirement_id for c in criteria} - self.brief.requirement_ids()
        if unknown:
            raise ValueError(f"Unknown research requirement IDs: {sorted(unknown)}")
        quality_ids = {r.id for r in self.brief.quality_requirements}
        wrong = [c.id for c in criteria if c.kind == "quality_target" and c.requirement_id not in quality_ids]
        if wrong:
            raise ValueError(f"Quality target checks need quality requirement IDs: {wrong}")
        for claim in self.provenance.review_claims:
            if claim.subject_sha256 != self.subject_digest():
                raise ValueError("Review claim subject_sha256 does not match case content")
        return self


class ResearchCriterionResult(SchemaModel):
    id: Identifier
    kind: CriterionKind
    description: NonEmptyText
    weight: int
    required: bool
    present: bool
    reason: NonEmptyText


class AlternativeAssessment(SchemaModel):
    id: Identifier
    name: NonEmptyText
    style_status: Literal["matched", "mismatched", "unclassified"]
    permitted_styles: list[StyleId]
    score: float = Field(ge=0, le=100)
    all_required_present: bool
    missing_required: list[Identifier]
    results: list[ResearchCriterionResult]


class ResearchAssessment(SchemaModel):
    case_id: Identifier
    case_title: NonEmptyText
    split: CaseSplit
    origin: CaseOrigin
    review_status: Literal["curated_unreviewed", "self_declared_claims_unverified"]
    review_claim_count: int
    case_subject_sha256: Sha256
    candidate_sha256: Sha256
    selected_style: str | None
    detected_style_family: StyleId | None
    common_score: float = Field(ge=0, le=100)
    common_results: list[ResearchCriterionResult]
    alternatives: list[AlternativeAssessment]
    best_path: Identifier | None
    result: Literal["criteria_present_review_required", "criteria_gaps", "no_compatible_style"]
    uncovered_mandatory: list[str]
    pending_verification: list[str]
    open_high_or_critical_findings: list[str]
    caveat: NonEmptyText = (
        "Requirement-linked structural/documentation signals only. A full score does NOT "
        "verify semantic correctness, independent expert review, security or deployability. "
        "Reviews listed here, if any, are self-declared and NOT authenticated."
    )


def _criterion(spec: ArchitectureSpec, item: ResearchCriterion) -> ResearchCriterionResult:
    requirement_id = item.requirement_id
    # A system-root's blanket requirement list is not sufficient ownership in a
    # multi-component design: require a concrete non-root responsibility link.
    owners = [c for c in spec.components if requirement_id in c.requirement_ids
              and (c.parent_id is not None or len(spec.components) == 1)]
    kind = item.kind
    if kind == "requirement_mapped":
        present = bool(owners)
        reason = "Requirement is linked to an architecture component" if present else "No responsible component link"
    elif kind == "verification_link":
        coverage = spec.coverage_report()
        # For optional requirements, check linked cases manually; coverage_report covers mandatory only.
        present = any(requirement_id in case.requirement_ids and any(
            c.id in case.component_ids for c in owners) for case in spec.verification_cases)
        if present and requirement_id in coverage.verified:
            reason = "Linked design verification case with authored evidence (not externally verified)"
        else:
            reason = "Linked design verification case (may be planned only)" if present else "No requirement-linked verification case"
    elif kind == "quality_target":
        present = any(requirement_id in c.quality_targets for c in owners)
        reason = "Responsible component has an authored quality target" if present else "No quality target on a responsible component"
    elif kind == "failure_contract":
        present = any(interface.failure_behavior for c in owners for interface in c.interfaces)
        reason = "At least one responsible interface describes failure behavior" if present else "No failure behavior on a responsible interface"
    elif kind == "interface_contract":
        present = any(i.direction == item.direction and i.kind == item.interface_kind
                      for c in owners for i in c.interfaces)
        reason = "Matching directional interface exists on a requirement owner" if present else "Missing directional interface for requirement"
    elif kind == "typed_interaction":
        owner_ids = {c.id for c in owners}
        present = any(r.kind == item.relationship_kind and requirement_id in r.requirement_ids
                      and (r.source_id in owner_ids or r.target_id in owner_ids)
                      for r in spec.relationships)
        reason = "Matching typed relationship traces to requirement" if present else "No matching typed relationship traced to requirement"
    elif kind == "single_data_owner":
        normalized = " ".join(item.data_label.casefold().split())
        holders = [c.id for c in spec.components if any(
            " ".join(label.casefold().split()) == normalized for label in c.owned_data)]
        present = len(holders) == 1 and holders[0] in {c.id for c in owners}
        reason = (f"Matching data owners: {', '.join(holders) or 'none'}; require one responsible owner")
    else:
        raise ValueError(f"Unsupported criterion type: {kind}")
    return ResearchCriterionResult(
        id=item.id, kind=item.kind, description=item.description, weight=item.weight,
        required=item.required, present=bool(present), reason=reason,
    )


def _score(items: list[ResearchCriterionResult]) -> float:
    return round(100 * sum(c.weight for c in items if c.present) / sum(c.weight for c in items), 2)


def evaluate_case(case: ResearchCase, spec: ArchitectureSpec) -> ResearchAssessment:
    """Match against the strongest *compatible* alternative, not exact node IDs."""
    if case.brief.model_dump(mode="json") != spec.brief.model_dump(mode="json"):
        raise ValueError("Research case and architecture must have the same original SystemBrief")
    style = _style_family(spec.selected_style)
    common = [_criterion(spec, c) for c in case.common_criteria]
    paths: list[AlternativeAssessment] = []
    for alt in case.alternatives:
        if style is None:
            state: Literal["matched", "mismatched", "unclassified"] = "unclassified"
        elif style in alt.style_families:
            state = "matched"
        else:
            state = "mismatched"
        items = [_criterion(spec, c) for c in alt.criteria]
        missing = [c.id for c in items if c.required and not c.present]
        paths.append(AlternativeAssessment(
            id=alt.id, name=alt.name, style_status=state,
            permitted_styles=alt.style_families, score=_score(items),
            all_required_present=not missing, missing_required=missing, results=items,
        ))
    compatible = [p for p in paths if p.style_status == "matched"]
    # Expose a diagnostic path if no compatible style, but NEVER count it as passing.
    ranked = sorted(compatible or paths, key=lambda p: (not p.all_required_present, -p.score, p.id))
    best = ranked[0]
    coverage = spec.coverage_report()
    risks = sorted(f.id for f in spec.findings
                   if f.status == "open" and f.severity in {"critical", "high"})
    common_ok = all(c.present for c in common if c.required)
    if not compatible:
        result = "no_compatible_style"
    elif common_ok and best.all_required_present and not coverage.uncovered and not risks:
        result = "criteria_present_review_required"
    else:
        result = "criteria_gaps"
    return ResearchAssessment(
        case_id=case.id, case_title=case.title, split=case.split, origin=case.provenance.origin,
        review_status="self_declared_claims_unverified" if case.provenance.review_claims else "curated_unreviewed",
        review_claim_count=len(case.provenance.review_claims),
        case_subject_sha256=case.subject_digest(), candidate_sha256=digest(spec),
        selected_style=spec.selected_style, detected_style_family=style,
        common_score=_score(common), common_results=common,
        alternatives=paths, best_path=best.id,
        result=result, uncovered_mandatory=coverage.uncovered,
        pending_verification=coverage.planned_only, open_high_or_critical_findings=risks,
    )


class SuiteEntry(SchemaModel):
    id: Identifier
    case_path: NonEmptyText
    architecture_path: NonEmptyText


class ResearchSuite(SchemaModel):
    name: NonEmptyText
    entries: list[SuiteEntry] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_entries(self) -> ResearchSuite:
        ids = [x.id for x in self.entries]
        if len(set(ids)) != len(ids):
            raise ValueError("Suite entry IDs must be unique")
        return self


class SplitSummary(SchemaModel):
    split: CaseSplit
    count: int
    criteria_present_review_required: int
    criteria_gaps: int
    no_compatible_style: int
    average_common_criterion_coverage: float | None = None


class SuiteAssessment(SchemaModel):
    suite_name: NonEmptyText
    cases: dict[str, ResearchAssessment]
    by_split: list[SplitSummary]
    total: int
    caveat: NonEmptyText = (
        "Public synthetic fixtures are not an independent holdout or professional review set. "
        "Aggregate counts are diagnostic, not architecture correctness rates."
    )


def summarize_suite(name: str, results: dict[str, ResearchAssessment]) -> SuiteAssessment:
    summaries = []
    for split in ("development", "public_holdout"):
        group = [x for x in results.values() if x.split == split]
        summaries.append(SplitSummary(
            split=split, count=len(group),
            criteria_present_review_required=sum(x.result == "criteria_present_review_required" for x in group),
            criteria_gaps=sum(x.result == "criteria_gaps" for x in group),
            no_compatible_style=sum(x.result == "no_compatible_style" for x in group),
            average_common_criterion_coverage=round(sum(x.common_score for x in group) / len(group), 2) if group else None,
        ))
    return SuiteAssessment(suite_name=name, cases=results, by_split=summaries, total=len(results))
