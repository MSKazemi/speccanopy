"""Local source inventory and digest-bound architecture evidence tests.

All projects are temporary synthetic files. The tests do not access private
applications, use LLMs, or assert that file hashes prove architectural truth.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy import source_evidence
from speccanopy.cli import main
from speccanopy.models import ArchitectureSpec
from speccanopy.source_evidence import (
    InventoryScope, SourceClaim, SourceEvidence, SourceFile, SourceInventory,
    assess_sources, inventory_policy_digest, safe_source_path, scan_sources,
    save_inventory,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
ARCH = EXAMPLES / "generated/cli-utility/architecture.json"


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "sample-app"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "node_modules").mkdir()
    (root / ".hidden").mkdir()
    (root / "private").mkdir()
    (root / "README.md").write_text("# Demo app\n\nRuns a local command.\n", encoding="utf-8")
    (root / "src" / "main.py").write_text(
        "def main():\n    return 'example'\n", encoding="utf-8",
    )
    (root / "tests" / "test_main.py").write_text(
        "def test_main():\n    assert True\n", encoding="utf-8",
    )
    (root / ".env").write_text("SECRET_CREDENTIAL=must-not-appear")
    (root / ".hidden" / "internal.py").write_text("secret")
    (root / "private" / "details.py").write_text("secret")
    (root / "node_modules" / "leak.js").write_text("secret")
    (root / "src" / "credentials.yml").write_text("token: hidden")
    (root / "src" / "secrets.py").write_text("hidden")
    (root / "data.json").write_text('{"secret":"no"}')
    return root


def _claim(source: SourceFile, target: str, *, basis="observed", start=1, end=1):
    return SourceClaim(
        architecture_id=target, source_path=source.path,
        sha256=source.sha256, assertion="Authored source observation",
        basis=basis, line_start=start, line_end=end,
    )


def _map(root: Path) -> SourceEvidence:
    entries = {x.path: x for x in scan_sources(root).files}
    return SourceEvidence(claims=[
        _claim(entries["README.md"], "FR-001"),
        _claim(entries["src/main.py"], "system"),
    ])


def _write_map(tmp_path: Path, evidence: SourceEvidence) -> Path:
    path = tmp_path / "source-evidence.json"
    path.write_text(evidence.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_inventory_safe_deterministic_metadata_and_no_contents(tmp_path):
    root = _project(tmp_path)
    a = scan_sources(root)
    b = scan_sources(root)
    assert a.model_dump() == b.model_dump()
    assert [x.path for x in a.files] == [
        "README.md", "src/main.py", "tests/test_main.py",
    ]
    assert a.files[0].kind == "documentation"
    assert a.files[2].kind == "test"
    assert a.files[1].sha256 == hashlib.sha256(
        (root / "src/main.py").read_bytes()
    ).hexdigest()
    assert a.files[1].line_count == 2
    text = a.model_dump_json()
    assert "must-not-appear" not in text
    assert "def main" not in text
    assert "token: hidden" not in text
    assert str(tmp_path) not in text
    assert a.skipped_oversized == 0


def test_inventory_cli_saves_reproducible_json_and_refuses_overwrite(tmp_path, capsys):
    root = _project(tmp_path)
    path = tmp_path / "out" / "sources.json"
    assert main(["source-inventory", str(root), "--output", str(path)]) == 0
    raw = path.read_bytes()
    obj = SourceInventory.model_validate_json(path.read_text())
    assert len(obj.files) == 3
    assert main(["source-inventory", str(root), "--output", str(path)]) == 1
    assert path.read_bytes() == raw
    assert "Error inventorying sources" in capsys.readouterr().err
    assert main(["source-inventory", str(root), "--output",
                 str(tmp_path / "out" / "second.json")]) == 0
    second = tmp_path / "out" / "second.json"
    assert second.read_bytes() == raw


def test_inventory_skips_symlinks_and_oversized_files(tmp_path):
    root = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("EXTERNAL_TOP_SECRET")
    (root / "src" / "linked.py").symlink_to(outside / "secret.py")
    (root / "linked-dir").symlink_to(outside, target_is_directory=True)
    (root / "src" / "big.py").write_text("z" * 300)
    result = scan_sources(root, max_bytes=100)
    assert result.skipped_oversized == 1
    assert all("linked" not in x.path and "big" not in x.path for x in result.files)
    assert all("secret" not in x.path for x in result.files)
    with pytest.raises(ValueError, match="not a symlink"):
        scan_sources(root / "linked-dir")


def test_inventory_records_scan_scope_and_policy_digest(tmp_path):
    root = _project(tmp_path)
    inventory = scan_sources(root, max_files=50, max_bytes=4096)
    assert inventory.scope == InventoryScope(
        max_files=50, max_file_bytes=4096, policy_sha256=inventory_policy_digest(),
    )
    assert inventory_policy_digest() == inventory_policy_digest()
    assert len(inventory_policy_digest()) == 64
    assert scan_sources(root).scope.max_files == 2000
    assert str(tmp_path) not in inventory.model_dump_json()


def test_inventory_policy_digest_changes_with_privacy_policy(monkeypatch):
    original = inventory_policy_digest()
    monkeypatch.setattr(
        source_evidence, "EXCLUDED_DIRS", source_evidence.EXCLUDED_DIRS | {"extra"},
    )
    assert inventory_policy_digest() != original
    monkeypatch.undo()
    monkeypatch.setattr(source_evidence, "INVENTORY_POLICY_VERSION", 99)
    assert inventory_policy_digest() != original


def test_legacy_inventory_without_scope_still_loads_with_unknown_scope(tmp_path):
    raw = json.loads(scan_sources(_project(tmp_path)).model_dump_json())
    del raw["scope"]
    legacy = SourceInventory.model_validate(raw)
    assert legacy.scope is None
    raw["scope"] = {"max_files": 1, "max_file_bytes": 1, "policy_sha256": "bad"}
    with pytest.raises(ValidationError):
        SourceInventory.model_validate(raw)


def test_inventory_file_limit_fails_closed(tmp_path):
    root = _project(tmp_path)
    with pytest.raises(ValueError, match="file limit"):
        scan_sources(root, max_files=1)
    with pytest.raises(ValueError, match="max_files"):
        scan_sources(root, max_files=0)
    with pytest.raises(ValueError, match="max_bytes"):
        scan_sources(root, max_bytes=0)
    with pytest.raises(ValueError):
        save_inventory(scan_sources(root), root / "README.md")


@pytest.mark.parametrize("unsafe", [
    "../README.md", "/etc/passwd", "src/../README.md", "src//main.py",
    "./README.md", "src\\main.py", ".env", "private/abc.py",
    "secrets.py", "src/credentials.yml", "data.json", "README.md\nINJECTION",
])
def test_source_evidence_rejects_unsafe_paths(unsafe):
    with pytest.raises((ValidationError, ValueError)):
        SourceClaim(
            architecture_id="FR-001", source_path=unsafe, sha256="a" * 64,
            assertion="Claim", basis="observed",
        )


def test_invalid_range_hash_and_duplicate_claims_rejected(tmp_path):
    root = _project(tmp_path)
    first = scan_sources(root).files[0]
    base = _claim(first, "FR-001")
    with pytest.raises(ValidationError, match="Duplicate source claims"):
        SourceEvidence(claims=[base, base])
    with pytest.raises(ValidationError, match="line_start and line_end"):
        SourceClaim(
            architecture_id="FR-001", source_path="README.md",
            sha256="a" * 64, assertion="Claim", basis="observed", line_start=2,
        )
    with pytest.raises(ValidationError):
        SourceClaim(
            architecture_id="FR-001", source_path="README.md",
            sha256="not-sha", assertion="Claim", basis="observed",
        )
    with pytest.raises(ValidationError, match="reversed"):
        SourceClaim(
            architecture_id="FR-001", source_path="README.md",
            sha256="a" * 64, assertion="Claim", basis="observed",
            line_start=5, line_end=4,
        )


def test_document_cli_sources_connected_and_gap_report(tmp_path, capsys):
    root = _project(tmp_path)
    evidence = _write_map(tmp_path, _map(root))
    output = tmp_path / "docs"
    args = [
        "document", str(ARCH),
        "--source-root", str(root), "--source-evidence", str(evidence),
        "--output", str(output),
    ]
    assert main(args) == 0
    report = (output / "source-evidence.md").read_text(encoding="utf-8")
    assert "matching\\_snapshot" in report
    assert "FR-001" in report
    assert "src/main.py" in report
    assert "Matching byte snapshots: 2" in report
    assert "not independently verified" not in report.lower() or "not" in report.lower()
    assert "Source evidence and change status" in (output / "README.md").read_text()
    questions = (output / "open-questions.md").read_text()
    assert "source provenance" in questions.lower()
    assert "source citations" in capsys.readouterr().out.lower()
    assert main(args) == 1  # Existing, nonempty documentation never overwritten.


def test_document_changes_missing_and_invalid_line_spans_remain_visible(tmp_path):
    root = _project(tmp_path)
    manifest = _map(root)
    a, b = manifest.claims
    b.line_end = 900
    b.line_start = 900
    report = assess_sources(ArchitectureSpec.model_validate_json(ARCH.read_text()),
                            manifest, root)
    assert [x.status for x in report.checks] == ["matching_snapshot", "line_out_of_range"]
    assert report.requires_review
    (root / "README.md").write_text("Changed contents.", encoding="utf-8")
    (root / "src" / "main.py").unlink()
    report2 = assess_sources(ArchitectureSpec.model_validate_json(ARCH.read_text()),
                             manifest, root)
    assert [x.status for x in report2.checks] == ["changed", "missing"]
    evidence = _write_map(tmp_path, manifest)
    output = tmp_path / "docs"
    assert main(["document", str(ARCH), "--source-root", str(root),
                 "--source-evidence", str(evidence), "--output", str(output)]) == 0
    text = (output / "source-evidence.md").read_text()
    assert "changed" in text and "missing" in text
    assert "Investigate changed source" in (output / "open-questions.md").read_text()
    assert "Investigate missing source" in (output / "open-questions.md").read_text()


def test_document_evidence_with_unknown_architecture_id_rejected_before_write(tmp_path):
    root = _project(tmp_path)
    claim = _map(root).claims[0].model_copy(update={"architecture_id": "GHOST"})
    evidence = _write_map(tmp_path, SourceEvidence(claims=[claim]))
    out = tmp_path / "docs"
    assert main(["document", str(ARCH), "--source-root", str(root),
                 "--source-evidence", str(evidence), "--output", str(out)]) == 1
    assert not out.exists()


def test_document_rejects_only_one_evidence_argument_without_writing(tmp_path):
    root = _project(tmp_path)
    path = _write_map(tmp_path, _map(root))
    o = tmp_path / "docs"
    assert main(["document", str(ARCH), "--source-evidence",
                 str(path), "--output", str(o)]) == 1
    assert not o.exists()
    assert main(["document", str(ARCH), "--source-root",
                 str(root), "--output", str(o)]) == 1
    assert not o.exists()


def test_document_rejects_sensitive_symlink_and_marks_as_unreadable(tmp_path):
    root = _project(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("secret from outside", encoding="utf-8")
    (root / "src" / "redirect.py").symlink_to(outside)
    claim = SourceClaim(
        architecture_id="FR-001", source_path="src/redirect.py",
        sha256="a" * 64, assertion="Authored claim", basis="observed",
    )
    result = assess_sources(
        ArchitectureSpec.model_validate_json(ARCH.read_text()),
        SourceEvidence(claims=[claim]), root,
    )
    assert len(result.checks) == 1
    assert result.checks[0].status == "unreadable"
    assert result.checks[0].actual_sha256 is None


def test_inferred_proposed_source_claims_never_count_as_observed(tmp_path):
    root = _project(tmp_path)
    claim = _map(root).claims[0]
    claim.basis = "inferred"
    report = assess_sources(
        ArchitectureSpec.model_validate_json(ARCH.read_text()),
        SourceEvidence(claims=[claim]), root,
    )
    assert report.checks[0].status == "matching_snapshot"
    assert "FR-001" in report.unlinked_mandatory_requirements
    assert report.requires_review


def test_evidence_claim_text_escaped_from_markdown_injection(tmp_path):
    root = _project(tmp_path)
    evidence_obj = _map(root)
    evidence_obj.claims[0].assertion = "<script>bad()</script> | Bad\n# heading"
    evidence = _write_map(tmp_path, evidence_obj)
    out = tmp_path / "docs"
    assert main(["document", str(ARCH), "--source-root", str(root),
                 "--source-evidence", str(evidence), "--output", str(out)]) == 0
    text = (out / "source-evidence.md").read_text()
    assert "&lt;script&gt;" in text
    assert "Bad # heading" in text
    assert "\n# heading\n" not in text
