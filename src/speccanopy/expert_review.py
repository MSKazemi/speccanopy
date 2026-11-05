"""Independent-review coordination, *not* automated expert certification.

This workflow blinds candidate source labels, binds responses to immutable packet
hashes, and aggregates self-declared assessments without authenticating reviewers.
All private manifests and submissions must remain outside the public repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


SHA256 = r"^[0-9a-f]{64}$"
CODE = r"^[A-Za-z][A-Za-z0-9_.:-]*$"


def canonical(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _save(path: Path, value: object, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700 if private else 0o755)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if private:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
    else:
        path.write_text(data, encoding="utf-8")


class Dimension(StrictModel):
    id: str = Field(pattern=CODE, min_length=1)
    question: str = Field(min_length=12)
    anchor_hint: str = Field(min_length=8)


class CandidateSource(StrictModel):
    id: str = Field(pattern=CODE, min_length=1)
    path: str = Field(min_length=1)


class ReviewStudy(StrictModel):
    id: str = Field(pattern=CODE, min_length=1)
    research_case_path: str = Field(min_length=1)
    candidates: list[CandidateSource] = Field(min_length=2, max_length=20)
    dimensions: list[Dimension] = Field(min_length=3, max_length=20)
    min_distinct_reviewers: int = Field(default=2, ge=2, le=20)
    partition: Literal["development", "private_holdout"] = "development"
    distribution_rights_confirmed: bool = False
    scope: str = Field(min_length=12)

    @model_validator(mode="after")
    def consistent(self) -> ReviewStudy:
        if not self.distribution_rights_confirmed:
            raise ValueError("Explicit distribution rights confirmation is required")
        if len({c.id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Candidate IDs must be unique")
        if len({d.id for d in self.dimensions}) != len(self.dimensions):
            raise ValueError("Rubric dimension IDs must be unique")
        return self


class Packet(StrictModel):
    study_id: str
    case_id: str
    candidate_label: str = Field(pattern=r"^C-[0-9a-f]{12}$")
    case_sha256: str = Field(pattern=SHA256)
    brief: dict
    architecture: dict
    dimensions: list[Dimension]
    scope: str
    warning: str = "Source identities are hidden best-effort, not cryptographically anonymized. No independent expert verification is claimed."


class ManifestItem(StrictModel):
    label: str = Field(pattern=r"^C-[0-9a-f]{12}$")
    candidate_id: str
    source_path: str
    source_sha256: str = Field(pattern=SHA256)
    packet_sha256: str = Field(pattern=SHA256)


class ReviewManifest(StrictModel):
    study_id: str
    case_id: str
    study_sha256: str = Field(pattern=SHA256)
    case_sha256: str = Field(pattern=SHA256)
    min_distinct_reviewers: int = Field(ge=2)
    partition: Literal["development", "private_holdout"]
    dimensions: list[Dimension]
    packets: list[ManifestItem] = Field(min_length=2)
    status: Literal["awaiting_external_review"] = "awaiting_external_review"
    warning: str = "PRIVATE mapping, not an expert attestation. Never commit this file or private holdout cases."

    @model_validator(mode="after")
    def unique_mapping(self) -> ReviewManifest:
        if len({p.label for p in self.packets}) != len(self.packets):
            raise ValueError("Private manifest candidate labels must be unique")
        if len({p.candidate_id for p in self.packets}) != len(self.packets):
            raise ValueError("Private manifest candidate IDs must be unique")
        if len({d.id for d in self.dimensions}) != len(self.dimensions):
            raise ValueError("Private manifest dimensions must be unique")
        return self


class DimensionRating(StrictModel):
    dimension_id: str
    score: int = Field(ge=1, le=5)
    evidence: str = Field(min_length=12)


class ReviewerFinding(StrictModel):
    severity: Literal["critical", "high", "medium", "low"]
    description: str = Field(min_length=15)
    requirement_ids: list[str] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)


class ReviewerSubmission(StrictModel):
    study_id: str
    candidate_label: str = Field(pattern=r"^C-[0-9a-f]{12}$")
    case_sha256: str = Field(pattern=SHA256)
    packet_sha256: str = Field(pattern=SHA256)
    reviewer_id: str = Field(min_length=2)
    submitted_on: date
    expertise: str = Field(min_length=12)
    independence: Literal["self_declared_independent", "conflict", "uncertain"]
    conflict_details: str | None = None
    permission_to_publish_aggregate: bool
    verdict: Literal["viable_with_conditions", "not_viable", "insufficient_information"]
    verdict_rationale: str = Field(min_length=15)
    ratings: list[DimensionRating] = Field(min_length=1)
    findings: list[ReviewerFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def conflict_consistent(self) -> ReviewerSubmission:
        if self.independence != "self_declared_independent" and not self.conflict_details:
            raise ValueError("Conflicts or uncertain independence require conflict_details")
        if self.independence == "self_declared_independent" and self.conflict_details:
            raise ValueError("An independent declaration cannot also include conflict_details")
        if len({r.dimension_id for r in self.ratings}) != len(self.ratings):
            raise ValueError("Duplicate dimension ratings")
        return self


def anonymized_architecture(spec: object) -> dict:
    """Omit generator provenance and priorities, not design details needed to review."""
    data = spec.model_dump(mode="json") if isinstance(spec, BaseModel) else dict(spec)
    components = []
    for source in data["components"]:
        components.append({k: source[k] for k in (
            "id", "name", "responsibility", "boundary", "parent_id", "requirement_ids",
            "interfaces", "owned_data", "quality_targets", "assumptions", "risks",
        ) if k in source})
    return {
        "selected_style": data.get("selected_style"),
        "components": components,
        "relationships": data.get("relationships", []),
        "verification_cases": data.get("verification_cases", []),
        "decisions": data.get("decisions", []),
        "findings": data.get("findings", []),
    }


def make_packet(study: ReviewStudy, case: dict, architecture: dict, *, label: str, case_sha: str) -> Packet:
    return Packet(
        study_id=study.id, case_id=case["id"], candidate_label=label,
        case_sha256=case_sha, brief=case["brief"],
        architecture=anonymized_architecture(architecture), dimensions=study.dimensions,
        scope=study.scope,
    )


def _template(packet: Packet) -> dict:
    return {
        "instructions": "TEMPLATE ONLY, not a real review. Fill every field, remove this instructions key, then save as <anything>.submission.json outside the repository.",
        "study_id": packet.study_id,
        "candidate_label": packet.candidate_label,
        "case_sha256": packet.case_sha256,
        "packet_sha256": digest(packet),
        "reviewer_id": "",
        "submitted_on": None,
        "expertise": "",
        "independence": "uncertain",
        "conflict_details": "",
        "permission_to_publish_aggregate": False,
        "verdict": "insufficient_information",
        "verdict_rationale": "",
        "ratings": [{"dimension_id": d.id, "score": None, "evidence": ""} for d in packet.dimensions],
        "findings": [],
    }


def prepare(study_path: Path, output: Path) -> ReviewManifest:
    """Validate research cases and architecture files using existing Speccanopy models."""
    from .models import ArchitectureSpec
    from .research import ResearchCase

    study = ReviewStudy.model_validate_json(study_path.read_text(encoding="utf-8"))
    case_path = study_path.parent / study.research_case_path
    case = ResearchCase.model_validate_json(case_path.read_text(encoding="utf-8"))
    if case.provenance.usage_rights.strip() == "":
        raise ValueError("Research case is missing usage rights")
    case_sha = case.subject_digest()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Review packet output directory must be empty to avoid mixing study runs")
    all_items: list[ManifestItem] = []
    packets: list[tuple[Packet, dict]] = []
    used: set[str] = set()
    for candidate in study.candidates:
        source = (study_path.parent / candidate.path).resolve()
        spec = ArchitectureSpec.model_validate_json(source.read_text(encoding="utf-8"))
        if spec.brief.model_dump(mode="json") != case.brief.model_dump(mode="json"):
            raise ValueError(f"Candidate {candidate.id} does not match original research case brief")
        label = "C-" + secrets.token_hex(6)
        while label in used:
            label = "C-" + secrets.token_hex(6)
        used.add(label)
        packet = make_packet(
            study, case.model_dump(mode="json"), spec.model_dump(mode="json"),
            label=label, case_sha=case_sha,
        )
        all_items.append(ManifestItem(
            label=label, candidate_id=candidate.id, source_path=str(source),
            source_sha256=digest(spec), packet_sha256=digest(packet),
        ))
        packets.append((packet, _template(packet)))
    output.mkdir(parents=True, exist_ok=True)
    manifest = ReviewManifest(
        study_id=study.id, case_id=case.id, study_sha256=digest(study),
        case_sha256=case_sha, min_distinct_reviewers=study.min_distinct_reviewers,
        partition=study.partition, dimensions=study.dimensions, packets=all_items,
    )
    # The manifest is a PRIVATE lookup. Public packets never contain source paths or candidate IDs.
    _save(output / "private" / "manifest.json", manifest.model_dump(mode="json"), private=True)
    for packet, template in packets:
        _save(output / "packets" / f"{packet.candidate_label}.json", packet.model_dump(mode="json"))
        _save(output / "templates" / f"{packet.candidate_label}.template.json", template)
    return manifest


def _validate_submission(submission: ReviewerSubmission, packet: Packet, expected_sha: str) -> None:
    if submission.study_id != packet.study_id or submission.candidate_label != packet.candidate_label:
        raise ValueError("Submission belongs to a different study/candidate")
    if submission.case_sha256 != packet.case_sha256 or submission.packet_sha256 != expected_sha:
        raise ValueError("Submission packet or case digest mismatch")
    expected = {d.id for d in packet.dimensions}
    actual = {r.dimension_id for r in submission.ratings}
    if expected != actual:
        raise ValueError(f"Submitted dimension set differs from packet rubric: {sorted(expected ^ actual)}")
    reqs = {r["id"] for field in ("functional_requirements", "quality_requirements")
            for r in packet.brief.get(field, [])}
    comps = {c["id"] for c in packet.architecture["components"]}
    for finding in submission.findings:
        if set(finding.requirement_ids) - reqs or set(finding.component_ids) - comps:
            raise ValueError("Finding references unknown component/requirement IDs")


def _stats(rows: list[ReviewerSubmission], dimension_ids: list[str]) -> tuple[dict, list[str]]:
    dimension_stats: dict[str, dict] = {}
    disputed: list[str] = []
    for dimension in dimension_ids:
        values = [next(r.score for r in row.ratings if r.dimension_id == dimension) for row in rows]
        delta = max(values) - min(values)
        if delta >= 2:
            disputed.append(dimension)
        dimension_stats[dimension] = {
            "median": statistics.median(values), "minimum": min(values),
            "maximum": max(values), "range": delta,
        }
    return dimension_stats, disputed


def aggregate(manifest_path: Path, submissions_dir: Path, output: Path) -> dict:
    manifest = ReviewManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    packet_dir = manifest_path.parent.parent / "packets"
    items = {item.label: item for item in manifest.packets}
    packet_by_label: dict[str, Packet] = {}
    for label, item in items.items():
        packet = Packet.model_validate_json((packet_dir / f"{label}.json").read_text(encoding="utf-8"))
        if (digest(packet) != item.packet_sha256 or packet.case_sha256 != manifest.case_sha256
                or packet.study_id != manifest.study_id or packet.case_id != manifest.case_id):
            raise ValueError("Original review packet has changed since manifest creation")
        if [d.id for d in packet.dimensions] != [d.id for d in manifest.dimensions]:
            raise ValueError("Packet rubric differs from private manifest")
        packet_by_label[label] = packet

    accepted: dict[str, list[ReviewerSubmission]] = {label: [] for label in items}
    seen: set[tuple[str, str]] = set()
    excluded: dict[str, int] = {label: 0 for label in items}
    names = sorted(submissions_dir.glob("*.submission.json")) if submissions_dir.exists() else []
    for path in names:
        submission = ReviewerSubmission.model_validate_json(path.read_text(encoding="utf-8"))
        if submission.candidate_label not in items:
            raise ValueError(f"Unknown candidate label in submission {path.name}")
        label = submission.candidate_label
        _validate_submission(submission, packet_by_label[label], items[label].packet_sha256)
        identity = (label, submission.reviewer_id.casefold().strip())
        if identity in seen:
            raise ValueError(f"Duplicate self-declared reviewer for {label}")
        seen.add(identity)
        if submission.independence == "self_declared_independent" and submission.permission_to_publish_aggregate:
            accepted[label].append(submission)
        else:
            excluded[label] += 1

    groups: list[dict] = []
    for label in sorted(items):
        rows = accepted[label]
        reached = len(rows) >= manifest.min_distinct_reviewers
        scores, disputed = (_stats(rows, [d.id for d in manifest.dimensions]) if reached else ({}, []))
        verdicts = {v: sum(x.verdict == v for x in rows) for v in (
            "viable_with_conditions", "not_viable", "insufficient_information")}
        groups.append({
            "candidate_label": label,
            "self_declared_consented_reviewers": len(rows),
            "excluded_reviews": excluded[label],
            "minimum_required": manifest.min_distinct_reviewers,
            "self_declared_quorum_met": reached,
            "dimension_statistics": scores,
            "disputed_dimensions_range_at_least_two": disputed,
            "verdict_counts": verdicts if reached else None,
            "critical_or_high_findings": sum(f.severity in {"critical", "high"} for x in rows for f in x.findings) if reached else None,
            "status": "requires_external_identity_and_independence_check" if reached else "awaiting_self_declared_reviewer_quorum",
        })
    report = {
        "study_id": manifest.study_id,
        "case_id": manifest.case_id,
        "partition": manifest.partition,
        "status": "self_declared_quorum_only_not_verified" if all(g["self_declared_quorum_met"] for g in groups) else "awaiting_reviewers",
        "received_submission_files": len(names),
        "candidates": groups,
        "caveat": "These ratings are self-declared, reviewer identities, independence and expertise are NOT authenticated. No architectural certification or validated holdout performance is claimed. Do not publish private case content without permission.",
    }
    _save(output / "expert-review-summary.json", report)
    lines = ["# Architecture panel review summary", "", "**NOT independently verified.**", "",
             f"Study: {manifest.study_id}", f"Case: {manifest.case_id}",
             f"Partition: {manifest.partition}", f"Status: {report['status']}", "",
             "| Candidate | Consent + self-declared independence | Excluded | Quorum | Disputed dimensions |",
             "| --- | ---: | ---: | --- | --- |"]
    for row in groups:
        lines.append(f"| {row['candidate_label']} | {row['self_declared_consented_reviewers']} | {row['excluded_reviews']} | {'yes' if row['self_declared_quorum_met'] else 'no'} | {', '.join(row['disputed_dimensions_range_at_least_two']) or 'not available'} |")
    lines.extend(["", report["caveat"], ""])
    (output / "expert-review-summary.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="speccanopy-experts", description="Prepare blind review packets and aggregate self-declared architecture evaluations")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_cmd = sub.add_parser("prepare", help="Create source-blinded candidate packets and private manifest")
    prepare_cmd.add_argument("study", type=Path)
    prepare_cmd.add_argument("--output", type=Path, required=True)
    aggregate_cmd = sub.add_parser("aggregate", help="Aggregate locally collected reviewer submissions")
    aggregate_cmd.add_argument("manifest", type=Path)
    aggregate_cmd.add_argument("--submissions", type=Path, required=True)
    aggregate_cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            m = prepare(args.study, args.output)
            print(f"Prepared {len(m.packets)} blind candidate packets; private mapping: {args.output / 'private' / 'manifest.json'}")
            print("No expert review has occurred. Distribute only packets and blank templates.")
        else:
            report = aggregate(args.manifest, args.submissions, args.output)
            print(f"Panel status: {report['status']}; submission files: {report['received_submission_files']}")
            print("All claims remain self-declared; independent verification is manual.")
    except (OSError, ValidationError, ValueError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
