"""Panel logistics tests: no fixture impersonates a real independent expert."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.expert_review import (
    CandidateSource, Dimension, DimensionRating, ManifestItem, Packet,
    ReviewManifest, ReviewStudy, ReviewerFinding, ReviewerSubmission,
    _save, _template, _validate_submission, aggregate,
    anonymized_architecture, digest, make_packet, prepare,
)


@pytest.fixture
def study():
    return ReviewStudy(
        id="test-panel", research_case_path="case.json",
        candidates=[CandidateSource(id="modular", path="modular.json"), CandidateSource(id="distributed", path="distributed.json")],
        dimensions=[
            Dimension(id="cohesion", question="Are component responsibility boundaries clear?", anchor_hint="Cite specific components"),
            Dimension(id="interfaces", question="Are failure and integration contracts described?", anchor_hint="Cite interface evidence"),
            Dimension(id="security", question="Are security trust boundaries and controls stated?", anchor_hint="Cite trust boundaries"),
        ],
        min_distinct_reviewers=2, distribution_rights_confirmed=True,
        scope="Compare design quality, gaps, and operational trade-offs",
    )


@pytest.fixture
def fake_case():
    return {"id": "case-1", "brief": {"system": "Example", "functional_requirements": [
        {"id": "FR-001", "statement": "Perform work", "mandatory": True},
    ], "quality_requirements": [{"id": "NFR-001", "statement": "Authorize operations", "attribute": "security", "mandatory": True}]}}


@pytest.fixture
def fake_arch():
    return {
        "selected_style": "modular monolith",
        "components": [
            {"id": "system", "name": "System", "responsibility": "Coordinate work", "boundary": "Application boundary",
             "parent_id": None, "requirement_ids": ["FR-001"], "interfaces": [], "owned_data": [],
             "quality_targets": {}, "assumptions": [], "risks": [], "priority_score": 10,
             "validation_evidence": ["Curated fixture: not independent evidence"], "status": "ready"},
            {"id": "worker", "name": "Worker", "responsibility": "Perform work", "boundary": "Work module",
             "parent_id": "system", "requirement_ids": ["FR-001", "NFR-001"], "interfaces": [],
             "owned_data": ["Job"], "quality_targets": {"NFR-001": "Authorize"}, "assumptions": [], "risks": []},
        ],
        "relationships": [], "decisions": [], "findings": [], "verification_cases": [],
    }


def local_fixture(tmp_path, study, fake_case, fake_arch):
    root = tmp_path / "study"
    label_a, label_b = "C-000000000001", "C-000000000002"
    packets = [make_packet(study, fake_case, fake_arch, label=label, case_sha="a" * 64) for label in (label_a, label_b)]
    items = [ManifestItem(label=p.candidate_label, candidate_id=str(i), source_path="private-source.json",
                          source_sha256="b" * 64, packet_sha256=digest(p)) for i, p in enumerate(packets)]
    manifest = ReviewManifest(study_id=study.id, case_id=fake_case["id"], study_sha256=digest(study),
                              case_sha256="a"*64, min_distinct_reviewers=2,
                              partition="development", dimensions=study.dimensions, packets=items)
    mp = root / "private" / "manifest.json"
    _save(mp, manifest.model_dump(mode="json"), private=True)
    for p in packets:
        _save(root / "packets" / f"{p.candidate_label}.json", p.model_dump(mode="json"))
    return mp, packets


def submitted(packet, reviewer="reviewer-a", scores=(2, 3, 3), **overrides):
    data = dict(
        study_id=packet.study_id, candidate_label=packet.candidate_label,
        case_sha256=packet.case_sha256, packet_sha256=digest(packet),
        reviewer_id=reviewer, submitted_on=date(2026, 11, 5),
        expertise="Architecture design experience (self declared)",
        independence="self_declared_independent", conflict_details=None,
        permission_to_publish_aggregate=True, verdict="viable_with_conditions",
        verdict_rationale="Review is conditional on security and failure checks",
        ratings=[dict(dimension_id=d.id, score=s, evidence=f"Observed candidate description for {d.id}")
                 for d, s in zip(packet.dimensions, scores)], findings=[],
    )
    data.update(overrides)
    return ReviewerSubmission.model_validate(data)


def save_review(path, review):
    _save(path, review.model_dump(mode="json"))


def test_study_rights_required(study):
    data = study.model_dump(mode="json")
    data["distribution_rights_confirmed"] = False
    with pytest.raises(ValidationError, match="distribution rights"):
        ReviewStudy.model_validate(data)


def test_study_requires_multiple_distinct_candidates(study):
    raw = study.model_dump(mode="json")
    raw["candidates"][1]["id"] = raw["candidates"][0]["id"]
    with pytest.raises(ValidationError, match="unique"):
        ReviewStudy.model_validate(raw)
    raw["candidates"] = raw["candidates"][:1]
    with pytest.raises(ValidationError):
        ReviewStudy.model_validate(raw)


def test_study_has_distinct_dimensions_and_min_two(study):
    raw = study.model_dump(mode="json")
    raw["dimensions"][1]["id"] = raw["dimensions"][0]["id"]
    with pytest.raises(ValidationError, match="unique"):
        ReviewStudy.model_validate(raw)
    raw = study.model_dump(mode="json")
    raw["min_distinct_reviewers"] = 1
    with pytest.raises(ValidationError):
        ReviewStudy.model_validate(raw)


def test_packet_blinds_generator_metadata(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    assert p.candidate_label.startswith("C-")
    assert "validation_evidence" not in p.architecture["components"][0]
    assert "priority_score" not in p.architecture["components"][0]
    assert "status" not in p.architecture["components"][0]
    assert "curated fixture" not in str(p.model_dump()).lower()
    assert "modular" not in p.candidate_label.lower()
    assert p.architecture["components"][1]["quality_targets"]["NFR-001"] == "Authorize"


def test_unknown_packet_fields_rejected(study, fake_case, fake_arch):
    packet = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    raw = packet.model_dump(mode="json")
    raw["hidden_source"] = "generator X"
    with pytest.raises(ValidationError):
        Packet.model_validate(raw)


def test_template_cannot_be_mistaken_for_valid_review(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    template = _template(p)
    assert template["instructions"].startswith("TEMPLATE ONLY")
    assert all(x["score"] is None for x in template["ratings"])
    with pytest.raises(ValidationError):
        ReviewerSubmission.model_validate(template)


def test_canonical_digests_are_invariant_to_mapping_order():
    assert digest({"a": 1, "b": [2, 3]}) == digest({"b": [2, 3], "a": 1})


def test_submission_rejects_invalid_rating(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    raw = submitted(p).model_dump(mode="json")
    raw["ratings"][0]["score"] = 6
    with pytest.raises(ValidationError):
        ReviewerSubmission.model_validate(raw)


def test_conflict_details_required(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    with pytest.raises(ValidationError, match="conflict_details"):
        submitted(p, independence="conflict", conflict_details=None)


def test_submission_rejects_duplicate_dimension(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    ratings = submitted(p).model_dump(mode="json")["ratings"]
    with pytest.raises(ValidationError, match="Duplicate dimension ratings"):
        submitted(p, ratings=ratings + [ratings[0]])


def test_submission_checks_exact_rubric(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    s = submitted(p)
    s.ratings.pop()
    with pytest.raises(ValueError, match="dimension set differs"):
        _validate_submission(s, p, digest(p))


def test_submission_rejects_false_requirement_anchor(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    s = submitted(p, findings=[dict(severity="high", description="An anchored gap in requirement handling", requirement_ids=["FR-MISSING"])])
    with pytest.raises(ValueError, match="unknown component/requirement"):
        _validate_submission(s, p, digest(p))


def test_review_is_cryptographically_bound_to_snapshot(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    s = submitted(p)
    _validate_submission(s, p, digest(p))
    with pytest.raises(ValueError, match="digest mismatch"):
        _validate_submission(s, p, "f"*64)


def test_aggregate_no_reviews_stays_pending(tmp_path, study, fake_case, fake_arch):
    manifest, _ = local_fixture(tmp_path, study, fake_case, fake_arch)
    report = aggregate(manifest, tmp_path/"none", tmp_path/"out")
    assert report["status"] == "awaiting_reviewers"
    assert all(not x["self_declared_quorum_met"] for x in report["candidates"])
    assert all(x["dimension_statistics"] == {} for x in report["candidates"])
    assert "NOT authenticated" in report["caveat"]
    assert (tmp_path/"out/expert-review-summary.md").exists()


def test_aggregate_one_review_suppresses_scores(tmp_path, study, fake_case, fake_arch):
    manifest, packets = local_fixture(tmp_path, study, fake_case, fake_arch)
    folder = tmp_path/"responses"; folder.mkdir()
    save_review(folder/"one.submission.json", submitted(packets[0]))
    report = aggregate(manifest, folder, tmp_path/"out")
    candidate = next(x for x in report["candidates"] if x["candidate_label"] == packets[0].candidate_label)
    assert candidate["self_declared_consented_reviewers"] == 1
    assert candidate["dimension_statistics"] == {}
    assert candidate["verdict_counts"] is None


def test_aggregate_two_self_declarations_not_certification(tmp_path, study, fake_case, fake_arch):
    manifest, packets = local_fixture(tmp_path, study, fake_case, fake_arch)
    folder = tmp_path/"responses"; folder.mkdir()
    save_review(folder/"one.submission.json", submitted(packets[0], "rev1", (2, 3, 4)))
    save_review(folder/"two.submission.json", submitted(packets[0], "rev2", (5, 3, 2)))
    report = aggregate(manifest, folder, tmp_path/"out")
    row = next(x for x in report["candidates"] if x["candidate_label"] == packets[0].candidate_label)
    assert row["self_declared_quorum_met"]
    assert row["status"] == "requires_external_identity_and_independence_check"
    assert row["dimension_statistics"]["cohesion"] == {"median": 3.5, "minimum": 2, "maximum": 5, "range": 3}
    assert row["disputed_dimensions_range_at_least_two"] == ["cohesion", "security"]
    # Overall quorum remains false because the OTHER architecture has zero reviewers.
    assert report["status"] == "awaiting_reviewers"


def test_both_candidates_quorum_still_not_verified(tmp_path, study, fake_case, fake_arch):
    manifest, packets = local_fixture(tmp_path, study, fake_case, fake_arch)
    folder = tmp_path/"responses"; folder.mkdir()
    for i, packet in enumerate(packets):
        for n in range(2):
            save_review(folder/f"{i}-{n}.submission.json", submitted(packet, f"reviewer-{n}"))
    report = aggregate(manifest, folder, tmp_path/"out")
    assert report["status"] == "self_declared_quorum_only_not_verified"
    assert all(x["self_declared_quorum_met"] for x in report["candidates"])


def test_conflict_and_no_consent_excluded(tmp_path, study, fake_case, fake_arch):
    manifest, packets = local_fixture(tmp_path, study, fake_case, fake_arch)
    folder = tmp_path/"responses"; folder.mkdir()
    save_review(folder/"conflict.submission.json", submitted(packets[0], "rev-a", independence="conflict", conflict_details="Worked on original design"))
    save_review(folder/"private.submission.json", submitted(packets[0], "rev-b", permission_to_publish_aggregate=False))
    report = aggregate(manifest, folder, tmp_path/"out")
    row = next(x for x in report["candidates"] if x["candidate_label"] == packets[0].candidate_label)
    assert row["excluded_reviews"] == 2
    assert row["self_declared_consented_reviewers"] == 0
    assert "rev-a" not in (tmp_path/"out/expert-review-summary.json").read_text()


def test_duplicate_self_declared_reviewer_rejected(tmp_path, study, fake_case, fake_arch):
    manifest, packets = local_fixture(tmp_path, study, fake_case, fake_arch)
    folder = tmp_path/"responses"; folder.mkdir()
    save_review(folder/"one.submission.json", submitted(packets[0], "Alice"))
    save_review(folder/"two.submission.json", submitted(packets[0], "aLIce"))
    with pytest.raises(ValueError, match="Duplicate self-declared reviewer"):
        aggregate(manifest, folder, tmp_path/"out")


def test_tampered_packet_rejected(tmp_path, study, fake_case, fake_arch):
    manifest, packets = local_fixture(tmp_path, study, fake_case, fake_arch)
    path = manifest.parent.parent / "packets" / f"{packets[0].candidate_label}.json"
    raw = json.loads(path.read_text())
    raw["architecture"]["selected_style"] = "microservices"
    _save(path, raw)
    with pytest.raises(ValueError, match="Original review packet has changed"):
        aggregate(manifest, tmp_path/"none", tmp_path/"out")


def test_tampered_submission_rejected(tmp_path, study, fake_case, fake_arch):
    manifest, packets = local_fixture(tmp_path, study, fake_case, fake_arch)
    folder = tmp_path/"responses"; folder.mkdir()
    save_review(folder/"forged.submission.json", submitted(packets[0], packet_sha256="f"*64))
    with pytest.raises(ValueError, match="digest mismatch"):
        aggregate(manifest, folder, tmp_path/"out")


def test_overspecified_submission_rejected(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    raw = submitted(p).model_dump(mode="json")
    raw["expert_certificate"] = "not possible"
    with pytest.raises(ValidationError):
        ReviewerSubmission.model_validate(raw)


def test_private_manifest_permission(tmp_path, study, fake_case, fake_arch):
    manifest, _ = local_fixture(tmp_path, study, fake_case, fake_arch)
    assert manifest.stat().st_mode & 0o077 == 0


def test_real_existing_phase6_candidates_prepare_without_expert_claims(tmp_path):
    root = Path(__file__).resolve().parents[1]
    study_path = root / "examples/expert-review/ecommerce-study.json"
    if not (root / "src/speccanopy/research.py").exists():
        pytest.skip("Full Phase 6 repository sources are not in this local staging tree")
    manifest = prepare(study_path, tmp_path/"packets")
    assert len(manifest.packets) == 2
    assert len({x.label for x in manifest.packets}) == 2
    for item in manifest.packets:
        packet_path = tmp_path/"packets/packets"/f"{item.label}.json"
        assert digest(Packet.model_validate_json(packet_path.read_text())) == item.packet_sha256
        assert item.candidate_id not in packet_path.name
    summary = aggregate(tmp_path/"packets/private/manifest.json", tmp_path/"no-responses", tmp_path/"report")
    assert summary["status"] == "awaiting_reviewers"
    assert summary["received_submission_files"] == 0


def test_independence_declaration_cannot_contradict_conflict(study, fake_case, fake_arch):
    p = make_packet(study, fake_case, fake_arch, label="C-000000000001", case_sha="a"*64)
    with pytest.raises(ValidationError, match="cannot also include conflict_details"):
        submitted(p, independence="self_declared_independent", conflict_details="Potential conflict")


def test_prepare_refuses_nonempty_output_with_actual_examples(tmp_path):
    root = Path(__file__).resolve().parents[1]
    study_path = root / "examples/expert-review/ecommerce-study.json"
    if not (root / "src/speccanopy/research.py").exists():
        pytest.skip("Full Phase 6 repository sources are not in this local staging tree")
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale-sensitive.json").write_text("{}")
    with pytest.raises(ValueError, match="must be empty"):
        prepare(study_path, out)


def test_private_manifest_rejects_duplicate_mapping(study, fake_case, fake_arch, tmp_path):
    manifest_path, _ = local_fixture(tmp_path, study, fake_case, fake_arch)
    raw = json.loads(manifest_path.read_text())
    raw["packets"][1]["label"] = raw["packets"][0]["label"]
    with pytest.raises(ValidationError, match="labels must be unique"):
        ReviewManifest.model_validate(raw)


def test_private_manifest_rejects_path_like_label(study, fake_case, fake_arch, tmp_path):
    manifest_path, _ = local_fixture(tmp_path, study, fake_case, fake_arch)
    raw = json.loads(manifest_path.read_text())
    raw["packets"][0]["label"] = "../../sensitive"
    with pytest.raises(ValidationError):
        ReviewManifest.model_validate(raw)


def test_cli_empty_study_summary(tmp_path, study, fake_case, fake_arch):
    from speccanopy.expert_review import main
    manifest_path, _ = local_fixture(tmp_path, study, fake_case, fake_arch)
    out = tmp_path/"out"
    assert main(["aggregate", str(manifest_path), "--submissions", str(tmp_path/"none"), "--output", str(out)]) == 0
    data = json.loads((out/"expert-review-summary.json").read_text())
    assert data["status"] == "awaiting_reviewers"


def test_cli_unknown_command_rejected(tmp_path):
    from speccanopy.expert_review import main
    with pytest.raises(SystemExit) as exc:
        main(["nonexistent"])
    assert exc.value.code == 2
