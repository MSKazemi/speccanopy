"""Bounded, offline Python AST intake for provisional architecture documentation.

No target imports/execution/network calls. Reads allowlisted local Python files,
records only module metadata and syntax-level imports, and preserves review gaps.
User supplies all business goals/requirements, which are NOT inferred from code.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import html
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field

from .fixtures import FixtureDesign
from .models import Component, DesignConstraints, FunctionalRequirement, Identifier, NonEmptyText, Relationship, SchemaModel, SystemBrief
from .proposer import ComponentProposal
from .source_evidence import SourceClaim, SourceEvidence, SourceInventory, read_safe_source_bytes, scan_sources

MAX_MODULES = 50


class ModuleObservation(SchemaModel):
    component_id: Identifier
    module: NonEmptyText
    source_path: NonEmptyText
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    functions: list[str]
    classes: list[str]
    symbols_omitted: int = Field(ge=0)
    internal_imports: list[str]


class IntakeObservations(SchemaModel):
    status: Literal["provisional_requires_owner_review"] = "provisional_requires_owner_review"
    method: Literal["python_ast_static_imports"] = "python_ast_static_imports"
    modules: list[ModuleObservation]
    dependencies: list[Relationship]
    excluded_non_python_source: list[str]
    skipped_oversized_files: int = Field(ge=0)
    limitations: list[str] = Field(default_factory=lambda: [
        "No application source was imported, run, tested, or sent to a model.",
        "Static Python imports do not establish actual runtime calls.",
        "Module boundaries are candidate components, not certified architecture.",
        "Functional requirements are user-supplied and not mapped automatically.",
        "Interfaces, owned data, style, and implementation verification remain unknown.",
        "Source hash matches prove file-byte equality, not semantic correctness.",
        "Only allowlisted bounded Python .py modules were analyzed.",
    ])


@dataclass(frozen=True)
class IntakeResult:
    brief: SystemBrief
    fixture: FixtureDesign
    evidence: SourceEvidence
    inventory: SourceInventory
    observations: IntakeObservations


def _id(prefix: str, key: str) -> str:
    return prefix + hashlib.sha256(key.encode("utf-8")).hexdigest()[:14]


def _module(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if len(parts) > 1 and parts[0] == "src":
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "root_package"


def _base_for_relative(module: str, path: str, level: int) -> str:
    package = module if PurePosixPath(path).name == "__init__.py" else module.rpartition(".")[0]
    parts = package.split(".") if package else []
    if level > len(parts):
        return ""
    return ".".join(parts[:len(parts) - level + 1])


def _import_edges(tree: ast.Module, module: str, path: str, known: set[str]) -> dict[str, int]:
    links: dict[str, int] = {}
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Import):
            targets = [n.name for n in node.names if n.name in known]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _base_for_relative(module, path, node.level)
                if not base:
                    continue
                base = ".".join(x for x in (base, node.module or "") if x)
            else:
                base = node.module or ""
            for alias in node.names:
                value = base + "." + alias.name if alias.name != "*" else base
                if value in known:
                    targets.append(value)
            if base in known and not targets:
                targets.append(base)
        for target in targets:
            if target != module:
                links[target] = min(links.get(target, node.lineno), node.lineno)
    return links


def prepare_project_intake(
    project_root: str | Path, *,
    system: str, goal: str, requirements: list[str],
    max_modules: int = 30, max_files: int = 2000,
    max_file_bytes: int = 1_000_000,
) -> IntakeResult:
    """Produce a reviewable fixture and syntax-only evidence, never verified design."""
    if not 1 <= max_modules <= MAX_MODULES:
        raise ValueError("max_modules must be between 1 and 50")
    if not system.strip() or not goal.strip() or not requirements or any(
        not req.strip() for req in requirements
    ):
        raise ValueError("Supply --system, --goal, and at least one --requirement")
    if len(requirements) > 99:
        raise ValueError("At most 99 user requirements are supported")
    root = Path(project_root)
    inventory = scan_sources(root, max_files=max_files, max_bytes=max_file_bytes)
    selected = [x for x in inventory.files if x.path.endswith(".py") and x.kind == "source"]
    if not selected:
        raise ValueError("No Python source modules found. This intake supports Python .py only.")
    if len(selected) > max_modules:
        raise ValueError(
            f"Found {len(selected)} Python modules, exceeding --max-modules={max_modules}; "
            "choose a smaller subtree or increase the limit."
        )
    by_module = {_module(f.path): f for f in selected}
    if len(by_module) != len(selected):
        raise ValueError("Ambiguous Python module names; select a narrower source directory")
    files = {f.path: f for f in selected}
    ids = {f.path: _id("mod_", f.path) for f in selected}
    if len(set(ids.values())) != len(ids):
        raise ValueError("Hashed component ID collision")
    syntax: dict[str, ast.Module] = {}
    for file in selected:
        data = read_safe_source_bytes(root, file.path, byte_limit=max_file_bytes)
        if hashlib.sha256(data).hexdigest() != file.sha256:
            raise ValueError(f"File changed during scanning: {file.path}")
        try:
            syntax[file.path] = ast.parse(data, filename=file.path)
        except (SyntaxError, RecursionError, UnicodeError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            where = f" at line {line}" if line else ""
            raise ValueError(f"Cannot safely parse Python module {file.path}{where}") from None
    brief = SystemBrief(
        system=system.strip(), goals=[goal.strip()],
        functional_requirements=[
            FunctionalRequirement(id=f"FR-USER-{i:03d}", statement=s.strip(), mandatory=True)
            for i, s in enumerate(requirements, 1)
        ],
        constraints=DesignConstraints(
            max_depth=3, max_nodes=max(20, len(selected) + 1),
            max_refinement_rounds=2,
        ),
    )
    root_component = Component(
        id="system", name=brief.system,
        responsibility="Provisional grouping of Python source modules for owner review.",
        boundary="Draft documentation scope; no deployment boundary was observed.",
        assumptions=[
            "The source-module grouping may not match true architectural responsibilities.",
            "User-provided requirements are not mapped automatically to implementation.",
        ],
        status="proposed",
    )
    proposals: list[ComponentProposal] = []
    observations: list[ModuleObservation] = []
    claims: list[SourceClaim] = []
    imports: dict[str, dict[str, int]] = {}
    for path in sorted(files):
        file = files[path]
        name = _module(path)
        ast_tree = syntax[path]
        links = _import_edges(ast_tree, name, path, set(by_module))
        imports[path] = links
        funcs = [node.name for node in ast_tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [node.name for node in ast_tree.body if isinstance(node, ast.ClassDef)]
        observations.append(ModuleObservation(
            component_id=ids[path], module=name, source_path=path,
            sha256=file.sha256, functions=funcs[:30], classes=classes[:30],
            symbols_omitted=max(0, len(funcs) - 30) + max(0, len(classes) - 30),
            internal_imports=sorted(links),
        ))
        proposals.append(ComponentProposal(
            id=ids[path], name="Python module " + name,
            responsibility=f"Candidate module boundary for {name}; business role unverified.",
            boundary=f"Observed Python file {path}, not a verified runtime service boundary.",
            rationale="Observed module declaration is a structural proposal; owner must assess grouping.",
            assumptions=["Static module imports do not confirm actual runtime interactions."],
            risks=["Interfaces, data ownership, and requirement coverage are not yet documented."],
        ))
        claims.append(SourceClaim(
            architecture_id=ids[path], source_path=path, sha256=file.sha256,
            assertion=f"AST parsed Python module {name} at this path; semantic role unknown.",
            basis="observed",
            line_start=1 if file.line_count else None,
            line_end=1 if file.line_count else None,
        ))
    edges = []
    for path in sorted(files):
        source = files[path]
        for target in sorted(imports[path]):
            target_file = by_module[target]
            rel_id = _id("dep_", path + "\0" + target_file.path)
            edges.append(Relationship(
                id=rel_id, source_id=ids[path], target_id=ids[target_file.path],
                kind="dependency",
                description=(
                    f"AST import declaration from {_module(path)} to {target}; "
                    "could be conditional and is not a verified runtime call."
                ),
            ))
            line = imports[path][target]
            claims.append(SourceClaim(
                architecture_id=rel_id, source_path=path, sha256=source.sha256,
                assertion=f"AST import declaration names module {target}.",
                basis="observed", line_start=line, line_end=line,
            ))
    if len({edge.id for edge in edges}) != len(edges):
        raise ValueError("Hashed dependency ID collision")
    fixture = FixtureDesign(
        root=root_component, proposals_by_parent={"system": proposals},
        relationships=edges,
    )
    report = IntakeObservations(
        modules=observations, dependencies=edges,
        excluded_non_python_source=[
            f.path for f in inventory.files
            if f.kind in {"source", "schema"} and f.path not in files
        ],
        skipped_oversized_files=inventory.skipped_oversized,
    )
    return IntakeResult(
        brief=brief, fixture=fixture, evidence=SourceEvidence(claims=claims),
        inventory=inventory, observations=report,
    )


def _md(value: object) -> str:
    text = html.escape(" ".join(str(value).split()), quote=False)
    for character in ("\\", "|", "*", "_", chr(96), "[", "]"):
        text = text.replace(character, "\\" + character)
    return text


def _report(result: IntakeResult) -> str:
    obs = result.observations
    lines = [
        "# Provisional Python project architecture intake",
        "",
        "> Owner review required. This report records syntax-level module/import "
        "observations and candidate boundaries. No code was executed and no "
        "business architecture, security, or production behavior was verified.",
        "",
        "## Supplied project intent",
        "",
        "- System: " + _md(result.brief.system),
        "- Goal: " + _md(result.brief.goals[0]),
        f"- User-supplied requirements: {len(result.brief.functional_requirements)}",
        "",
        "## Static analysis",
        "",
        f"- Modules parsed: {len(obs.modules)}",
        f"- Import dependencies detected: {len(obs.dependencies)}",
        f"- Non-Python source/schema files NOT analyzed: {len(obs.excluded_non_python_source)}",
        f"- Oversized inventory files skipped: {obs.skipped_oversized_files}",
        "",
        "| Component ID | Python module | Project-relative file | Top-level symbols | Internal imports |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in obs.modules:
        names = item.functions + item.classes
        symbols = ", ".join(names) or "None"
        if item.symbols_omitted:
            symbols += f" ({item.symbols_omitted} more names omitted)"
        values = [
            item.component_id, item.module, item.source_path,
            symbols, ", ".join(item.internal_imports) or "None",
        ]
        lines.append("| " + " | ".join(_md(x) for x in values) + " |")
    lines.extend(["", "## Other allowlisted source files NOT analyzed", ""])
    lines += ["- " + _md(x) for x in obs.excluded_non_python_source] or [
        "No non-Python source/schema files were identified in the inventory."
    ]
    lines.extend(["", "## Human and Claude Code review checklist", "",
        "- [ ] Confirm module boundaries represent useful architecture components.",
        "- [ ] Confirm roles, user actors, and business requirements with the owner.",
        "- [ ] Map real requirements to the correct source-backed components.",
        "- [ ] Analyze interfaces, data ownership, runtime behavior, external dependencies.",
        "- [ ] Add appropriate architecture style choices, decisions and quality scenarios.",
        "- [ ] Verify dynamic imports, conditional imports, and unsupported languages.",
        "- [ ] Run design, review and document with this draft and its source map.",
        "- [ ] Preserve unverified statuses; do not invent completed tests or expert reviews.",
        "", "## Research and evidence limitations", "",
    ])
    lines.extend("- " + _md(x) for x in obs.limitations)
    return "\n".join(lines) + "\n"


def export_project_intake(result: IntakeResult, destination: str | Path) -> dict[str, Path]:
    """Only create new/empty destination; never silently replace edited documents."""
    out = Path(destination)
    if out.is_symlink() or (out.exists() and (not out.is_dir() or any(out.iterdir()))):
        raise ValueError("Intake output must be a new or empty directory")
    content = {
        "brief.json": result.brief.model_dump_json(indent=2) + "\n",
        "design.json": result.fixture.model_dump_json(indent=2) + "\n",
        "source-evidence.json": result.evidence.model_dump_json(indent=2) + "\n",
        "source-inventory.json": result.inventory.model_dump_json(indent=2) + "\n",
        "module-observations.json": result.observations.model_dump_json(indent=2) + "\n",
        "intake-review.md": _report(result),
    }
    out.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    for name, text in content.items():
        path = out / name
        path.write_text(text, encoding="utf-8")
        saved[name] = path
    return saved
