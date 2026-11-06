"""Claim impact tests.

Inventories are built in memory from synthetic text; no project is touched, no
network is used. A digest comparison says nothing about whether an architecture
claim is still true, so no test asserts that anything is verified.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.models import ArchitectureSpec
from speccanopy.source_diff import compare_inventories
from speccanopy.source_evidence import (
    InventoryScope, SourceClaim, SourceEvidence, SourceFile, SourceInventory,
    inventory_policy_digest,
)
from speccanopy.source_impact import (
    ClaimImpactReport, assess_claim_impact, export_claim_impact,
    render_claim_impact_markdown,
)

ARCH = Path(__file__).resolve().parents[1] / "examples/generated/cli-utility/architecture.json"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _file(path: str, text: str = "x\n", kind: str = "source") -> SourceFile:
    data = text.encode()
    return SourceFile(
        path=path, sha256=hashlib.sha256(data).hexdigest(),
        byte_count=len(data), line_count=len(data.splitlines()), kind=kind,
    )


def _inv(*files: SourceFile, skipped: int = 0) -> SourceInventory:
    return SourceInventory(
        files=sorted(files, key=lambda f: f.path), skipped_oversized=skipped,
        scope=InventoryScope(
            max_files=2000, max_file_bytes=1_000_000, policy_sha256=inventory_policy_digest(),
        ),
    )


def _claim(path: str, text: str, target: str = "FR-001", *, basis="observed",
           assertion="Authored observation", start=None, end=None) -> SourceClaim:
    return SourceClaim(
        architecture_id=target, source_path=path, sha256=_sha(text),
        assertion=assertion, basis=basis, line_start=start, line_end=end,
    )


def _evidence(*claims: SourceClaim) -> SourceEvidence:
    return SourceEvidence(claims=list(claims))


def _spec() -> ArchitectureSpec:
    return ArchitectureSpec.model_validate_json(ARCH.read_text(encoding="utf-8"))


def _status_of(report: ClaimImpactReport, path: str) -> str:
    return next(e.status for e in report.entries if e.source_path == path)


# ---------------------------------------------------------------- statuses

def test_unaffected_requires_unchanged_path_and_matching_digest():
    inv = _inv(_file("a.py", "one\n"))
    report = assess_claim_impact(
        compare_inventories(inv, inv), _evidence(_claim("a.py", "one\n")),
    )
    assert [e.status for e in report.entries] == ["unaffected"]
    assert report.affected_architecture_ids == []
    assert report.requires_review is False


def test_stale_changed_when_claim_bound_to_before_digest():
    before, after = _inv(_file("a.py", "one\n")), _inv(_file("a.py", "two\n"))
    report = assess_claim_impact(
        compare_inventories(before, after), _evidence(_claim("a.py", "one\n")),
    )
    entry = report.entries[0]
    assert entry.status == "stale_changed"
    assert entry.before_sha256 == _sha("one\n") and entry.after_sha256 == _sha("two\n")
    assert report.affected_architecture_ids == ["FR-001"]
    assert report.requires_review is True


def test_stale_removed_and_rename_is_removed_plus_added():
    before = _inv(_file("old_name.py", "body\n"))
    after = _inv(_file("new_name.py", "body\n"))
    report = assess_claim_impact(
        compare_inventories(before, after), _evidence(_claim("old_name.py", "body\n")),
    )
    assert report.entries[0].status == "stale_removed"
    assert "rename" in report.entries[0].reason.lower()
    # The new path is not linked to the old claim: it is only reported as uncited.
    assert report.uncited_added_paths == ["new_name.py"]
    assert report.requires_review is True


def test_not_bound_to_before_when_claim_digest_matches_neither_side():
    before, after = _inv(_file("a.py", "one\n")), _inv(_file("a.py", "two\n"))
    report = assess_claim_impact(
        compare_inventories(before, after), _evidence(_claim("a.py", "other\n")),
    )
    assert report.entries[0].status == "not_bound_to_before"
    assert report.requires_review is True


def test_not_bound_to_before_when_unchanged_path_but_claim_digest_differs():
    inv = _inv(_file("a.py", "one\n"))
    report = assess_claim_impact(
        compare_inventories(inv, inv), _evidence(_claim("a.py", "other\n")),
    )
    assert report.entries[0].status == "not_bound_to_before"
    assert report.affected_architecture_ids == ["FR-001"]


def test_rebound_to_after_is_review_required_never_unaffected():
    before, after = _inv(_file("a.py", "one\n")), _inv(_file("a.py", "two\n"))
    report = assess_claim_impact(
        compare_inventories(before, after), _evidence(_claim("a.py", "two\n")),
    )
    assert report.entries[0].status == "rebound_to_after"
    assert report.affected_architecture_ids == ["FR-001"]
    assert report.requires_review is True
    assert "verified" in report.caveat.lower()


def test_rebound_to_after_also_for_added_file_with_matching_digest():
    before, after = _inv(), _inv(_file("new.py", "n\n"))
    report = assess_claim_impact(
        compare_inventories(before, after), _evidence(_claim("new.py", "n\n")),
    )
    assert report.entries[0].status == "rebound_to_after"
    # A cited added path is not "uncited".
    assert report.uncited_added_paths == []
    assert report.requires_review is True


def test_not_in_inventory_when_path_absent_from_both():
    inv = _inv(_file("a.py", "one\n"))
    report = assess_claim_impact(
        compare_inventories(inv, inv), _evidence(_claim("gone.py", "z\n")),
    )
    entry = report.entries[0]
    assert entry.status == "not_in_inventory"
    assert entry.before_sha256 is None and entry.after_sha256 is None
    assert report.requires_review is True


def test_every_status_together_and_counts():
    before = _inv(
        _file("same.py", "s\n"), _file("chg.py", "c1\n"), _file("rm.py", "r\n"),
        _file("nb.py", "n1\n"), _file("rb.py", "b1\n"),
    )
    after = _inv(
        _file("same.py", "s\n"), _file("chg.py", "c2\n"),
        _file("nb.py", "n2\n"), _file("rb.py", "b2\n"),
    )
    evidence = _evidence(
        _claim("same.py", "s\n", "FR-001"), _claim("chg.py", "c1\n", "FR-002"),
        _claim("rm.py", "r\n", "FR-003"), _claim("nb.py", "zzz\n", "NFR-001"),
        _claim("rb.py", "b2\n", "system"), _claim("ghost.py", "g\n", "input"),
    )
    report = assess_claim_impact(compare_inventories(before, after), evidence)
    assert report.status_counts == {
        "unaffected": 1, "stale_changed": 1, "stale_removed": 1,
        "not_bound_to_before": 1, "rebound_to_after": 1, "not_in_inventory": 1,
    }
    assert report.affected_architecture_ids == sorted(
        ["FR-002", "FR-003", "NFR-001", "system", "input"])


def test_entries_sorted_deterministically_with_line_spans():
    inv = _inv(_file("a.py", "one\n"), _file("b.py", "two\n"))
    evidence = _evidence(
        _claim("b.py", "two\n", "FR-002"),
        _claim("a.py", "one\n", "FR-002", start=5, end=6),
        _claim("a.py", "one\n", "FR-002", start=1, end=2),
        _claim("a.py", "one\n", "FR-001"),
    )
    report = assess_claim_impact(compare_inventories(inv, inv), evidence)
    keys = [(e.architecture_id, e.source_path, e.line_start, e.line_end) for e in report.entries]
    assert keys == [
        ("FR-001", "a.py", None, None), ("FR-002", "a.py", 1, 2),
        ("FR-002", "a.py", 5, 6), ("FR-002", "b.py", None, None),
    ]


# ------------------------------------------------------- uncited observations

def test_uncited_added_and_changed_paths_are_listed_and_force_review():
    before = _inv(_file("a.py", "1\n"), _file("b.py", "1\n"), _file("c.py", "1\n"))
    after = _inv(_file("a.py", "1\n"), _file("b.py", "2\n"), _file("c.py", "1\n"),
                 _file("z_new.py", "n\n"), _file("m_new.py", "n\n"))
    report = assess_claim_impact(
        compare_inventories(before, after), _evidence(_claim("a.py", "1\n")),
    )
    assert report.uncited_added_paths == ["m_new.py", "z_new.py"]
    assert report.uncited_changed_paths == ["b.py"]
    assert [e.status for e in report.entries] == ["unaffected"]
    assert report.requires_review is True  # every claim unaffected, still review


def test_empty_evidence_requires_review_even_with_identical_inventories():
    inv = _inv()
    report = assess_claim_impact(compare_inventories(inv, inv), _evidence())
    assert report.entries == []
    assert report.requires_review is True  # zero claims checked is not an all-clear


def test_diff_requires_review_is_propagated():
    before = _inv(_file("a.py", "1\n"), skipped=0)
    after = _inv(_file("a.py", "1\n"), skipped=2)  # oversized files skipped
    diff = compare_inventories(before, after)
    assert diff.requires_review is True
    report = assess_claim_impact(diff, _evidence(_claim("a.py", "1\n")))
    assert [e.status for e in report.entries] == ["unaffected"]
    assert report.diff_requires_review is True
    assert report.requires_review is True


def test_diff_scope_differences_are_propagated_not_hidden():
    other = SourceInventory(files=[_file("a.py", "1\n")], scope=None)
    diff = compare_inventories(other, other)
    report = assess_claim_impact(diff, _evidence(_claim("a.py", "1\n")))
    assert report.diff_coverage == "scope_unknown"
    assert report.requires_review is True


# ----------------------------------------------------------------- spec checks

def test_unknown_architecture_id_raises_value_error():
    inv = _inv(_file("a.py", "1\n"))
    with pytest.raises(ValueError, match="unknown architecture ID: NOPE-9"):
        assess_claim_impact(
            compare_inventories(inv, inv), _evidence(_claim("a.py", "1\n", "NOPE-9")), _spec(),
        )


def test_unknown_architecture_id_not_checked_without_spec():
    inv = _inv(_file("a.py", "1\n"))
    report = assess_claim_impact(
        compare_inventories(inv, inv), _evidence(_claim("a.py", "1\n", "NOPE-9")),
    )
    assert report.mandatory_requirements_without_current_observed_evidence is None


def test_mandatory_requirements_without_current_observed_evidence():
    before = _inv(_file("a.py", "1\n"), _file("b.py", "1\n"), _file("c.py", "1\n"),
                  _file("d.py", "1\n"))
    after = _inv(_file("a.py", "1\n"), _file("b.py", "2\n"), _file("c.py", "1\n"),
                 _file("d.py", "1\n"))
    evidence = _evidence(
        _claim("a.py", "1\n", "FR-001", basis="observed"),            # current observed
        _claim("b.py", "1\n", "FR-002", basis="observed"),            # stale
        _claim("c.py", "1\n", "FR-003", basis="inferred"),            # not observed
        _claim("d.py", "1\n", "system", basis="observed"),            # not a requirement
    )
    report = assess_claim_impact(compare_inventories(before, after), evidence, _spec())
    assert report.mandatory_requirements_without_current_observed_evidence == [
        "FR-002", "FR-003", "NFR-001"]
    assert report.requires_review is True


def test_all_mandatory_requirements_with_current_observed_evidence_is_clean():
    inv = _inv(_file("a.py", "1\n"))
    evidence = _evidence(*(_claim("a.py", "1\n", rid, start=i + 1, end=i + 1)
                           for i, rid in enumerate(["FR-001", "FR-002", "FR-003", "NFR-001"])))
    report = assess_claim_impact(compare_inventories(inv, inv), evidence, _spec())
    assert report.mandatory_requirements_without_current_observed_evidence == []
    assert report.requires_review is False


# ----------------------------------------------------------------- determinism

def _scenario():
    before = _inv(_file("a.py", "1\n"), _file("b.py", "1\n"))
    after = _inv(_file("a.py", "2\n"), _file("b.py", "1\n"), _file("n.py", "n\n"))
    evidence = _evidence(_claim("a.py", "1\n", "FR-001"), _claim("b.py", "1\n", "FR-002"))
    return compare_inventories(before, after), evidence


def test_json_and_markdown_are_byte_identical_on_repeat(tmp_path):
    diff, evidence = _scenario()
    one = export_claim_impact(assess_claim_impact(diff, evidence, _spec()), tmp_path / "one")
    two = export_claim_impact(assess_claim_impact(diff, evidence, _spec()), tmp_path / "two")
    for name in ("claim-impact.json", "claim-impact.md"):
        assert one[name].read_bytes() == two[name].read_bytes()


def test_output_has_no_host_paths_or_timestamps(tmp_path):
    diff, evidence = _scenario()
    paths = export_claim_impact(assess_claim_impact(diff, evidence), tmp_path / "out")
    text = "".join(p.read_text(encoding="utf-8") for p in paths.values())
    assert str(tmp_path) not in text
    assert "T00:" not in text and "datetime" not in text.lower()


def test_json_round_trips_and_is_sorted():
    diff, evidence = _scenario()
    report = assess_claim_impact(diff, evidence)
    again = ClaimImpactReport.model_validate_json(
        json.dumps(report.model_dump(mode="json")))
    assert again == report


def test_report_rejects_inconsistent_hand_edits():
    diff, evidence = _scenario()
    data = assess_claim_impact(diff, evidence).model_dump(mode="json")
    data["status_counts"]["unaffected"] += 1
    with pytest.raises(ValidationError):
        ClaimImpactReport.model_validate(data)


# -------------------------------------------------------------------- markdown

def test_markdown_escapes_hostile_assertion_text():
    inv = _inv(_file("a.py", "1\n"))
    hostile = "a | b `code` <script>alert(1)</script>\n# Heading\n[x](http://evil) *bold*"
    report = assess_claim_impact(
        compare_inventories(inv, inv),
        _evidence(_claim("a.py", "1\n", assertion=hostile)),
    )
    md = render_claim_impact_markdown(report)
    assert "<script>" not in md
    assert "&lt;script&gt;" in md
    assert "\\|" in md and "\\`code\\`" in md and "\\[x\\]" in md
    assert "\n# Heading" not in md  # newline collapsed; cannot start a heading
    for line in md.splitlines():
        if line.startswith("| FR-001"):
            # table row keeps exactly its own columns despite the hostile pipe
            assert line.replace("\\|", "").count("|") == 8


def test_markdown_states_limits_and_never_claims_verification():
    diff, evidence = _scenario()
    md = render_claim_impact_markdown(assess_claim_impact(diff, evidence, _spec()))
    assert "Metadata" in md
    assert "not verified" in md.lower() or "no claim is marked verified" in md.lower()
    assert "rename" in md.lower()
    assert "Requires review: **yes**" in md


# ---------------------------------------------------------------------- export

def test_export_writes_exactly_two_files(tmp_path):
    diff, evidence = _scenario()
    paths = export_claim_impact(assess_claim_impact(diff, evidence), tmp_path / "out" / "nested")
    assert sorted(paths) == ["claim-impact.json", "claim-impact.md"]
    assert sorted(p.name for p in (tmp_path / "out" / "nested").iterdir()) == sorted(paths)
    assert json.loads(paths["claim-impact.json"].read_text())["schema_version"] == 1


def test_export_accepts_existing_empty_directory(tmp_path):
    diff, evidence = _scenario()
    (tmp_path / "empty").mkdir()
    export_claim_impact(assess_claim_impact(diff, evidence), tmp_path / "empty")


def test_export_refuses_non_empty_directory(tmp_path):
    diff, evidence = _scenario()
    report = assess_claim_impact(diff, evidence)
    (tmp_path / "full").mkdir()
    keep = tmp_path / "full" / "mine.txt"
    keep.write_text("owner file")
    with pytest.raises(ValueError, match="new or empty directory"):
        export_claim_impact(report, tmp_path / "full")
    assert keep.read_text() == "owner file"
    assert [p.name for p in (tmp_path / "full").iterdir()] == ["mine.txt"]


def test_export_refuses_file_destination(tmp_path):
    diff, evidence = _scenario()
    target = tmp_path / "afile"
    target.write_text("x")
    with pytest.raises(ValueError, match="new or empty directory"):
        export_claim_impact(assess_claim_impact(diff, evidence), target)
    assert target.read_text() == "x"


def test_export_refuses_symlink_destination(tmp_path):
    diff, evidence = _scenario()
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="new or empty directory"):
        export_claim_impact(assess_claim_impact(diff, evidence), link)
    assert list(real.iterdir()) == []


def test_export_refuses_dangling_symlink_destination(tmp_path):
    diff, evidence = _scenario()
    link = tmp_path / "dangling"
    link.symlink_to(tmp_path / "nowhere")
    with pytest.raises(ValueError, match="new or empty directory"):
        export_claim_impact(assess_claim_impact(diff, evidence), link)
    assert not (tmp_path / "nowhere").exists()


# --- review-round fixes ---------------------------------------------------------

def test_report_rejects_forged_entry_status_reason_and_caveat_and_empty_is_review():
    import hashlib as _h
    from speccanopy.source_impact import ClaimImpactReport

    sha = lambda b: _h.sha256(b).hexdigest()  # noqa: E731
    entry = {
        "architecture_id": "c1", "source_path": "src/a.py", "assertion": "x",
        "basis": "observed", "claim_sha256": sha(b"old"), "before_sha256": sha(b"new"),
        "after_sha256": sha(b"new"), "status": "unaffected",
        "reason": "Verified.",
    }
    base = {
        "entries": [entry], "status_counts": {
            "unaffected": 1, "stale_changed": 0, "stale_removed": 0,
            "not_bound_to_before": 0, "rebound_to_after": 0, "not_in_inventory": 0},
        "affected_architecture_ids": [], "uncited_added_paths": [],
        "uncited_changed_paths": [], "diff_requires_review": False,
        "diff_coverage": "comparable",
    }
    with pytest.raises(ValidationError):  # status contradicts digests, forged reason
        ClaimImpactReport.model_validate(base)
    with pytest.raises(ValidationError):  # forged caveat
        ClaimImpactReport.model_validate({
            **base, "entries": [], "status_counts": {k: 0 for k in base["status_counts"]},
            "caveat": "Verified by expert."})
    empty = ClaimImpactReport.model_validate({
        **base, "entries": [], "status_counts": {k: 0 for k in base["status_counts"]}})
    assert empty.requires_review  # zero claims checked is not an all-clear
