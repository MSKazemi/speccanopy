"""CLI integration of `speccanopy source-impact` and `speccanopy doc-gate`.

Synthetic temporary projects and the repository's committed synthetic examples
only. Neither command verifies architecture semantics or certifies anything;
these tests check exit codes, artifacts, refusal of existing outputs and that
no stronger-than-authored status is ever reported.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from speccanopy.cli import main
from speccanopy.doc_gate import DocumentationGate
from speccanopy.source_impact import ClaimImpactReport

EX = Path(__file__).resolve().parents[1] / "examples"
CLI_ARCH = EX / "generated/cli-utility/architecture.json"
IMPACT_OUTPUTS = {"claim-impact.json", "claim-impact.md"}
GATE_OUTPUTS = {"documentation-gate.json", "documentation-gate.md"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project(root: Path) -> Path:
    (root / "src" / "app").mkdir(parents=True)
    (root / "src" / "app" / "api.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    (root / "src" / "app" / "store.py").write_text("ROWS = []\n", encoding="utf-8")
    (root / "src" / "app" / "cli.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (root / ".env").write_text("TOKEN=IMPACT_SECRET_MARKER", encoding="utf-8")
    return root


def _evidence(root: Path, path: Path, claims: list[tuple[str, str, str]]) -> Path:
    data = {"schema_version": 1, "claims": [
        {"architecture_id": aid, "source_path": rel, "sha256": _sha(root / rel),
         "assertion": f"{aid} is implemented in {rel}", "basis": basis}
        for aid, rel, basis in claims
    ]}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _inventory(root: Path, path: Path) -> Path:
    assert main(["source-inventory", str(root), "--output", str(path)]) == 0
    return path


def test_source_impact_cli_reports_stale_claims_and_strict_exit(tmp_path, capsys):
    root = _project(tmp_path / "app")
    evidence = _evidence(root, tmp_path / "evidence.json", [
        ("input", "src/app/api.py", "observed"),
        ("normalize", "src/app/store.py", "observed"),
        ("output", "src/app/cli.py", "observed"),
    ])
    before = _inventory(root, tmp_path / "before.json")
    (root / "src" / "app" / "api.py").write_text("def handler():\n    return 2\n", encoding="utf-8")
    (root / "src" / "app" / "store.py").unlink()
    (root / "src" / "app" / "queue.py").write_text("JOBS = []\n", encoding="utf-8")
    after = _inventory(root, tmp_path / "after.json")
    capsys.readouterr()

    out = tmp_path / "impact"
    args = ["source-impact", str(before), str(after), "--evidence", str(evidence)]
    assert main([*args, "--architecture", str(CLI_ARCH), "--output", str(out)]) == 0
    stdout = capsys.readouterr().out
    assert "Claim impact: 3 claims" in stdout
    assert "Requires review: yes" in stdout
    assert "no claim verified" in stdout
    assert {p.name for p in out.iterdir()} == IMPACT_OUTPUTS
    report = ClaimImpactReport.model_validate_json((out / "claim-impact.json").read_text())
    status = {e.architecture_id: e.status for e in report.entries}
    assert status == {"input": "stale_changed", "normalize": "stale_removed",
                      "output": "unaffected"}
    assert report.affected_architecture_ids == ["input", "normalize"]
    assert report.uncited_added_paths == ["src/app/queue.py"]
    # No claim maps a requirement, so every mandatory requirement lacks current evidence.
    assert report.mandatory_requirements_without_current_observed_evidence == [
        "FR-001", "FR-002", "FR-003", "NFR-001"]
    for name in IMPACT_OUTPUTS:
        text = (out / name).read_text()
        assert "IMPACT_SECRET_MARKER" not in text and ".env" not in text
        assert str(tmp_path) not in text

    strict = tmp_path / "impact-strict"
    assert main([*args, "--architecture", str(CLI_ARCH), "--output", str(strict), "--strict"]) == 2
    assert (strict / "claim-impact.json").read_bytes() == (out / "claim-impact.json").read_bytes()


def test_source_impact_cli_unchanged_snapshot_without_architecture_exits_zero_strict(tmp_path, capsys):
    root = _project(tmp_path / "app")
    evidence = _evidence(root, tmp_path / "evidence.json", [
        ("anything", "src/app/api.py", "observed"),
        ("anything", "src/app/store.py", "observed"),
        ("anything", "src/app/cli.py", "observed"),
    ])
    a = _inventory(root, tmp_path / "a.json")
    b = _inventory(root, tmp_path / "b.json")
    assert main(["source-impact", str(a), str(b), "--evidence", str(evidence),
                 "--output", str(tmp_path / "i"), "--strict"]) == 0
    assert "Requires review: no" in capsys.readouterr().out


def test_source_impact_cli_unknown_id_and_existing_output_fail_closed(tmp_path, capsys):
    root = _project(tmp_path / "app")
    evidence = _evidence(root, tmp_path / "evidence.json", [("not-a-component", "src/app/api.py", "observed")])
    a = _inventory(root, tmp_path / "a.json")
    capsys.readouterr()
    bad = tmp_path / "bad"
    assert main(["source-impact", str(a), str(a), "--evidence", str(evidence),
                 "--architecture", str(CLI_ARCH), "--output", str(bad)]) == 1
    assert "unknown architecture ID" in capsys.readouterr().err
    assert not bad.exists()

    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "notes.md").write_text("OWNER", encoding="utf-8")
    assert main(["source-impact", str(a), str(a), "--evidence", str(evidence),
                 "--output", str(owned)]) == 1
    assert "existing files not overwritten" in capsys.readouterr().err
    assert (owned / "notes.md").read_text() == "OWNER"
    assert {p.name for p in owned.iterdir()} == {"notes.md"}


def test_doc_gate_cli_examples_require_review_and_strict_exit(tmp_path, capsys):
    out = tmp_path / "gate"
    arch = EX / "generated/ecommerce/architecture.json"
    assert main(["doc-gate", str(arch), "--output", str(out)]) == 0
    stdout = capsys.readouterr().out
    assert "Outcome: requires_review" in stdout
    assert "not expert review or certification" in stdout
    assert {p.name for p in out.iterdir()} == GATE_OUTPUTS
    gate = DocumentationGate.model_validate_json((out / "documentation-gate.json").read_text())
    assert gate.outcome == "requires_review"
    assert any(i.category == "unknown_source_mapping" and i.severity == "blocking"
               for i in gate.items)
    assert main(["doc-gate", str(arch), "--output", str(tmp_path / "g2"), "--strict"]) == 2
    assert ((tmp_path / "g2" / "documentation-gate.json").read_bytes()
            == (out / "documentation-gate.json").read_bytes())


def test_doc_gate_cli_with_review_and_source_evidence(tmp_path, capsys):
    root = _project(tmp_path / "app")
    evidence = _evidence(root, tmp_path / "evidence.json", [
        ("input", "src/app/api.py", "observed"),
        ("FR-001", "src/app/api.py", "inferred"),
    ])
    review_dir = tmp_path / "review"
    assert main(["review", str(CLI_ARCH), "--config", str(EX / "cli-utility.review.json"),
                 "--output", str(review_dir)]) == 0
    capsys.readouterr()
    out = tmp_path / "gate"
    assert main(["doc-gate", str(CLI_ARCH), "--review", str(review_dir / "architecture-review.json"),
                 "--source-root", str(root), "--source-evidence", str(evidence),
                 "--output", str(out)]) == 0
    gate = DocumentationGate.model_validate_json((out / "documentation-gate.json").read_text())
    assert gate.review_supplied and gate.sources_supplied
    assert gate.outcome == "requires_review"  # components/requirements remain unlinked
    unlinked = {i.subject_id for i in gate.items if i.category == "unknown_source_mapping"}
    assert {"normalize", "output", "FR-002"} <= unlinked
    assert "input" not in unlinked
    assert any(i.category == "unsupported_claim" and i.subject_id == "FR-001"
               and i.severity == "attention" for i in gate.items)
    text = (out / "documentation-gate.md").read_text()
    assert "IMPACT_SECRET_MARKER" not in text and str(tmp_path) not in text


def test_doc_gate_cli_rejects_half_source_options_and_existing_output(tmp_path, capsys):
    bad = tmp_path / "bad"
    assert main(["doc-gate", str(CLI_ARCH), "--source-root", str(tmp_path),
                 "--output", str(bad)]) == 1
    assert "must be provided together" in capsys.readouterr().err
    assert not bad.exists()
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "notes.md").write_text("OWNER", encoding="utf-8")
    assert main(["doc-gate", str(CLI_ARCH), "--output", str(owned)]) == 1
    assert "existing files not overwritten" in capsys.readouterr().err
    assert {p.name for p in owned.iterdir()} == {"notes.md"}
