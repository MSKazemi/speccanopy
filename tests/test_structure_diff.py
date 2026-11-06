"""Structural comparison of two project-intake outputs (synthetic projects only).

A static structure comparison is not behavioural or architectural verification,
and these tests do not claim it is.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.cli import main
from speccanopy.project_intake import IntakeObservations, ModuleObservation
from speccanopy.structure_diff import (
    StructureDiff, compare_module_observations, export_structure_diff,
    load_module_observations, render_structure_diff_markdown,
)

OUTPUTS = {"structure-diff.json", "structure-diff.md"}
SHA_A = "a" * 64
SHA_B = "b" * 64


def _project(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _intake(root: Path, out: Path) -> Path:
    assert main(["project-intake", str(root), "--system", "Synthetic", "--goal", "Test",
                 "--requirement", "Do things", "--output", str(out)]) == 0
    return out


BASE = {
    "app/__init__.py": "",
    "app/api.py": "from app import store\n\ndef handler():\n    return store.ROWS\n",
    "app/store.py": "ROWS = []\n\nclass Row:\n    pass\n",
}


def _obs(modules: list[ModuleObservation]) -> IntakeObservations:
    return IntakeObservations(modules=modules, dependencies=[],
                              excluded_non_python_source=[], skipped_oversized_files=0)


def _mod(name: str, cid: str | None = None, sha: str = SHA_A, funcs: list[str] | None = None,
         classes: list[str] | None = None, imports: list[str] | None = None,
         omitted: int = 0, path: str | None = None) -> ModuleObservation:
    return ModuleObservation(
        component_id=cid or "c_" + name.replace(".", "_"), module=name,
        source_path=path or name.replace(".", "/") + ".py", sha256=sha,
        functions=funcs or [], classes=classes or [], symbols_omitted=omitted,
        internal_imports=imports or [])


def test_byte_churn_only_is_not_a_structure_change(tmp_path):
    root = _project(tmp_path / "proj", BASE)
    before = _intake(root, tmp_path / "before")
    (root / "app/api.py").write_text(
        "from app import store\n\n# reworded\ndef handler():\n    return list(store.ROWS)\n",
        encoding="utf-8")
    (root / "app/store.py").write_text("ROWS = [1]\n\nclass Row:\n    x = 1\n", encoding="utf-8")
    after = _intake(root, tmp_path / "after")
    b, a = load_module_observations(before), load_module_observations(after)
    assert {m.sha256 for m in b.modules} != {m.sha256 for m in a.modules}
    diff = compare_module_observations(b, a)
    assert diff.structure_changed is False
    assert diff.added_modules == diff.removed_modules == []
    assert diff.edges_added == diff.edges_removed == []
    assert len(diff.edges_kept) == 1
    changed = [m.module for m in diff.modules if m.source_bytes_changed]
    assert changed == ["app.api", "app.store"]
    md = render_structure_diff_markdown(diff)
    assert "Structure changed: **no**" in md
    assert "app.api" in md.split("byte changes only")[1]


def test_module_added_and_removed(tmp_path):
    root = _project(tmp_path / "proj", BASE)
    before = _intake(root, tmp_path / "before")
    (root / "app/store.py").unlink()
    (root / "app/queue.py").write_text("JOBS = []\n", encoding="utf-8")
    (root / "app/api.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    after = _intake(root, tmp_path / "after")
    diff = compare_module_observations(load_module_observations(before),
                                       load_module_observations(after))
    assert diff.structure_changed is True
    assert diff.added_modules == ["app.queue"]
    assert diff.removed_modules == ["app.store"]
    assert diff.kept_modules == ["app", "app.api"]
    assert [(e.source, e.target, e.status) for e in diff.edges] == [("app.api", "app.store", "removed")]
    assert diff.renames_inferred is False


def test_edge_added_and_removed():
    before = _obs([_mod("a", imports=["b"]), _mod("b"), _mod("c")])
    after = _obs([_mod("a", imports=["c"]), _mod("b"), _mod("c", imports=["b"])])
    diff = compare_module_observations(before, after)
    assert diff.structure_changed is True
    assert [(e.source, e.target) for e in diff.edges_added] == [("a", "c"), ("c", "b")]
    assert [(e.source, e.target) for e in diff.edges_removed] == [("a", "b")]
    assert diff.edges_kept == []
    assert diff.added_modules == diff.removed_modules == []


def test_function_and_class_changes_on_kept_module():
    before = _obs([_mod("m", funcs=["keep", "gone"], classes=["Old", "Same"])])
    after = _obs([_mod("m", sha=SHA_B, funcs=["keep", "new"], classes=["Same", "New"])])
    diff = compare_module_observations(before, after)
    (m,) = diff.modules
    assert (m.functions_added, m.functions_removed) == (["new"], ["gone"])
    assert (m.classes_added, m.classes_removed) == (["New"], ["Old"])
    assert m.source_bytes_changed is True
    assert diff.structure_changed is True


def test_function_reorder_is_not_a_change():
    diff = compare_module_observations(_obs([_mod("m", funcs=["a", "b"])]),
                                       _obs([_mod("m", funcs=["b", "a"])]))
    assert diff.structure_changed is False


def test_symbols_omitted_change_and_incomplete_listing():
    diff = compare_module_observations(_obs([_mod("m", omitted=0), _mod("n", omitted=2)]),
                                       _obs([_mod("m", omitted=3), _mod("n", omitted=2)]))
    assert diff.structure_changed is True
    by = {m.module: m for m in diff.modules}
    assert by["m"].symbols_omitted_changed and not by["n"].symbols_omitted_changed
    assert diff.incomplete_symbol_modules == ["m", "n"]
    assert "name comparison is incomplete" in render_structure_diff_markdown(diff)


def test_component_ids_may_differ_and_are_mapped_by_module_name():
    before = _obs([_mod("a", cid="id_one", imports=["b"]), _mod("b", cid="id_two")])
    after = _obs([_mod("b", cid="id_new_b"), _mod("a", cid="id_new_a", imports=["b"])])
    diff = compare_module_observations(before, after)
    assert diff.structure_changed is False
    by = {m.module: m for m in diff.modules}
    assert (by["a"].before_component_id, by["a"].after_component_id) == ("id_one", "id_new_a")
    assert by["b"].component_id_changed
    md = render_structure_diff_markdown(diff)
    assert "id\\_one" in md and "id\\_new\\_b" in md


def test_rename_is_one_removed_plus_one_added():
    diff = compare_module_observations(_obs([_mod("old_name", funcs=["f"])]),
                                       _obs([_mod("new_name", funcs=["f"])]))
    assert diff.removed_modules == ["old_name"] and diff.added_modules == ["new_name"]
    assert diff.structure_changed is True
    assert "renames are not inferred" in render_structure_diff_markdown(diff).lower()


def test_source_path_change_for_kept_module_is_structural():
    diff = compare_module_observations(_obs([_mod("pkg", path="pkg.py")]),
                                       _obs([_mod("pkg", path="pkg/__init__.py")]))
    assert diff.structure_changed is True


def test_deterministic_json_and_markdown(tmp_path):
    before = _obs([_mod("a", imports=["b"], funcs=["x"]), _mod("b")])
    after = _obs([_mod("b"), _mod("a", funcs=["y"])])
    one, two = (compare_module_observations(before, after) for _ in range(2))
    assert render_structure_diff_markdown(one) == render_structure_diff_markdown(two)
    export_structure_diff(one, tmp_path / "x")
    export_structure_diff(two, tmp_path / "y")
    for name in OUTPUTS:
        assert (tmp_path / "x" / name).read_bytes() == (tmp_path / "y" / name).read_bytes()
    assert str(tmp_path) not in (tmp_path / "x" / "structure-diff.md").read_text()
    reloaded = StructureDiff.model_validate_json((tmp_path / "x" / "structure-diff.json").read_text())
    assert reloaded == one


def test_hostile_names_are_escaped_in_markdown():
    hostile = "evil|*_`[x](http://e)<script>\n# H"
    diff = compare_module_observations(
        _obs([_mod("ok")]),
        _obs([_mod("ok", funcs=[hostile]), _mod(hostile, cid="c_h", imports=[]), _mod("z", imports=["ok"])]))
    md = render_structure_diff_markdown(diff)
    assert "<script>" not in md
    assert "\n# H" not in md
    assert "evil\\|\\*\\_\\`\\[x\\]" in md
    # no unescaped pipe inside a hostile table cell
    for line in md.splitlines():
        if line.startswith("| ") and "evil" in line:
            assert "evil|" not in line


@pytest.mark.parametrize("bad", [
    lambda: _obs([_mod("a"), _mod("a", cid="other")]),
    lambda: _obs([_mod("a", cid="same"), _mod("b", cid="same")]),
    lambda: _obs([_mod("a", imports=["ghost"])]),
    lambda: _obs([_mod("a", imports=["a"])]),
])
def test_inconsistent_observations_fail_closed(bad):
    with pytest.raises(ValueError):
        compare_module_observations(bad(), _obs([_mod("a")]))
    with pytest.raises(ValueError):
        compare_module_observations(_obs([_mod("a")]), bad())


def _valid_dump() -> dict:
    diff = compare_module_observations(_obs([_mod("a"), _mod("b")]),
                                       _obs([_mod("a", imports=["b"]), _mod("b")]))
    return diff.model_dump(mode="json")


def test_validator_rejects_forged_reports():
    good = _valid_dump()
    assert good["structure_changed"] is True
    StructureDiff.model_validate(good)

    def forge(**changes):
        data = json.loads(json.dumps(good))
        data.update(changes)
        return data

    with pytest.raises(ValidationError):
        StructureDiff.model_validate(forge(structure_changed=False))  # added edge present
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(forge(added_modules=["a"]))
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(forge(caveat="Everything verified."))
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(forge(renames_inferred=True))
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(forge(edges=[
            {"source": "a", "target": "ghost", "status": "added"}]))
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(forge(edges=[
            {"source": "a", "target": "b", "status": "added"},
            {"source": "a", "target": "b", "status": "kept"}]))
    # structure_changed True with nothing changed is also forged
    same = compare_module_observations(_obs([_mod("a")]), _obs([_mod("a")])).model_dump(mode="json")
    StructureDiff.model_validate(same)
    same["structure_changed"] = True
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(same)
    # a module delta whose sides contradict its status
    data = forge()
    data["modules"][0]["status"] = "added"
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(data)
    # symbol changes on a module that is not kept
    data = forge()
    data["modules"][0].update(status="removed", after_component_id=None, after_source_path=None,
                              after_sha256=None, after_symbols_omitted=None,
                              functions_added=["f"])
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(data)
    # an edge touching a removed module cannot be 'added'
    forged = compare_module_observations(
        _obs([_mod("a"), _mod("b")]), _obs([_mod("a")])).model_dump(mode="json")
    forged["edges"] = [{"source": "a", "target": "b", "status": "added"}]
    with pytest.raises(ValidationError):
        StructureDiff.model_validate(forged)


def test_load_accepts_directory_or_file_and_rejects_missing(tmp_path):
    root = _project(tmp_path / "proj", BASE)
    out = _intake(root, tmp_path / "intake")
    assert load_module_observations(out) == load_module_observations(out / "module-observations.json")
    with pytest.raises(ValueError):
        load_module_observations(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError):
        load_module_observations(tmp_path / "empty")


def test_export_refuses_existing_output(tmp_path):
    diff = compare_module_observations(_obs([_mod("a")]), _obs([_mod("a")]))
    existing = tmp_path / "out"
    existing.mkdir()
    (existing / "mine.txt").write_text("keep")
    with pytest.raises(ValueError):
        export_structure_diff(diff, existing)
    assert [p.name for p in existing.iterdir()] == ["mine.txt"]


def _two_intakes(tmp_path: Path, mutate) -> tuple[Path, Path]:
    root = _project(tmp_path / "proj", BASE)
    before = _intake(root, tmp_path / "before")
    mutate(root)
    return before, _intake(root, tmp_path / "after")


def test_cli_identical_structure_exit_codes(tmp_path, capsys):
    def edit(root: Path) -> None:
        (root / "app/api.py").write_text(
            "from app import store\n\ndef handler():\n    return 42\n", encoding="utf-8")
    before, after = _two_intakes(tmp_path, edit)
    capsys.readouterr()
    out = tmp_path / "sd"
    assert main(["structure-diff", str(before), str(after), "--output", str(out), "--strict"]) == 0
    stdout = capsys.readouterr().out
    assert "Structure changed: no" in stdout
    assert "not behavioural or architectural verification" in stdout
    assert {p.name for p in out.iterdir()} == OUTPUTS
    StructureDiff.model_validate_json((out / "structure-diff.json").read_text())


def test_cli_changed_structure_strict_and_file_inputs(tmp_path, capsys):
    def edit(root: Path) -> None:
        (root / "app/extra.py").write_text("def f():\n    pass\n", encoding="utf-8")
    before, after = _two_intakes(tmp_path, edit)
    args = [str(before / "module-observations.json"), str(after / "module-observations.json")]
    assert main(["structure-diff", *args, "--output", str(tmp_path / "o1")]) == 0
    assert main(["structure-diff", *args, "--output", str(tmp_path / "o2"), "--strict"]) == 2
    diff = StructureDiff.model_validate_json((tmp_path / "o2" / "structure-diff.json").read_text())
    assert diff.added_modules == ["app.extra"]
    capsys.readouterr()


def test_cli_invalid_input_and_unsafe_output_write_nothing(tmp_path, capsys):
    before, after = _two_intakes(tmp_path, lambda root: None)
    capsys.readouterr()
    bad = tmp_path / "bad.json"
    bad.write_text('{"modules": "nope"}', encoding="utf-8")
    out = tmp_path / "o"
    assert main(["structure-diff", str(bad), str(after), "--output", str(out)]) == 1
    assert not out.exists()
    assert main(["structure-diff", str(tmp_path / "missing"), str(after), "--output", str(out)]) == 1
    assert not out.exists()
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "x.txt").write_text("mine")
    assert main(["structure-diff", str(before), str(after), "--output", str(taken)]) == 1
    assert [p.name for p in taken.iterdir()] == ["x.txt"]
    link = tmp_path / "link"
    link.symlink_to(taken)
    assert main(["structure-diff", str(before), str(after), "--output", str(link)]) == 1
    assert "Error comparing project structure" in capsys.readouterr().err
