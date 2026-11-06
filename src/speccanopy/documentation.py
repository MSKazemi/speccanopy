"""Deterministic Markdown architecture documentation.

Renders what an author supplied. Does not inspect application code, verify
architecture claims, run an application, or authenticate any reviewer.
"""

from __future__ import annotations

import html
from pathlib import Path

from .exporters import prepare_new_output_dir, relationships_mermaid, to_mermaid
from .models import ArchitectureSpec, InterfaceContract, Relationship
from .review import ArchitectureReview
from .source_evidence import SourceAssessment


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


# ---------------------------------------------------------------- focused views
#
# Four pages derived ONLY from ArchitectureSpec fields (Relationship.kind,
# Component.parent_id / owned_data / interfaces). They are authored design data.

_MERMAID_UNSAFE = frozenset('#"<>[]{}()|\\`&;%')


def _mm(value: object) -> str:
    """Encode untrusted text for use inside a double-quoted Mermaid label.

    Every character that Mermaid or Markdown could treat as syntax is replaced
    by a numeric entity (``#NN;``), so a label can never close its quotes,
    start an edge or comment, or open a code fence.
    """
    out = []
    for char in " ".join(str(value).split()):
        if char in _MERMAID_UNSAFE or not char.isprintable():
            out.append(f"#{ord(char)};")
        else:
            out.append(char)
    return "".join(out)


def _view_diagram(
    spec: ArchitectureSpec, relationships: list[Relationship],
    arrows: dict[str, str], direction: str = "LR",
) -> str:
    """Flowchart of just ``relationships`` and their endpoint components."""
    ids = {c.id: f"N{i}" for i, c in enumerate(spec.components)}
    used = {r.source_id for r in relationships} | {r.target_id for r in relationships}
    lines = [f"flowchart {direction}"]
    for c in spec.components:
        if c.id in used:
            lines.append(f'    {ids[c.id]}["{_mm(c.name)}"]')
    for r in relationships:
        label = _mm(r.id) + ": " + _mm(r.kind.replace("_", " "))
        lines.append(f'    {ids[r.source_id]} {arrows[r.kind]}|"{label}"| {ids[r.target_id]}')
    return "\n".join(lines) + "\n"


def _of_kind(spec: ArchitectureSpec, *kinds: str) -> list[Relationship]:
    """Relationships of the given kinds, sorted by ID so order never implies sequence."""
    return sorted((r for r in spec.relationships if r.kind in kinds), key=lambda r: r.id)


def _missing(statement: str) -> str:
    return "**" + statement + "**"


def _source_note(sources: SourceAssessment | None) -> str:
    if sources is None:
        return ("No source evidence was supplied (`--source-evidence`); no component or "
                "relationship in this view is annotated with observed source status.")
    return ("Source evidence column: an *observed source claim with a matching snapshot* "
            "means the author's source map links this ID to a local file whose SHA-256 "
            "still matches and whose basis is `observed`. It does not prove the claim. "
            "File paths are deliberately not repeated here; see "
            "[source-evidence.md](source-evidence.md).")


def _source_status(sources: SourceAssessment, architecture_id: str) -> str:
    checks = [c for c in sources.checks if c.architecture_id == architecture_id]
    if not checks:
        return "No source claim"
    matching = [c for c in checks if c.status == "matching_snapshot" and c.basis == "observed"]
    if matching:
        return f"Observed source claim with matching snapshot ({len(matching)})"
    kinds = sorted({f"{c.basis}/{c.status.removesuffix('_snapshot')}" for c in checks})
    return "Source claim present, but none is a matching observed snapshot: " + ", ".join(kinds)


def _with_source(
    headings: list[str], rows: list[list[object]], ids: list[str],
    sources: SourceAssessment | None,
) -> tuple[list[str], list[list[object]]]:
    if sources is None:
        return headings, rows
    return (headings + ["Source evidence"],
            [row + [_source_status(sources, rid)] for row, rid in zip(rows, ids, strict=True)])


def _view_page(
    spec: ArchitectureSpec, title: str, derived_from: str,
    sources: SourceAssessment | None, sections: list[str], limits: str,
) -> str:
    head = (
        "## Source of this view\n\n"
        "- Derived only from ArchitectureSpec fields: " + derived_from + ".\n"
        "- This is **authored design data, not observed runtime behaviour**: nothing "
        "here was measured, traced, scanned or executed.\n"
        "- " + _source_note(sources)
    )
    return _page(spec, title, "\n\n".join([head, *sections, "## Limits\n\n" + limits]))


