"""Group project-intake modules into reviewable components (``speccanopy group``).

``project-intake`` produces one flat component per source module. An owner (or an
assistant, or the owner by delegation) then decides which modules belong together
and which requirements each group serves. This module applies that declared
decision from a small, strict ``groups.json`` and writes a design that feeds
``speccanopy design`` unchanged.

Grouping only restructures and maps. It never adds verification cases, evidence,
interfaces, data ownership or ``ready`` status, and it never decides who made the
decision: ``decided_by`` is recorded as declared, and only the value ``owner``
means owner-confirmed (even then, Speccanopy cannot verify the declaration).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from .exporters import check_new_output_dir, prepare_new_output_dir
from .fixtures import FixtureDesign
from .models import Identifier, NonEmptyText, SchemaModel, SystemBrief
from .project_intake import MAX_MODULES, IntakeObservations, ModuleObservation, _md
from .proposer import ComponentProposal

DecidedBy = Literal["owner", "owner_delegated", "assistant_proposed"]

MAX_GROUPS = MAX_MODULES
MAX_INPUT_BYTES = 1_000_000

_Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_Responsibility = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
_ModuleName = Annotated[str, StringConstraints(min_length=1, max_length=512)]

# How the decision basis is worded in each group proposal and in the review.
_RATIONALE = {
    "owner": (
        "Grouping declared in the groups file as decided by the owner (decided_by=owner). "
        "Speccanopy cannot verify who wrote the file or that the owner confirmed it."
    ),
    "owner_delegated": (
        "Owner delegated the grouping decision (decided_by=owner_delegated); "
        "the groups were not individually confirmed by the owner."
    ),
    "assistant_proposed": (
        "Grouping proposed by an assistant (decided_by=assistant_proposed); "
        "not confirmed by the owner."
    ),
}
_REVIEW_MEANING = {
    "owner": (
        "The groups file declares this grouping owner-confirmed. Speccanopy cannot verify "
        "who wrote the file or whether the owner confirmed it; it records the declaration."
    ),
    "owner_delegated": (
        "The owner delegated this grouping decision. The groups were not individually "
        "confirmed by the owner. This is NOT owner-confirmed."
    ),
    "assistant_proposed": (
        "The groups were proposed by an assistant. This is NOT owner-confirmed."
    ),
}


class GroupSpec(SchemaModel):
    id: Identifier
    name: _Name
    responsibility: _Responsibility
    modules: list[_ModuleName] = Field(min_length=1, max_length=MAX_MODULES)
    requirement_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_repeats(self) -> GroupSpec:
        for label, values in (("modules", self.modules), ("requirement_ids", self.requirement_ids)):
            repeated = sorted({v for v in values if values.count(v) > 1})
            if repeated:
                raise ValueError(f"Group {self.id} lists {label} more than once: {repeated}")
        return self


class GroupsFile(SchemaModel):
    schema_version: Literal[1]
    decided_by: DecidedBy
    groups: list[GroupSpec] = Field(min_length=1, max_length=MAX_GROUPS)

    @model_validator(mode="after")
    def _unique(self) -> GroupsFile:
        ids = [g.id for g in self.groups]
        repeated_ids = sorted({i for i in ids if ids.count(i) > 1})
        if repeated_ids:
            raise ValueError(f"Duplicate group IDs: {repeated_ids}")
        owner: dict[str, str] = {}
        for group in self.groups:
            for module in group.modules:
                if module in owner:
                    raise ValueError(
                        f"Module {module!r} is in more than one group "
                        f"({owner[module]}, {group.id}); a module belongs to exactly one group"
                    )
                owner[module] = group.id
        return self


@dataclass(frozen=True)
class IntakeInputs:
    brief: SystemBrief
    brief_text: str
    design: FixtureDesign
    design_sha256: str
    observations: IntakeObservations


@dataclass(frozen=True)
class GroupingResult:
    brief: SystemBrief
    brief_text: str
    fixture: FixtureDesign
    groups: GroupsFile
    groups_sha256: str
    design_sha256: str
    modules_by_group: dict[str, list[ModuleObservation]]
    ungrouped: list[ModuleObservation]
    allow_ungrouped: bool


def _read_bounded(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{label} is larger than {MAX_INPUT_BYTES} bytes; refusing to load it")
    return path.read_bytes()


def load_groups(path: str | Path) -> tuple[GroupsFile, str]:
    """Parse a groups file strictly. Returns the model and the file's SHA-256."""
    data = _read_bounded(Path(path), "Groups file")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Groups file is not valid UTF-8") from None
    return GroupsFile.model_validate_json(text), hashlib.sha256(data).hexdigest()


