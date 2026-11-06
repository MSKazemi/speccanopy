"""Documentation review gate: deterministic, never upgrades a status, fails closed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.doc_gate import (
    CATEGORY_ORDER,
    DocumentationGate,
    GateItem,
    evaluate_documentation_gate,
    export_documentation_gate,
    render_documentation_gate_markdown,
)
from speccanopy.models import ArchitectureSpec
from speccanopy.review import ArchitectureReview, assess_architecture
from speccanopy.source_evidence import (
    SourceAssessment,
    SourceCheck,
    SourceClaim,
    SourceEvidence,
    assess_sources,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
STEMS = ["cli-utility", "ecommerce", "file-transfer"]


def _example(stem: str) -> ArchitectureSpec:
    return ArchitectureSpec.model_validate_json(
        (EXAMPLES / "generated" / stem / "architecture.json").read_text())


def _review(stem: str) -> ArchitectureReview:
    return ArchitectureReview.model_validate_json(
        (EXAMPLES / "reviews" / stem / "architecture-review.json").read_text())


def _comp(**over):
    base = {
        "id": "root", "name": "Root", "responsibility": "Do the work", "boundary": "Whole app",
        "requirement_ids": ["FR-1", "QR-1"], "interfaces_not_applicable_reason": "CLI only",
        "data_not_applicable_reason": "Stateless", "validation_evidence": ["Design walk-through"],
        "stop_reason": "Atomic enough", "quality_targets": {"QR-1": "p95 < 1s"},
        "status": "ready",
    }
    base.update(over)
    return base


def _spec(status="draft", **over) -> ArchitectureSpec:
    data = {
        "brief": {
            "system": "Tiny", "goals": ["Be tiny"],
            "functional_requirements": [{"id": "FR-1", "statement": "Do it"}],
            "quality_requirements": [{"id": "QR-1", "attribute": "latency", "statement": "Fast"}],
        },
        "selected_style": "single process",
        "components": [_comp()],
        "verification_cases": [{
            "id": "VC-1", "description": "Walk-through", "method": "design_review",
            "requirement_ids": ["FR-1", "QR-1"], "component_ids": ["root"],
            "status": "verified", "evidence": "Reviewed by author"}],
        "status": status,
    }
    data.update(over)
    return ArchitectureSpec.model_validate(data)


def _project(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    body = b"def main():\n    return 1\n"
    (root / "src" / "app.py").write_bytes(body)
    return root, hashlib.sha256(body).hexdigest()


def _assessment(tmp_path: Path, spec: ArchitectureSpec, ids, basis="observed") -> SourceAssessment:
    root, sha = _project(tmp_path)
    evidence = SourceEvidence(claims=[
        SourceClaim(architecture_id=i, source_path="src/app.py", sha256=sha,
                    assertion=f"Implements {i}", basis=basis) for i in ids])
    return assess_sources(spec, evidence, root)


def _cats(gate: DocumentationGate, category, severity=None):
    return [i for i in gate.items if i.category == category
            and (severity is None or i.severity == severity)]


# --- categories -------------------------------------------------------------

def test_uncovered_requirement_blocks_including_unmapped():
    spec = _spec(
        verification_cases=[],
        components=[_comp(requirement_ids=["FR-1"], quality_targets={})],
    )
    gate = evaluate_documentation_gate(spec)
    items = _cats(gate, "uncovered_requirement", "blocking")
    assert {i.subject_id for i in items} == {"FR-1", "QR-1"}
    assert any("mapped to no component" in i.message for i in items if i.subject_id == "QR-1")
    assert any("no verification case" in i.message for i in items if i.subject_id == "FR-1")
    assert len([i for i in items if i.subject_id == "QR-1"]) == 1
    assert gate.outcome == "requires_review"


def test_planned_only_requirement_is_attention():
    spec = _spec(verification_cases=[{
        "id": "VC-1", "description": "Plan", "method": "test_plan",
        "requirement_ids": ["FR-1", "QR-1"], "component_ids": ["root"]}])
    gate = evaluate_documentation_gate(spec)
    items = _cats(gate, "planned_only_requirement")
    assert {i.subject_id for i in items} == {"FR-1", "QR-1"}
    assert {i.severity for i in items} == {"attention"}
    assert not _cats(gate, "uncovered_requirement")


def test_sources_none_is_one_blocking_unmapped_item():
    gate = evaluate_documentation_gate(_spec())
    items = _cats(gate, "unknown_source_mapping")
    assert len(items) == 1 and items[0].severity == "blocking" and items[0].subject_id is None
    assert "no source evidence supplied" in items[0].message.lower()
    assert gate.outcome == "requires_review"
    assert not gate.sources_supplied


def test_unlinked_requirements_and_components_block(tmp_path):
    spec = _spec()
    gate = evaluate_documentation_gate(spec, sources=_assessment(tmp_path, spec, ["root"]))
    items = _cats(gate, "unknown_source_mapping", "blocking")
    assert {i.subject_id for i in items} == {"FR-1", "QR-1"}
    assert gate.sources_supplied


def test_unsupported_claims_changed_blocks_inferred_attention(tmp_path):
    spec = _spec()
    root, sha = _project(tmp_path)
    ev = SourceEvidence(claims=[
        SourceClaim(architecture_id="root", source_path="src/app.py", sha256="0" * 64,
                    assertion="stale", basis="observed"),
        SourceClaim(architecture_id="FR-1", source_path="src/app.py", sha256=sha,
                    assertion="guess", basis="inferred"),
        SourceClaim(architecture_id="QR-1", source_path="src/app.py", sha256=sha,
                    assertion="plan", basis="proposed"),
    ])
    gate = evaluate_documentation_gate(spec, sources=assess_sources(spec, ev, root))
    blocking = _cats(gate, "unsupported_claim", "blocking")
    attention = [i for i in _cats(gate, "unsupported_claim", "attention") if i.subject_id != "VC-1"]
    assert [i.subject_id for i in blocking] == ["root"] and "changed" in blocking[0].message
    assert {i.subject_id for i in attention} == {"FR-1", "QR-1"}


def test_verified_case_flagged_as_self_reported_even_without_sources():
    gate = evaluate_documentation_gate(_spec())
    items = [i for i in _cats(gate, "unsupported_claim") if i.subject_id == "VC-1"]
    assert len(items) == 1 and items[0].severity == "attention"
    assert "not independently checked" in items[0].message


def test_manual_decisions_findings_and_component_status():
    def child(cid, status=None):
        c = {"id": cid, "name": cid, "responsibility": "x", "boundary": "y", "parent_id": "root"}
        if status:
            c["status"] = status
        return c

    spec = _spec(
        components=[_comp(), child("child", "needs_decomposition"), child("blk", "blocked"),
                    child("rr", "requires_review"), child("pr")],
        decisions=[{"id": "ADR-1", "title": "Pick", "choice": "a", "rationale": "b"},
                   {"id": "ADR-2", "title": "Done", "choice": "a", "rationale": "b",
                    "status": "accepted"}],
        findings=[
            {"id": "F-1", "severity": "critical", "description": "bad"},
            {"id": "F-2", "severity": "high", "description": "bad"},
            {"id": "F-3", "severity": "medium", "description": "meh"},
            {"id": "F-4", "severity": "critical", "description": "gone", "status": "resolved"},
        ])
    gate = evaluate_documentation_gate(spec)
    sev = {i.subject_id: i.severity for i in _cats(gate, "manual_decision")}
    assert sev["child"] == sev["blk"] == sev["rr"] == "blocking"
    assert sev["pr"] == "attention"
    assert sev["F-1"] == sev["F-2"] == "blocking" and sev["F-3"] == "attention"
    assert sev["ADR-1"] == "attention"
    assert sev["ADR-2"] == "attention"  # authored acceptance still needs owner confirmation
    assert "F-4" not in sev


def test_incomplete_status_blocks():
    gate = evaluate_documentation_gate(_spec("incomplete_requires_review"))
    assert any(i.severity == "blocking" and i.subject_id is None
               for i in _cats(gate, "manual_decision"))


def test_review_requires_review_is_attention_and_findings_listed():
    spec = _example("ecommerce")
    review = _review("ecommerce")
    assert review.overall_status == "requires_review"
    gate = evaluate_documentation_gate(spec, review=review)
    assert gate.review_supplied
    msgs = [i.message for i in _cats(gate, "manual_decision", "attention")]
    assert any("overall status is requires_review" in m for m in msgs)
    assert any(i.message.startswith("Advisory review finding") for i in gate.items)


def test_mismatched_review_system_is_blocking_and_not_raised():
    gate = evaluate_documentation_gate(_example("ecommerce"), review=_review("cli-utility"))
    mism = [i for i in _cats(gate, "manual_decision", "blocking") if "different system" in i.message]
    assert len(mism) == 1
    assert not any(i.message.startswith("Advisory review finding") for i in gate.items)


def test_mismatched_review_status_is_blocking():
    spec = _spec()
    review = assess_architecture(spec).model_copy(
        update={"source_architecture_status": "validated_for_scope"})
    gate = evaluate_documentation_gate(spec, review=review)
    assert any("different system or architecture status" in i.message for i in gate.items)


# --- status and outcome -----------------------------------------------------

def test_validated_for_scope_never_yields_more_than_signoff_readiness(tmp_path):
    spec = _spec("validated_for_scope")
    assert spec.status == "validated_for_scope"
    gate = evaluate_documentation_gate(spec)  # no sources => still blocked
    assert gate.outcome == "requires_review"
    claims = _cats(gate, "status_claim")
    assert len(claims) == 1 and claims[0].severity == "attention"
    assert "cannot confirm" in claims[0].message
    full = evaluate_documentation_gate(
        spec, review=_candidate_review(spec),
        sources=_assessment(tmp_path, spec, ["root", "FR-1", "QR-1"]))
    assert full.outcome == "ready_for_human_signoff"
    assert spec.status == "validated_for_scope"  # untouched
    assert DocumentationGate.model_fields["outcome"].annotation.__args__ == (
        "requires_review", "ready_for_human_signoff")
    assert _cats(full, "status_claim")  # still reported, never upgraded


def test_all_good_path_reaches_ready_for_human_signoff_but_keeps_attention(tmp_path):
    spec = _spec()  # draft, all components ready, verified coverage
    review = assess_architecture(spec)  # honest review: overall requires_review is attention
    gate = evaluate_documentation_gate(
        spec, review=review, sources=_assessment(tmp_path, spec, ["root", "FR-1", "QR-1"]))
    assert gate.outcome == "ready_for_human_signoff"
    assert gate.blocking_count == 0
    assert gate.attention_count >= 2  # draft status + self-reported verification
    assert "not expert review" in gate.caveat and "human must" in gate.caveat
    assert "NOT validation or approval" in render_documentation_gate_markdown(gate)


def test_ready_with_matching_candidate_review(tmp_path):
    spec = _spec("validated_for_scope")
    # Synthetic: flips only the advisory review's own status to its non-blocking value.
    review = assess_architecture(spec).model_copy(
        update={"overall_status": "candidate_for_human_review"})
    gate = evaluate_documentation_gate(
        spec, review=review, sources=_assessment(tmp_path, spec, ["root", "FR-1", "QR-1"]))
    assert gate.outcome == "ready_for_human_signoff"


def test_model_rejects_forged_outcome_counts_caveat_and_category():
    gate = evaluate_documentation_gate(_spec())
    data = gate.model_dump()
    data["outcome"] = "ready_for_human_signoff"
    with pytest.raises(ValidationError):
        DocumentationGate.model_validate(data)
    data = gate.model_dump()
    data["counts"]["manual_decision"] += 1
    with pytest.raises(ValidationError):
        DocumentationGate.model_validate(data)
    data = gate.model_dump()
    data["caveat"] = "It is certified."
    with pytest.raises(ValidationError):
        DocumentationGate.model_validate(data)
    with pytest.raises(ValidationError):
        GateItem(category="validated", severity="blocking", message="x")


@pytest.mark.parametrize("stem", STEMS)
def test_shipped_examples_do_not_pass_and_stay_unmodified(stem):
    spec = _example(stem)
    before = spec.model_dump_json()
    gate = evaluate_documentation_gate(spec, review=_review(stem))
    assert gate.outcome == "requires_review"
    assert set(gate.counts) == set(CATEGORY_ORDER)
    assert sum(gate.counts.values()) == len(gate.items)
    assert spec.model_dump_json() == before and spec.status == "draft"


def test_items_sorted_blocking_first():
    gate = evaluate_documentation_gate(_example("ecommerce"), review=_review("ecommerce"))
    ranks = [0 if i.severity == "blocking" else 1 for i in gate.items]
    assert ranks == sorted(ranks)


# --- determinism, rendering, escaping ---------------------------------------

def test_deterministic_json_and_markdown(tmp_path):
    spec, review = _example("ecommerce"), _review("ecommerce")
    a = evaluate_documentation_gate(spec, review=review)
    b = evaluate_documentation_gate(spec, review=review)
    assert a.model_dump_json() == b.model_dump_json()
    assert render_documentation_gate_markdown(a) == render_documentation_gate_markdown(b)
    pa = export_documentation_gate(a, tmp_path / "a")
    pb = export_documentation_gate(b, tmp_path / "b")
    for name in ("documentation-gate.json", "documentation-gate.md"):
        assert pa[name].read_bytes() == pb[name].read_bytes()
    assert set(pa) == {"documentation-gate.json", "documentation-gate.md"}
    assert json.loads(pa["documentation-gate.json"].read_text())["outcome"] == "requires_review"


def test_markdown_summary_first_and_blocking_sections_first():
    md = render_documentation_gate_markdown(
        evaluate_documentation_gate(_spec("validated_for_scope")))
    assert md.index("Outcome") < md.index("## Summary") < md.index("| Category |")
    assert md.index("## Unknown source mappings") < md.index("## Authored status claims")
    for title in ("Uncovered requirements", "Planned-only requirements",
                  "Unsupported or self-reported claims", "Remaining manual decisions"):
        assert "## " + title in md


def test_markdown_escapes_hostile_authored_text():
    hostile = "x\n# PWNED <script>alert(1)</script> | [a](http://e) `c` *b* _u_"
    spec = _spec(
        brief={"system": hostile, "goals": ["g"],
               "functional_requirements": [{"id": "FR-1", "statement": "s"}],
               "quality_requirements": [{"id": "QR-1", "attribute": "a", "statement": "s"}]},
        findings=[{"id": "F-1", "severity": "high", "description": hostile}],
        decisions=[{"id": "ADR-1", "title": hostile, "choice": "c", "rationale": "r"}],
    )
    md = render_documentation_gate_markdown(evaluate_documentation_gate(spec))
    assert "<script>" not in md
    assert "\n# PWNED" not in md
    assert "&lt;script&gt;" in md
    assert "\\|" in md and "\\[a\\]" in md and "\\`c\\`" in md and "\\*b\\*" in md


# --- export guard -----------------------------------------------------------

def test_export_refuses_nonempty_dir_file_and_symlink(tmp_path):
    gate = evaluate_documentation_gate(_spec())
    full = tmp_path / "full"
    full.mkdir()
    (full / "notes.md").write_text("MINE")
    with pytest.raises(ValueError, match="new or empty"):
        export_documentation_gate(gate, full)
    assert (full / "notes.md").read_text() == "MINE"
    afile = tmp_path / "file"
    afile.write_text("x")
    with pytest.raises(ValueError):
        export_documentation_gate(gate, afile)
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        export_documentation_gate(gate, link)
    assert not any(target.iterdir())
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "nowhere")
    with pytest.raises(ValueError):
        export_documentation_gate(gate, dangling)
    empty = tmp_path / "empty"
    empty.mkdir()
    export_documentation_gate(gate, empty)
    assert (empty / "documentation-gate.md").exists()


def test_hand_built_assessment_is_accepted_without_filesystem():
    spec = _spec()
    check = SourceCheck(architecture_id="root", source_path="src/app.py", assertion="a",
                        basis="observed", line_start=None, line_end=None,
                        expected_sha256="0" * 64, actual_sha256=None, status="missing")
    sources = SourceAssessment(checks=[check], unlinked_mandatory_requirements=["FR-1"],
                               unlinked_components=["root"])
    gate = evaluate_documentation_gate(spec, sources=sources)
    assert [i.subject_id for i in _cats(gate, "unsupported_claim", "blocking")] == ["root"]
    assert {i.subject_id for i in _cats(gate, "unknown_source_mapping")} == {"FR-1", "root"}


# --- review-round fixes (gaming / forgery / rendering) ------------------------

def _candidate_review(spec: ArchitectureSpec) -> ArchitectureReview:
    return assess_architecture(spec).model_copy(
        update={"overall_status": "candidate_for_human_review"})


def test_omitting_review_is_blocking_so_omission_is_never_rewarded(tmp_path):
    spec = _spec()
    sources = _assessment(tmp_path, spec, ["root", "FR-1", "QR-1"])
    without = evaluate_documentation_gate(spec, sources=sources)
    assert without.outcome == "requires_review"
    assert any(i.category == "manual_decision" and i.severity == "blocking"
               and i.subject_id is None and "No advisory review" in i.message
               for i in without.items)
    honest = evaluate_documentation_gate(spec, review=assess_architecture(spec), sources=sources)
    assert honest.outcome == "ready_for_human_signoff"  # supplying an honest review never hurts


def test_review_overall_requires_review_is_attention_but_high_findings_block(tmp_path):
    spec = _spec()
    review = assess_architecture(spec)
    assert review.overall_status == "requires_review"
    gate = evaluate_documentation_gate(
        spec, review=review, sources=_assessment(tmp_path, spec, ["root", "FR-1", "QR-1"]))
    overall = [i for i in gate.items if "overall status is requires_review" in i.message]
    assert len(overall) == 1 and overall[0].severity == "attention"
    for rf in review.quality_review.findings:
        sev = {i.severity for i in gate.items if i.subject_id == rf.id}
        assert sev == {"blocking" if rf.severity in {"critical", "high"} else "attention"}


def test_brief_without_mandatory_requirements_blocks(tmp_path):
    spec = _spec(brief={
        "system": "Tiny", "goals": ["Be tiny"],
        "functional_requirements": [{"id": "FR-1", "statement": "Do it", "mandatory": False}],
        "quality_requirements": [{"id": "QR-1", "attribute": "latency", "statement": "Fast",
                                  "mandatory": False}],
    })
    gate = evaluate_documentation_gate(
        spec, review=_candidate_review(spec),
        sources=_assessment(tmp_path, spec, ["root", "FR-1", "QR-1"]))
    assert gate.outcome == "requires_review"
    assert any(i.category == "uncovered_requirement" and i.severity == "blocking"
               and "no mandatory requirements" in i.message for i in gate.items)


def test_authored_acceptances_and_ready_components_get_attention():
    spec = _spec(
        findings=[{"id": "F-1", "severity": "critical", "description": "Bad", "status": "accepted"}],
        decisions=[{"id": "ADR-1", "title": "Use X", "choice": "X", "rationale": "Because",
                    "status": "accepted"}],
    )
    gate = evaluate_documentation_gate(spec)
    by_subject = {i.subject_id: i for i in gate.items if i.category == "manual_decision"}
    assert by_subject["F-1"].severity == "attention" and "accepted" in by_subject["F-1"].message
    assert by_subject["ADR-1"].severity == "attention" and "accepted" in by_subject["ADR-1"].message
    assert by_subject["root"].severity == "attention" and "ready" in by_subject["root"].message


def test_gate_model_rejects_header_inconsistent_with_items():
    gate = evaluate_documentation_gate(_spec("incomplete_requires_review"))
    data = gate.model_dump()
    data["items"] = []
    data["counts"] = {c: 0 for c in CATEGORY_ORDER}
    data["blocking_count"] = data["attention_count"] = 0
    data["outcome"] = "ready_for_human_signoff"
    with pytest.raises(ValidationError):
        DocumentationGate.model_validate(data)


def test_subject_ids_render_without_backslashes_inside_code_spans():
    spec = _spec(findings=[{"id": "mod_a_b", "severity": "low", "description": "x"}])
    md = render_documentation_gate_markdown(evaluate_documentation_gate(spec))
    assert "`mod_a_b`" in md and "`mod\\_" not in md