def _descendants(spec: ArchitectureSpec, root: str) -> list[str]:
    """Component IDs contained under ``root`` via parent_id (excluding root), in spec order."""
    found = {root}
    changed = True
    while changed:
        changed = False
        for c in spec.components:
            if c.parent_id in found and c.id not in found:
                found.add(c.id)
                changed = True
    return [c.id for c in spec.components if c.id in found and c.id != root]


def _component_name(spec: ArchitectureSpec, cid: str) -> str:
    return next(c.name for c in spec.components if c.id == cid)


EDGE_HEADINGS = ["ID", "Source", "Target", "Kind", "Description", "Requirements"]


def _edge_rows(spec: ArchitectureSpec, rels: list[Relationship]) -> list[list[object]]:
    return [[r.id, r.source_id + " (" + _component_name(spec, r.source_id) + ")",
             r.target_id + " (" + _component_name(spec, r.target_id) + ")",
             r.kind, r.description, _joined(r.requirement_ids)] for r in rels]


def _edge_table(spec: ArchitectureSpec, rels: list[Relationship],
                sources: SourceAssessment | None) -> str:
    headings, rows = _with_source(
        EDGE_HEADINGS, _edge_rows(spec, rels), [r.id for r in rels], sources)
    return _table(headings, rows, "")


def _data_flow_view(spec: ArchitectureSpec, sources: SourceAssessment | None) -> str:
    rels = _of_kind(spec, "data_flow", "shared_resource")
    if rels:
        edges = (_mermaid(_view_diagram(
            spec, rels, {"data_flow": "-->", "shared_resource": "---"}))
            + "\n\n" + _edge_table(spec, rels, sources))
    else:
        edges = _missing(
            "No data_flow or shared_resource relationships are recorded in the "
            "architecture; the edge part of this view is MISSING, not 'none exist'.")
    by_item: dict[str, list[str]] = {}
    for c in spec.components:
        for item in dict.fromkeys(" ".join(x.split()) for x in c.owned_data):
            by_item.setdefault(item, []).append(c.id)
    parent = {c.id: c.parent_id for c in spec.components}
    owner_rows: list[list[object]] = []
    for item in sorted(by_item):
        owners = by_item[item]
        if len(owners) == 1:
            flag = "Single owner"
        elif len({parent[o] for o in owners}) == 1:
            flag = "MULTIPLE OWNERS (siblings under " + (parent[owners[0]] or "root") + ")"
        else:
            flag = "MULTIPLE OWNERS (different parents)"
        owner_rows.append([item, ", ".join(owners), flag])
    gap_rows: list[list[object]] = [
        [c.id, c.name,
         "Not applicable: " + c.data_not_applicable_reason
         if c.data_not_applicable_reason else "Not recorded"]
        for c in spec.components if not c.owned_data
    ]
    gap_headings, gap_rows = _with_source(
        ["Component", "Name", "Data ownership"], gap_rows, [str(r[0]) for r in gap_rows], sources)
    return _view_page(
        spec, "View: data flow and data ownership",
        "`Relationship.kind` of `data_flow` and `shared_resource` (source, target, "
        "description, requirement IDs) and `Component.owned_data` / "
        "`Component.data_not_applicable_reason`",
        sources, [
            "## Data-flow and shared-resource edges\n\n" + edges,
            "## Data items and their owners\n\n" + _table(
                ["Data item", "Owner component(s)", "Ownership"], owner_rows,
                "No owned data is recorded for any component; ownership is MISSING."),
            "## Components without recorded data ownership\n\n"
            "Components that list no owned data either carry an authored "
            "not-applicable reason or ownership is **not recorded**.\n\n" +
            _table(gap_headings, gap_rows, "Every component records owned data."),
        ],
        "The schema does not record which data item travels on an edge, its payload "
        "schema, volume, retention or consistency model (transactions, eventual "
        "consistency, idempotency). Owner matching is by exact authored text after "
        "whitespace normalisation; differently worded names for the same data are "
        "listed as different items. See [data-security.md](data-security.md) for the "
        "per-component ownership list.",
    )


