"""Offline Python AST intake: schema-valid drafts, import edges, source claims.

All source examples are synthetic temporary repos. No target Python imports,
application code execution, API calls or independent human verification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.decomposer import generate_architecture
from speccanopy.fixtures import FixtureDesign
from speccanopy.models import ArchitectureSpec, SystemBrief
from speccanopy.project_intake import IntakeObservations, prepare_project_intake
from speccanopy.source_evidence import SourceEvidence, SourceInventory, assess_sources

ARTIFACTS = {
    "brief.json", "design.json", "source-evidence.json",
    "source-inventory.json", "module-observations.json", "intake-review.md",
}


def _demo(root: Path) -> Path:
    root.mkdir(parents=True)
    pkg = root / "src" / "sample"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "api.py").write_text(
        "from . import store\n"
        "from .service import Service\n"
        "import os\n"
        "\n"
        "class API:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "service.py").write_text(
        "from .store import get\n"
        "raise RuntimeError('this module MUST NEVER execute in intake')\n"
        "\n"
        "class Service:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "store.py").write_text("def get():\n    return 123\n", encoding="utf-8")
    (root / "README.md").write_text("User requirements must be stated separately.")
    (root / "frontend.ts").write_text("export const x = true;")
    (root / ".env").write_text("PASSWORD=SECRET_MARKER")
    (root / "private").mkdir()
    (root / "private" / "passwords.py").write_text("TOKEN=SECRET")
    (root / "tests").mkdir()
    (root / "tests" / "test_api.py").write_text("def test_a(): pass")
    return root


def _args(root: Path, output: Path) -> list[str]:
    return [
        "project-intake", str(root), "--system", "Sample App",
        "--goal", "Document the existing module boundaries",
        "--requirement", "The application must present a user-facing API",
        "--requirement", "The application must persist application records",
        "--output", str(output),
    ]


def test_intake_cli_writes_schema_valid_drafts_and_detects_python_imports(tmp_path, capsys):
    root = _demo(tmp_path / "my-app")
    folder = tmp_path / "generated"
    assert main(_args(root, folder)) == 0
    assert {p.name for p in folder.iterdir()} == ARTIFACTS

    brief = SystemBrief.model_validate_json((folder / "brief.json").read_text())
    design = FixtureDesign.model_validate_json((folder / "design.json").read_text())
    evidence = SourceEvidence.model_validate_json((folder / "source-evidence.json").read_text())
    obs = IntakeObservations.model_validate_json(
        (folder / "module-observations.json").read_text()
    )
    inventory = SourceInventory.model_validate_json(
        (folder / "source-inventory.json").read_text()
    )
    assert brief.system == "Sample App"
    assert [x.id for x in brief.functional_requirements] == [
        "FR-USER-001", "FR-USER-002",
    ]
    assert brief.quality_requirements == []
    assert design.selected_style is None
    assert design.verification_cases == []
    assert design.decisions == []
    assert design.root.requirement_ids == []
    assert design.root.status == "proposed"
    assert len(design.proposals_by_parent["system"]) == 4
    assert all(not p.requirement_ids for p in design.proposals_by_parent["system"])
    assert all(not p.validation_evidence for p in design.proposals_by_parent["system"])
    names = {x.module: x.component_id for x in obs.modules}
    assert set(names) == {"sample", "sample.api", "sample.service", "sample.store"}
    assert len(obs.dependencies) == 3
    edge_names = {
        (next(x.module for x in obs.modules if x.component_id == e.source_id),
         next(x.module for x in obs.modules if x.component_id == e.target_id))
        for e in obs.dependencies
    }
    assert edge_names == {
        ("sample.api", "sample.service"),
        ("sample.api", "sample.store"),
        ("sample.service", "sample.store"),
    }
    assert len(evidence.claims) == 4 + 3
    assert all(c.basis == "observed" for c in evidence.claims)
    assert "frontend.ts" in obs.excluded_non_python_source
    assert "README.md" in {x.path for x in inventory.files}
    assert ".env" not in (folder / "source-inventory.json").read_text()
    assert "SECRET_MARKER" not in (folder / "intake-review.md").read_text()
    assert "MUST NEVER execute" not in (folder / "intake-review.md").read_text()
    assert "Owner review required" in (folder / "intake-review.md").read_text()
    assert "PROVISIONAL" in capsys.readouterr().out


def test_end_to_end_intake_design_review_document_with_source_provenance(tmp_path):
    root = _demo(tmp_path / "project")
    inputs = tmp_path / "inputs"
    assert main(_args(root, inputs)) == 0
    design_out = tmp_path / "design"
    assert main([
        "design", str(inputs / "brief.json"), "--fixture",
        str(inputs / "design.json"), "--output", str(design_out),
    ]) == 0
    spec = ArchitectureSpec.model_validate_json((design_out / "architecture.json").read_text())
    assert spec.status == "incomplete_requires_review"
    assert spec.coverage_report().verified == []
    assert spec.coverage_report().planned_only == []
    assert set(spec.coverage_report().uncovered) == {"FR-USER-001", "FR-USER-002"}
    review_out = tmp_path / "review"
    assert main(["review", str(design_out / "architecture.json"),
                 "--output", str(review_out)]) == 0
    docs = tmp_path / "docs"
    assert main([
        "document", str(design_out / "architecture.json"),
        "--review", str(review_out / "architecture-review.json"),
        "--source-root", str(root),
        "--source-evidence", str(inputs / "source-evidence.json"),
        "--output", str(docs),
    ]) == 0
    assert (docs / "README.md").is_file()
    assert (docs / "source-evidence.md").is_file()
    assert (docs / "open-questions.md").is_file()
    source_check = (docs / "source-evidence.md").read_text()
    assert "Matching byte snapshots: 7" in source_check
    assert "FR-USER-001" in source_check
    assert "FR-USER-002" in source_check
    assert "source" in (docs / "open-questions.md").read_text().lower()
    report = assess_sources(
        spec,
        SourceEvidence.model_validate_json((inputs / "source-evidence.json").read_text()),
        root,
    )
    assert all(c.status == "matching_snapshot" for c in report.checks)
    assert report.requires_review
    assert "system" in report.unlinked_components
    assert len(report.unlinked_mandatory_requirements) == 2


def test_intake_is_deterministic_and_path_ids_stable_when_more_files_added(tmp_path):
    root = _demo(tmp_path / "project")
    a = prepare_project_intake(
        root, system="Sample App", goal="Document", requirements=["Handle request"]
    )
    b = prepare_project_intake(
        root, system="Sample App", goal="Document", requirements=["Handle request"]
    )
    assert a.brief.model_dump() == b.brief.model_dump()
    assert a.fixture.model_dump() == b.fixture.model_dump()
    assert a.evidence.model_dump() == b.evidence.model_dump()
    before = {x.source_path: x.component_id for x in a.observations.modules}
    (root / "src" / "sample" / "extra.py").write_text(
        "def extra(): return 1\n", encoding="utf-8",
    )
    c = prepare_project_intake(
        root, system="Sample App", goal="Document", requirements=["Handle request"]
    )
    after = {x.source_path: x.component_id for x in c.observations.modules}
    assert all(after[k] == v for k, v in before.items())
    assert len(after) == len(before) + 1


def test_stale_source_claims_are_flagged_after_local_change(tmp_path):
    root = _demo(tmp_path / "project")
    result = prepare_project_intake(
        root, system="App", goal="Document", requirements=["Store records"]
    )
    arch = generate_architecture(result.brief, result.fixture).architecture
    (root / "src" / "sample" / "store.py").write_text(
        "def get():\n    return 567\n", encoding="utf-8",
    )
    assessment = assess_sources(arch, result.evidence, root)
    assert any(c.status == "changed" for c in assessment.checks)
    assert assessment.requires_review


def test_source_code_is_not_imported_or_executed(tmp_path):
    root = _demo(tmp_path / "project")
    (root / "src" / "sample" / "service.py").write_text(
        "import os\n"
        "raise RuntimeError('NOT SAFE TO EXECUTE')\n"
        "os.environ['DANGEROUS_SIDE_EFFECT'] = 'yes'\n",
        encoding="utf-8",
    )
    import os
    os.environ.pop("DANGEROUS_SIDE_EFFECT", None)
    result = prepare_project_intake(
        root, system="App", goal="Document", requirements=["Do things"]
    )
    assert result.observations.modules
    assert "DANGEROUS_SIDE_EFFECT" not in os.environ
    assert "NOT SAFE TO EXECUTE" not in str(result.observations.model_dump())


def test_unsupported_only_project_fails_without_writing(tmp_path, capsys):
    root = tmp_path / "js-project"
    root.mkdir()
    (root / "server.ts").write_text("export function run() { return 1; }")
    out = tmp_path / "new-docs"
    assert main(_args(root, out)) == 1
    assert not out.exists()
    assert "supports Python" in capsys.readouterr().err


def test_invalid_python_syntax_fails_before_output(tmp_path):
    root = _demo(tmp_path / "project")
    (root / "src" / "sample" / "store.py").write_text("def broken(:\n")
    out = tmp_path / "outputs"
    assert main(_args(root, out)) == 1
    assert not out.exists()


def test_bound_failures_never_write_partial_artifacts(tmp_path):
    root = _demo(tmp_path / "project")
    a = tmp_path / "out1"
    assert main(_args(root, a) + ["--max-modules", "2"]) == 1
    assert not a.exists()
    b = tmp_path / "out2"
    assert main(_args(root, b) + ["--max-files", "1"]) == 1
    assert not b.exists()


def test_existing_output_and_symlink_root_are_rejected(tmp_path):
    root = _demo(tmp_path / "project")
    out = tmp_path / "existing"
    out.mkdir()
    (out / "brief.json").write_text("MY APPROVED BRIEF")
    assert main(_args(root, out)) == 1
    assert (out / "brief.json").read_text() == "MY APPROVED BRIEF"
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    out2 = tmp_path / "out2"
    assert main(_args(alias, out2)) == 1
    assert not out2.exists()


def test_ambiguous_module_names_fail_closed(tmp_path):
    root = _demo(tmp_path / "project")
    (root / "sample").mkdir()
    (root / "sample" / "service.py").write_text("def x(): pass\n")
    out = tmp_path / "ambiguous"
    assert main(_args(root, out)) == 1
    assert not out.exists()


def test_empty_package_and_unrelated_standard_imports_are_not_dependencies(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "app.py").write_text("import os\nimport json\n")
    result = prepare_project_intake(
        root, system="App", goal="Explain", requirements=["Process things"]
    )
    assert len(result.observations.modules) == 1
    assert result.observations.dependencies == []
    assert len(result.evidence.claims) == 1


def test_self_repository_python_intake_smoke(tmp_path):
    """Dogfood against Speccanopy source; NOT an external validation study."""
    root = Path(__file__).resolve().parents[1]
    inputs = tmp_path / "self-inputs"
    assert main([
        "project-intake", str(root), "--system", "Speccanopy",
        "--goal", "Document the existing Python module boundaries",
        "--requirement", "Provide structured software architecture documentation",
        "--max-modules", "50", "--output", str(inputs),
    ]) == 0
    obs = IntakeObservations.model_validate_json(
        (inputs / "module-observations.json").read_text()
    )
    names = {item.module for item in obs.modules}
    assert {"speccanopy.cli", "speccanopy.project_intake", "speccanopy.source_evidence"} <= names
    assert obs.dependencies
    structure = tmp_path / "self-design"
    assert main([
        "design", str(inputs / "brief.json"), "--fixture",
        str(inputs / "design.json"), "--output", str(structure),
    ]) == 0
    review = tmp_path / "self-review"
    assert main(["review", str(structure / "architecture.json"),
                 "--output", str(review)]) == 0
    docs = tmp_path / "self-docs"
    assert main([
        "document", str(structure / "architecture.json"),
        "--review", str(review / "architecture-review.json"),
        "--source-root", str(root),
        "--source-evidence", str(inputs / "source-evidence.json"),
        "--output", str(docs),
    ]) == 0
    assert "matching\\_snapshot" in (docs / "source-evidence.md").read_text()
    assert "FR-USER-001" in (docs / "open-questions.md").read_text()
    assert "incomplete_requires_review" in (
        structure / "architecture.json"
    ).read_text()
