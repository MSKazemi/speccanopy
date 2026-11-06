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
  ``removed`` path plus one ``added`` path. As a labelled *observation only*,
  a removed and an added path with the identical SHA-256 and byte size are
  listed in ``rename_candidates`` ("identical bytes moved"); this never changes
  the ``added``/``removed`` lists. Ambiguous digests (more than one removed or
  added path) are not paired and are listed in ``ambiguous_rename_digests``.
  Zero-byte files are never paired (empty content is not distinguishing), and a
  rename combined with any edit changes the digest, so it stays unpaired.
* Files excluded by the privacy filters, the extension allowlist or the size
  limit are invisible. A file that grows past the size limit is reported as
  ``removed`` (and ``requires_review`` is raised because oversized files were
  skipped), not as ``changed``.
* Inventories carry no verified project identity. An inventory may carry an
  optional, unauthenticated git revision (commit and branch ref read from
  ``.git`` files); it is shown and compared, but it cannot prove that both
  inventories describe the same project, it never makes the comparison fail
  closed, and it does not say whether the working tree was clean.
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
from .source_evidence import (
    InventoryScope, SourceInventory, SourceRevision, safe_source_path,
)

DeltaStatus = Literal["added", "removed", "changed", "unchanged"]
FileKind = Literal["source", "test", "documentation", "configuration", "schema"]
Coverage = Literal["comparable", "scope_differs", "scope_unknown"]

_STATUSES: tuple[DeltaStatus, ...] = ("added", "removed", "changed", "unchanged")
_SHA = r"^[0-9a-f]{64}$"
_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_RENAME_OBSERVATION = (
    "Identical bytes (same SHA-256 and size) were removed from one path and added "
    "at another. This is an observation, not an asserted rename."
)
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


class RenameCandidate(SchemaModel):
    """One removed path and one added path holding identical bytes. Not a proven rename."""

    removed: str
    added: str
    sha256: str = Field(pattern=_SHA)
    byte_count: int = Field(ge=0)
    line_count: int = Field(ge=0)
    removed_kind: FileKind
    added_kind: FileKind
    # True when another path in either inventory carries the same digest, so the
    # bytes may have been copied rather than moved.
    digest_also_in_other_paths: bool
    observation: str = _RENAME_OBSERVATION

    @field_validator("removed", "added")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return safe_source_path(value)


