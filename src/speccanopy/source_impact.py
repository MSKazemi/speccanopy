"""Metadata-only mapping of source inventory changes onto authored source claims.

Given an :class:`~speccanopy.source_diff.InventoryDiff` and a
:class:`~speccanopy.source_evidence.SourceEvidence` map, this module reports,
for every authored source claim, whether the cited file's bytes changed between
two inventories and which architecture IDs therefore deserve a fresh look. It
never reads source files, never touches a scanned project, never executes
target code and makes no network calls.

What the report can and cannot say:

* A claim is bound to a SHA-256 digest of the cited file. Comparing that digest
  with the before/after digests of the diff shows only whether the *bytes* the
  claim was authored against still exist. It says nothing about whether the
  architecture, the claim's assertion or any business behaviour changed or
  stayed the same. A changed file may leave a claim true; an unchanged file
  cannot make a wrong claim right.
* No claim is ever marked verified. ``unaffected`` means only "the cited bytes
  are identical in both snapshots and equal the claim's digest".
* Renames and moves are not detected: a renamed file is one ``removed`` path
  plus one ``added`` path, so its claims become ``stale_removed`` and the new
  path appears as an uncited added path.
* Files excluded by privacy filters, the extension allowlist or the size limit
  are invisible; claims citing them are ``not_in_inventory`` (unknown).
* Inventories carry no project identity, so the report cannot verify that the
  diff, the evidence map and the architecture all describe the same project.
* The report never edits or regenerates documentation.

The output is deterministic: identical inputs give byte-identical JSON and
Markdown (no timestamps, host paths or randomness).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .documentation import _md
from .exporters import check_new_output_dir, prepare_new_output_dir
from .models import ArchitectureSpec, Identifier, NonEmptyText, SchemaModel
from .source_diff import Coverage, InventoryDiff, SourceFileDelta
from .source_evidence import SourceClaim, SourceEvidence

ImpactStatus = Literal[
    "unaffected", "stale_changed", "stale_removed",
    "not_bound_to_before", "rebound_to_after", "not_in_inventory",
]

_STATUSES: tuple[ImpactStatus, ...] = (
    "unaffected", "stale_changed", "stale_removed",
    "not_bound_to_before", "rebound_to_after", "not_in_inventory",
)
_SHA = r"^[0-9a-f]{64}$"

_REASONS: dict[ImpactStatus, str] = {
    "unaffected": (
        "Cited bytes are identical in both inventories and equal the claim digest. "
        "This is not verification of the assertion."
    ),
    "stale_changed": (
        "The cited file's bytes differ between the inventories and the claim digest "
        "equals the earlier digest, so the claim may describe superseded bytes."
    ),
    "stale_removed": (
        "The cited path is absent from the later inventory. A rename or move also "
        "appears as removed plus added; renames are not detected."
    ),
    "not_bound_to_before": (
        "The claim digest equals neither the earlier nor the later digest of this path, "
        "so the claim was authored against some other snapshot."
    ),
    "rebound_to_after": (
        "The claim digest equals the later digest, so it was authored or refreshed "
        "against the newer bytes. Whether its assertion was re-reviewed cannot be "
        "determined from digests."
    ),
    "not_in_inventory": (
        "The cited path is in neither inventory (excluded by privacy filter, allowlist "
        "or size limit, or never scanned). Its state is unknown."
    ),
}

_CAVEAT = (
    "This is a digest and path comparison of metadata-only snapshots. It says nothing "
    "about whether the architecture or the meaning of any claim changed. It never edits "
    "or regenerates documentation, and no claim is marked verified. Inventories carry "
    "no project identity, so the tool cannot confirm that the diff, the evidence map "
    "and the architecture describe the same project."
)


class ClaimImpact(SchemaModel):
    architecture_id: Identifier
    source_path: str
    assertion: NonEmptyText
    basis: Literal["observed", "inferred", "proposed"]
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    claim_sha256: str = Field(pattern=_SHA)
    before_sha256: str | None = Field(default=None, pattern=_SHA)
    after_sha256: str | None = Field(default=None, pattern=_SHA)
    status: ImpactStatus
    reason: str


class ClaimImpactReport(SchemaModel):
    schema_version: Literal[1] = 1
    entries: list[ClaimImpact]
    status_counts: dict[str, int]
    affected_architecture_ids: list[str]
    uncited_added_paths: list[str]
    uncited_changed_paths: list[str]
    # None means no architecture was supplied, so mandatory coverage was not assessed.
    mandatory_requirements_without_current_observed_evidence: list[str] | None = None
    diff_requires_review: bool
    diff_coverage: Coverage
    diff_coverage_notes: list[str] = Field(default_factory=list)
    caveat: str = _CAVEAT

    @model_validator(mode="after")
    def consistent(self) -> ClaimImpactReport:
        keys = [_sort_key(e) for e in self.entries]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("Impact entries must be unique and sorted")
        counts = {s: sum(1 for e in self.entries if e.status == s) for s in _STATUSES}
        if self.status_counts != counts:
            raise ValueError("Impact status_counts do not match its entries")
        affected = sorted({e.architecture_id for e in self.entries if e.status != "unaffected"})
        if self.affected_architecture_ids != affected:
            raise ValueError("Impact affected_architecture_ids do not match its entries")
        for name in ("uncited_added_paths", "uncited_changed_paths"):
            values = getattr(self, name)
            if values != sorted(set(values)):
                raise ValueError(f"Impact {name} must be unique and sorted")
        missing = self.mandatory_requirements_without_current_observed_evidence
        if missing is not None and missing != sorted(set(missing)):
            raise ValueError("Impact mandatory requirement list must be unique and sorted")
        return self

    @property
    def requires_review(self) -> bool:
        return bool(
            self.diff_requires_review
            or any(e.status != "unaffected" for e in self.entries)
            or self.uncited_added_paths
            or self.uncited_changed_paths
            or self.mandatory_requirements_without_current_observed_evidence
        )


def _sort_key(entry: ClaimImpact | SourceClaim) -> tuple[str, str, int, int]:
    return (entry.architecture_id, entry.source_path,
            entry.line_start or 0, entry.line_end or 0)


def _status(claim: SourceClaim, delta: SourceFileDelta | None) -> ImpactStatus:
    if delta is None:
        return "not_in_inventory"
    if delta.status == "removed":
        return "stale_removed"
    if delta.status == "unchanged":
        return "unaffected" if claim.sha256 == delta.after_sha256 else "not_bound_to_before"
    if delta.status == "changed" and claim.sha256 == delta.before_sha256:
        return "stale_changed"
    # changed or added: a digest equal to the later bytes was (re)authored against them.
    if claim.sha256 == delta.after_sha256:
        return "rebound_to_after"
    return "not_bound_to_before"


def _known_ids(spec: ArchitectureSpec) -> set[str]:
    # Same ID set that source_evidence.assess_sources accepts.
    return (
        spec.brief.requirement_ids() |
        {x.id for group in (spec.components, spec.relationships, spec.decisions,
                            spec.findings, spec.verification_cases) for x in group}
    )


def assess_claim_impact(
    diff: InventoryDiff, evidence: SourceEvidence, spec: ArchitectureSpec | None = None,
) -> ClaimImpactReport:
    """Map inventory changes onto authored source claims. Pure; reads no source files."""
    if spec is not None:
        valid_ids = _known_ids(spec)
        for claim in evidence.claims:
            if claim.architecture_id not in valid_ids:
                raise ValueError(
                    f"Source claim refers to unknown architecture ID: {claim.architecture_id}")
    deltas = {entry.path: entry for entry in diff.entries}
    entries: list[ClaimImpact] = []
    for claim in sorted(evidence.claims, key=_sort_key):
        delta = deltas.get(claim.source_path)
        status = _status(claim, delta)
        entries.append(ClaimImpact(
            architecture_id=claim.architecture_id, source_path=claim.source_path,
            assertion=claim.assertion, basis=claim.basis,
            line_start=claim.line_start, line_end=claim.line_end,
            claim_sha256=claim.sha256,
            before_sha256=delta.before_sha256 if delta else None,
            after_sha256=delta.after_sha256 if delta else None,
            status=status, reason=_REASONS[status],
        ))
    cited = {claim.source_path for claim in evidence.claims}
    missing: list[str] | None = None
    if spec is not None:
        current = {e.architecture_id for e in entries
                   if e.status == "unaffected" and e.basis == "observed"}
        missing = sorted(spec.brief.mandatory_requirement_ids() - current)
    return ClaimImpactReport(
        entries=entries,
        status_counts={s: sum(1 for e in entries if e.status == s) for s in _STATUSES},
        affected_architecture_ids=sorted(
            {e.architecture_id for e in entries if e.status != "unaffected"}),
        uncited_added_paths=sorted(p for p in diff.added if p not in cited),
        uncited_changed_paths=sorted(p for p in diff.changed if p not in cited),
        mandatory_requirements_without_current_observed_evidence=missing,
        diff_requires_review=diff.requires_review,
        diff_coverage=diff.coverage,
        diff_coverage_notes=list(diff.coverage_notes),
    )


def _short(value: str | None) -> str:
    return value[:12] if value else "-"


def _lines(entry: ClaimImpact) -> str:
    if entry.line_start is None:
        return "-"
    return f"{entry.line_start}-{entry.line_end}"


def _bullets(values: list[str]) -> list[str]:
    return [f"- {_md(v)}" for v in values] if values else ["None."]


def _path_section(title: str, note: str, paths: list[str]) -> list[str]:
    out = ["", f"## {title}", "", note, ""]
    out.extend(_bullets(paths))
    return out


def render_claim_impact_markdown(report: ClaimImpactReport) -> str:
    out: list[str] = [
        "# Source claim impact",
        "",
        "> **Metadata comparison only — not semantic or architectural verification.**",
        "",
        _md(report.caveat),
        "",
        "## Summary",
        "",
        f"Requires review: **{'yes' if report.requires_review else 'no'}**. "
        f"Source diff coverage: **{_md(report.diff_coverage)}** "
        f"(diff requires review: {'yes' if report.diff_requires_review else 'no'}).",
        "",
    ]
    out.extend(f"- {_md(s)}: {report.status_counts[s]}" for s in _STATUSES)
    out += ["", "### Diff coverage notes", ""]
    out.extend(_bullets(report.diff_coverage_notes))
    out += ["", "## Claims", ""]
    if not report.entries:
        out.append("No source claims were supplied.")
    else:
        out.append("| Architecture ID | Source path | Lines | Basis | Status | Assertion | Digests (claim / before / after) |")
        out.append("| --- | --- | --- | --- | --- | --- | --- |")
        for e in report.entries:
            out.append(
                f"| {_md(e.architecture_id)} | {_md(e.source_path)} | {_lines(e)} | "
                f"{_md(e.basis)} | {_md(e.status)} | {_md(e.assertion)} | "
                f"{_short(e.claim_sha256)} / {_short(e.before_sha256)} / "
                f"{_short(e.after_sha256)} |")
        out += ["", "### Status meanings", ""]
        used = [s for s in _STATUSES if report.status_counts[s]]
        out.extend(f"- **{_md(s)}**: {_md(_REASONS[s])}" for s in used)
    out += ["", "## Possibly affected architecture IDs", ""]
    out.extend(_bullets(report.affected_architecture_ids))
    out += _path_section(
        "Added files not cited by any claim",
        "Observation only: these files may or may not belong to an undocumented component. "
        "A renamed file appears here with its old path under removed claims.",
        report.uncited_added_paths)
    out += _path_section(
        "Changed files not cited by any claim",
        "Observation only: no authored claim is bound to these changed files.",
        report.uncited_changed_paths)
    out += ["", "## Mandatory requirements without current observed evidence", ""]
    missing = report.mandatory_requirements_without_current_observed_evidence
    if missing is None:
        out.append("Not assessed: no architecture file was supplied.")
    else:
        out.append("A requirement counts as covered only by an `unaffected` claim with "
                   "basis `observed`; this is not verification.")
        out.append("")
        out.extend(_bullets(missing))
    return "\n".join(out) + "\n"


def export_claim_impact(report: ClaimImpactReport, destination: str | Path) -> dict[str, Path]:
    """Write claim-impact.json and claim-impact.md into a new or empty real directory."""
    check_new_output_dir(destination, "Claim impact")
    contents = {
        "claim-impact.json": json.dumps(
            report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        "claim-impact.md": render_claim_impact_markdown(report),
    }
    out = prepare_new_output_dir(destination, "Claim impact")
    paths: dict[str, Path] = {}
    for name, content in contents.items():
        path = out / name
        path.write_text(content, encoding="utf-8")
        paths[name] = path
    return paths
