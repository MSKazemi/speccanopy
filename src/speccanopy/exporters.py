"""Deterministic architecture exports: documents are drafts, not application code."""

from __future__ import annotations

import json
from pathlib import Path

from .decomposer import GenerationResult
from .models import ArchitectureSpec


def _escape_mermaid_label(value: str) -> str:
    return value.replace("\"", "#quot;").replace("\r", " ").replace("\n", " ")


def to_mermaid(spec: ArchitectureSpec) -> str:
    """Simple containment diagram using safe generated identifiers."""
    ids = {node.id: f"N{i}" for i, node in enumerate(spec.components)}
    lines = ["flowchart TD"]
    for node in spec.components:
        label = _escape_mermaid_label(f"{node.name} [{node.status}]")
        lines.append(f'    {ids[node.id]}["{label}"]')
    for node in spec.components:
        if node.parent_id is not None:
            lines.append(f"    {ids[node.parent_id]} --> {ids[node.id]}")
    return "\n".join(lines) + "\n"


def relationships_mermaid(spec: ArchitectureSpec) -> str:
    """Typed interaction graph separate from the containment tree."""
    ids = {node.id: f"N{i}" for i, node in enumerate(spec.components)}
    lines = ["flowchart LR"]
    for node in spec.components:
        label = _escape_mermaid_label(node.name)
        lines.append(f'    {ids[node.id]}["{label}"]')
    for relation in spec.relationships:
        label = relation.kind.replace("_", " ")
        lines.append(f'    {ids[relation.source_id]} -->|"{label}"| {ids[relation.target_id]}')
    return "\n".join(lines) + "\n"


def check_new_output_dir(destination: str | Path, label: str) -> Path:
    """Raise unless ``destination`` is absent or an empty real directory. No side effects.

    Refuses symlinks (including dangling ones), regular files and non-empty
    directories, so hand-edited owner files are never replaced or mixed with
    generated artifacts. Best-effort: only the final path component is checked
    for a symlink, and a concurrent local writer could still race the check.
    """
    out = Path(destination)
    if out.is_symlink() or (out.exists() and (not out.is_dir() or any(out.iterdir()))):
        raise ValueError(
            f"{label} output must be a new or empty directory; existing files not overwritten"
        )
    return out


def check_new_output_file(destination: str | Path, label: str) -> Path:
    """Raise if ``destination`` already exists or is a symlink (dangling included). No side effects."""
    out = Path(destination)
    if out.is_symlink() or out.exists():
        raise ValueError(f"{label} output must be a new file; existing files not overwritten")
    return out


def prepare_new_output_dir(destination: str | Path, label: str) -> Path:
    """Check with :func:`check_new_output_dir`, then create the directory."""
    out = check_new_output_dir(destination, label)
    out.mkdir(parents=True, exist_ok=True)
    return out


def export_generation(
    result: GenerationResult, destination: str | Path, *,
    generator: str = "deterministic-fixture",
    note: str = "Curated proposals and design-level verification plans; not AI-generated or independently validated.",
) -> dict[str, Path]:
    out = prepare_new_output_dir(destination, "Architecture")
    spec = result.architecture
    report = spec.coverage_report()
    owners = {rid: sorted(c.id for c in spec.components if rid in c.requirement_ids)
              for rid in sorted(spec.brief.requirement_ids())}
    items = {
        "architecture.json": json.loads(spec.model_dump_json()),
        "architecture.mmd": to_mermaid(spec),
        "relationships.mmd": relationships_mermaid(spec),
        "requirements-report.json": {"coverage": report.model_dump(), "component_owners": owners,
                                     "status": spec.status},
        "decisions.json": {"selected_style": spec.selected_style,
                           "decisions": [x.model_dump() for x in spec.decisions],
                           "findings": [x.model_dump() for x in spec.findings]},
        "generation-trace.json": {"generator": generator, "statistics": result.stats(),
                                  "events": [x.model_dump() for x in result.trace],
                                  "note": note},
    }
    paths: dict[str, Path] = {}
    for name, value in items.items():
        path = out / name
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths[name] = path
    return paths
