"""Metadata-only comparison of two local source inventories.

This module compares two :class:`~speccanopy.source_evidence.SourceInventory`
snapshots by relative path and SHA-256 digest. It never reads source file
contents, never touches a scanned project, never executes or imports target
code and makes no network calls.

What a comparison can and cannot say:

* Equal digest for a path means the *bytes* are equal. A different digest means
  the bytes differ. Neither establishes that an architecture, a business
  behaviour or any authored architecture claim changed or stayed the same.
* File mode, ownership, permissions and modification times are not recorded in
  an inventory, so changes to them are invisible and appear as ``unchanged``.
* Renames and moves are not detected: a renamed file is reported as one
  ``removed`` path plus one ``added`` path.
* Files excluded by the privacy filters, the extension allowlist or the size
  limit are invisible. A file that grows past the size limit is reported as
  ``removed`` (and ``requires_review`` is raised because oversized files were
  skipped), not as ``changed``.
* Inventories carry no project identity, so the tool cannot verify that both
  inventories describe the same project.
* Equal digests with unequal byte count, line count or kind indicate a corrupt
  or hand-edited inventory; the comparison fails closed with ``ValueError``.

The output is deterministic: identical inputs give byte-identical JSON and
Markdown (no timestamps, host paths or randomness).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .documentation import _md
from .exporters import check_new_output_dir, prepare_new_output_dir
from .models import SchemaModel
from .source_evidence import InventoryScope, SourceInventory, safe_source_path

DeltaStatus = Literal["added", "removed", "changed", "unchanged"]
FileKind = Literal["source", "test", "documentation", "configuration", "schema"]
Coverage = Literal["comparable", "scope_differs", "scope_unknown"]

_STATUSES: tuple[DeltaStatus, ...] = ("added", "removed", "changed", "unchanged")
_SHA = r"^[0-9a-f]{64}$"
_IDENTITY_NOTE = (
    "Inventories record no project identity; this comparison cannot verify "
    "that both inventories describe the same project."
)


class SourceFileDelta(SchemaModel):
    path: str
    status: DeltaStatus
    kind: FileKind
    before_sha256: str | None = Field(default=None, pattern=_SHA)
    after_sha256: str | None = Field(default=None, pattern=_SHA)
    before_byte_count: int | None = Field(default=None, ge=0)
    after_byte_count: int | None = Field(default=None, ge=0)
    before_line_count: int | None = Field(default=None, ge=0)
    after_line_count: int | None = Field(default=None, ge=0)

    @field_validator("path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return safe_source_path(value)

    @model_validator(mode="after")
    def status_matches_sides(self) -> SourceFileDelta:
        before = (self.before_sha256, self.before_byte_count, self.before_line_count)
        after = (self.after_sha256, self.after_byte_count, self.after_line_count)
        before_set = all(x is not None for x in before)
        after_set = all(x is not None for x in after)
        before_none = all(x is None for x in before)
        after_none = all(x is None for x in after)
        if self.status == "added":
            ok = before_none and after_set
        elif self.status == "removed":
            ok = after_none and before_set
        else:
            ok = before_set and after_set
        if not ok:
            raise ValueError(f"Delta fields are inconsistent with status '{self.status}'")
        if self.status == "changed" and self.before_sha256 == self.after_sha256:
            raise ValueError("A changed file must have different SHA-256 digests")
        if self.status == "unchanged" and (
            self.before_sha256 != self.after_sha256
            or self.before_byte_count != self.after_byte_count
            or self.before_line_count != self.after_line_count
        ):
            raise ValueError("An unchanged file must have identical digest and counts")
        return self


class InventoryDiff(SchemaModel):
    schema_version: Literal[1] = 1
    entries: list[SourceFileDelta]
    added: list[str]
    removed: list[str]
    changed: list[str]
    unchanged: list[str]
    coverage: Coverage
    coverage_notes: list[str]
    before_scope: InventoryScope | None = None
    after_scope: InventoryScope | None = None
    before_skipped_oversized: int = Field(default=0, ge=0)
    after_skipped_oversized: int = Field(default=0, ge=0)
    caveat: str = (
        "This compares metadata-only snapshots. A hash match proves byte "
        "equality only; changed bytes do not imply a changed architecture or "
        "changed business behaviour. Files excluded by privacy filters or size "
        "limits are invisible. Inventories carry no project identity, so this "
        "tool cannot verify that both describe the same project."
    )

    @model_validator(mode="after")
    def consistent(self) -> InventoryDiff:
        paths = [entry.path for entry in self.entries]
        if paths != sorted(set(paths)):
            raise ValueError("Diff entries must have unique paths sorted by path")
        for status in _STATUSES:
            expected = [e.path for e in self.entries if e.status == status]
            if getattr(self, status) != expected:
                raise ValueError(f"Diff '{status}' list does not match its entries")
        if _coverage(self.before_scope, self.after_scope) != self.coverage:
            raise ValueError("Diff coverage does not match the recorded scopes")
        return self

    @property
    def requires_review(self) -> bool:
        return bool(
            self.added or self.removed or self.changed
            or self.coverage != "comparable"
            or self.before_skipped_oversized > 0
            or self.after_skipped_oversized > 0
        )


def _coverage(before: InventoryScope | None, after: InventoryScope | None) -> Coverage:
    if before is None or after is None:
        return "scope_unknown"
    if (before.policy_sha256 != after.policy_sha256
            or before.max_file_bytes != after.max_file_bytes):
        return "scope_differs"
    return "comparable"


def _coverage_notes(before: SourceInventory, after: SourceInventory) -> list[str]:
    notes: list[str] = []
    bs, af = before.scope, after.scope
    if bs is None and af is None:
        notes.append("Neither inventory records its scan scope (written before scope "
                     "recording existed); coverage is unknown.")
    elif bs is None:
        notes.append("The before inventory records no scan scope (written before scope "
                     "recording existed); coverage is unknown.")
    elif af is None:
        notes.append("The after inventory records no scan scope (written before scope "
                     "recording existed); coverage is unknown.")
    else:
        if bs.policy_sha256 != af.policy_sha256:
            notes.append(
                "The privacy/allowlist policy differs between inventories, so added "
                "or removed files may reflect policy changes rather than source changes.")
        if bs.max_file_bytes != af.max_file_bytes:
            notes.append(
                f"The per-file size limit differs (before {bs.max_file_bytes} bytes, "
                f"after {af.max_file_bytes} bytes), so added or removed files may only "
                "have crossed the size limit.")
        if bs.max_files != af.max_files:
            notes.append(
                f"The file-count limit differs (before {bs.max_files}, after "
                f"{af.max_files}); this does not change coverage because a scan fails "
                "rather than truncating when the limit is reached.")
    for label, inv in (("before", before), ("after", after)):
        if not inv.files:
            notes.append(
                f"The {label} inventory lists no files; check that it was taken from the "
                "intended project root and that its files are not all excluded.")
    for label, inv in (("before", before), ("after", after)):
        if inv.skipped_oversized > 0:
            notes.append(
                f"The {label} inventory skipped {inv.skipped_oversized} oversized "
                "file(s); a path reported as added or removed may only have crossed "
                "the size limit.")
    notes.append(_IDENTITY_NOTE)
    return notes


def compare_inventories(before: SourceInventory, after: SourceInventory) -> InventoryDiff:
    """Compare two inventories by path and SHA-256. Pure; reads no source files."""
    old = {f.path: f for f in before.files}
    new = {f.path: f for f in after.files}
    entries: list[SourceFileDelta] = []
    for path in sorted(old.keys() | new.keys()):
        b, a = old.get(path), new.get(path)
        if b is not None and a is not None:
            if b.sha256 == a.sha256:
                if (b.byte_count, b.line_count, b.kind) != (a.byte_count, a.line_count, a.kind):
                    raise ValueError(
                        f"inconsistent inventory metadata for '{path}': equal SHA-256 "
                        "but different byte count, line count or kind")
                status: DeltaStatus = "unchanged"
            else:
                status = "changed"
        else:
            status = "added" if a is not None else "removed"
        kind = (a or b).kind  # type: ignore[union-attr]
        entries.append(SourceFileDelta(
            path=path, status=status, kind=kind,
            before_sha256=b.sha256 if b else None,
            after_sha256=a.sha256 if a else None,
            before_byte_count=b.byte_count if b else None,
            after_byte_count=a.byte_count if a else None,
            before_line_count=b.line_count if b else None,
            after_line_count=a.line_count if a else None,
        ))
    return InventoryDiff(
        entries=entries,
        added=[e.path for e in entries if e.status == "added"],
        removed=[e.path for e in entries if e.status == "removed"],
        changed=[e.path for e in entries if e.status == "changed"],
        unchanged=[e.path for e in entries if e.status == "unchanged"],
        coverage=_coverage(before.scope, after.scope),
        coverage_notes=_coverage_notes(before, after),
        before_scope=before.scope, after_scope=after.scope,
        before_skipped_oversized=before.skipped_oversized,
        after_skipped_oversized=after.skipped_oversized,
    )


def _short(value: str | None) -> str:
    return value[:12] if value else "-"


def _num(value: int | None) -> str:
    return "-" if value is None else str(value)


def _table(headings: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headings) + " |",
             "| " + " | ".join("---" for _ in headings) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _scope_line(label: str, scope: InventoryScope | None) -> str:
    if scope is None:
        return f"- {label} scope: not recorded"
    return (f"- {label} scope: max files {scope.max_files}, max file bytes "
            f"{scope.max_file_bytes}, policy {scope.policy_sha256[:12]}")


def render_inventory_diff_markdown(diff: InventoryDiff) -> str:
    out: list[str] = [
        "# Source inventory comparison",
        "",
        "> **Metadata comparison only — not semantic or architectural verification.**",
        "",
        _md(diff.caveat),
        "",
        "## Coverage",
        "",
        f"Coverage: **{_md(diff.coverage)}**. Requires review: "
        f"**{'yes' if diff.requires_review else 'no'}**.",
        "",
        _scope_line("Before", diff.before_scope),
        _scope_line("After", diff.after_scope),
        f"- Before skipped oversized files: {diff.before_skipped_oversized}",
        f"- After skipped oversized files: {diff.after_skipped_oversized}",
        "",
    ]
    out.extend("- " + _md(note) for note in diff.coverage_notes)
    out += ["", "## Counts", ""]
    out.extend(f"- {status.capitalize()}: {len(getattr(diff, status))}" for status in _STATUSES)
    by_status = {s: [e for e in diff.entries if e.status == s] for s in _STATUSES}
    for status, title in (("added", "Added files"), ("removed", "Removed files")):
        out += ["", f"## {title}", ""]
        entries = by_status[status]
        if not entries:
            out.append("None.")
            continue
        side = "after" if status == "added" else "before"
        out.append(_table(
            ["Path", "Kind", "SHA-256 (first 12)", "Bytes"],
            [[_md(e.path), _md(e.kind), _short(getattr(e, f"{side}_sha256")),
              _num(getattr(e, f"{side}_byte_count"))] for e in entries]))
    out += ["", "## Changed files", ""]
    if not by_status["changed"]:
        out.append("None.")
    else:
        out.append(_table(
            ["Path", "Kind", "Before SHA-256 (first 12)", "After SHA-256 (first 12)",
             "Before bytes", "After bytes"],
            [[_md(e.path), _md(e.kind), _short(e.before_sha256), _short(e.after_sha256),
              _num(e.before_byte_count), _num(e.after_byte_count)]
             for e in by_status["changed"]]))
    out += ["", "## Unchanged files", "",
            f"{len(diff.unchanged)} file(s) have identical SHA-256 digests. The full "
            "list is in source-diff.json."]
    return "\n".join(out) + "\n"


def export_inventory_diff(diff: InventoryDiff, destination: str | Path) -> dict[str, Path]:
    """Write source-diff.json and source-diff.md into a new or empty real directory."""
    check_new_output_dir(destination, "Source diff")
    contents = {
        "source-diff.json": json.dumps(diff.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        "source-diff.md": render_inventory_diff_markdown(diff),
    }
    out = prepare_new_output_dir(destination, "Source diff")
    paths: dict[str, Path] = {}
    for name, content in contents.items():
        path = out / name
        path.write_text(content, encoding="utf-8")
        paths[name] = path
    return paths
