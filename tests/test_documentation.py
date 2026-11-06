"""Architecture documentation pack: real CLI outputs, deterministic rendering and safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.documentation import render_documentation
from speccanopy.models import ArchitectureSpec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
FILES = {
    "README.md", "overview.md", "requirements.md", "components.md",
    "interactions.md", "data-security.md", "decisions.md", "quality-risks.md",
    "open-questions.md", "architecture.mmd", "relationships.mmd",
    "view-data-flow.md", "view-trust-boundaries.md", "view-deployment.md",
    "view-runtime.md",
}


@pytest.mark.parametrize("stem", ["cli-utility", "ecommerce", "file-transfer"])
def test_document_cli_generates_all_views_without_certifying(stem, tmp_path, capsys):
    src = EXAMPLES / "generated" / stem / "architecture.json"
    output = tmp_path / stem
    assert main(["document", str(src), "--output", str(output)]) == 0
    assert {p.name for p in output.iterdir()} == FILES
    spec = ArchitectureSpec.model_validate_json(src.read_text())
    assert (output / "architecture.mmd").read_text() == (
        EXAMPLES / "generated" / stem / "architecture.mmd"
    ).read_text()
    assert (output / "relationships.mmd").read_text() == (
        EXAMPLES / "generated" / stem / "relationships.mmd"
    ).read_text()
    assert spec.brief.system in (output / "README.md").read_text()
    assert "Architecture status: **draft**" in (output / "overview.md").read_text()
    assert "not independently verified" in (output / "components.md").read_text().lower()
    questions = (output / "open-questions.md").read_text()
    assert "source" in questions.lower()
    assert "planned" in questions.lower()
    assert "Artifacts:" in capsys.readouterr().out


def test_document_reproducible_and_never_modifies_architecture(tmp_path):
    src = EXAMPLES / "generated/ecommerce/architecture.json"
    original = src.read_bytes()
    assert main(["document", str(src), "--output", str(tmp_path / "a")]) == 0
    assert main(["document", str(src), "--output", str(tmp_path / "b")]) == 0
    for name in FILES:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    assert src.read_bytes() == original


def test_document_with_matching_review_surfaces_heuristic_findings(tmp_path):
    arch = EXAMPLES / "generated/ecommerce/architecture.json"
    review = EXAMPLES / "reviews/ecommerce/architecture-review.json"
    out = tmp_path / "docs"
    assert main(["document", str(arch), "--review", str(review), "--output", str(out)]) == 0
    findings = (out / "quality-risks.md").read_text()
    assert "Rule findings" in findings
    assert "Freshness warning" in findings
    assert "requires\\_review" in findings
    assert "Investigate heuristic finding" in (out / "open-questions.md").read_text()


def test_document_rejects_mismatched_review_before_writing(tmp_path, capsys):
    arch = EXAMPLES / "generated/ecommerce/architecture.json"
    other = EXAMPLES / "reviews/cli-utility/architecture-review.json"
    out = tmp_path / "docs"
    assert main(["document", str(arch), "--review", str(other), "--output", str(out)]) == 1
    assert not out.exists()
    assert "does not match" in capsys.readouterr().err


def test_document_rejects_nonempty_dir_and_symlink_without_overwrite(tmp_path):
    arch = EXAMPLES / "generated/cli-utility/architecture.json"
    out = tmp_path / "docs"
    out.mkdir()
    existing = out / "README.md"
    existing.write_text("PERSONAL NOTES", encoding="utf-8")
    assert main(["document", str(arch), "--output", str(out)]) == 1
    assert existing.read_text() == "PERSONAL NOTES"
    assert list(out.iterdir()) == [existing]
    alias = tmp_path / "alias"
    alias.symlink_to(out, target_is_directory=True)
    assert main(["document", str(arch), "--output", str(alias)]) == 1
    assert existing.read_text() == "PERSONAL NOTES"


def test_document_invalid_input_fails_without_creating_output(tmp_path, capsys):
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"no": "architecture"}', encoding="utf-8")
    out = tmp_path / "docs"
    assert main(["document", str(invalid), "--output", str(out)]) == 1
    assert not out.exists()
    assert "Error documenting architecture" in capsys.readouterr().err


def test_document_strict_preserves_output_but_flags_draft(tmp_path):
    arch = EXAMPLES / "generated/cli-utility/architecture.json"
    out = tmp_path / "docs"
    assert main(["document", str(arch), "--output", str(out), "--strict"]) == 2
    assert (out / "README.md").is_file()
    assert "draft" in (out / "README.md").read_text()


def test_document_missing_relationships_and_decisions_are_explicit(tmp_path):
    spec = ArchitectureSpec.model_validate_json(
        (EXAMPLES / "generated/cli-utility/architecture.json").read_text()
    )
    spec.relationships = []
    spec.decisions = []
    spec.verification_cases = []
    rendered = render_documentation(spec)
    assert "No relationships recorded" in rendered["interactions.md"]
    assert "No ADRs supplied" in rendered["decisions.md"]
    assert "Uncovered" in rendered["requirements.md"]
    assert "No verification cases recorded" in rendered["quality-risks.md"]


def test_document_escapes_untrusted_markdown_and_long_backtick_fences():
    spec = ArchitectureSpec.model_validate_json(
        (EXAMPLES / "generated/cli-utility/architecture.json").read_text()
    )
    spec.brief.system = "Project | <script>attack()</script>\\n# Forged"
    spec.components[0].name = "My ``` unsafe label"
    rendered = render_documentation(spec)
    assert "&lt;script&gt;" in rendered["README.md"]
    assert "Project \\| " in rendered["README.md"]
    assert "\n# Forged\n" not in rendered["README.md"]
    # The Mermaid block uses a larger fence than backticks in a label.
    assert "````mermaid" in rendered["components.md"]
    assert "````\n" in rendered["components.md"]