def load_intake(directory: str | Path) -> IntakeInputs:
    """Load and cross-check ``brief.json``, ``design.json`` and ``module-observations.json``."""
    folder = Path(directory)
    if not folder.is_dir():
        raise ValueError(f"Intake directory not found: {folder}")
    brief_bytes = _read_bounded(folder / "brief.json", "brief.json")
    design_bytes = _read_bounded(folder / "design.json", "design.json")
    obs_bytes = _read_bounded(folder / "module-observations.json", "module-observations.json")
    brief = SystemBrief.model_validate_json(brief_bytes)
    design = FixtureDesign.model_validate_json(design_bytes)
    observations = IntakeObservations.model_validate_json(obs_bytes)

    if set(design.proposals_by_parent) != {design.root.id}:
        raise ValueError(
            "design.json is not a flat intake design (modules directly under the root): "
            "it already has grouped or nested components. Group from a fresh project-intake output."
        )
    child_ids = [p.id for p in design.proposals_by_parent[design.root.id]]
    observed = [m.component_id for m in observations.modules]
    if sorted(child_ids) != sorted(observed):
        raise ValueError(
            "design.json and module-observations.json disagree on the module components; "
            "use the two files exactly as project-intake wrote them"
        )
    return IntakeInputs(
        brief=brief, brief_text=brief_bytes.decode("utf-8"), design=design,
        design_sha256=hashlib.sha256(design_bytes).hexdigest(), observations=observations,
    )


def _existing_ids(design: FixtureDesign) -> set[str]:
    ids = {design.root.id}
    ids |= {p.id for group in design.proposals_by_parent.values() for p in group}
    for records in (design.relationships, design.verification_cases, design.decisions, design.findings):
        ids |= {r.id for r in records}
    return ids


def _group_proposal(group: GroupSpec, decided_by: str, count: int) -> ComponentProposal:
    return ComponentProposal(
        id=group.id, name=group.name, responsibility=group.responsibility,
        boundary=(
            f"Logical grouping of {count} source module(s); "
            "not a deployment or runtime boundary."
        ),
        requirement_ids=list(group.requirement_ids),
        rationale=_RATIONALE[decided_by],
        assumptions=[
            f"Grouping basis: decided_by={decided_by}; see grouping-review.md.",
            "Module membership is a logical grouping, not a verified runtime boundary.",
        ],
        risks=["Interfaces, data ownership and verification evidence for this group are not yet documented."],
    )