def _trust_view(spec: ArchitectureSpec, sources: SourceAssessment | None) -> str:
    rels = _of_kind(spec, "trust_boundary")
    if not rels:
        sections = [
            "## Trust boundaries\n\n" + _missing(
                "No trust boundaries are recorded in the architecture; this view is "
                "MISSING, not 'none exist'.") +
            "\n\nAbsence of a recorded boundary is not evidence that the system has "
            "none or that it is safe."]
    else:
        sections = ["## Recorded trust boundaries\n\n"
                    + _mermaid(_view_diagram(spec, rels, {"trust_boundary": "-.->"}))
                    + "\n\n" + _edge_table(spec, rels, sources)]
        side_rows: list[list[object]] = []
        crossing: list[list[object]] = []
        involved: set[str] = set()
        for r in rels:
            src_side = [r.source_id, *_descendants(spec, r.source_id)]
            dst_side = [r.target_id, *_descendants(spec, r.target_id)]
            involved.update(src_side + dst_side)
            side_rows.append([r.id, ", ".join(src_side), ", ".join(dst_side)])
            for o in sorted(spec.relationships, key=lambda x: x.id):
                if o.kind != "trust_boundary" and (
                    (o.source_id in src_side and o.target_id in dst_side) or
                    (o.source_id in dst_side and o.target_id in src_side)
                ):
                    crossing.append([r.id, o.id, o.kind, o.source_id, o.target_id,
                                     o.description])
        sections.append(
            "## Components on each side\n\n"
            "Each side is the boundary's endpoint component plus the components "
            "contained under it through `parent_id`. The schema does not otherwise "
            "assign components to zones.\n\n"
            + _table(["Boundary", "Source side", "Target side"], side_rows, ""))
        sections.append(
            "## Other recorded interactions between the two sides\n\n" +
            _table(["Boundary", "Interaction", "Kind", "From", "To", "Description"],
                   crossing, "No other recorded relationship connects the two sides."))
        if sources is not None:
            ordered = [c.id for c in spec.components if c.id in involved]
            headings, rows = _with_source(
                ["Component", "Name"], [[cid, _component_name(spec, cid)] for cid in ordered],
                ordered, sources)
            sections.append("## Component source status\n\n" + _table(headings, rows, ""))
    return _view_page(
        spec, "View: trust boundaries",
        "`Relationship.kind == trust_boundary` and `Component.parent_id`",
        sources, sections,
        "Authentication, authorisation, secret handling, encryption, network "
        "segmentation and threat models are not modelled by the schema and are not "
        "checked. Security and privacy quality requirements are listed in "
        "[data-security.md](data-security.md).",
    )


def _deployment_view(spec: ArchitectureSpec, sources: SourceAssessment | None) -> str:
    rels = _of_kind(spec, "deployment")
    if not rels:
        sections = [
            "## Deployment relationships\n\n" + _missing(
                "No deployment relationships are recorded in the architecture; this view "
                "is MISSING, not 'none exist'.") +
            "\n\nThe system may well be deployed; the authored design does not say how."]
    else:
        sections = ["## Deployment relationships\n\n"
                    + _mermaid(_view_diagram(spec, rels, {"deployment": "-->"}))
                    + "\n\n" + _edge_table(spec, rels, sources)]
    return _view_page(
        spec, "View: deployment",
        "`Relationship.kind == deployment` (source, target, description)",
        sources, sections,
        "The schema has no model of environments, hosts, regions, clusters, "
        "containers, networks, scaling or release processes; a `deployment` "
        "relationship is only an authored edge between two components with a "
        "free-text description. Nothing is checked against infrastructure code or a "
        "running system.",
    )


def _interface_text(items: list[InterfaceContract]) -> str:
    return "; ".join(f"{i.name} ({i.kind})" for i in items) or "none recorded"


