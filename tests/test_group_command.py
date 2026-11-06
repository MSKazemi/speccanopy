"""``speccanopy group``: owner-declared grouping of intake modules into components.

Every project here is synthetic and temporary except the pilot test, which runs
intake on this repository's own ``src/`` (read only, nothing executed). Nothing
here claims an architecture is correct: grouping adds structure and requirement
mapping only, never verification evidence, interfaces, data ownership or
``ready`` status.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.fixtures import FixtureDesign
from speccanopy.grouping import GroupsFile
from speccanopy.models import ArchitectureSpec, SystemBrief
from speccanopy.project_intake import (
    IntakeObservations, export_project_intake, prepare_project_intake,
)

REPO = Path(__file__).resolve().parents[1]
OUTPUTS = {"brief.json", "design.json", "grouping-review.md"}


# ------------------------------------------------------------------ helpers

def _python_project(root: Path) -> Path:
    pkg = root / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "api.py").write_text("from . import store\nfrom .service import Service\n", encoding="utf-8")
    (pkg / "service.py").write_text("from .store import get\n", encoding="utf-8")
    (pkg / "store.py").write_text("def get():\n    return 1\n", encoding="utf-8")
    (pkg / "util.py").write_text("X = 1\n", encoding="utf-8")
    return root


def _intake(tmp_path: Path, name: str = "intake", *, requirements: int = 2) -> Path:
    root = tmp_path / "proj"
    if not root.exists():
        _python_project(root)
    result = prepare_project_intake(
        root, system="Sample App", goal="Document module boundaries",
        requirements=[f"The application must do thing {i}" for i in range(1, requirements + 1)],
    )
    out = tmp_path / name
    export_project_intake(result, out)
    return out


def _groups(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "decided_by": "owner",
        "groups": [
            {"id": "grp_edge", "name": "Edge", "responsibility": "Entry points.",
             "modules": ["app.api"], "requirement_ids": ["FR-USER-001"]},
            {"id": "grp_core", "name": "Core", "responsibility": "Business logic and storage.",
             "modules": ["app.service", "app.store"], "requirement_ids": ["FR-USER-002"]},
        ],
    }
    data.update(overrides)
    return data


def _write(path: Path, data) -> Path:
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _run(tmp_path: Path, intake: Path, groups, *extra: str, out: str = "grouped") -> tuple[int, Path]:
    gfile = _write(tmp_path / "groups.json", groups)
    output = tmp_path / out
    code = main(["group", str(intake), "--groups", str(gfile), "--output", str(output), *extra])
    return code, output


def _load_design(out: Path) -> FixtureDesign:
    return FixtureDesign.model_validate_json((out / "design.json").read_text(encoding="utf-8"))


def _build(out: Path, tmp_path: Path, name: str = "built") -> ArchitectureSpec:
    assert main(["design", str(out / "brief.json"), "--fixture", str(out / "design.json"),
                 "--output", str(tmp_path / name)]) == 0
    return ArchitectureSpec.model_validate_json(
        (tmp_path / name / "architecture.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------- happy path

def _all_modules_groups() -> dict:
    return _groups(groups=[
        {"id": "grp_edge", "name": "Edge", "responsibility": "Entry points.",
         "modules": ["app", "app.api"], "requirement_ids": ["FR-USER-001"]},
        {"id": "grp_core", "name": "Core", "responsibility": "Business logic and storage.",
         "modules": ["app.service", "app.store", "app.util"], "requirement_ids": ["FR-USER-002"]},
    ])


def test_group_builds_root_groups_and_modules_that_feed_design(tmp_path, capsys):
    intake = _intake(tmp_path)
    code, out = _run(tmp_path, intake, _all_modules_groups())
    assert code == 0, capsys.readouterr().err
    assert {p.name for p in out.iterdir()} == OUTPUTS
    flat = FixtureDesign.model_validate_json((intake / "design.json").read_text())
    design = _load_design(out)
    assert design.root == flat.root
    assert design.verification_cases == [] and design.decisions == [] and design.findings == []

    flat_modules = {p.id: p for p in flat.proposals_by_parent["system"]}
    grouped_modules = {p.id: p for g in ("grp_edge", "grp_core") for p in design.proposals_by_parent[g]}
    assert grouped_modules == flat_modules  # module proposals unchanged
    assert design.relationships == flat.relationships  # relationships preserved

    spec = _build(out, tmp_path)
    assert len(spec.components) == 1 + 2 + 5
    assert not [c for c in spec.components if c.status == "blocked"]
    trace = json.loads((tmp_path / "built" / "generation-trace.json").read_text())
    assert not [e for e in trace["events"] if e["action"].startswith("blocked")]
    parent = {c.id: c.parent_id for c in spec.components}
    assert parent["grp_edge"] == "system" and parent["grp_core"] == "system"
    assert {parent[i] for i in flat_modules} == {"grp_edge", "grp_core"}
    assert len(spec.relationships) == len(flat.relationships)
    by_id = {c.id: c for c in spec.components}
    assert by_id["grp_edge"].requirement_ids == ["FR-USER-001"]
    assert by_id["grp_core"].requirement_ids == ["FR-USER-002"]


def test_grouping_alone_leaves_requirements_uncovered_until_verification_cases_exist(tmp_path):
    """Per coverage_report: 'planned' needs a verification case linked to the owning component."""
    intake = _intake(tmp_path)
    _, out = _run(tmp_path, intake, _all_modules_groups())
    report = _build(out, tmp_path).coverage_report()
    assert report.uncovered == ["FR-USER-001", "FR-USER-002"]
    assert report.planned_only == [] and report.verified == []

    # An owner adding a (non-verified) test plan against the group is what moves it to planned.
    fixture = json.loads((out / "design.json").read_text())
    fixture["verification_cases"] = [{
        "id": "VC-1", "requirement_ids": ["FR-USER-001"], "component_ids": ["grp_edge"],
        "method": "test_plan", "description": "Owner-authored test plan.", "status": "planned",
    }]
    (tmp_path / "with-case.json").write_text(json.dumps(fixture), encoding="utf-8")
    assert main(["design", str(out / "brief.json"), "--fixture", str(tmp_path / "with-case.json"),
                 "--output", str(tmp_path / "planned")]) == 0
    spec = ArchitectureSpec.model_validate_json(
        (tmp_path / "planned" / "architecture.json").read_text())
    report = spec.coverage_report()
    assert report.planned_only == ["FR-USER-001"] and report.uncovered == ["FR-USER-002"]


def test_group_proposals_add_no_evidence_interfaces_data_or_ready_status(tmp_path):
    intake = _intake(tmp_path)
    _, out = _run(tmp_path, intake, _all_modules_groups())
    for proposal in _load_design(out).proposals_by_parent["system"]:
        assert proposal.interfaces == [] and proposal.owned_data == []
        assert proposal.validation_evidence == [] and proposal.stop_reason is None
        assert proposal.interfaces_not_applicable_reason is None
        assert proposal.data_not_applicable_reason is None
        assert proposal.quality_targets == {}
    spec = _build(out, tmp_path)
    assert not [c for c in spec.components if c.status == "ready"]


def test_brief_is_copied_from_intake(tmp_path):
    intake = _intake(tmp_path)
    _, out = _run(tmp_path, intake, _all_modules_groups())
    assert (out / "brief.json").read_bytes() == (intake / "brief.json").read_bytes()


def test_cli_summary_says_what_was_not_done(tmp_path, capsys):
    intake = _intake(tmp_path)
    code, out = _run(tmp_path, intake, _all_modules_groups())
    assert code == 0
    text = capsys.readouterr().out
    assert "2 groups" in text and "5 modules" in text
    assert "owner" in text
    assert "verification" in text.lower()
    assert str(out / "grouping-review.md") in text


def test_every_group_proposal_states_the_decided_by_basis(tmp_path):
    for decided_by, phrase in (
        ("owner", "declared in the groups file as decided by the owner"),
        ("owner_delegated", "delegated"),
        ("assistant_proposed", "proposed by an assistant"),
    ):
        intake = _intake(tmp_path, f"intake-{decided_by}")
        _, out = _run(tmp_path, intake, _all_modules_groups() | {"decided_by": decided_by},
                      out=f"out-{decided_by}")
        for proposal in _load_design(out).proposals_by_parent["system"]:
            assert phrase in proposal.rationale
            assert any(decided_by in a for a in proposal.assumptions)


# ------------------------------------------------------ validation: fail closed

def _group(**overrides) -> dict:
    base = {"id": "grp_all", "name": "All", "responsibility": "Everything.",
            "modules": ["app", "app.api", "app.service", "app.store", "app.util"],
            "requirement_ids": []}
    base.update(overrides)
    return base


def _bad(groups: list[dict], **top) -> dict:
    return _groups(groups=groups, **top)


@pytest.mark.parametrize("case, data, message", [
    ("unknown module", _bad([_group(modules=["app", "app.api", "app.service", "app.store",
                                             "app.util", "app.ghost"])]), "app.ghost"),
    ("module in two groups", _bad([_group(), _group(id="grp_two", modules=["app.api"])]), "app.api"),
    ("module twice in one group", _bad([_group(modules=["app", "app", "app.api", "app.service",
                                                        "app.store", "app.util"])]), "app"),
    ("unknown requirement", _bad([_group(requirement_ids=["FR-NOPE-9"])]), "FR-NOPE-9"),
    ("duplicate requirement in group", _bad([_group(requirement_ids=["FR-USER-001", "FR-USER-001"])]),
     "FR-USER-001"),
    ("duplicate group id", _bad([_group(modules=["app"]),
                                 _group(modules=["app.api", "app.service", "app.store", "app.util"])]),
     "grp_all"),
    ("invalid group id", _bad([_group(id="1 bad id")]), "id"),
    ("group id collides with root", _bad([_group(id="system")]), "system"),
    ("empty group", _bad([_group(), _group(id="grp_empty", modules=[])]), "modules"),
    ("no groups", _bad([]), "groups"),
    ("wrong schema version", _bad([_group()], schema_version=2), "schema_version"),
    ("unknown decided_by", _bad([_group()], decided_by="the_team"), "decided_by"),
    ("missing decided_by", {k: v for k, v in _bad([_group()]).items() if k != "decided_by"}, "decided_by"),
    ("extra field", _bad([_group(extra="x")]), "extra"),
    ("blank group name", _bad([_group(name="  ")]), "name"),
], ids=lambda v: v if isinstance(v, str) and " " in v and len(v) < 40 else None)
def test_invalid_groups_fail_closed(tmp_path, capsys, case, data, message):
    intake = _intake(tmp_path)
    code, out = _run(tmp_path, intake, data)
    assert code == 1, case
    assert not out.exists(), case
    assert message in capsys.readouterr().err, case


def test_group_id_colliding_with_existing_module_component_id_is_refused(tmp_path, capsys):
    intake = _intake(tmp_path)
    module_id = json.loads((intake / "module-observations.json").read_text())["modules"][0]["component_id"]
    code, out = _run(tmp_path, intake, _bad([_group(id=module_id)]))
    assert code == 1 and not out.exists()
    assert module_id in capsys.readouterr().err


def test_group_id_colliding_with_relationship_id_is_refused(tmp_path, capsys):
    intake = _intake(tmp_path)
    rel_id = json.loads((intake / "design.json").read_text())["relationships"][0]["id"]
    code, out = _run(tmp_path, intake, _bad([_group(id=rel_id)]))
    assert code == 1 and not out.exists()
    assert rel_id in capsys.readouterr().err


def test_malformed_and_missing_inputs_fail_closed(tmp_path, capsys):
    intake = _intake(tmp_path)
    code, out = _run(tmp_path, intake, "{not json")
    assert code == 1 and not out.exists()
    code = main(["group", str(intake), "--groups", str(tmp_path / "absent.json"),
                 "--output", str(tmp_path / "o2")])
    assert code == 1 and not (tmp_path / "o2").exists()
    code = main(["group", str(tmp_path / "no-such-intake"), "--groups",
                 str(_write(tmp_path / "g.json", _all_modules_groups())), "--output", str(tmp_path / "o3")])
    assert code == 1 and not (tmp_path / "o3").exists()
    assert "Error grouping modules" in capsys.readouterr().err


def test_oversized_groups_file_is_refused(tmp_path, capsys):
    intake = _intake(tmp_path)
    huge = _all_modules_groups()
    huge["groups"][0]["responsibility"] = "x" * 2_000_000
    code, out = _run(tmp_path, intake, huge)
    assert code == 1 and not out.exists()
    assert "larger than" in capsys.readouterr().err


def test_already_grouped_design_is_refused(tmp_path, capsys):
    intake = _intake(tmp_path)
    _, once = _run(tmp_path, intake, _all_modules_groups())
    # Treat the grouped output as if it were an intake directory: it has no
    # module-observations.json, and its design is no longer a flat intake.
    code = main(["group", str(once), "--groups", str(tmp_path / "groups.json"),
                 "--output", str(tmp_path / "twice")])
    assert code == 1 and not (tmp_path / "twice").exists()
    # Same, with observations present but the design hand-grouped.
    nested = tmp_path / "nested"
    nested.mkdir()
    for name in ("brief.json", "module-observations.json"):
        (nested / name).write_bytes((intake / name).read_bytes())
    (nested / "design.json").write_bytes((once / "design.json").read_bytes())
    code = main(["group", str(nested), "--groups", str(tmp_path / "groups.json"),
                 "--output", str(tmp_path / "thrice")])
    assert code == 1 and not (tmp_path / "thrice").exists()
    assert "flat" in capsys.readouterr().err


def test_design_that_disagrees_with_observations_is_refused(tmp_path, capsys):
    intake = _intake(tmp_path)
    design = json.loads((intake / "design.json").read_text())
    design["proposals_by_parent"]["system"].pop()
    (intake / "design.json").write_text(json.dumps(design), encoding="utf-8")
    code, out = _run(tmp_path, intake, _all_modules_groups())
    assert code == 1 and not out.exists()
    assert "module-observations.json" in capsys.readouterr().err


# ---------------------------------------------------------- --allow-ungrouped

def test_ungrouped_modules_fail_closed_and_are_named(tmp_path, capsys):
    intake = _intake(tmp_path)
    code, out = _run(tmp_path, intake, _groups())  # leaves "app" and "app.util" out
    assert code == 1 and not out.exists()
    err = capsys.readouterr().err
    assert "app.util" in err and "--allow-ungrouped" in err


def test_allow_ungrouped_keeps_them_under_root_and_lists_them(tmp_path, capsys):
    intake = _intake(tmp_path)
    code, out = _run(tmp_path, intake, _groups(), "--allow-ungrouped")
    assert code == 0
    flat = FixtureDesign.model_validate_json((intake / "design.json").read_text())
    design = _load_design(out)
    by_name = {m["module"]: m["component_id"]
               for m in json.loads((intake / "module-observations.json").read_text())["modules"]}
    root_children = [p.id for p in design.proposals_by_parent["system"]]
    assert root_children[:2] == ["grp_edge", "grp_core"]
    assert set(root_children[2:]) == {by_name["app"], by_name["app.util"]}
    spec = _build(out, tmp_path)
    assert len(spec.components) == 1 + 2 + 5
    assert not [c for c in spec.components if c.status == "blocked"]
    assert {p.id: p for p in flat.proposals_by_parent["system"]}[by_name["app.util"]] in \
        design.proposals_by_parent["system"]
    review = (out / "grouping-review.md").read_text()
    section = review.split("## Ungrouped modules", 1)[1].split("\n## ", 1)[0]
    assert "app.util" in section and "app" in section
    assert "app.api" not in section


def test_review_without_ungrouped_says_none(tmp_path):
    intake = _intake(tmp_path)
    _, out = _run(tmp_path, intake, _all_modules_groups())
    section = (out / "grouping-review.md").read_text().split("## Ungrouped modules", 1)[1].split("\n## ", 1)[0]
    assert "None" in section


# ------------------------------------------------------------------- budgets

def _set_constraints(intake: Path, **values) -> None:
    brief = json.loads((intake / "brief.json").read_text())
    brief["constraints"].update(values)
    (intake / "brief.json").write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")


def test_grouped_tree_over_max_nodes_fails_clearly(tmp_path, capsys):
    intake = _intake(tmp_path)
    _set_constraints(intake, max_nodes=7)  # needs 1 + 2 groups + 5 modules = 8
    code, out = _run(tmp_path, intake, _all_modules_groups())
    assert code == 1 and not out.exists()
    err = capsys.readouterr().err
    assert "max_nodes" in err and "8" in err and "7" in err


def test_grouped_tree_exactly_at_max_nodes_is_accepted(tmp_path):
    intake = _intake(tmp_path)
    _set_constraints(intake, max_nodes=8)
    code, out = _run(tmp_path, intake, _all_modules_groups())
    assert code == 0
    spec = _build(out, tmp_path)
    assert len(spec.components) == 8
    assert not [c for c in spec.components if c.status == "blocked"]


def test_grouped_tree_over_max_depth_fails_clearly(tmp_path, capsys):
    intake = _intake(tmp_path)
    _set_constraints(intake, max_depth=1)
    code, out = _run(tmp_path, intake, _all_modules_groups())
    assert code == 1 and not out.exists()
    err = capsys.readouterr().err
    assert "max_depth" in err and "2" in err


def test_budgets_are_never_silently_raised(tmp_path):
    intake = _intake(tmp_path)
    _set_constraints(intake, max_nodes=50, max_depth=2)
    _, out = _run(tmp_path, intake, _all_modules_groups())
    brief = SystemBrief.model_validate_json((out / "brief.json").read_text())
    assert brief.constraints.max_nodes == 50 and brief.constraints.max_depth == 2


# ------------------------------------------------------------------- review

def test_review_states_who_decided_verbatim_and_what_it_means(tmp_path):
    expectations = {
        "owner": ("owner-confirmed", "cannot verify"),
        "owner_delegated": ("not individually confirmed", "NOT owner-confirmed"),
        "assistant_proposed": ("proposed by an assistant", "NOT owner-confirmed"),
    }
    for decided_by, phrases in expectations.items():
        intake = _intake(tmp_path, f"in-{decided_by}")
        _, out = _run(tmp_path, intake, _all_modules_groups() | {"decided_by": decided_by},
                      out=f"out-{decided_by}")
        review = (out / "grouping-review.md").read_text()
        assert "decided_by: " + decided_by.replace("_", "\\_") in review.replace("`", "")
        for phrase in phrases:
            assert phrase in review, (decided_by, phrase)
        assert "Only `owner`" in review
    # Wording specific to one value must not leak into the others.
    only_owner = (tmp_path / "out-owner" / "grouping-review.md").read_text()
    assert "NOT owner-confirmed" not in only_owner


def test_review_lists_groups_modules_requirements_and_unmapped_requirements(tmp_path):
    intake = _intake(tmp_path, requirements=3)
    groups = _all_modules_groups()
    _, out = _run(tmp_path, intake, groups)
    review = (out / "grouping-review.md").read_text()
    for needle in ("grp\\_edge", "grp\\_core", "app.service", "app.store", "app.util",
                   "FR-USER-001", "FR-USER-002", "FR-USER-003"):
        assert needle in review, needle
    unmapped = review.split("## Requirements mapped to no group", 1)[1].split("\n## ", 1)[0]
    assert "FR-USER-003" in unmapped
    assert "FR-USER-001" not in unmapped and "FR-USER-002" not in unmapped
    assert "verification" in review.lower()
    assert "interfaces" in review.lower() and "data ownership" in review.lower()
    assert "ready" in review
    assert "speccanopy design" in review


def test_review_says_all_requirements_mapped_when_none_are_left(tmp_path):
    intake = _intake(tmp_path)
    _, out = _run(tmp_path, intake, _all_modules_groups())
    unmapped = (out / "grouping-review.md").read_text().split(
        "## Requirements mapped to no group", 1)[1].split("\n## ", 1)[0]
    assert "None" in unmapped


def test_review_warns_about_groups_larger_than_ten_modules(tmp_path):
    project = tmp_path / "big"
    (project / "pkg").mkdir(parents=True)
    for i in range(12):
        (project / "pkg" / f"m{i:02d}.py").write_text(f"V = {i}\n", encoding="utf-8")
    export_project_intake(prepare_project_intake(project, system="S", goal="G", requirements=["R"]),
                          tmp_path / "bigintake")
    names = [m["module"] for m in json.loads(
        (tmp_path / "bigintake" / "module-observations.json").read_text())["modules"]]
    groups = {"schema_version": 1, "decided_by": "owner", "groups": [
        {"id": "grp_one", "name": "One", "responsibility": "All of it.", "modules": names}]}
    code, out = _run(tmp_path, tmp_path / "bigintake", groups)
    assert code == 0
    assert "more than 10" in (out / "grouping-review.md").read_text()


def test_hostile_names_are_escaped_in_markdown(tmp_path):
    intake = _intake(tmp_path)
    hostile = "<script>alert(1)</script> | **bold** [x](http://evil.example) `tick`\n# heading"
    groups = _groups(groups=[
        {"id": "grp_core", "name": hostile, "responsibility": hostile,
         "modules": ["app", "app.api", "app.service", "app.store", "app.util"],
         "requirement_ids": ["FR-USER-001"]}])
    code, out = _run(tmp_path, intake, groups)
    assert code == 0
    review = (out / "grouping-review.md").read_text()
    assert "<script>" not in review and "&lt;script&gt;" in review
    assert "[x](http://evil.example)" not in review
    assert "\n# heading" not in review
    # An unescaped pipe would add table columns: every row of a table must have equal width.
    block: list[str] = []
    seen_tables = 0
    for line in review.splitlines() + [""]:
        if line.startswith("|"):
            block.append(line)
        elif block:
            assert len({len(re.split(r"(?<!\\)\|", row)) for row in block}) == 1, block
            seen_tables += 1
            block = []
    assert seen_tables >= 2


def test_group_names_are_stored_unchanged_in_design_json(tmp_path):
    intake = _intake(tmp_path)
    groups = _all_modules_groups()
    groups["groups"][0]["name"] = "Edge | <b>API</b>"
    _, out = _run(tmp_path, intake, groups)
    assert _load_design(out).proposals_by_parent["system"][0].name == "Edge | <b>API</b>"


# ----------------------------------------------------------- output / determinism

def test_output_is_deterministic(tmp_path):
    intake = _intake(tmp_path)
    _, a = _run(tmp_path, intake, _all_modules_groups(), out="a")
    _, b = _run(tmp_path, intake, _all_modules_groups(), out="b")
    for name in OUTPUTS:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_existing_nonempty_output_is_refused_and_untouched(tmp_path, capsys):
    intake = _intake(tmp_path)
    out = tmp_path / "grouped"
    out.mkdir()
    (out / "design.json").write_text("HAND EDITED", encoding="utf-8")
    code, _ = _run(tmp_path, intake, _all_modules_groups())
    assert code == 1
    assert (out / "design.json").read_text() == "HAND EDITED"
    assert {p.name for p in out.iterdir()} == {"design.json"}
    assert "new or empty" in capsys.readouterr().err


def test_empty_existing_output_directory_is_accepted(tmp_path):
    intake = _intake(tmp_path)
    (tmp_path / "grouped").mkdir()
    code, out = _run(tmp_path, intake, _all_modules_groups())
    assert code == 0 and {p.name for p in out.iterdir()} == OUTPUTS


def test_symlink_output_is_refused(tmp_path):
    intake = _intake(tmp_path)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (tmp_path / "grouped").symlink_to(target, target_is_directory=True)
    code, _ = _run(tmp_path, intake, _all_modules_groups())
    assert code == 1 and list(target.iterdir()) == []


def test_intake_directory_is_never_modified(tmp_path):
    intake = _intake(tmp_path)
    before = {p.name: p.read_bytes() for p in intake.iterdir()}
    _run(tmp_path, intake, _all_modules_groups())
    assert {p.name: p.read_bytes() for p in intake.iterdir()} == before


def test_groups_file_model_is_strict():
    ok = GroupsFile.model_validate(_all_modules_groups())
    assert ok.schema_version == 1 and ok.decided_by == "owner"
    with pytest.raises(ValueError):
        GroupsFile.model_validate(_all_modules_groups() | {"surprise": 1})


# ------------------------------------------------------------- JavaScript intake

def test_group_works_on_javascript_intake(tmp_path, capsys):
    root = tmp_path / "jsapp"
    (root / "src" / "lib").mkdir(parents=True)
    (root / "src" / "index.js").write_text("import { a } from './lib/a.js';\n", encoding="utf-8")
    (root / "src" / "lib" / "a.js").write_text("import { b } from './b.js';\nexport const a = 1;\n", encoding="utf-8")
    (root / "src" / "lib" / "b.ts").write_text("export const b = 2;\n", encoding="utf-8")
    intake = tmp_path / "jsintake"
    export_project_intake(prepare_project_intake(
        root, system="JS App", goal="Document modules", requirements=["It must serve pages"],
        language="javascript"), intake)
    names = sorted(m["module"] for m in json.loads(
        (intake / "module-observations.json").read_text())["modules"])
    assert len(names) == 3 and any(n.endswith("index") for n in names)
    entry = next(n for n in names if n.endswith("index"))
    libs = [n for n in names if n != entry]
    groups = {"schema_version": 1, "decided_by": "assistant_proposed", "groups": [
        {"id": "grp_entry", "name": "Entry", "responsibility": "Application entry.",
         "modules": [entry], "requirement_ids": ["FR-USER-001"]},
        {"id": "grp_lib", "name": "Library", "responsibility": "Helpers.", "modules": libs}]}
    code, out = _run(tmp_path, intake, groups)
    assert code == 0, capsys.readouterr().err
    assert {p.name for p in out.iterdir()} == OUTPUTS
    spec = _build(out, tmp_path)
    assert len(spec.components) == 1 + 2 + 3
    assert not [c for c in spec.components if c.status == "blocked"]
    assert len(spec.relationships) == 2
    assert "proposed by an assistant" in (out / "grouping-review.md").read_text()


# ------------------------------------------------------------------ owner pilot

def _pilot_groups() -> dict:
    return json.loads((REPO / "examples" / "owner-pilot" / "groups.json").read_text(encoding="utf-8"))


def _pilot_intake(tmp_path: Path) -> Path:
    """Intake on this repository's own src/, limited to the modules the pilot grouped.

    Modules added to the repo after the pilot are excluded by file so the test keeps
    checking the pilot's tree; the pilot's own modules must all still exist.
    """
    pilot_modules = {m for g in _pilot_groups()["groups"] for m in g["modules"]}
    requirements = [
        "Turn a requirements brief and curated design into a rooted component tree plus typed relationship graph",
        "Review an architecture for coverage, style trade-offs and quality risks without claiming validation",
        "Render reviewable Markdown documentation with requirement traceability and evidence status",
        "Draft provisional architecture inputs from an existing project's source without executing it",
    ]
    src = REPO / "src"
    probe = prepare_project_intake(src, system="Speccanopy (owner pilot)", goal="Pilot", requirements=requirements,
                                   max_modules=50)
    present = {m.module: m.source_path for m in probe.observations.modules}
    assert pilot_modules <= set(present), sorted(pilot_modules - set(present))
    extras = sorted(path for name, path in present.items() if name not in pilot_modules)
    result = prepare_project_intake(src, system="Speccanopy (owner pilot)", goal="Pilot", requirements=requirements,
                                    max_modules=50, exclude=extras or None)
    out = tmp_path / "pilot-intake"
    export_project_intake(result, out)
    return out


def test_group_reproduces_the_owner_pilot_tree(tmp_path):
    groups_path = REPO / "examples" / "owner-pilot" / "groups.json"
    parsed = GroupsFile.model_validate_json(groups_path.read_text(encoding="utf-8"))
    assert parsed.decided_by == "owner_delegated"
    intake = _pilot_intake(tmp_path)

    pilot_design = tmp_path / "pilot-design.json"
    subprocess.run([sys.executable, str(REPO / "examples" / "owner-pilot" / "apply_grouping.py"),
                    str(intake / "design.json"), str(pilot_design)], check=True, capture_output=True)
    out = tmp_path / "grouped"
    assert main(["group", str(intake), "--groups", str(groups_path), "--output", str(out)]) == 0

    def tree(path: Path):
        design = FixtureDesign.model_validate_json(path.read_text(encoding="utf-8"))
        return {
            parent: [(p.id, p.name, p.responsibility, tuple(p.requirement_ids)) for p in kids]
            for parent, kids in design.proposals_by_parent.items()
        }

    pilot_tree = tree(pilot_design)
    new_tree = tree(out / "design.json")
    # Same parent -> children structure, group names, responsibilities and requirement mapping.
    assert new_tree.keys() == pilot_tree.keys()
    assert new_tree == pilot_tree  # every parent -> children list, incl. group names and requirements

    spec = _build(out, tmp_path)
    assert len(spec.components) == 34
    assert len([c for c in spec.components if c.parent_id == "system"]) == 6
    assert not [c for c in spec.components if c.status == "blocked"]
    # `group` adds no verification cases; the pilot script did, separately.
    assert spec.verification_cases == []
    assert "owner\\_delegated" in (out / "grouping-review.md").read_text()
