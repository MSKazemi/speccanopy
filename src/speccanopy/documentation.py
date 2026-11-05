"""Deterministic Markdown architecture documentation.

Renders what an author supplied. Does not inspect application code, verify
architecture claims, run an application, or authenticate any reviewer.
"""

from __future__ import annotations

import html
from pathlib import Path

from .exporters import relationships_mermaid, to_mermaid
from .models import ArchitectureSpec
from .review import ArchitectureReview


def _md(value: object) -> str:
    """Escape untrusted authored text as a single Markdown line/table cell."""
    s = html.escape(" ".join(str(value).split()), quote=False)
    for char in ("\\", "|", "*", "_", "`", "[", "]"):
        s = s.replace(char, "\\" + char)
    return s


def _joined(values: list[str]) -> str:
    return ", ".join(_md(x) for x in values) if values else "Not recorded"


def _bullets(values: list[str], missing: str = "Not recorded.") -> str:
    return "\n".join("- " + _md(x) for x in values) if values else missing


def _table(headings: list[str], rows: list[list[object]], missing: str) -> str:
    if not rows:
        return missing
    lines = ["| " + " | ".join(_md(x) for x in headings) + " |",
             "| " + " | ".join("---" for _ in headings) + " |"]
    for row in rows:
        if len(row) != len(headings):
            raise ValueError("Internal documentation table has incorrect column count")
        lines.append("| " + " | ".join(_md(x) for x in row) + " |")
    return "\n".join(lines)


def _mermaid(source: str) -> str:
    """Protect Markdown fences even if an authored diagram label has backticks."""
    tick = chr(96)
    longest = max((len(p) for p in source.split(" ") if p and set(p) == {tick}), default=0)
    # Also cover runs embedded within labels, not just whitespace-separated runs.
    for chunk in source.split(tick)[1::2]:
        longest = max(longest, 1)
    run = length = 0
    for char in source:
        if char == tick:
            length += 1
            run = max(run, length)
        else:
            length = 0
    fence = tick * max(3, run + 1)
    return fence + "mermaid\n" + source.rstrip("\n") + "\n" + fence


def _page(spec: ArchitectureSpec, title: str, body: str) -> str:
    return (
        "# " + _md(title) + "\n\n"
        "> **Draft architecture documentation.** This is derived from an authored "
        "ArchitectureSpec, not a scan of implementation code, independent "
        "expert verification, or executed application tests. "
        "Architecture status: **" + _md(spec.status) + "**.\n\n"
        + body.strip() + "\n"
    )


def _overview(spec: ArchitectureSpec) -> str:
    c = spec.brief.constraints
    cov = spec.coverage_report()
    body = "\n\n".join([
        "## System\n\n" + _md(spec.brief.system),
        "## Goals\n\n" + _bullets(spec.brief.goals),
        "## Actors\n\n" + _bullets(spec.brief.actors, "No actors specified."),
        "## Declared architecture\n\n"
        "- Style: " + _md(spec.selected_style or "Not chosen") + "\n"
        "- Status: " + _md(spec.status) + "\n"
        "- Component count: " + str(len(spec.components)) + "\n"
        "- Interaction count: " + str(len(spec.relationships)) + "\n"
        "- Mandatory requirements planned only: " + str(len(cov.planned_only)) + "\n"
        "- Mandatory requirements uncovered: " + str(len(cov.uncovered)),
        "## Author-specified constraints\n\n"
        "- Preferred style: " + _md(c.preferred_architecture or "Not specified") + "\n"
        "- Max depth: " + str(c.max_depth) + "\n"
        "- Max components: " + str(c.max_nodes) + "\n"
        "- Max refinement rounds: " + str(c.max_refinement_rounds),
        "## Source and scope limits\n\n"
        "No source-file/commit provenance, actual deployment topology or runtime "
        "traces can be established from the current ArchitectureSpec. These must "
        "be confirmed against the real application. A component status of "
        "`ready` means described structurally, not certified as implemented.",
    ])
    return _page(spec, "System overview", body)