def apply_grouping(
    intake_dir: str | Path, groups: GroupsFile, *, groups_sha256: str = "",
    allow_ungrouped: bool = False,
) -> GroupingResult:
    """Validate a grouping against an intake and build the grouped design (nothing is written)."""
    inputs = load_intake(intake_dir)
    design, brief, observations = inputs.design, inputs.brief, inputs.observations

    by_name: dict[str, list[ModuleObservation]] = {}
    for module in observations.modules:
        by_name.setdefault(module.module, []).append(module)
    proposals = {p.id: p for p in design.proposals_by_parent[design.root.id]}

    problems: list[str] = []
    clashes = sorted({g.id for g in groups.groups} & _existing_ids(design))
    if clashes:
        problems.append(f"Group IDs collide with existing component or relationship IDs: {clashes}")
    unknown_requirements = sorted(
        {rid for g in groups.groups for rid in g.requirement_ids} - brief.requirement_ids()
    )
    if unknown_requirements:
        problems.append(f"Unknown requirement IDs (not in the intake brief): {unknown_requirements}")
    unknown_modules = sorted({m for g in groups.groups for m in g.modules if m not in by_name})
    if unknown_modules:
        problems.append(f"Unknown modules (not in module-observations.json): {unknown_modules}")
    ambiguous = sorted({m for g in groups.groups for m in g.modules if len(by_name.get(m, ())) > 1})
    if ambiguous:
        problems.append(f"Ambiguous module names (several source files share them): {ambiguous}")

    grouped_names = {m for g in groups.groups for m in g.modules}
    ungrouped = [m for m in observations.modules if m.module not in grouped_names]
    if ungrouped and not allow_ungrouped:
        problems.append(
            f"{len(ungrouped)} module(s) are in no group: {[m.module for m in ungrouped]}. "
            "Add them to a group or pass --allow-ungrouped to keep them directly under the root."
        )

    node_count = 1 + len(groups.groups) + len(observations.modules)
    if node_count > brief.constraints.max_nodes:
        problems.append(
            f"The grouped tree needs {node_count} components (root + {len(groups.groups)} groups + "
            f"{len(observations.modules)} modules) but the brief's constraints.max_nodes is "
            f"{brief.constraints.max_nodes}. Budgets are not raised automatically; "
            "raise max_nodes in the brief yourself or use fewer groups."
        )
    if brief.constraints.max_depth < 2:
        problems.append(
            f"The grouped tree has depth 2 (root, group, module) but the brief's "
            f"constraints.max_depth is {brief.constraints.max_depth}. "
            "Budgets are not raised automatically."
        )
    if problems:
        raise ValueError("\n".join(problems))

    modules_by_group: dict[str, list[ModuleObservation]] = {}
    new_proposals: dict[str, list[ComponentProposal]] = {design.root.id: []}
    for group in groups.groups:
        members = [by_name[name][0] for name in group.modules]
        modules_by_group[group.id] = members
        new_proposals[design.root.id].append(_group_proposal(group, groups.decided_by, len(members)))
        new_proposals[group.id] = [proposals[m.component_id].model_copy(deep=True) for m in members]
    new_proposals[design.root.id].extend(
        proposals[m.component_id].model_copy(deep=True) for m in ungrouped
    )
    fixture = FixtureDesign(
        root=design.root.model_copy(deep=True), selected_style=design.selected_style,
        proposals_by_parent=new_proposals,
        relationships=[r.model_copy(deep=True) for r in design.relationships],
        verification_cases=[c.model_copy(deep=True) for c in design.verification_cases],
        decisions=[d.model_copy(deep=True) for d in design.decisions],
        findings=[f.model_copy(deep=True) for f in design.findings],
    )
    return GroupingResult(
        brief=brief, brief_text=inputs.brief_text, fixture=fixture, groups=groups,
        groups_sha256=groups_sha256, design_sha256=inputs.design_sha256,
        modules_by_group=modules_by_group, ungrouped=ungrouped, allow_ungrouped=allow_ungrouped,
    )


def _list(values: list[str]) -> str:
    return ", ".join(_md(v) for v in values) if values else "-"


