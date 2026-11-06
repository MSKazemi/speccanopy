"""Structural comparison of two ``project-intake`` module observations.

``source-diff`` and ``source-impact`` compare bytes: any edit, even a comment,
changes a SHA-256 digest and marks every claim about that file stale. This
module answers the complementary question "did the *static module and import
structure* change, or only file contents?" by comparing two parsed
``module-observations.json`` documents. It is pure and deterministic: it reads
no source files, imports or executes nothing, and makes no network calls.

What a comparison can and cannot say:

* Modules are matched by module *name* (derived from the file path by the
  intake). Component IDs are hashes of the path and may differ between runs;
  they are reported as a mapping, never used to match. **Renames are not
  inferred**: a renamed or moved module is one ``removed`` module plus one
  ``added`` module, and its import edges follow the old and new names.
* Edges are static ``import`` declarations between modules inside the observed
  set (``internal_imports``). Import line numbers, conditional imports,
  dynamic imports and imports of anything outside the observed set are not
  represented. An edge present in both snapshots is ``kept`` even if the import
  statement moved.
* Per kept module, only top-level function and class *names* are compared (as
  sets). Signatures, bodies, decorators, nesting, ordering and duplicate names
  are invisible. The intake records at most 30 functions and 30 classes per
  module and counts the rest in ``symbols_omitted``; modules where either side
  omitted symbols are listed in ``incomplete_symbol_modules`` and their name
  comparison is incomplete.
* A module whose bytes changed but whose names and edges did not is reported
  with ``source_bytes_changed`` and does **not** count as a structural change.
* A different set of observed modules can also come from a different scan
  scope (size limit, allowlist); skipped-oversized counts are shown, but scope
  equality is not verified and the two intakes carry no project identity.
* Identical structure does not mean identical behaviour, and changed structure
  does not mean changed architecture. Nothing is verified.

The output is deterministic: identical inputs give byte-identical JSON and
Markdown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .documentation import _md
from .exporters import check_new_output_dir, prepare_new_output_dir
from .models import Identifier, NonEmptyText, SchemaModel
from .project_intake import IntakeObservations, ModuleObservation

ModuleStatus = Literal["added", "removed", "kept"]
EdgeStatus = Literal["added", "removed", "kept"]

INPUT_FILENAME = "module-observations.json"
_MAX_INPUT_BYTES = 20_000_000
_SHA = r"^[0-9a-f]{64}$"
_CAVEAT = (
    "This compares static syntax only: module names, static internal import "
    "declarations and top-level function/class names taken from two intake "
    "runs. Identical structure does not mean identical behaviour, and changed "
    "structure does not mean changed architecture. Module renames are not "
    "inferred. Nothing here is verified, and the intakes carry no project "
    "identity."
)


class ModuleDelta(SchemaModel):
    module: NonEmptyText
    status: ModuleStatus
    before_component_id: Identifier | None = None
    after_component_id: Identifier | None = None
    before_source_path: NonEmptyText | None = None
    after_source_path: NonEmptyText | None = None
    before_sha256: str | None = Field(default=None, pattern=_SHA)
    after_sha256: str | None = Field(default=None, pattern=_SHA)
    functions_added: list[str] = Field(default_factory=list)
    functions_removed: list[str] = Field(default_factory=list)
    classes_added: list[str] = Field(default_factory=list)
    classes_removed: list[str] = Field(default_factory=list)
    before_symbols_omitted: int | None = Field(default=None, ge=0)
    after_symbols_omitted: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def consistent(self) -> ModuleDelta:
        before = (self.before_component_id, self.before_source_path,
                  self.before_sha256, self.before_symbols_omitted)
        after = (self.after_component_id, self.after_source_path,
                 self.after_sha256, self.after_symbols_omitted)
        has_before = all(x is not None for x in before)
        has_after = all(x is not None for x in after)
        none_before = all(x is None for x in before)
        none_after = all(x is None for x in after)
        ok = {"added": none_before and has_after,
              "removed": has_before and none_after,
              "kept": has_before and has_after}[self.status]
        if not ok:
            raise ValueError(f"Module delta fields are inconsistent with status '{self.status}'")
        for name in ("functions_added", "functions_removed", "classes_added", "classes_removed"):
            values = getattr(self, name)
            if values != sorted(set(values)):
                raise ValueError(f"Module delta '{name}' must be unique and sorted")
            if values and self.status != "kept":
                raise ValueError("Symbol changes are only recorded for kept modules")
        return self

    @property
    def source_bytes_changed(self) -> bool | None:
        if self.status != "kept":
            return None
        return self.before_sha256 != self.after_sha256

    @property
    def symbols_omitted_changed(self) -> bool:
        return (self.status == "kept"
                and self.before_symbols_omitted != self.after_symbols_omitted)

    @property
    def source_path_changed(self) -> bool:
        return self.status == "kept" and self.before_source_path != self.after_source_path

    @property
    def component_id_changed(self) -> bool:
        return self.status == "kept" and self.before_component_id != self.after_component_id

    @property
    def structure_changed(self) -> bool:
        if self.status != "kept":
            return True
        return bool(self.functions_added or self.functions_removed
                    or self.classes_added or self.classes_removed
                    or self.symbols_omitted_changed or self.source_path_changed)

    @property
    def symbols_incomplete(self) -> bool:
        return (self.status == "kept"
                and bool(self.before_symbols_omitted or self.after_symbols_omitted))


class EdgeDelta(SchemaModel):
    source: NonEmptyText
    target: NonEmptyText
    status: EdgeStatus


class StructureDiff(SchemaModel):
    schema_version: Literal[1] = 1
    modules: list[ModuleDelta]
    edges: list[EdgeDelta]
    added_modules: list[str]
    removed_modules: list[str]
    kept_modules: list[str]
    incomplete_symbol_modules: list[str]
    before_skipped_oversized_files: int = Field(ge=0)
    after_skipped_oversized_files: int = Field(ge=0)
    structure_changed: bool
    renames_inferred: Literal[False] = False
    caveat: str = _CAVEAT

    @model_validator(mode="after")
    def consistent(self) -> StructureDiff:
        names = [m.module for m in self.modules]
        if names != sorted(set(names)):
            raise ValueError("Module deltas must have unique names sorted by name")
        for status, attr in (("added", "added_modules"), ("removed", "removed_modules"),
                             ("kept", "kept_modules")):
            if getattr(self, attr) != [m.module for m in self.modules if m.status == status]:
                raise ValueError(f"Diff '{attr}' list does not match its module deltas")
        if self.incomplete_symbol_modules != [
                m.module for m in self.modules if m.symbols_incomplete]:
            raise ValueError("Diff incomplete_symbol_modules does not match its module deltas")
        keys = [(e.source, e.target) for e in self.edges]
        if keys != sorted(set(keys)):
            raise ValueError("Edge deltas must be unique and sorted by (source, target)")
        status_of = {m.module: m.status for m in self.modules}
        for edge in self.edges:
            ends = [status_of.get(edge.source), status_of.get(edge.target)]
            if None in ends:
                raise ValueError("An edge references a module that is not in the module deltas")
            if edge.source == edge.target:
                raise ValueError("A module cannot import itself in this report")
            if edge.status == "kept" and any(s != "kept" for s in ends):
                raise ValueError("A kept edge must connect two kept modules")
            if edge.status == "added" and "removed" in ends:
                raise ValueError("An added edge cannot touch a removed module")
            if edge.status == "removed" and "added" in ends:
                raise ValueError("A removed edge cannot touch an added module")
        if self.structure_changed != self.computed_structure_changed:
            raise ValueError(
                "structure_changed does not match the module and edge deltas")
        if self.caveat != _CAVEAT:
            raise ValueError("The fixed structure-diff caveat must not be altered")
        return self

    @property
    def computed_structure_changed(self) -> bool:
        return (any(m.structure_changed for m in self.modules)
                or any(e.status != "kept" for e in self.edges))

    @property
    def edges_added(self) -> list[EdgeDelta]:
        return [e for e in self.edges if e.status == "added"]

    @property
    def edges_removed(self) -> list[EdgeDelta]:
        return [e for e in self.edges if e.status == "removed"]

    @property
    def edges_kept(self) -> list[EdgeDelta]:
        return [e for e in self.edges if e.status == "kept"]


def _edge_set(observations: IntakeObservations, label: str) -> set[tuple[str, str]]:
    names = {m.module for m in observations.modules}
    if len(names) != len(observations.modules):
        raise ValueError(f"{label} observations contain duplicate module names")
    if len({m.component_id for m in observations.modules}) != len(observations.modules):
        raise ValueError(f"{label} observations contain duplicate component IDs")
    edges: set[tuple[str, str]] = set()
    for module in observations.modules:
        for target in module.internal_imports:
            if target not in names:
                raise ValueError(
                    f"{label} observations: '{module.module}' imports '{target}', "
                    "which is not an observed module")
            if target == module.module:
                raise ValueError(f"{label} observations: '{module.module}' imports itself")
            edges.add((module.module, target))
    return edges


def _module_delta(old: ModuleObservation | None, new: ModuleObservation | None) -> ModuleDelta:
    name = (new or old).module  # type: ignore[union-attr]
    fields: dict[str, object] = {}
    if old is not None:
        fields.update(before_component_id=old.component_id, before_source_path=old.source_path,
                      before_sha256=old.sha256, before_symbols_omitted=old.symbols_omitted)
    if new is not None:
        fields.update(after_component_id=new.component_id, after_source_path=new.source_path,
                      after_sha256=new.sha256, after_symbols_omitted=new.symbols_omitted)
    status: ModuleStatus = "kept" if old and new else ("added" if new else "removed")
    if old is not None and new is not None:
        fields.update(
            functions_added=sorted(set(new.functions) - set(old.functions)),
            functions_removed=sorted(set(old.functions) - set(new.functions)),
            classes_added=sorted(set(new.classes) - set(old.classes)),
            classes_removed=sorted(set(old.classes) - set(new.classes)),
        )
    return ModuleDelta(module=name, status=status, **fields)  # type: ignore[arg-type]


def compare_module_observations(
    before: IntakeObservations, after: IntakeObservations,
) -> StructureDiff:
    """Compare two parsed intake observations by module name. Pure; reads no files."""
    old_edges = _edge_set(before, "Before")
    new_edges = _edge_set(after, "After")
    old = {m.module: m for m in before.modules}
    new = {m.module: m for m in after.modules}
    modules = [_module_delta(old.get(n), new.get(n)) for n in sorted(old.keys() | new.keys())]
    edges = [
        EdgeDelta(source=s, target=t,
                  status="kept" if (s, t) in old_edges and (s, t) in new_edges
                  else ("added" if (s, t) in new_edges else "removed"))
        for s, t in sorted(old_edges | new_edges)
    ]
    return StructureDiff(
        modules=modules, edges=edges,
        added_modules=[m.module for m in modules if m.status == "added"],
        removed_modules=[m.module for m in modules if m.status == "removed"],
        kept_modules=[m.module for m in modules if m.status == "kept"],
        incomplete_symbol_modules=[m.module for m in modules if m.symbols_incomplete],
        before_skipped_oversized_files=before.skipped_oversized_files,
        after_skipped_oversized_files=after.skipped_oversized_files,
        structure_changed=(any(m.structure_changed for m in modules)
                           or any(e.status != "kept" for e in edges)),
    )


def load_module_observations(source: str | Path) -> IntakeObservations:
    """Load ``module-observations.json`` from that file or from an intake directory."""
    path = Path(source)
    if path.is_dir():
        path = path / INPUT_FILENAME
    if not path.is_file():
        raise ValueError(f"No {INPUT_FILENAME} found at {source}")
    if path.stat().st_size > _MAX_INPUT_BYTES:
        raise ValueError(f"{path} is larger than {_MAX_INPUT_BYTES} bytes; refusing to load it")
    return IntakeObservations.model_validate_json(path.read_text(encoding="utf-8"))


def _items(values: list[str]) -> str:
    return ", ".join(_md(v) for v in values) if values else "-"


def _table(headings: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headings) + " |",
             "| " + " | ".join("---" for _ in headings) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render_structure_diff_markdown(diff: StructureDiff) -> str:
    kept = [m for m in diff.modules if m.status == "kept"]
    out: list[str] = [
        "# Static structure comparison",
        "",
        "> **Static syntax only. Not behavioural or architectural verification.**",
        "",
        _md(diff.caveat),
        "",
        "## Result",
        "",
        f"Structure changed: **{'yes' if diff.structure_changed else 'no'}**.",
        "",
        f"- Modules: {len(diff.added_modules)} added, {len(diff.removed_modules)} removed, "
        f"{len(diff.kept_modules)} kept",
        f"- Import edges: {len(diff.edges_added)} added, {len(diff.edges_removed)} removed, "
        f"{len(diff.edges_kept)} kept",
        f"- Kept modules with name changes or other structural changes: "
        f"{sum(1 for m in kept if m.structure_changed)}",
        f"- Kept modules whose bytes changed: {sum(1 for m in kept if m.source_bytes_changed)}",
        f"- Kept modules whose bytes changed but structure did not: "
        f"{sum(1 for m in kept if m.source_bytes_changed and not m.structure_changed)}",
        "- Module renames are not inferred: a rename appears as one removed and one added module.",
        f"- Skipped oversized files: before {diff.before_skipped_oversized_files}, "
        f"after {diff.after_skipped_oversized_files}",
    ]
    for heading, names in (("Added modules", diff.added_modules),
                           ("Removed modules", diff.removed_modules)):
        out += ["", f"## {heading}", ""]
        out.extend(["- " + _md(n) for n in names] or ["None."])
    for heading, edges in (("Added import edges", diff.edges_added),
                           ("Removed import edges", diff.edges_removed)):
        out += ["", f"## {heading}", ""]
        out.extend([f"- {_md(e.source)} -> {_md(e.target)}" for e in edges] or ["None."])
    out += ["", "## Kept import edges", "",
            f"{len(diff.edges_kept)} edge(s) are present in both snapshots. The full list "
            "is in structure-diff.json."]
    out += ["", "## Kept modules with structural changes", ""]
    changed = [m for m in kept if m.structure_changed]
    if changed:
        out.append(_table(
            ["Module", "Functions added", "Functions removed", "Classes added",
             "Classes removed", "Omitted symbols (before/after)", "Source path changed"],
            [[_md(m.module), _items(m.functions_added), _items(m.functions_removed),
              _items(m.classes_added), _items(m.classes_removed),
              f"{m.before_symbols_omitted}/{m.after_symbols_omitted}",
              "yes" if m.source_path_changed else "no"] for m in changed]))
    else:
        out.append("None.")
    out += ["", "## Kept modules with byte changes only", ""]
    churn = [m for m in kept if m.source_bytes_changed and not m.structure_changed]
    out.extend(["- " + _md(m.module) for m in churn] or ["None."])
    out += ["", "## Component ID mapping (kept modules)", "",
            "Component IDs are derived from file paths by each intake run and are not "
            "used for matching; modules are matched by name."]
    if kept:
        out += ["", _table(
            ["Module", "Before component ID", "After component ID", "Differs"],
            [[_md(m.module), _md(m.before_component_id), _md(m.after_component_id),
              "yes" if m.component_id_changed else "no"] for m in kept])]
    else:
        out += ["", "None."]
    out += ["", "## Incomplete symbol comparison", ""]
    if diff.incomplete_symbol_modules:
        out.append("The intake omits symbols beyond 30 functions and 30 classes per module; "
                   "name comparison is incomplete for these kept modules:")
        out += [""] + ["- " + _md(n) for n in diff.incomplete_symbol_modules]
    else:
        out.append("None.")
    return "\n".join(out) + "\n"


def export_structure_diff(diff: StructureDiff, destination: str | Path) -> dict[str, Path]:
    """Write structure-diff.json and structure-diff.md into a new or empty real directory."""
    check_new_output_dir(destination, "Structure diff")
    contents = {
        "structure-diff.json": json.dumps(diff.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        "structure-diff.md": render_structure_diff_markdown(diff),
    }
    out = prepare_new_output_dir(destination, "Structure diff")
    paths: dict[str, Path] = {}
    for name, content in contents.items():
        path = out / name
        path.write_text(content, encoding="utf-8")
        paths[name] = path
    return paths