def _requirements(spec: ArchitectureSpec) -> str:
    cov = spec.coverage_report()
    owners = {rid: [c.id for c in spec.components if rid in c.requirement_ids]
              for rid in spec.brief.requirement_ids()}

    def state(rid: str, mandatory: bool) -> str:
        if not mandatory:
            return "Optional (mandatory coverage not assessed)"
        if rid in cov.verified:
            return "Authored verified-evidence link (not independently checked)"
        if rid in cov.planned_only:
            return "Planned only"
        return "Uncovered"

    rows = []
    for req in spec.brief.functional_requirements:
        rows.append([req.id, "functional", req.mandatory, req.statement,
                     _joined(owners[req.id]), state(req.id, req.mandatory)])
    for req in spec.brief.quality_requirements:
        rows.append([req.id, "quality / " + req.attribute, req.mandatory,
                     req.statement, _joined(owners[req.id]), state(req.id, req.mandatory)])
    cases = [[v.id, _joined(v.requirement_ids), _joined(v.component_ids),
              v.method, v.status] for v in spec.verification_cases]
    return _page(spec, "Requirements and traceability", "\n\n".join([
        "## Authored requirement links\n\n" +
        _table(["ID", "Type", "Mandatory", "Statement", "Components", "Coverage"],
               rows, "No requirements recorded."),
        "## Authored verification cases\n\n" +
        _table(["ID", "Requirements", "Components", "Method", "Author-entered status"],
               cases, "No verification cases recorded."),
        "## Mandatory coverage gaps\n\n"
        "- Uncovered: " + _joined(cov.uncovered) + "\n"
        "- Planned-only: " + _joined(cov.planned_only) + "\n"
        "- Authored verified-evidence links: " + _joined(cov.verified) + "\n\n"
        "The renderer checks structural links, **not the truth of evidence text**.",
    ]))


def _components(spec: ArchitectureSpec) -> str:
    parts = ["## Containment diagram\n\n" + _mermaid(to_mermaid(spec)),
             "## Component responsibilities"]
    for c in spec.components:
        info = [
            "### " + _md(c.id) + " — " + _md(c.name),
            "- Status: " + _md(c.status) + "\n"
            "- Parent: " + _md(c.parent_id or "Root") + "\n"
            "- Requirements: " + _joined(c.requirement_ids) + "\n"
            "- Responsibility: " + _md(c.responsibility) + "\n"
            "- Boundary: " + _md(c.boundary),
            "**Interfaces**\n\n" +
            _table(["Name", "Direction", "Kind", "Description", "Failure behavior"],
                   [[i.name, i.direction, i.kind, i.description,
                     i.failure_behavior or "Not specified"] for i in c.interfaces],
                   "No interfaces recorded. N/A reason: " +
                   _md(c.interfaces_not_applicable_reason or "not specified")),
            "**Data ownership**\n\n" +
            _bullets(c.owned_data, "No owned data recorded. N/A reason: " +
                     _md(c.data_not_applicable_reason or "not specified")),
            "**Quality targets**\n\n" +
            _table(["Requirement", "Target"],
                   [[rid, target] for rid, target in sorted(c.quality_targets.items())],
                   "No quality targets recorded."),
            "**Assumptions**\n\n" + _bullets(c.assumptions),
            "**Risks**\n\n" + _bullets(c.risks),
            "**Author-provided design evidence (not independently verified)**\n\n"
            + _bullets(c.validation_evidence),
            "**Decomposition stop rationale**\n\n" +
            _md(c.stop_reason or "Not specified."),
        ]
        parts.append("\n\n".join(info))
    return _page(spec, "Components and boundaries", "\n\n".join(parts))


def _interactions(spec: ArchitectureSpec) -> str:
    rows = [[r.id, r.source_id, r.target_id, r.kind, r.description,
             _joined(r.requirement_ids)] for r in spec.relationships]
    return _page(spec, "Interactions and dependencies", "\n\n".join([
        "## Interaction graph\n\n" + _mermaid(relationships_mermaid(spec)),
        "## Authored relationships\n\n" +
        _table(["ID", "Source", "Target", "Kind", "Description", "Requirements"],
               rows, "No relationships recorded. Confirm whether this is intentional."),
        "## Unmodeled interaction details\n\n"
        "Payload schemas, retries, ordering, idempotency, transaction boundaries, "
        "timeouts, runtime sequences, network security and operational failure "
        "behavior may require additional project evidence. Do not infer them "
        "from a diagram alone.",
    ]))


def _data_security(spec: ArchitectureSpec) -> str:
    owners = [
        [c.id, c.name, ", ".join(c.owned_data) or
         ("N/A: " + c.data_not_applicable_reason
          if c.data_not_applicable_reason else "Unspecified")]
        for c in spec.components
    ]
    boundaries = [[r.id, r.source_id, r.target_id, r.description]
                  for r in spec.relationships if r.kind == "trust_boundary"]
    security = [[q.id, q.attribute, q.statement]
                for q in spec.brief.quality_requirements
                if any(s in q.attribute.lower() for s in ("secur", "privac", "auth"))]
    return _page(spec, "Data ownership and security", "\n\n".join([
        "## Declared data ownership\n\n" +
        _table(["Component", "Name", "Owned data"], owners,
               "No data ownership recorded."),
        "## Explicit trust-boundary relationships\n\n" +
        _table(["ID", "From", "To", "Description"], boundaries,
               "No trust boundaries recorded. Confirm whether they are missing "
               "or not applicable; absence is not evidence of safety."),
        "## Security and privacy quality requirements\n\n" +
        _table(["Requirement", "Attribute", "Statement"], security,
               "No separately classified security/privacy requirements "
               "recorded; confirm applicable requirements."),
        "## Unverified security controls\n\n"
        "Access control, authentication, secret handling, encryption, trust, "
        "compliance and threat models are not automatically checked against "
        "application code or runtime infrastructure.",
    ]))