def render_grouping_review(result: GroupingResult) -> str:
    groups, brief = result.groups, result.brief
    decided_by = groups.decided_by
    lines = [
        "# Module grouping review",
        "",
        "> Draft structure only. This grouping organizes the modules found by `project-intake` "
        "and maps requirements to groups. It is not verification, not an expert review and "
        "not an approval of the architecture.",
        "",
        "## Who decided",
        "",
        f"- decided_by: {_md(decided_by)} (recorded verbatim from the groups file)",
        f"- {_REVIEW_MEANING[decided_by]}",
        "- Only `owner` means owner-confirmed; `owner_delegated` and `assistant_proposed` are not.",
        f"- System: {_md(brief.system)}",
        f"- Groups file SHA-256: {result.groups_sha256 or 'not recorded'}",
        f"- Intake design.json SHA-256: {result.design_sha256}",
        "",
        "## Groups",
        "",
        f"{len(groups.groups)} group(s) over "
        f"{sum(len(m) for m in result.modules_by_group.values())} module(s).",
        "",
        "| Group ID | Name | Modules | Requirements |",
        "| --- | --- | --- | --- |",
    ]
    for group in groups.groups:
        names = [m.module for m in result.modules_by_group[group.id]]
        lines.append("| " + " | ".join([
            _md(group.id), _md(group.name), _list(names), _list(group.requirement_ids),
        ]) + " |")
    lines.append("")
    for group in groups.groups:
        lines += [f"### {_md(group.name)} ({_md(group.id)})", "",
                  f"- Responsibility: {_md(group.responsibility)}",
                  f"- Modules: {_list([m.module for m in result.modules_by_group[group.id]])}",
                  f"- Requirements: {_list(group.requirement_ids)}", ""]

    lines += ["## Ungrouped modules", ""]
    if result.ungrouped:
        lines.append("These modules were left directly under the root (`--allow-ungrouped`):")
        lines.append("")
        lines += [f"- {_md(m.module)}" for m in result.ungrouped]
    else:
        lines.append("None. Every module is in a group.")
    lines.append("")

    requirements = [*brief.functional_requirements, *brief.quality_requirements]
    mapped_to: dict[str, list[str]] = {r.id: [] for r in requirements}
    for group in groups.groups:
        for rid in group.requirement_ids:
            mapped_to[rid].append(group.id)
    lines += ["## Requirement mapping", "",
              "| Requirement | Statement | Mapped to groups |", "| --- | --- | --- |"]
    for req in requirements:
        lines.append("| " + " | ".join([_md(req.id), _md(req.statement), _list(mapped_to[req.id])]) + " |")
    lines += ["", "## Requirements mapped to no group", ""]
    unmapped = [r.id for r in requirements if not mapped_to[r.id]]
    if unmapped:
        lines += [f"- {_md(rid)}" for rid in unmapped]
    else:
        lines.append("None. Every requirement is mapped to at least one group.")
    lines.append("")

    root_children = len(groups.groups) + len(result.ungrouped)
    crowded = [(g.id, len(result.modules_by_group[g.id])) for g in groups.groups
               if len(result.modules_by_group[g.id]) > 10]
    if root_children > 10:
        crowded.insert(0, (result.fixture.root.id, root_children))
    if crowded:
        lines += ["## Size notes", "",
                  "`speccanopy design` records a medium finding for any component with more than "
                  "10 children, so consider splitting these:", ""]
        lines += [f"- {_md(cid)}: {n} children (more than 10)" for cid, n in crowded]
        lines.append("")

    lines += [
        "## Not done by this command (owner work)", "",
        "- No verification cases or evidence were added. A mandatory requirement counts as "
        "planned or verified only when a verification case links it to a component that owns it, "
        "so requirements mapped here still show as uncovered until the owner adds those cases.",
        "- No interfaces, data ownership, quality targets or stop rationale were added.",
        "- No component was marked `ready`; `speccanopy design` will report them as "
        "`requires_review`.",
        "- Group membership is a logical grouping of source modules, not a deployment or "
        "runtime boundary.",
        "", "## Next step", "",
        "Review the groups, then build the draft:",
        "",
        "```bash",
        "speccanopy design OUTPUT/brief.json --fixture OUTPUT/design.json --output OUTPUT-design",
        "```",
        "",
    ]
    return "\n".join(lines)


def export_grouping(result: GroupingResult, destination: str | Path) -> dict[str, Path]:
    """Write ``brief.json``, ``design.json`` and ``grouping-review.md`` to a new or empty directory."""
    check_new_output_dir(destination, "Grouping")
    content = {
        "brief.json": result.brief_text,
        "design.json": result.fixture.model_dump_json(indent=2) + "\n",
        "grouping-review.md": render_grouping_review(result),
    }
    out = prepare_new_output_dir(destination, "Grouping")
    saved: dict[str, Path] = {}
    for name, text in content.items():
        path = out / name
        path.write_text(text, encoding="utf-8")
        saved[name] = path
    return saved
