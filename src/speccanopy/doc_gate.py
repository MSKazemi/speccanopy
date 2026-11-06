"""Deterministic documentation review gate.

A pure completeness check over *already loaded* authored data: it never reads
project sources, never calls a network or a model, and never changes a status.
Its strongest outcome is ``ready_for_human_signoff``: "nothing blocking remains
in the authored data". It is not expert review, not certification and never
produces ``validated`` or ``approved``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .documentation import _md
from .exporters import prepare_new_output_dir
from .models import ArchitectureSpec, NonEmptyText, SchemaModel
from .review import ArchitectureReview
from .source_evidence import SourceAssessment

GateCategory = Literal[
    "uncovered_requirement",
    "planned_only_requirement",
    "unsupported_claim",
    "unknown_source_mapping",
    "manual_decision",
    "status_claim",
]
GateSeverity = Literal["blocking", "attention"]
GateOutcome = Literal["requires_review", "ready_for_human_signoff"]

CATEGORY_ORDER: tuple[GateCategory, ...] = (
    "uncovered_requirement",
    "planned_only_requirement",
    "unsupported_claim",
    "unknown_source_mapping",
    "manual_decision",
    "status_claim",
)
CATEGORY_TITLES: dict[str, str] = {
    "uncovered_requirement": "Uncovered requirements",
    "planned_only_requirement": "Planned-only requirements",
    "unsupported_claim": "Unsupported or self-reported claims",
    "unknown_source_mapping": "Unknown source mappings",
    "manual_decision": "Remaining manual decisions",
    "status_claim": "Authored status claims",
}
_SEVERITY_RANK = {"blocking": 0, "attention": 1}

GATE_CAVEAT = (
    "This gate is a deterministic completeness check of authored data. It is "
    "not expert review, not certification and not proof that the architecture "
    "or its documentation is correct. It never upgrades any status. A human "
    "must review the findings and sign off."
)
NO_SOURCES = "No source evidence supplied; every factual claim is unmapped."
NO_REVIEW = (
    "No advisory review supplied; run `speccanopy review` on this architecture and pass "
    "--review so its findings are considered."
)
NO_MANDATORY = (
    "The brief has no mandatory requirements, so coverage cannot be judged; mark the "
    "requirements the owner actually needs as mandatory."
)
INCOMPLETE = "Authored architecture status is incomplete_requires_review."


class GateItem(SchemaModel):
    category: GateCategory
    severity: GateSeverity
    subject_id: str | None = None
    message: NonEmptyText


class DocumentationGate(SchemaModel):
    schema_version: Literal[1] = 1
    system: NonEmptyText
    architecture_status: str
    review_supplied: bool
    sources_supplied: bool
    outcome: GateOutcome
    counts: dict[str, int]
    blocking_count: int = Field(ge=0)
    attention_count: int = Field(ge=0)
    items: list[GateItem]
    caveat: str = GATE_CAVEAT

    @model_validator(mode="after")
    def consistent(self) -> DocumentationGate:
        blocking = sum(i.severity == "blocking" for i in self.items)
        if self.blocking_count != blocking or self.attention_count != len(self.items) - blocking:
            raise ValueError("Gate severity counts do not match its items")
        expected = {c: sum(i.category == c for i in self.items) for c in CATEGORY_ORDER}
        if self.counts != expected:
            raise ValueError("Gate category counts do not match its items")
        if (self.outcome == "ready_for_human_signoff") != (blocking == 0):
            raise ValueError("Gate outcome must be ready_for_human_signoff only with no blocking items")
        if self.caveat != GATE_CAVEAT:
            raise ValueError("Gate caveat is fixed")
        # Header facts must be backed by the blocking items they always produce.
        required = []
        if not self.sources_supplied:
            required.append(("unknown_source_mapping", NO_SOURCES))
        if not self.review_supplied:
            required.append(("manual_decision", NO_REVIEW))
        if self.architecture_status == "incomplete_requires_review":
            required.append(("manual_decision", INCOMPLETE))
        present = {(i.category, i.message) for i in self.items
                   if i.severity == "blocking" and i.subject_id is None}
        if any(key not in present for key in required):
            raise ValueError("Gate items are inconsistent with its supplied inputs or status")
        return self


def _sort_key(item: GateItem) -> tuple[int, int, str, str]:
    return (_SEVERITY_RANK[item.severity], CATEGORY_ORDER.index(item.category),
            item.subject_id or "", item.message)


def evaluate_documentation_gate(
    spec: ArchitectureSpec, *,
    review: ArchitectureReview | None = None,
    sources: SourceAssessment | None = None,
) -> DocumentationGate:
    """Return the gate result; the architecture status is never modified."""
    items: list[GateItem] = []

    def add(category: GateCategory, severity: GateSeverity,
            subject: str | None, message: str) -> None:
        items.append(GateItem(category=category, severity=severity,
                              subject_id=subject, message=message))

    cov = spec.coverage_report()
    names = {c.id: c.name for c in spec.components}

    def comp_label(cid: str) -> str:
        name = names.get(cid)
        return f"{cid} ({name})" if name and name != cid else cid

    # Mandatory requirements with no verification link (including those mapped
    # to no component at all, which can never be covered).
    owned = {rid for c in spec.components for rid in c.requirement_ids}
    for rid in cov.uncovered:
        if rid not in owned:
            add("uncovered_requirement", "blocking", rid,
                f"Mandatory requirement {rid} is mapped to no component and has no verification case.")
        else:
            add("uncovered_requirement", "blocking", rid,
                f"Mandatory requirement {rid} has no verification case linked to an owning component.")
    if not spec.brief.mandatory_requirement_ids():
        add("uncovered_requirement", "blocking", None, NO_MANDATORY)
    for rid in cov.planned_only:
        add("planned_only_requirement", "attention", rid,
            f"Mandatory requirement {rid} has only planned verification; no evidence is recorded.")

    # Claims: authored verification and (optionally) source snapshots.
    for case in spec.verification_cases:
        if case.status == "verified":
            add("unsupported_claim", "attention", case.id,
                f"Verification case {case.id} is marked verified from authored evidence; "
                "that evidence is not independently checked.")
    if sources is not None:
        for check in sources.checks:
            span = check.source_path
            if check.line_start is not None:
                span += f":{check.line_start}-{check.line_end}"
            if check.status != "matching_snapshot":
                add("unsupported_claim", "blocking", check.architecture_id,
                    f"Source claim for {check.architecture_id} at {span} is {check.status}; "
                    "the cited snapshot cannot be confirmed.")
            elif check.basis in {"inferred", "proposed"}:
                add("unsupported_claim", "attention", check.architecture_id,
                    f"Source claim for {check.architecture_id} at {span} is only "
                    f"{check.basis}, not observed.")

    # Source mapping.
    if sources is None:
        add("unknown_source_mapping", "blocking", None, NO_SOURCES)
    else:
        for rid in sources.unlinked_mandatory_requirements:
            add("unknown_source_mapping", "blocking", rid,
                f"Mandatory requirement {rid} has no matching observed source file link.")
        for cid in sources.unlinked_components:
            add("unknown_source_mapping", "blocking", cid,
                f"Component {comp_label(cid)} has no matching observed source file link.")

    # Manual decisions.
    if spec.status == "incomplete_requires_review":
        add("manual_decision", "blocking", None, INCOMPLETE)
    elif spec.status == "draft":
        add("manual_decision", "attention", None, "Authored architecture status is draft.")
    for decision in spec.decisions:
        if decision.status == "proposed":
            add("manual_decision", "attention", decision.id,
                f"Decision {decision.id} ({decision.title}) is proposed; a human must accept or reject it.")
        elif decision.status == "accepted":
            add("manual_decision", "attention", decision.id,
                f"Decision {decision.id} ({decision.title}) is marked accepted in authored data; "
                "confirm a human owner accepted it.")
    for finding in spec.findings:
        if finding.status == "open":
            sev: GateSeverity = "blocking" if finding.severity in {"critical", "high"} else "attention"
            add("manual_decision", sev, finding.id,
                f"Open {finding.severity} finding {finding.id}: {finding.description}")
        elif finding.status == "accepted" and finding.severity in {"critical", "high"}:
            add("manual_decision", "attention", finding.id,
                f"{finding.severity.capitalize()} finding {finding.id} is marked accepted in "
                "authored data; confirm a human owner accepted the risk.")
    for comp in spec.components:
        if comp.status in {"needs_decomposition", "blocked", "requires_review"}:
            add("manual_decision", "blocking", comp.id,
                f"Component {comp_label(comp.id)} has status {comp.status}.")
        elif comp.status == "proposed":
            add("manual_decision", "attention", comp.id,
                f"Component {comp_label(comp.id)} is only proposed, not marked ready.")
        elif comp.status == "ready":
            add("manual_decision", "attention", comp.id,
                f"Component {comp_label(comp.id)} is marked ready on authored validation evidence; "
                "that evidence is not independently checked.")
    if review is None:
        add("manual_decision", "blocking", None, NO_REVIEW)
    else:
        if review.system != spec.brief.system or review.source_architecture_status != spec.status:
            add("manual_decision", "blocking", None,
                "Supplied review was produced for a different system or architecture status; "
                "it is ignored and cannot support this gate.")
        else:
            if review.overall_status == "requires_review":
                # The heuristic review defaults to requires_review for every draft;
                # its high/critical findings below block individually.
                add("manual_decision", "attention", None,
                    "The advisory review's overall status is requires_review.")
            for rf in review.quality_review.findings:
                sev = "blocking" if rf.severity in {"critical", "high"} else "attention"
                add("manual_decision", sev, rf.id,
                    f"Advisory review finding {rf.id} ({rf.severity}): {rf.description}")

    # Authored status is only reported, never upgraded.
    if spec.status == "validated_for_scope":
        add("status_claim", "attention", None,
            "The architecture claims validated_for_scope. This gate cannot confirm that; "
            "the status is authored and the gate outcome never upgrades a status.")

    items.sort(key=_sort_key)
    blocking = sum(i.severity == "blocking" for i in items)
    return DocumentationGate(
        system=spec.brief.system,
        architecture_status=spec.status,
        review_supplied=review is not None,
        sources_supplied=sources is not None,
        outcome="requires_review" if blocking else "ready_for_human_signoff",
        counts={c: sum(i.category == c for i in items) for c in CATEGORY_ORDER},
        blocking_count=blocking,
        attention_count=len(items) - blocking,
        items=items,
    )


def render_documentation_gate_markdown(gate: DocumentationGate) -> str:
    """Render the gate as Markdown; all authored text is escaped."""
    lines = [
        "# Documentation review gate: " + _md(gate.system),
        "",
        "> **Outcome: `" + gate.outcome + "`.** "
        + ("Blocking items remain; see below." if gate.blocking_count
           else "No blocking items remain in the authored data. This is NOT validation or approval."),
        "",
        gate.caveat,
        "",
        "## Summary",
        "",
        f"- Outcome: **{gate.outcome}**",
        f"- Blocking items: {gate.blocking_count}",
        f"- Attention items: {gate.attention_count}",
        "- Authored architecture status: " + _md(gate.architecture_status),
        "- Review supplied: " + ("yes" if gate.review_supplied else "no"),
        "- Source evidence supplied: " + ("yes" if gate.sources_supplied else "no"),
        "",
        "| Category | Blocking | Attention |",
        "| --- | --- | --- |",
    ]
    for cat in CATEGORY_ORDER:
        b = sum(i.category == cat and i.severity == "blocking" for i in gate.items)
        a = sum(i.category == cat and i.severity == "attention" for i in gate.items)
        lines.append(f"| {CATEGORY_TITLES[cat]} | {b} | {a} |")
    lines.append("")
    # Categories holding blocking items come first; fixed order otherwise.
    ordered = sorted(CATEGORY_ORDER, key=lambda c: (
        not any(i.category == c and i.severity == "blocking" for i in gate.items),
        CATEGORY_ORDER.index(c)))
    for cat in ordered:
        section = [i for i in gate.items if i.category == cat]
        lines += ["## " + CATEGORY_TITLES[cat] + f" ({len(section)})", ""]
        if not section:
            lines += ["None.", ""]
            continue
        for item in sorted(section, key=_sort_key):
            # Code spans render backslashes literally, so do not Markdown-escape IDs;
            # backticks cannot occur in IDs but are neutralized defensively.
            subject = f" `{item.subject_id.replace('`', chr(39))}`" if item.subject_id else ""
            lines.append(f"- **{item.severity.upper()}**{subject}: {_md(item.message)}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def export_documentation_gate(
    gate: DocumentationGate, destination: str | Path,
) -> dict[str, Path]:
    """Write the gate to a NEW directory; never overwrites existing files."""
    markdown = render_documentation_gate_markdown(gate)
    out = prepare_new_output_dir(destination, "Documentation gate")
    json_path = out / "documentation-gate.json"
    md_path = out / "documentation-gate.md"
    json_path.write_text(
        json.dumps(gate.model_dump(mode="json"), indent=2, sort_keys=True,
                   ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return {"documentation-gate.json": json_path, "documentation-gate.md": md_path}
