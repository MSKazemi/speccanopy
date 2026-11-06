"""Every writing command refuses existing outputs instead of overwriting them.

Covers the commands guarded after the Issue #5 acceptance tests found silent
overwrites: refine-plan, refine-apply, benchmark, research-case,
research-suite, approve-ai and speccanopy-experts prepare/aggregate. Inputs are
the repository's committed synthetic examples; outputs go to temp folders.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.expert_review import main as experts_main

EX = Path(__file__).resolve().parents[1] / "examples"
OWNER = "OWNER HAND-EDITED CONTENT"


def _refine_plan(out: Path) -> list[str]:
    return ["refine-plan", str(EX / "generated/ecommerce/architecture.json"),
            "--config", str(EX / "ecommerce.review.json"),
            "--edits", str(EX / "refinement/ecommerce.edits.json"), "--output", str(out)]


def _benchmark(out: Path) -> list[str]:
    return ["benchmark", str(EX / "generated/cli-utility/architecture.json"),
            "--config", str(EX / "cli-utility.review.json"),
            "--rubric", str(EX / "refinement/cli-utility.rubric.json"), "--output", str(out)]


def _research_case(out: Path) -> list[str]:
    return ["research-case", str(EX / "research/cases/cli-utility.json"),
            "--architecture", str(EX / "generated/cli-utility/architecture.json"),
            "--output", str(out)]


def _research_suite(out: Path) -> list[str]:
    return ["research-suite", str(EX / "research/suite.json"), "--output", str(out)]


DIR_COMMANDS = {
    "refine-plan": _refine_plan, "benchmark": _benchmark,
    "research-case": _research_case, "research-suite": _research_suite,
}


def _owned_dir(path: Path, name: str = "notes.md") -> Path:
    path.mkdir(parents=True)
    (path / name).write_text(OWNER, encoding="utf-8")
    return path


@pytest.mark.parametrize("command", sorted(DIR_COMMANDS))
def test_directory_commands_refuse_existing_and_symlinked_outputs(command, tmp_path, capsys):
    build = DIR_COMMANDS[command]
    owned = _owned_dir(tmp_path / "owned")
    assert main(build(owned)) == 1
    assert sorted(p.name for p in owned.iterdir()) == ["notes.md"]
    assert (owned / "notes.md").read_text() == OWNER
    assert "existing files not overwritten" in capsys.readouterr().err
    target = tmp_path / "elsewhere"
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    assert main(build(link)) == 1
    assert not target.exists()
    a_file = tmp_path / "a-file"
    a_file.write_text(OWNER, encoding="utf-8")
    assert main(build(a_file)) == 1
    assert a_file.read_text() == OWNER
    fresh = tmp_path / "fresh"
    assert main(build(fresh)) == 0
    first = {p.name: p.read_bytes() for p in fresh.iterdir()}
    assert first
    assert main(build(fresh)) == 1, "a re-run must not replace its own earlier report"
    assert {p.name: p.read_bytes() for p in fresh.iterdir()} == first


def test_refine_apply_refuses_existing_output(tmp_path):
    plan = tmp_path / "plan"
    assert main(_refine_plan(plan)) == 0
    args = ["refine-apply", str(EX / "generated/ecommerce/architecture.json"),
            "--config", str(EX / "ecommerce.review.json"),
            "--plan", str(plan / "refinement-plan.json"),
            "--reviewer", "human-1", "--acknowledge-review", "--output"]
    owned = _owned_dir(tmp_path / "owned", "architecture.json")
    assert main(args + [str(owned)]) == 1
    assert (owned / "architecture.json").read_text() == OWNER
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert main(args + [str(link)]) == 1
    assert not (tmp_path / "elsewhere").exists()
    assert main(args + [str(tmp_path / "released")]) == 0


def _bundle(tmp_path: Path) -> Path:
    out = tmp_path / "ai"
    assert main(["propose-ai", str(EX / "cli-utility.json"), "--backend", "scripted",
                 "--responses", str(EX / "ai-scripted-cli.json"), "--output", str(out)]) == 0
    return out / "ai-proposals.json"


def test_approve_ai_refuses_existing_fixture_or_receipt(tmp_path, capsys):
    bundle = _bundle(tmp_path)
    base = ["approve-ai", str(bundle), "--reviewer", "architect", "--acknowledge-review", "--output"]
    fixture = tmp_path / "owned.design.json"
    fixture.write_text(OWNER, encoding="utf-8")
    assert main(base + [str(fixture)]) == 1
    assert fixture.read_text() == OWNER
    assert not (tmp_path / "owned.design.approval.json").exists()
    assert "existing files not overwritten" in capsys.readouterr().err
    receipt_only = tmp_path / "second.design.json"
    receipt = tmp_path / "second.design.approval.json"
    receipt.write_text(OWNER, encoding="utf-8")
    assert main(base + [str(receipt_only)]) == 1
    assert not receipt_only.exists() and receipt.read_text() == OWNER
    dangling = tmp_path / "dangling.design.json"
    dangling.symlink_to(tmp_path / "nowhere.json")
    assert main(base + [str(dangling)]) == 1
    assert not (tmp_path / "nowhere.json").exists()
    fresh = tmp_path / "approved.design.json"
    assert main(base + [str(fresh)]) == 0
    first = fresh.read_bytes()
    assert main(base + [str(fresh)]) == 1
    assert fresh.read_bytes() == first


def test_experts_prepare_refuses_symlink_and_aggregate_refuses_existing(tmp_path, capsys):
    study = EX / "expert-review/ecommerce-study.json"
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert experts_main(["prepare", str(study), "--output", str(link)]) == 1
    assert not (tmp_path / "elsewhere").exists()
    panel = tmp_path / "panel"
    assert experts_main(["prepare", str(study), "--output", str(panel)]) == 0
    manifest = panel / "private" / "manifest.json"
    agg = ["aggregate", str(manifest), "--submissions", str(panel / "submissions"), "--output"]
    owned = _owned_dir(tmp_path / "report-owned", "expert-review-summary.md")
    assert experts_main(agg + [str(owned)]) == 1
    assert (owned / "expert-review-summary.md").read_text() == OWNER
    report = panel / "report"
    assert experts_main(agg + [str(report)]) == 0
    first = (report / "expert-review-summary.json").read_bytes()
    assert experts_main(agg + [str(report)]) == 1
    assert (report / "expert-review-summary.json").read_bytes() == first
    capsys.readouterr()
