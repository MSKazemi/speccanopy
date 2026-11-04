"""CLI and exporter checks. These exercise engine outputs, not target app builds."""

import json
from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.decomposer import generate_architecture
from speccanopy.exporters import export_generation, relationships_mermaid, to_mermaid
from speccanopy.fixtures import FixtureDesign
from speccanopy.models import ArchitectureSpec, SystemBrief

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("stem", ["cli-utility", "ecommerce", "file-transfer"])
def test_end_to_end_cli_artifacts(tmp_path, stem, capsys):
    dest = tmp_path / stem
    code = main(["design", str(EXAMPLES / f"{stem}.json"), "--output", str(dest)])
    assert code == 0
    assert (dest / "architecture.json").is_file()
    spec = ArchitectureSpec.model_validate_json((dest / "architecture.json").read_text())
    assert spec.status == "draft"
    coverage = json.loads((dest / "requirements-report.json").read_text())
    assert coverage["coverage"]["uncovered"] == []
    assert coverage["coverage"]["verified"] == []
    tree = (dest / "architecture.mmd").read_text()
    graph = (dest / "relationships.mmd").read_text()
    assert tree.startswith("flowchart TD\n")
    assert graph.startswith("flowchart LR\n")
    assert tree.count("-->") == len(spec.components) - 1
    assert graph.count("-->") == len(spec.relationships)
    trace = json.loads((dest / "generation-trace.json").read_text())
    assert trace["statistics"]["components"] == len(spec.components)
    assert trace["events"][-1]["action"] == "completed"
    decisions = json.loads((dest / "decisions.json").read_text())
    assert decisions["selected_style"] == spec.selected_style
    assert "Artifacts:" in capsys.readouterr().out


def test_cli_second_run_writes_identical_artifacts(tmp_path):
    paths = []
    for name in ("first", "second"):
        dest = tmp_path / name
        assert main(["design", str(EXAMPLES / "ecommerce.json"), "--output", str(dest)]) == 0
        paths.append(dest)
    assert sorted(p.name for p in paths[0].iterdir()) == sorted(p.name for p in paths[1].iterdir())
    for p in paths[0].iterdir():
        assert p.read_bytes() == (paths[1] / p.name).read_bytes()


def test_cli_missing_fixture_returns_error(tmp_path, capsys):
    brief = tmp_path / "missing.json"
    brief.write_text((EXAMPLES / "cli-utility.json").read_text())
    assert main(["design", str(brief), "--output", str(tmp_path / "out")]) == 1
    assert "Error designing architecture" in capsys.readouterr().err


def test_cli_strict_flags_incomplete_output(tmp_path):
    brief = json.loads((EXAMPLES / "ecommerce.json").read_text())
    brief["constraints"]["max_depth"] = 0
    brief_path = tmp_path / "ecommerce.json"
    brief_path.write_text(json.dumps(brief))
    dest = tmp_path / "out"
    assert main(["design", str(brief_path), "--fixture", str(EXAMPLES / "ecommerce.design.json"),
                 "--output", str(dest), "--strict"]) == 2
    spec = ArchitectureSpec.model_validate_json((dest / "architecture.json").read_text())
    assert spec.status == "incomplete_requires_review"
    assert spec.coverage_report().uncovered


def test_mermaid_escapes_labels_and_uses_opaque_ids():
    brief = SystemBrief.model_validate_json((EXAMPLES / "cli-utility.json").read_text())
    fixture = FixtureDesign.model_validate_json((EXAMPLES / "cli-utility.design.json").read_text())
    fixture.root.name = 'A "quoted" app'
    architecture = generate_architecture(brief, fixture).architecture
    tree = to_mermaid(architecture)
    assert 'N0["A \\"quoted\\" app [ready]"]' in tree
    assert 'system --> input' not in tree
    assert len(relationships_mermaid(architecture).splitlines()) > 3


@pytest.mark.parametrize("stem", ["cli-utility", "ecommerce", "file-transfer"])
def test_checked_in_example_artifacts_match_generator(stem, tmp_path):
    dest = tmp_path / stem
    assert main(["design", str(EXAMPLES / f"{stem}.json"), "--output", str(dest)]) == 0
    reference = EXAMPLES / "generated" / stem
    assert sorted(p.name for p in reference.iterdir()) == sorted(p.name for p in dest.iterdir())
    for path in reference.iterdir():
        assert (dest / path.name).read_bytes() == path.read_bytes()
