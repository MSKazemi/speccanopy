"""Intake's node budget leaves room for one owner grouping layer (owner-pilot finding)."""

from __future__ import annotations

import json
from pathlib import Path

from speccanopy.cli import main
from speccanopy.project_intake import prepare_project_intake


def _project(root: Path, n: int) -> Path:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    for i in range(n - 1):
        (root / "pkg" / f"m{i:02d}.py").write_text(f"V = {i}\n", encoding="utf-8")
    return root


def test_small_projects_keep_the_minimum_budget(tmp_path):
    r = prepare_project_intake(_project(tmp_path / "p", 4), system="S", goal="G", requirements=["R"])
    assert r.brief.constraints.max_nodes == 20


def test_budget_fits_root_plus_one_group_per_module_plus_modules(tmp_path):
    r = prepare_project_intake(_project(tmp_path / "p", 14), system="S", goal="G", requirements=["R"])
    assert r.brief.constraints.max_nodes == 2 * 14 + 1


def test_grouped_intake_design_builds_every_component_without_budget_edits(tmp_path):
    # 20 modules: the old budget (modules + 1 = 21) cannot hold root + 3 groups + 20.
    root = _project(tmp_path / "p", 20)
    intake = tmp_path / "intake"
    assert main(["project-intake", str(root), "--system", "S", "--goal", "G",
                 "--requirement", "R", "--output", str(intake)]) == 0
    design = json.loads((intake / "design.json").read_text())
    mods = design["proposals_by_parent"]["system"]
    groups = []
    for g in range(3):  # three owner groups over 20 modules
        groups.append({
            "id": f"grp_{g}", "name": f"Group {g}", "responsibility": "Grouping",
            "boundary": "Logical", "requirement_ids": [], "rationale": "Owner grouping",
            "assumptions": [], "risks": [], "interfaces": [], "owned_data": [],
            "quality_targets": {}, "validation_evidence": [],
        })
    design["proposals_by_parent"] = {"system": groups, **{
        f"grp_{g}": mods[g::3] for g in range(3)}}
    grouped = tmp_path / "grouped.json"
    grouped.write_text(json.dumps(design), encoding="utf-8")
    out = tmp_path / "design"
    assert main(["design", str(intake / "brief.json"), "--fixture", str(grouped),
                 "--output", str(out)]) == 0
    trace = json.loads((out / "generation-trace.json").read_text())
    actions = {e["action"] for e in trace["events"]}
    assert "blocked_nodes" not in actions and "unmaterialized_link" not in actions
    assert trace["statistics"]["components"] == 1 + 3 + 20
