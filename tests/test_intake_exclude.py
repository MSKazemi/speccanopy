"""`project-intake --exclude`: leave named subtrees (e.g. test fixtures) out of the
architecture, record the exclusion, and keep output without it byte-identical."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.project_intake import prepare_project_intake

REQ = ["Do the synthetic thing"]


def _py_project(root: Path) -> Path:
    (root / "src" / "app").mkdir(parents=True)
    (root / "src" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "app" / "core.py").write_text("X = 1\n", encoding="utf-8")
    (root / "examples" / "fixture").mkdir(parents=True)
    (root / "examples" / "fixture" / "demo.py").write_text("from app import core\n", encoding="utf-8")
    return root


def _modules(result) -> list[str]:
    return sorted(m.source_path for m in result.observations.modules)


def test_exclude_prefix_removes_subtree_and_is_recorded(tmp_path):
    root = _py_project(tmp_path / "p")
    full = prepare_project_intake(root, system="S", goal="G", requirements=REQ)
    assert "examples/fixture/demo.py" in _modules(full)
    cut = prepare_project_intake(root, system="S", goal="G", requirements=REQ, exclude=["examples"])
    assert _modules(cut) == ["src/app/__init__.py", "src/app/core.py"]
    assert cut.observations.excluded_by_request == ["examples"]
    assert all("demo" not in c.source_path for c in cut.evidence.claims)


def test_exclude_matching_nothing_fails_closed(tmp_path):
    root = _py_project(tmp_path / "p")
    with pytest.raises(ValueError, match="matches no inventoried file"):
        prepare_project_intake(root, system="S", goal="G", requirements=REQ, exclude=["exmaples"])


@pytest.mark.parametrize("bad", ["../outside", "/abs/path", ""])
def test_exclude_rejects_unsafe_paths(tmp_path, bad):
    root = _py_project(tmp_path / "p")
    with pytest.raises(ValueError):
        prepare_project_intake(root, system="S", goal="G", requirements=REQ, exclude=[bad])


def test_exclude_prefix_matches_whole_path_segments_only(tmp_path):
    root = _py_project(tmp_path / "p")
    (root / "examples_keep").mkdir()
    (root / "examples_keep" / "kept.py").write_text("Y = 2\n", encoding="utf-8")
    cut = prepare_project_intake(root, system="S", goal="G", requirements=REQ, exclude=["examples"])
    assert "examples_keep/kept.py" in _modules(cut)


def test_without_exclude_json_has_no_new_key(tmp_path):
    root = _py_project(tmp_path / "p")
    assert main(["project-intake", str(root), "--system", "S", "--goal", "G",
                 "--requirement", REQ[0], "--output", str(tmp_path / "o")]) == 0
    obs = json.loads((tmp_path / "o" / "module-observations.json").read_text())
    assert "excluded_by_request" not in obs


def test_cli_exclude_repeatable_and_reported(tmp_path, capsys):
    root = _py_project(tmp_path / "p")
    (root / "scripts").mkdir()
    (root / "scripts" / "tool.py").write_text("Z = 3\n", encoding="utf-8")
    out = tmp_path / "o"
    assert main(["project-intake", str(root), "--system", "S", "--goal", "G",
                 "--requirement", REQ[0], "--exclude", "examples", "--exclude", "scripts/tool.py",
                 "--output", str(out)]) == 0
    obs = json.loads((out / "module-observations.json").read_text())
    assert obs["excluded_by_request"] == ["examples", "scripts/tool.py"]
    assert [m["source_path"] for m in obs["modules"]] == ["src/app/__init__.py", "src/app/core.py"]
    review = (out / "intake-review.md").read_text()
    assert "Excluded by request" in review and "scripts/tool.py" in review


def test_exclude_applies_to_javascript_intake(tmp_path):
    root = tmp_path / "js"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.js").write_text("const b = require('./b');\n", encoding="utf-8")
    (root / "src" / "b.js").write_text("module.exports = 1;\n", encoding="utf-8")
    (root / "examples").mkdir()
    (root / "examples" / "demo.js").write_text("require('../src/a');\n", encoding="utf-8")
    cut = prepare_project_intake(root, system="S", goal="G", requirements=REQ,
                                 language="javascript", exclude=["examples"])
    assert _modules(cut) == ["src/a.js", "src/b.js"]
    assert cut.observations.excluded_by_request == ["examples"]
