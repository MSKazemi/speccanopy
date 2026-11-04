"""Auditable, deterministic architecture-style comparison and design quality review.

This is a *review aid*, not a verifier of architectural correctness. Only
explicitly supplied drivers and scenarios influence style scoring. Independent
quality rules inspect the structural draft; they do not run application code.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field, model_validator

from .models import (
    ArchitectureSpec,
    CoverageReport,
    Identifier,
    NonEmptyText,
    SchemaModel,
)

StyleId = Literal["single_process", "modular_monolith", "microservices", "event_driven", "serverless"]
DriverId = Literal[
    "operational_simplicity", "independent_deployment", "elastic_scaling",
    "strong_consistency", "asynchronous_workflows", "fault_isolation", "modular_boundaries",
]
RelationshipKind = Literal[
    "dependency", "synchronous_call", "event", "data_flow", "shared_resource",
    "trust_boundary", "deployment", "other",
]
ReviewStatus = Literal["design_gap", "verification_pending", "evidence_documented"]

# Engineering heuristics on a 1-5 scale; not measured performance data.
# Greater numbers indicate a stronger *fit for that particular priority*.
STYLE_PROFILES: dict[str, dict[str, int]] = {
    "single_process": {
        "operational_simplicity": 5, "independent_deployment": 1,
        "elastic_scaling": 1, "strong_consistency": 5,
        "asynchronous_workflows": 1, "fault_isolation": 1, "modular_boundaries": 2,
    },
    "modular_monolith": {
        "operational_simplicity": 4, "independent_deployment": 1,
        "elastic_scaling": 2, "strong_consistency": 5,
        "asynchronous_workflows": 3, "fault_isolation": 2, "modular_boundaries": 5,
    },
    "microservices": {
        "operational_simplicity": 1, "independent_deployment": 5,
        "elastic_scaling": 5, "strong_consistency": 2,
        "asynchronous_workflows": 4, "fault_isolation": 5, "modular_boundaries": 5,
    },
    "event_driven": {
        "operational_simplicity": 2, "independent_deployment": 3,
        "elastic_scaling": 4, "strong_consistency": 2,
        "asynchronous_workflows": 5, "fault_isolation": 4, "modular_boundaries": 4,
    },
    "serverless": {
        "operational_simplicity": 3, "independent_deployment": 4,
        "elastic_scaling": 5, "strong_consistency": 2,
        "asynchronous_workflows": 4, "fault_isolation": 4, "modular_boundaries": 3,
    },
}
STYLE_TRADEOFFS: dict[str, str] = {
    "single_process": "Minimal operational overhead, but one deployment unit and limited independent scaling.",
    "modular_monolith": "Clear internal boundaries and simple transactions, but modules share a deployment lifecycle.",
    "microservices": "Service-level deployment and scaling at the cost of distributed coordination, observability and consistency.",
    "event_driven": "Loose asynchronous coupling and buffering, but ordering, replay and delivery semantics need explicit design.",
    "serverless": "Managed execution and elastic capacity, but platform limits, cold starts and state handling require review.",
}


class StyleDriver(SchemaModel):
    key: DriverId
    importance: int = Field(ge=1, le=5)
    desired: int = Field(ge=1, le=5)
    rationale: NonEmptyText


class ExpectedInteraction(SchemaModel):
    source_id: Identifier
    target_id: Identifier
    kind: RelationshipKind


class QualityScenario(SchemaModel):
    id: Identifier
    requirement_id: Identifier
    stimulus: NonEmptyText
    expected_response: NonEmptyText
    measure: NonEmptyText
    component_ids: list[Identifier] = Field(min_length=1)
    expected_interactions: list[ExpectedInteraction] = Field(default_factory=list)

    @model_validator(mode="after")
    def scenario_ids_unique(self) -> QualityScenario:
        if len(self.component_ids) != len(set(self.component_ids)):
            raise ValueError("Quality scenario component_ids must be unique")
        return self


class ReviewConfig(SchemaModel):
    drivers: list[StyleDriver] = Field(default_factory=list)
    candidates: list[StyleId] = Field(default_factory=lambda: list(STYLE_PROFILES))
    scenarios: list[QualityScenario] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_duplicates(self) -> ReviewConfig:
        for label, values in (
            ("driver", [x.key for x in self.drivers]),
            ("candidate", self.candidates),
            ("scenario", [x.id for x in self.scenarios]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {label} in review configuration")
        if len(self.candidates) < 2:
            raise ValueError("At least two style candidates required for comparison")
        return self


class DriverFit(SchemaModel):
    key: DriverId
    importance: int
    desired: int
    profile_fit: int
    compatibility: float = Field(ge=0, le=10)
    explanation: NonEmptyText


class StyleCandidate(SchemaModel):
    style: StyleId
    score: float | None = Field(default=None, ge=0, le=10)
    driver_fits: list[DriverFit] = Field(default_factory=list)
    tradeoff: NonEmptyText


class StyleComparison(SchemaModel):
    status: Literal["recommendation", "ambiguous", "insufficient_drivers"]
    recommendation: StyleId | None = None
    declared_style: str | None = None
    declared_style_family: StyleId | None = None
    candidates: list[StyleCandidate]
    reason: NonEmptyText
    methodology: NonEmptyText = (
        "Heuristic 1-5 profiles and user-authored drivers; scores are not measured benchmarks "
        "and do not constitute proof of architectural fitness. Orthogonal patterns may be combined."
    )


class ReviewFinding(SchemaModel):
    id: Identifier
    severity: Literal["critical", "high", "medium", "low"]
    category: NonEmptyText
    description: NonEmptyText
    recommendation: NonEmptyText
    requirement_ids: list[Identifier] = Field(default_factory=list)
    component_ids: list[Identifier] = Field(default_factory=list)


class ScenarioAssessment(SchemaModel):
    scenario_id: Identifier
    requirement_id: Identifier
    status: ReviewStatus
    missing_design_elements: list[str] = Field(default_factory=list)
    verification_status: Literal["verified_evidence_authored", "planned_only", "missing"]
    description: NonEmptyText


class QualityReview(SchemaModel):
    status: Literal["requires_review", "evidence_documented"]
    coverage: CoverageReport
    scenario_assessments: list[ScenarioAssessment]
    findings: list[ReviewFinding]
    source_findings: list[str]
    caveat: NonEmptyText = (
        "Independent deterministic checks assess documentation/traceability only; authored "
        "evidence and scenarios require expert scrutiny. No application implementation was tested."
    )


class ArchitectureReview(SchemaModel):
    system: NonEmptyText
    source_architecture_status: str
    overall_status: Literal["requires_review", "candidate_for_human_review"]
    style_comparison: StyleComparison
    quality_review: QualityReview
    provenance: NonEmptyText = (
        "Heuristic style profiles plus explicit reviewer drivers/scenarios. "
        "No LLM inference, production-code generation, or independent expert signoff."
    )


def _style_family(text: str | None) -> StyleId | None:
    if not text:
        return None
    t = text.lower().replace("-", " ").replace("_", " ")
    if "event driven" in t:
        return "event_driven"
    if "microservice" in t:
        return "microservices"
    if "serverless" in t:
        return "serverless"
    if "modular monolith" in t:
        return "modular_monolith"
    if "single process" in t or "cli" in t:
        return "single_process"
    return None


def compare_styles(spec: ArchitectureSpec, config: ReviewConfig) -> StyleComparison:
    """Compare styles using *only explicit* constraints, never guessed scale/team size."""
    candidates: list[StyleCandidate] = []
    for style in config.candidates:
        fits: list[DriverFit] = []
        for driver in config.drivers:
            profile = STYLE_PROFILES[style][driver.key]
            value = round((5 - abs(profile - driver.desired)) * 2, 2)
            fits.append(DriverFit(
                key=driver.key, importance=driver.importance, desired=driver.desired,
                profile_fit=profile, compatibility=value,
                explanation=f"{driver.rationale}; requested {driver.desired}/5, heuristic style fit {profile}/5",
            ))
        total = sum(f.compatibility * f.importance for f in fits)
        weight = sum(f.importance for f in fits)
        candidates.append(StyleCandidate(
            style=style, score=round(total / weight, 2) if weight else None,
            driver_fits=fits, tradeoff=STYLE_TRADEOFFS[style],
        ))
    family = _style_family(spec.selected_style)
    if not config.drivers:
        return StyleComparison(
            status="insufficient_drivers", declared_style=spec.selected_style,
            declared_style_family=family, candidates=candidates,
            reason="No explicit design drivers provided; abstaining from an architecture-style recommendation.",
        )
    candidates.sort(key=lambda x: (-float(x.score), x.style))
    if candidates[0].score - candidates[1].score < 0.5:
        return StyleComparison(
            status="ambiguous", declared_style=spec.selected_style,
            declared_style_family=family, candidates=candidates,
            reason="Top scores are within 0.5 points; a human must resolve the trade-off or add drivers.",
        )
    return StyleComparison(
        status="recommendation", recommendation=candidates[0].style,
        declared_style=spec.selected_style, declared_style_family=family, candidates=candidates,
        reason="Highest weighted fit to explicitly supplied drivers; recommendation is advisory only.",
    )


def _validate_config_refs(spec: ArchitectureSpec, config: ReviewConfig) -> None:
    components = {c.id for c in spec.components}
    qids = {q.id for q in spec.brief.quality_requirements}
    for scenario in config.scenarios:
        if scenario.requirement_id not in qids:
            raise ValueError(f"Scenario {scenario.id} must reference an existing quality requirement")
        unknown = set(scenario.component_ids) - components
        if unknown:
            raise ValueError(f"Scenario {scenario.id} references unknown components: {sorted(unknown)}")
        for edge in scenario.expected_interactions:
            if edge.source_id not in components or edge.target_id not in components:
                raise ValueError(f"Scenario {scenario.id} interaction references unknown components")
            if edge.source_id == edge.target_id:
                raise ValueError(f"Scenario {scenario.id} interaction must connect two components")


def review_quality(spec: ArchitectureSpec, config: ReviewConfig) -> QualityReview:
    """Run cross-cutting design/documentation checks without fabricating evidence."""
    _validate_config_refs(spec, config)
    components = {c.id: c for c in spec.components}
    coverage = spec.coverage_report()
    findings: list[ReviewFinding] = []
    assessments: list[ScenarioAssessment] = []

    def finding(category: str, severity: Literal["critical", "high", "medium", "low"],
                description: str, recommendation: str, *, reqs: list[str] | None = None,
                comps: list[str] | None = None) -> None:
        findings.append(ReviewFinding(
            id=f"REVIEW-{len(findings)+1:03d}", severity=severity,
            category=category, description=description, recommendation=recommendation,
            requirement_ids=reqs or [], component_ids=comps or [],
        ))

    if coverage.uncovered:
        finding("requirement_coverage", "high", f"Mandatory requirements lack verification links: {coverage.uncovered}",
                "Assign responsible components and write architecture verification cases.", reqs=coverage.uncovered)
    if coverage.planned_only:
        finding("verification_pending", "medium", f"Verification is planned but not evidenced for: {coverage.planned_only}",
                "Review the architecture and record credible, requirement-linked evidence.", reqs=coverage.planned_only)

    if not spec.selected_style:
        finding("style_decision", "medium", "The architecture lacks a recorded style choice.",
                "Document the chosen style, trade-offs and boundaries in an architecture decision record.")
    for existing in spec.findings:
        if existing.status == "open" and existing.severity in {"critical", "high"}:
            finding("source_architecture_risk", existing.severity,
                    f"Unresolved source finding {existing.id}: {existing.description}",
                    "Resolve, explicitly accept with rationale, or revise the affected design.",
                    reqs=existing.requirement_ids, comps=existing.component_ids)

    for q in spec.brief.quality_requirements:
        if not q.mandatory:
            continue
        owners = [c for c in spec.components if q.id in c.requirement_ids]
        target_owners = [c for c in owners if q.id in c.quality_targets]
        if not owners:
            finding("quality_ownership", "high", f"No component owns mandatory quality requirement {q.id}.",
                    "Assign an owner and its quality responsibilities.", reqs=[q.id])
        if not target_owners:
            finding("quality_target", "high", f"Mandatory quality requirement {q.id} lacks a stated quality target.",
                    "State measurable or reviewable quality criteria on its responsible component.", reqs=[q.id], comps=[c.id for c in owners])
        if not any(s.requirement_id == q.id for s in config.scenarios):
            finding("quality_scenario", "medium", f"Mandatory quality requirement {q.id} lacks an explicit evaluation scenario.",
                    "Add a stimulus, expected response, measurable criterion and focus components.", reqs=[q.id])

    edges = {(e.source_id, e.target_id, e.kind) for e in spec.relationships}
    for s in config.scenarios:
        issues: list[str] = []
        focus = [components[c] for c in s.component_ids]
        if not any(s.requirement_id in c.requirement_ids for c in focus):
            issues.append("Focus components do not claim this quality requirement")
        if not any(s.requirement_id in c.quality_targets for c in focus):
            issues.append("No focused component states a target for this quality requirement")
        for edge in s.expected_interactions:
            if (edge.source_id, edge.target_id, edge.kind) not in edges:
                issues.append(f"Missing expected {edge.kind} from {edge.source_id} to {edge.target_id}")
            elif not any(e.source_id == edge.source_id and e.target_id == edge.target_id
                         and e.kind == edge.kind and s.requirement_id in e.requirement_ids
                         for e in spec.relationships):
                issues.append(f"Interaction {edge.source_id} -> {edge.target_id} does not trace to {s.requirement_id}")
        evidence = [case for case in spec.verification_cases
                    if s.requirement_id in case.requirement_ids
                    and set(case.component_ids).intersection(s.component_ids)]
        vstatus: Literal["verified_evidence_authored", "planned_only", "missing"] = "missing"
        if any(case.status == "verified" and case.evidence for case in evidence):
            vstatus = "verified_evidence_authored"
        elif evidence:
            vstatus = "planned_only"
        status: ReviewStatus = "design_gap" if issues else (
            "evidence_documented" if vstatus == "verified_evidence_authored" else "verification_pending"
        )
        assessments.append(ScenarioAssessment(
            scenario_id=s.id, requirement_id=s.requirement_id,
            status=status, missing_design_elements=issues, verification_status=vstatus,
            description=f"Scenario response: {s.expected_response}; acceptance measure: {s.measure}",
        ))
        if issues:
            finding("scenario_design", "high", f"Scenario {s.id}: {'; '.join(issues)}",
                    "Correct the component/quality target/interaction design before review.",
                    reqs=[s.requirement_id], comps=s.component_ids)
        if vstatus != "verified_evidence_authored":
            finding("scenario_evidence", "medium", f"Scenario {s.id} lacks documented completed architectural verification.",
                    "Carry out the stated architecture review or analysis and attach evidence.",
                    reqs=[s.requirement_id], comps=s.component_ids)

    # Sibling data ownership conflicts are a review signal, not a definitive error.
    owners_by_data: dict[tuple[str | None, str], list[str]] = defaultdict(list)
    for c in spec.components:
        for datum in set(c.owned_data):
            owners_by_data[(c.parent_id, datum.strip().casefold())].append(c.id)
    for (parent_id, datum), owners in sorted(owners_by_data.items(), key=lambda item: str(item[0])):
        if len(owners) > 1:
            finding("data_ownership", "medium", f"Sibling components claim the same data '{datum}': {sorted(owners)}.",
                    "Choose a canonical owner or document the intended shared-ownership contract.", comps=sorted(owners))

    # API/event edges should have contracts on both ends; an unrelated interface is insufficient.
    for edge in spec.relationships:
        if edge.kind not in {"synchronous_call", "event"}:
            continue
        src, dst = components[edge.source_id], components[edge.target_id]
        kinds = {"event"} if edge.kind == "event" else {"api", "function", "other"}
        missing = []
        if not any(c.direction == "outbound" and c.kind in kinds for c in src.interfaces):
            missing.append(f"outbound contract on {src.id}")
        if not any(c.direction == "inbound" and c.kind in kinds for c in dst.interfaces):
            missing.append(f"inbound contract on {dst.id}")
        if missing:
            finding("interaction_contract", "medium", f"{edge.id} lacks {' and '.join(missing)}.",
                    "Specify directional contracts, message semantics and failure behavior.",
                    reqs=edge.requirement_ids, comps=[src.id, dst.id])

    return QualityReview(
        status="requires_review" if findings or spec.status != "validated_for_scope" else "evidence_documented",
        coverage=coverage, scenario_assessments=assessments, findings=findings,
        source_findings=[f.id for f in spec.findings if f.status == "open"],
    )


def assess_architecture(spec: ArchitectureSpec, config: ReviewConfig | None = None) -> ArchitectureReview:
    """Produce reproducible recommendations, not automatic architecture approval."""
    config = config or ReviewConfig()
    style = compare_styles(spec, config)
    quality = review_quality(spec, config)
    if style.recommendation and style.declared_style_family and style.recommendation != style.declared_style_family:
        quality.findings.append(ReviewFinding(
            id=f"REVIEW-{len(quality.findings)+1:03d}", severity="medium",
            category="style_tradeoff",
            description=f"Authored style '{spec.selected_style}' differs from advisory family '{style.recommendation}'.",
            recommendation="Review constraints and note whether a hybrid or the authored choice better fits the system.",
        ))
        quality.status = "requires_review"
    return ArchitectureReview(
        system=spec.brief.system,
        source_architecture_status=spec.status,
        overall_status=("candidate_for_human_review" if quality.status == "evidence_documented"
                        and style.status == "recommendation" else "requires_review"),
        style_comparison=style, quality_review=quality,
    )