class AmbiguousRenameGroup(SchemaModel):
    """A digest removed and added, but not one-to-one; deliberately left unpaired."""

    sha256: str = Field(pattern=_SHA)
    removed: list[str] = Field(min_length=1)
    added: list[str] = Field(min_length=1)

    @field_validator("removed", "added")
    @classmethod
    def canonical_paths(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("Ambiguous rename paths must be unique and sorted")
        return [safe_source_path(item) for item in value]

    @model_validator(mode="after")
    def not_one_to_one(self) -> AmbiguousRenameGroup:
        if len(self.removed) == 1 and len(self.added) == 1:
            raise ValueError("A one-to-one digest match is a rename candidate, not ambiguous")
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
    # Defaults keep diffs written before these fields existed loadable.
    before_revision: SourceRevision | None = None
    after_revision: SourceRevision | None = None
    rename_candidates: list[RenameCandidate] = Field(default_factory=list)
    ambiguous_rename_digests: list[AmbiguousRenameGroup] = Field(default_factory=list)
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
        self._check_rename_observations()
        return self

    def _check_rename_observations(self) -> None:
        by_path = {e.path: e for e in self.entries}

        def side(status: str, digest: str) -> list[str]:
            attr = "before_sha256" if status == "removed" else "after_sha256"
            return sorted(e.path for e in self.entries
                          if e.status == status and getattr(e, attr) == digest)

        keys = [(c.removed, c.added) for c in self.rename_candidates]
        if keys != sorted(set(keys)):
            raise ValueError("Rename candidates must be unique and sorted")
        used_removed = [c.removed for c in self.rename_candidates]
        used_added = [c.added for c in self.rename_candidates]
        if len(used_removed) != len(set(used_removed)) or len(used_added) != len(set(used_added)):
            raise ValueError("A path may appear in at most one rename candidate")
        for cand in self.rename_candidates:
            old, new = by_path.get(cand.removed), by_path.get(cand.added)
            if (old is None or new is None or old.status != "removed" or new.status != "added"
                    or old.before_sha256 != cand.sha256 or new.after_sha256 != cand.sha256
                    or (old.before_byte_count, old.before_line_count)
                    != (cand.byte_count, cand.line_count)
                    or (new.after_byte_count, new.after_line_count)
                    != (cand.byte_count, cand.line_count)
                    or (old.kind, new.kind) != (cand.removed_kind, cand.added_kind)):
                raise ValueError("Rename candidate does not match the removed/added entries")
            if side("removed", cand.sha256) != [cand.removed] or side("added", cand.sha256) != [cand.added]:
                raise ValueError("Rename candidate digest is not a one-to-one match")
            if cand.digest_also_in_other_paths != _digest_elsewhere(
                    self.entries, cand.sha256, {cand.removed, cand.added}):
                raise ValueError("Rename candidate other-path flag does not match the entries")
        digests = [g.sha256 for g in self.ambiguous_rename_digests]
        if digests != sorted(set(digests)):
            raise ValueError("Ambiguous rename digests must be unique and sorted")
        for group in self.ambiguous_rename_digests:
            if group.sha256 == _EMPTY_SHA256:
                raise ValueError("Zero-byte files are never grouped as rename observations")
            if side("removed", group.sha256) != group.removed or side("added", group.sha256) != group.added:
                raise ValueError("Ambiguous rename group does not match the removed/added entries")

    @property
    def requires_review(self) -> bool:
        return bool(
            self.added or self.removed or self.changed
            or self.coverage != "comparable"
            or self.before_skipped_oversized > 0
            or self.after_skipped_oversized > 0
        )


def _digest_elsewhere(entries: list[SourceFileDelta], digest: str, exclude: set[str]) -> bool:
    return any(e.path not in exclude and digest in (e.before_sha256, e.after_sha256)
               for e in entries)


def _rename_observations(
    entries: list[SourceFileDelta],
) -> tuple[list[RenameCandidate], list[AmbiguousRenameGroup]]:
    """Pair removed/added paths with identical digests; leave ambiguity unpaired."""
    removed: dict[str, list[SourceFileDelta]] = {}
    added: dict[str, list[SourceFileDelta]] = {}
    for entry in entries:
        if entry.status == "removed" and entry.before_sha256 != _EMPTY_SHA256:
            removed.setdefault(entry.before_sha256, []).append(entry)  # type: ignore[arg-type]
        elif entry.status == "added" and entry.after_sha256 != _EMPTY_SHA256:
            added.setdefault(entry.after_sha256, []).append(entry)  # type: ignore[arg-type]
    candidates: list[RenameCandidate] = []
    groups: list[AmbiguousRenameGroup] = []
    for digest in sorted(removed.keys() & added.keys()):
        olds, news = removed[digest], added[digest]
        sizes = ({(e.before_byte_count, e.before_line_count) for e in olds}
                 | {(e.after_byte_count, e.after_line_count) for e in news})
        if len(sizes) != 1:
            raise ValueError(
                f"inconsistent inventory metadata for digest {digest[:12]}: equal SHA-256 "
                "but different byte count or line count across removed/added paths")
        if len(olds) == 1 and len(news) == 1:
            old, new = olds[0], news[0]
            candidates.append(RenameCandidate(
                removed=old.path, added=new.path, sha256=digest,
                byte_count=old.before_byte_count, line_count=old.before_line_count,  # type: ignore[arg-type]
                removed_kind=old.kind, added_kind=new.kind,
                digest_also_in_other_paths=_digest_elsewhere(
                    entries, digest, {old.path, new.path}),
            ))
        else:
            groups.append(AmbiguousRenameGroup(
                sha256=digest, removed=[e.path for e in olds], added=[e.path for e in news]))
    return sorted(candidates, key=lambda c: (c.removed, c.added)), groups


def _revision_text(revision: SourceRevision | None) -> str:
    if revision is None:
        return "not recorded"
    if revision.status == "unknown":
        return f"unknown ({revision.reason})"
    ref = f", ref {revision.ref}" if revision.ref else ", detached HEAD"
    return f"commit {revision.commit[:12]}{ref}"  # type: ignore[index]


def _revision_notes(before: SourceInventory, after: SourceInventory, files_differ: bool) -> list[str]:
    notes: list[str] = []
    b, a = before.revision, after.revision
    if b is None and a is None:
        notes.append(
            "Neither inventory records a revision, so there is no project revision "
            "binding between them (scan with --record-git-revision to record one).")
    else:
        for label, rev in (("before", b), ("after", a)):
            if rev is None:
                notes.append(
                    f"The {label} inventory records no project revision (scanned without "
                    "--record-git-revision, or written before revision recording existed).")
    for label, rev in (("before", b), ("after", a)):
        if rev is not None and rev.status == "unknown":
            notes.append(f"The {label} inventory's git revision is unknown: {rev.reason}.")
    if b is not None and a is not None and b.status == "recorded" == a.status:
        if b.commit == a.commit:
            if files_differ:
                notes.append(
                    f"Both inventories record the same commit ({b.commit[:12]}) but their file "  # type: ignore[index]
                    "digests differ: this suggests uncommitted working-tree changes (or a "
                    "different tree at one scan). Working-tree state itself is not recorded.")
        else:
            notes.append(
                f"The inventories record different commits (before {b.commit[:12]}, "  # type: ignore[index]
                f"after {a.commit[:12]}); differing files are expected.")  # type: ignore[index]
    return notes


def _coverage(before: InventoryScope | None, after: InventoryScope | None) -> Coverage:
    if before is None or after is None:
        return "scope_unknown"
    if (before.policy_sha256 != after.policy_sha256
            or before.max_file_bytes != after.max_file_bytes):
        return "scope_differs"
    return "comparable"


def _coverage_notes(
    before: SourceInventory, after: SourceInventory, files_differ: bool = False,
) -> list[str]:
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
    notes.extend(_revision_notes(before, after, files_differ))
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
    candidates, ambiguous = _rename_observations(entries)
    files_differ = any(e.status != "unchanged" for e in entries)
    return InventoryDiff(
        entries=entries,
        added=[e.path for e in entries if e.status == "added"],
        removed=[e.path for e in entries if e.status == "removed"],
        changed=[e.path for e in entries if e.status == "changed"],
        unchanged=[e.path for e in entries if e.status == "unchanged"],
        coverage=_coverage(before.scope, after.scope),
        coverage_notes=_coverage_notes(before, after, files_differ),
        before_scope=before.scope, after_scope=after.scope,
        before_skipped_oversized=before.skipped_oversized,
        after_skipped_oversized=after.skipped_oversized,
        before_revision=before.revision, after_revision=after.revision,
        rename_candidates=candidates, ambiguous_rename_digests=ambiguous,
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
    out += ["", "## Project revisions", "",
            f"- Before: {_md(_revision_text(diff.before_revision))}",
            f"- After: {_md(_revision_text(diff.after_revision))}",
            "- A recorded revision is an unauthenticated hint read from `.git` files. It does "
            "not say whether the working tree was clean; the file digests are the content "
            "binding. Revisions never change the comparison result.",
            ]
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
    out += ["", "## Possible renames (identical bytes)", ""]
    if not diff.rename_candidates and not diff.ambiguous_rename_digests:
        out.append("No removed and added paths share identical bytes.")
    else:
        out.append("Observations of identical bytes at different paths; these are "
                   "not asserted renames. A rename combined with an edit is not detected.")
        if diff.rename_candidates:
            out += ["", _table(
                ["Removed path", "Added path", "SHA-256 (first 12)", "Bytes", "Also elsewhere"],
                [[_md(c.removed), _md(c.added), _short(c.sha256), str(c.byte_count),
                  "yes (possible copy)" if c.digest_also_in_other_paths else "no"]
                 for c in diff.rename_candidates])]
        if diff.ambiguous_rename_digests:
            out += ["", "Ambiguous (not paired; more than one removed or added path shares these bytes):", ""]
            out.extend(
                f"- {_short(g.sha256)}: removed {_md(', '.join(g.removed))}; "
                f"added {_md(', '.join(g.added))}"
                for g in diff.ambiguous_rename_digests)
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