def _runtime_view(spec: ArchitectureSpec, sources: SourceAssessment | None) -> str:
    rels = _of_kind(spec, "synchronous_call", "event")
    comps = {c.id: c for c in spec.components}
    rows: list[list[object]] = []
    for r in rels:
        is_event = r.kind == "event"
        src, dst = comps[r.source_id], comps[r.target_id]
        label = "event-kind" if is_event else "non-event"
        problems = []
        if not any(i.direction == "outbound" and (i.kind == "event") == is_event
                   for i in src.interfaces):
            problems.append(f"source has no outbound {label} interface recorded")
        if not any(i.direction == "inbound" and (i.kind == "event") == is_event
                   for i in dst.interfaces):
            problems.append(f"target has no inbound {label} interface recorded")
        status = ("Interface contracts recorded on both ends" if not problems
                  else "NO MATCHING INTERFACE: " + "; ".join(problems))
        rows.append([
            r.id, r.kind, r.source_id,
            _interface_text([i for i in src.interfaces if i.direction == "outbound"]),
            r.target_id,
            _interface_text([i for i in dst.interfaces if i.direction == "inbound"]),
            status, r.description])
    headings = ["ID", "Kind", "Source", "Source outbound interfaces", "Target",
                "Target inbound interfaces", "Interface check", "Description"]
    if rels:
        headings, rows = _with_source(headings, rows, [r.id for r in rels], sources)
        body = (_mermaid(_view_diagram(
            spec, rels, {"synchronous_call": "-->", "event": "-.->"}))
            + "\n\n" + _table(headings, rows, ""))
    else:
        body = _missing("No synchronous_call or event relationships are recorded in the "
                        "architecture; this view is MISSING, not 'none exist'.")
    return _view_page(
        spec, "View: runtime interactions",
        "`Relationship.kind` of `synchronous_call` and `event`, and "
        "`Component.interfaces` (name, direction, kind) of both endpoints",
        sources, [
            "## Synchronous and event interactions\n\n" + body,
            "## How interfaces are matched\n\n"
            "Each edge points from its source to its target. The check expects the "
            "source to list an `outbound` interface and the target an `inbound` one; "
            "for an `event` edge both must have kind `event`, for a `synchronous_call` "
            "edge neither may. The schema does not link an edge to a named interface, "
            "so this only shows whether *a plausible* contract is recorded on each "
            "end; it does not say which one realises the edge. A flagged edge is a "
            "documentation gap, not proof of a defect.",
            "## Sequences are not modelled\n\n"
            "Sequences are not modelled: the schema has no ordering, steps, "
            "request/response pairing, timing, retry or timeout data, or alternative "
            "and failure paths for an interaction. Edges are listed sorted by ID, "
            "which carries no execution order. No sequence diagram is drawn because "
            "it would have to invent that order.",
        ],
        "Payload schemas, ordering, idempotency, delivery guarantees, transaction "
        "boundaries and failure handling are not modelled. Interface "
        "`failure_behavior` text is on [components.md](components.md).",
    )


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




def _source_evidence_page(spec: ArchitectureSpec, sources: SourceAssessment) -> str:
    """Link claims to live local file snapshots without asserting semantic truth."""
    rows = []
    for check in sources.checks:
        loc = check.source_path
        if check.line_start is not None:
            loc += f":{check.line_start}-{check.line_end}"
        rows.append([
            check.architecture_id,
            loc,
            check.basis,
            check.status,
            check.assertion,
            check.expected_sha256,
            check.actual_sha256 or "Unavailable",
        ])
    matched = sum(check.status == "matching_snapshot" for check in sources.checks)
    body = "\n\n".join([
        "## Meaning of this evidence\n\n"
        "**A matching SHA-256 means only that a cited LOCAL file currently has "
        "the referenced bytes.** It does **not** prove the author's assertion, "
        "the source's behavioral meaning, independent verification, or "
        "architectural correctness. All assertions and basis labels were "
        "supplied by a person or AI; no source text is copied into this page.",
        "## Snapshot status\n\n"
        "- Claims provided: " + str(len(sources.checks)) + "\n"
        "- Matching byte snapshots: " + str(matched) + "\n"
        "- Changed or missing/unreadable/invalid-span snapshots: " +
        str(len(sources.checks) - matched) + "\n"
        "- Mandatory requirements without a **matching observed source**: " +
        str(len(sources.unlinked_mandatory_requirements)) + "\n"
        "- Components without a **matching observed source**: " +
        str(len(sources.unlinked_components)),
        "## Authored source claims\n\n" +
        _table(
            ["Architecture ID", "Project-relative file[:lines]", "Author basis",
             "Byte status", "Authored claim", "Expected SHA-256", "Current SHA-256"],
            rows, "No source claims were supplied.",
        ),
        "## Unlinked mandatory requirements\n\n" +
        _bullets(sources.unlinked_mandatory_requirements,
                 "Every mandatory requirement has at least one matching observed "
                 "file link. This is NOT proof the requirement is implemented."),
        "## Unlinked components\n\n" +
        _bullets(sources.unlinked_components,
                 "Every component has at least one matching observed file link. "
                 "This is NOT proof of semantic correctness."),
        "## Caveats\n\n" + _md(sources.caveat) +
        "\n\nThe report uses project-relative paths, not absolute host paths, "
        "and does not copy source code or credentials. A source mapping may still "
        "reveal private filenames, so review it before publishing.",
    ])
    return _page(spec, "Source-file evidence and change detection", body)