def _decisions(spec: ArchitectureSpec) -> str:
    parts = [
        "## Style choice\n\n" + _md(spec.selected_style or "Not chosen"),
        "Accepted or superseded ADR statuses are **authored claims**, not "
        "human approval recorded by this exporter.",
    ]
    if not spec.decisions:
        parts.append("No ADRs supplied. Capture rationale and alternatives, "
                     "or explicitly document why none are needed.")
    for d in spec.decisions:
        parts.append("\n\n".join([
            "## " + _md(d.id) + " — " + _md(d.title),
            "- Authored status: " + _md(d.status) + "\n"
            "- Choice: " + _md(d.choice) + "\n"
            "- Rationale: " + _md(d.rationale) + "\n"
            "- Requirements: " + _joined(d.requirement_ids),
            "**Alternatives**\n\n" + _bullets(d.alternatives),
            "**Trade-offs**\n\n" + _bullets(d.tradeoffs),
        ]))
    return _page(spec, "Decisions and alternatives", "\n\n".join(parts))


def _quality_risks(spec: ArchitectureSpec, review: ArchitectureReview | None) -> str:
    targets = [[rid, c.id, target] for c in spec.components
               for rid, target in sorted(c.quality_targets.items())]
    checks = [[v.id, _joined(v.requirement_ids), v.method, v.status,
               v.evidence or "No evidence recorded"] for v in spec.verification_cases]
    findings = [[f.id, f.severity, f.status, _joined(f.component_ids),
                 f.description] for f in spec.findings]
    parts = [
        "## Authored quality targets\n\n" +
        _table(["Requirement", "Component", "Target"], targets,
               "No quality targets recorded."),
        "## Verification cases and authored evidence\n\n" +
        _table(["ID", "Requirements", "Method", "Authored status", "Evidence text"],
               checks, "No verification cases recorded.") +
        "\n\nAuthor-entered evidence was **not executed or independently checked**.",
        "## Authored findings\n\n" +
        _table(["ID", "Severity", "Status", "Components", "Description"],
               findings, "No findings recorded; this is not proof of no risks."),
    ]
    if review is None:
        parts.append(
            "## Advisory rule-based review\n\n"
            "No optional review was supplied. Run `speccanopy review`, then "
            "pass its `architecture-review.json` to `document --review` "
            "to include heuristic findings."
        )
    else:
        quality = review.quality_review
        parts.extend([
            "## Advisory rule-based review\n\n"
            "- Overall status: " + _md(review.overall_status) + "\n"
            "- Quality status: " + _md(quality.status) + "\n"
            "- Suggested style (heuristic): " +
            _md(review.style_comparison.recommendation or "Abstain") + "\n"
            "- Provenance: " + _md(review.provenance),
            "### Rule findings\n\n" +
            _table(["ID", "Severity", "Category", "Description", "Recommendation"],
                   [[f.id, f.severity, f.category, f.description, f.recommendation]
                    for f in quality.findings],
                   "No rule findings; this is not independent certification."),
            "### Quality scenarios\n\n" +
            _table(["Scenario", "Requirement", "Status", "Evidence", "Missing elements"],
                   [[s.scenario_id, s.requirement_id, s.status, s.verification_status,
                     "; ".join(s.missing_design_elements) or "None listed"]
                    for s in quality.scenario_assessments],
                   "No scenarios supplied."),
            "**Limitations:** " + _md(quality.caveat) +
            "\n\n**Freshness warning:** review data have no architecture-content "
            "digest. This command compares system name/status only; verify "
            "the review was created from this exact architecture revision.",
        ])
    return _page(spec, "Quality, risks and evidence", "\n\n".join(parts))


def _questions(spec: ArchitectureSpec, review: ArchitectureReview | None) -> str:
    questions = [
        "Confirm the authored architecture against the real project's source "
        "and revision. Source-file provenance is not tracked in ArchitectureSpec."
    ]
    cov = spec.coverage_report()
    if spec.status != "validated_for_scope":
        questions.append("Review current draft status: " + spec.status)
    if not spec.selected_style:
        questions.append("Choose or explicitly defer an architecture style.")
    if cov.uncovered:
        questions.append("Address uncovered mandatory requirements: " + ", ".join(cov.uncovered))
    if cov.planned_only:
        questions.append("Gather real evidence for planned requirements: " +
                         ", ".join(cov.planned_only))
    if cov.verified:
        questions.append("Authenticate author-supplied verification evidence: " +
                         ", ".join(cov.verified))
    if not spec.relationships:
        questions.append("Confirm whether component interactions have been omitted.")
    if not any(x.kind == "trust_boundary" for x in spec.relationships):
        questions.append("Confirm whether trust boundaries apply and need documentation.")
    if not spec.decisions:
        questions.append("Record important architecture decisions and alternatives.")
    for c in spec.components:
        if c.status != "ready":
            questions.append(f"Review component {c.id} with status {c.status}.")
        if not c.interfaces and not c.interfaces_not_applicable_reason:
            questions.append(f"Record interface contracts or N/A rationale for {c.id}.")
        if not c.owned_data and not c.data_not_applicable_reason:
            questions.append(f"Record owned data or N/A rationale for {c.id}.")
        for interface in c.interfaces:
            if interface.failure_behavior is None:
                questions.append(f"Specify failure behavior for {c.id}/{interface.name}.")
        for assumption in c.assumptions:
            questions.append(f"Confirm assumption for {c.id}: {assumption}")
        for risk in c.risks:
            questions.append(f"Assess risk for {c.id}: {risk}")
    for decision in spec.decisions:
        if decision.status == "proposed":
            questions.append(f"Decide whether to accept or reject ADR {decision.id}.")
    for finding in spec.findings:
        if finding.status == "open":
            questions.append(f"Resolve {finding.severity} finding {finding.id}: {finding.description}")
    if review is not None:
        if review.overall_status == "requires_review":
            questions.append("Resolve the advisory review's open issues.")
        for finding in review.quality_review.findings:
            questions.append(f"Investigate heuristic finding {finding.id}: {finding.description}")
    return _page(spec, "Open questions and owner review", "\n\n".join([
        "These are **review prompts, not independently verified defects**.",
        "\n".join("- [ ] " + _md(q) for q in questions),
    ]))


def render_documentation(
    spec: ArchitectureSpec, review: ArchitectureReview | None = None,
) -> dict[str, str]:
    """Render reproducible documents without changing a design's status."""
    if review is not None and (
        review.system != spec.brief.system or
        review.source_architecture_status != spec.status
    ):
        raise ValueError("Review system or source status does not match architecture")
    cover = spec.coverage_report()
    index = "\n\n".join([
        "## Purpose\n\n"
        "This pack describes the **authored architecture**, which may differ "
        "from the implementation. No repository scanning, external sign-off "
        "or production validation was performed by this command.",
        "## At a glance\n\n"
        "- System: " + _md(spec.brief.system) + "\n"
        "- Status: " + _md(spec.status) + "\n"
        "- Authored style: " + _md(spec.selected_style or "Not chosen") + "\n"
        "- Components: " + str(len(spec.components)) + "\n"
        "- Relationships: " + str(len(spec.relationships)) + "\n"
        "- Mandatory planned-only requirements: " + str(len(cover.planned_only)) + "\n"
        "- Mandatory uncovered requirements: " + str(len(cover.uncovered)),
        "## Pages\n\n"
        "- [Overview](overview.md)\n"
        "- [Requirements](requirements.md)\n"
        "- [Components and hierarchy](components.md)\n"
        "- [Interactions](interactions.md)\n"
        "- [Data and security](data-security.md)\n"
        "- [Architecture decisions](decisions.md)\n"
        "- [Quality and risks](quality-risks.md)\n"
        "- [Open questions](open-questions.md)",
        "## Provenance limits\n\n"
        "The current schema has no source-file references tying these assertions "
        "to application code. Authored verification cases, accepted ADR labels, "
        "and heuristic reviews are not independently authenticated.",
    ])
    return {
        "README.md": _page(spec, "Architecture documentation: " + spec.brief.system, index),
        "overview.md": _overview(spec),
        "requirements.md": _requirements(spec),
        "components.md": _components(spec),
        "interactions.md": _interactions(spec),
        "data-security.md": _data_security(spec),
        "decisions.md": _decisions(spec),
        "quality-risks.md": _quality_risks(spec, review),
        "open-questions.md": _questions(spec, review),
        "architecture.mmd": to_mermaid(spec),
        "relationships.mmd": relationships_mermaid(spec),
    }


def export_documentation(
    spec: ArchitectureSpec, destination: str | Path,
    *, review: ArchitectureReview | None = None,
) -> dict[str, Path]:
    """Refuse silent replacement of hand-edited or pre-existing documentation."""
    rendered = render_documentation(spec, review)
    out = Path(destination)
    if out.is_symlink() or (out.exists() and (not out.is_dir() or any(out.iterdir()))):
        raise ValueError("Documentation output must be an empty directory; existing files not overwritten")
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, content in rendered.items():
        path = out / name
        path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        paths[name] = path
    return paths