def _questions(spec: ArchitectureSpec, review: ArchitectureReview | None,
               sources: SourceAssessment | None = None) -> str:
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
    if sources is not None:
        questions.append(
            "Review the author's source-to-architecture mapping for semantic accuracy. "
            "Matching file hashes alone do not prove any architectural assertion."
        )
        if sources.unlinked_mandatory_requirements:
            questions.append(
                "Map these mandatory requirements to observed source files or "
                "mark them as unimplemented/unverified: " +
                ", ".join(sources.unlinked_mandatory_requirements)
            )
        if sources.unlinked_components:
            questions.append(
                "Confirm source provenance or proposed-only status of components: " +
                ", ".join(sources.unlinked_components)
            )
        for check in sources.checks:
            if check.status != "matching_snapshot":
                questions.append(
                    f"Investigate {check.status} source for {check.architecture_id}: "
                    f"{check.source_path}."
                )
            elif check.basis != "observed":
                questions.append(
                    f"Validate authored {check.basis} claim for "
                    f"{check.architecture_id}: {check.source_path}."
                )
    return _page(spec, "Open questions and owner review", "\n\n".join([
        "These are **review prompts, not independently verified defects**.",
        "\n".join("- [ ] " + _md(q) for q in questions),
    ]))


def render_documentation(
    spec: ArchitectureSpec, review: ArchitectureReview | None = None,
    sources: SourceAssessment | None = None,
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
        "- [View: data flow and ownership](view-data-flow.md)\n"
        "- [View: trust boundaries](view-trust-boundaries.md)\n"
        "- [View: deployment](view-deployment.md)\n"
        "- [View: runtime interactions](view-runtime.md)\n"
        "- [Architecture decisions](decisions.md)\n"
        "- [Quality and risks](quality-risks.md)\n"
        "- [Open questions](open-questions.md)" +
        ("\n- [Source evidence and change status](source-evidence.md)" if sources else ""),
        "## Provenance limits\n\n"
        "The ArchitectureSpec schema does not itself carry source-file references. "
        "An optional external source-evidence sidecar may bind authored claims "
        "to SHA-256 file snapshots, but matching bytes do not prove semantic "
        "correctness. Authored verification cases, accepted ADR labels, and "
        "heuristic reviews are not independently authenticated.",
    ])
    pages = {
        "README.md": _page(spec, "Architecture documentation: " + spec.brief.system, index),
        "overview.md": _overview(spec),
        "requirements.md": _requirements(spec),
        "components.md": _components(spec),
        "interactions.md": _interactions(spec),
        "data-security.md": _data_security(spec),
        "view-data-flow.md": _data_flow_view(spec, sources),
        "view-trust-boundaries.md": _trust_view(spec, sources),
        "view-deployment.md": _deployment_view(spec, sources),
        "view-runtime.md": _runtime_view(spec, sources),
        "decisions.md": _decisions(spec),
        "quality-risks.md": _quality_risks(spec, review),
        "open-questions.md": _questions(spec, review, sources),
        "architecture.mmd": to_mermaid(spec),
        "relationships.mmd": relationships_mermaid(spec),
    }
    if sources is not None:
        pages["source-evidence.md"] = _source_evidence_page(spec, sources)
    return pages


def export_documentation(
    spec: ArchitectureSpec, destination: str | Path,
    *, review: ArchitectureReview | None = None,
    sources: SourceAssessment | None = None,
) -> dict[str, Path]:
    """Refuse silent replacement of hand-edited or pre-existing documentation."""
    rendered = render_documentation(spec, review, sources)
    out = prepare_new_output_dir(destination, "Documentation")
    paths: dict[str, Path] = {}
    for name, content in rendered.items():
        path = out / name
        path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        paths[name] = path
    return paths
