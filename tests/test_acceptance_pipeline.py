"""Offline end-to-end acceptance coverage for intake -> design -> review -> document.

Everything here is SYNTHETIC. The project under test is the committed fixture
``examples/acceptance/synthetic-inventory-app`` (written for these tests, not a
real application, no real users or data) or small throw-away trees built in
``tmp_path``. This is self-dogfooding and NOT an externally permissioned,
real-world application acceptance or an independent expert evaluation.

No network, no model/API calls, no execution of the analyzed sources. All
outputs are written below ``tmp_path`` only.
"""

from __future__ import annotations

import contextlib
import getpass
import io
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.models import ArchitectureSpec
from speccanopy.project_intake import IntakeObservations
from speccanopy.review import ArchitectureReview
from speccanopy.source_evidence import (
    SourceEvidence, SourceInventory, assess_sources, inventory_policy_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples" / "acceptance" / "synthetic-inventory-app"
CONSOLE_SCRIPT = Path(sys.executable).parent / "speccanopy"
PACKAGE = "inventory_ledger_demo"

SYSTEM = "Synthetic Inventory Ledger"
GOAL = "SYNTHETIC: document the module boundaries of the acceptance fixture"
REQUIREMENTS = [
    "SYNTHETIC: the demo ledger records stock movements for catalog items",
    "SYNTHETIC: the demo reports summarize ledger balances",
]

INTAKE_FILES = {
    "brief.json", "design.json", "source-evidence.json",
    "source-inventory.json", "module-observations.json", "intake-review.md",
}
DESIGN_FILES = {
    "architecture.json", "architecture.mmd", "relationships.mmd",
    "requirements-report.json", "decisions.json", "generation-trace.json",
}
REVIEW_FILES = {
    "architecture-review.json", "architecture-review.md",
    "quality-review.json", "style-comparison.json",
}
DOC_FILES = {
    "README.md", "overview.md", "requirements.md", "components.md",
    "interactions.md", "data-security.md", "decisions.md", "quality-risks.md",
    "open-questions.md", "architecture.mmd", "relationships.mmd",
    "source-evidence.md",
}


# --------------------------------------------------------------------- helpers

@dataclass
class Result:
    rc: int
    out: str
    err: str


def run_inproc(argv: list[object]) -> Result:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main([str(a) for a in argv])
    return Result(rc, out.getvalue(), err.getvalue())


def run_script(argv: list[object], cwd: Path) -> Result:
    assert CONSOLE_SCRIPT.is_file(), "speccanopy console script is not installed"
    proc = subprocess.run(
        [str(CONSOLE_SCRIPT), *[str(a) for a in argv]],
        cwd=cwd, capture_output=True, text=True, timeout=180, check=False,
    )
    return Result(proc.returncode, proc.stdout, proc.stderr)


def copy_example(dest: Path) -> Path:
    shutil.copytree(EXAMPLE, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dest


def read_tree(root: Path) -> dict[str, bytes]:
    """Relative path -> bytes for every regular file; symlinks recorded as markers."""
    tree: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            tree[rel] = b"SYMLINK->" + os.readlink(path).encode()
        elif path.is_file():
            tree[rel] = path.read_bytes()
    return tree


def intake_argv(project: Path, out: Path, *, system: str = SYSTEM, goal: str = GOAL,
                requirements: list[str] | None = None, extra: tuple[str, ...] = ()) -> list[object]:
    argv: list[object] = ["project-intake", project, "--system", system, "--goal", goal]
    for req in REQUIREMENTS if requirements is None else requirements:
        argv += ["--requirement", req]
    return [*argv, "--output", out, *extra]


def design_argv(intake: Path, out: Path, *extra: str) -> list[object]:
    return ["design", intake / "brief.json", "--fixture", intake / "design.json",
            "--output", out, *extra]


def review_argv(design: Path, out: Path, *extra: str) -> list[object]:
    return ["review", design / "architecture.json", "--output", out, *extra]


def document_argv(design: Path, review: Path | None, intake: Path, project: Path | None,
                  out: Path, *extra: str, evidence: Path | None = None) -> list[object]:
    argv: list[object] = ["document", design / "architecture.json"]
    if review is not None:
        argv += ["--review", review / "architecture-review.json"]
    if project is not None:
        argv += ["--source-root", project]
    argv += ["--source-evidence", evidence or intake / "source-evidence.json"] if (
        project is not None or evidence is not None
    ) else []
    return [*argv, "--output", out, *extra]


@dataclass
class Pipeline:
    base: Path
    project: Path
    intake: Path
    design: Path
    review: Path
    docs: Path
    results: dict[str, Result]

    def stage_dirs(self) -> dict[str, Path]:
        return {"intake": self.intake, "design": self.design,
                "review": self.review, "docs": self.docs}

    def all_outputs(self) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        for stage, directory in self.stage_dirs().items():
            for rel, data in read_tree(directory).items():
                files[f"{stage}/{rel}"] = data
        return files

    def document(self, name: str, *extra: str, project: Path | None = None,
                 evidence: Path | None = None, runner: Callable = run_inproc) -> tuple[Result, Path]:
        out = self.base / name
        argv = document_argv(self.design, self.review, self.intake, project or self.project,
                             out, *extra, evidence=evidence)
        return runner(argv), out


def run_pipeline(
    base: Path, *, project_name: str = "app", runner: Callable = run_inproc,
    prepare: Callable[[Path], None] | None = None, relative_to: Path | None = None,
    project_tree: Path | None = None,
) -> Pipeline:
    """Run all four stages; assert each exits 0. Optionally with relative paths."""
    base.mkdir(parents=True, exist_ok=True)
    project = copy_example(base / project_name) if project_tree is None else project_tree
    if prepare is not None:
        prepare(project)
    rel = (lambda p: p.relative_to(relative_to)) if relative_to else (lambda p: p)
    intake, design, review, docs = (base / n for n in ("intake", "design", "review", "docs"))
    results: dict[str, Result] = {}
    results["intake"] = runner(intake_argv(rel(project), rel(intake)))
    results["design"] = runner(design_argv(rel(intake), rel(design)))
    results["review"] = runner(review_argv(rel(design), rel(review)))
    results["docs"] = runner(document_argv(rel(design), rel(review), rel(intake), rel(project), rel(docs)))
    for stage, result in results.items():
        assert result.rc == 0, (stage, result)
        assert result.err == "", (stage, result.err)
    return Pipeline(base, project, intake, design, review, docs, results)


@pytest.fixture
def pipeline(tmp_path: Path) -> Pipeline:
    return run_pipeline(tmp_path / "run")


def unescape_md(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def doc_rows(docs: Path) -> list[tuple[str, str, str]]:
    """(architecture id, file[:lines], byte status) rows of source-evidence.md."""
    rows = []
    for line in (docs / "source-evidence.md").read_text(encoding="utf-8").splitlines():
        text = unescape_md(line)
        if text.startswith("| ") and "src/" in text:
            cells = text[2:-2].split(" | ")
            rows.append((cells[0], cells[1], cells[3]))
    return rows


def module_ids(intake: Path) -> dict[str, str]:
    obs = IntakeObservations.model_validate_json(
        (intake / "module-observations.json").read_text(encoding="utf-8"))
    return {m.module: m.component_id for m in obs.modules}


def assert_clean_failure(result: Result, *outputs: Path, needle: str) -> None:
    assert result.rc == 1, result
    assert "Traceback" not in result.err
    assert result.err.startswith("Error"), result.err
    assert needle.lower() in result.err.lower(), result.err
    for out in outputs:
        assert not out.exists() and not out.is_symlink(), f"partial output created at {out}"


# ------------------------------------------------- 1. full pipeline, exact files

def test_full_pipeline_via_real_console_script_produces_exact_artifacts(tmp_path):
    project = copy_example(tmp_path / "app")
    before = read_tree(project)
    intake, design, review, docs = (tmp_path / n for n in ("intake", "design", "review", "docs"))

    r_intake = run_script(intake_argv(project, intake), tmp_path)
    r_design = run_script(design_argv(intake, design), tmp_path)
    r_review = run_script(review_argv(design, review), tmp_path)
    r_docs = run_script(document_argv(design, review, intake, project, docs), tmp_path)

    for result in (r_intake, r_design, r_review, r_docs):
        assert result.rc == 0, result
        assert result.err == ""
    assert "Python source intake: 4 modules, 3 static import edges" in r_intake.out
    assert "PROVISIONAL" in r_intake.out and "no code executed" in r_intake.out
    assert "Status: incomplete_requires_review" in r_design.out
    assert "Components: 5; max depth: 1" in r_design.out
    assert "0 verified, 0 planned, 2 uncovered" in r_design.out
    assert "Status: requires_review" in r_review.out
    assert "Advisory style: abstain" in r_review.out
    assert "Source architecture status: incomplete_requires_review" in r_docs.out
    assert "7/7 byte snapshots match; not proof of architectural correctness" in r_docs.out

    assert {p.name for p in intake.iterdir()} == INTAKE_FILES
    assert {p.name for p in design.iterdir()} == DESIGN_FILES
    assert {p.name for p in review.iterdir()} == REVIEW_FILES
    assert {p.name for p in docs.iterdir()} == DOC_FILES
    # No stage may modify, add to, or leave caches in the analyzed project.
    assert read_tree(project) == before
    assert not list(project.rglob("__pycache__")) and not list(project.rglob("*.pyc"))


def test_pipeline_artifact_contents_preserve_review_status_and_open_gaps(pipeline):
    pl = pipeline
    texts = {k: v.decode("utf-8") for k, v in pl.all_outputs().items()}
    assert "validated_for_scope" not in "\n".join(texts.values())

    spec = ArchitectureSpec.model_validate_json((pl.design / "architecture.json").read_text())
    assert spec.status == "incomplete_requires_review"
    assert spec.selected_style is None and not spec.decisions
    ids = module_ids(pl.intake)
    assert sorted(ids) == [PACKAGE, f"{PACKAGE}.catalog", f"{PACKAGE}.ledger", f"{PACKAGE}.reports"]
    assert {c.id for c in spec.components} == {"system", *ids.values()}
    assert {c.status for c in spec.components} == {"requires_review"}
    edges = {(r.source_id, r.target_id) for r in spec.relationships}
    assert edges == {
        (ids[f"{PACKAGE}.ledger"], ids[f"{PACKAGE}.catalog"]),
        (ids[f"{PACKAGE}.reports"], ids[f"{PACKAGE}.catalog"]),
        (ids[f"{PACKAGE}.reports"], ids[f"{PACKAGE}.ledger"]),
    }
    report = json.loads((pl.design / "requirements-report.json").read_text())
    assert report["status"] == "incomplete_requires_review"
    assert report["coverage"]["uncovered"] == ["FR-USER-001", "FR-USER-002"]
    assert report["coverage"]["verified"] == [] and report["coverage"]["planned_only"] == []

    review = ArchitectureReview.model_validate_json(
        (pl.review / "architecture-review.json").read_text())
    assert review.overall_status == "requires_review"
    assert review.source_architecture_status == "incomplete_requires_review"
    assert review.system == SYSTEM

    inventory = SourceInventory.model_validate_json((pl.intake / "source-inventory.json").read_text())
    assert [f.path for f in inventory.files] == [
        "README.md", "scripts/seed_demo.sh", f"src/{PACKAGE}/__init__.py",
        f"src/{PACKAGE}/catalog.py", f"src/{PACKAGE}/ledger.py", f"src/{PACKAGE}/reports.py",
    ]
    assert inventory.scope is not None
    assert (inventory.scope.max_files, inventory.scope.max_file_bytes) == (2000, 1_000_000)
    assert inventory.scope.policy_sha256 == inventory_policy_digest()
    obs = IntakeObservations.model_validate_json((pl.intake / "module-observations.json").read_text())
    assert obs.status == "provisional_requires_owner_review"
    assert obs.excluded_non_python_source == ["scripts/seed_demo.sh"]

    evidence = SourceEvidence.model_validate_json((pl.intake / "source-evidence.json").read_text())
    assert len(evidence.claims) == 7 and all(c.basis == "observed" for c in evidence.claims)
    assessment = assess_sources(spec, evidence, pl.project)
    assert [c.status for c in assessment.checks] == ["matching_snapshot"] * 7
    assert assessment.unlinked_mandatory_requirements == ["FR-USER-001", "FR-USER-002"]
    assert assessment.unlinked_components == ["system"]
    assert assessment.requires_review

    source_page = texts["docs/source-evidence.md"]
    assert "Claims provided: 7" in source_page and "Matching byte snapshots: 7" in source_page
    assert "Changed or missing/unreadable/invalid-span snapshots: 0" in source_page
    assert {status for _, _, status in doc_rows(pl.docs)} == {"matching_snapshot"}
    assert len(doc_rows(pl.docs)) == 7
    unlinked = source_page.split("## Unlinked mandatory requirements")[1]
    assert "FR-USER-001" in unlinked and "FR-USER-002" in unlinked and "- system" in unlinked
    questions = unescape_md(texts["docs/open-questions.md"])
    assert "- [ ] Map these mandatory requirements to observed source files" in questions
    assert "FR-USER-001, FR-USER-002" in questions
    assert "- [x]" not in questions
    assert "Review current draft status: incomplete_requires_review" in questions
    requirements_page = texts["docs/requirements.md"]
    assert requirements_page.count("Uncovered") >= 2


def test_strict_flag_returns_two_at_every_stage_and_still_writes_outputs(pipeline, tmp_path):
    pl = pipeline
    design = run_inproc(design_argv(pl.intake, tmp_path / "d-strict", "--strict"))
    review = run_inproc(review_argv(pl.design, tmp_path / "r-strict", "--strict"))
    docs = run_inproc(document_argv(pl.design, pl.review, pl.intake, pl.project,
                                    tmp_path / "doc-strict", "--strict"))
    assert (design.rc, review.rc, docs.rc) == (2, 2, 2)
    assert {p.name for p in (tmp_path / "d-strict").iterdir()} == DESIGN_FILES
    assert {p.name for p in (tmp_path / "r-strict").iterdir()} == REVIEW_FILES
    assert {p.name for p in (tmp_path / "doc-strict").iterdir()} == DOC_FILES
    # The strict run documents exactly the same bytes as the non-strict run.
    assert read_tree(tmp_path / "doc-strict") == read_tree(pl.docs)
    assert design.err == review.err == docs.err == ""


# ------------------------------------------- 2. repeatability / location independence

def _host_markers(*extra: Path) -> list[str]:
    markers = [str(p) for p in extra]
    markers += [str(REPO_ROOT), tempfile_dir()]
    home = str(Path.home())
    if home not in {"/", ""}:
        markers.append(home)
    user = getpass.getuser()
    markers += [f"/{user}/", f"\\{user}\\"]
    return markers


def tempfile_dir() -> str:
    import tempfile
    return tempfile.gettempdir().rstrip("/") + "/"


HOST_PATH_RE = re.compile(
    r"(?<![\w.\-])/(?:home|tmp|Users|root|var|mnt|run|opt|usr|etc|private/var)/|\b[A-Za-z]:\\"
)


def assert_no_host_leak(files: dict[str, bytes], *extra: Path) -> None:
    for name, data in files.items():
        text = data.decode("utf-8")
        for marker in _host_markers(*extra):
            assert marker not in text, f"{name} leaks {marker!r}"
        assert not HOST_PATH_RE.search(text), f"{name} contains a host-style absolute path"


def test_pipeline_is_byte_identical_at_different_locations_and_path_styles(tmp_path, monkeypatch):
    run_a = run_pipeline(tmp_path / "location-a" / "deeper" / "tree", project_name="projA-marker-aaa")
    base_b = tmp_path / "other-b"
    base_b.mkdir()
    monkeypatch.chdir(base_b)
    # Run B uses RELATIVE paths from a different directory, with a different project name.
    run_b = run_pipeline(base_b, project_name="projB-marker-bbb", relative_to=base_b)
    monkeypatch.undo()

    files_a, files_b = run_a.all_outputs(), run_b.all_outputs()
    assert set(files_a) == set(files_b)
    expected = (
        {f"intake/{n}" for n in INTAKE_FILES} | {f"design/{n}" for n in DESIGN_FILES}
        | {f"review/{n}" for n in REVIEW_FILES} | {f"docs/{n}" for n in DOC_FILES}
    )
    assert set(files_a) == expected
    for name in sorted(files_a):
        assert files_a[name] == files_b[name], f"{name} differs between locations"
    assert_no_host_leak(files_a, run_a.base, run_a.project, run_b.base, run_b.project, tmp_path)
    for data in files_a.values():
        text = data.decode("utf-8")
        assert "marker-aaa" not in text and "marker-bbb" not in text
        assert "location-a" not in text and "other-b" not in text


def test_pipeline_rerun_is_byte_identical_and_second_run_does_not_touch_first(tmp_path):
    first = run_pipeline(tmp_path / "one")
    snapshot = first.all_outputs()
    second = run_pipeline(tmp_path / "two")
    assert second.all_outputs() == snapshot
    assert first.all_outputs() == snapshot


# ---------------------------------------------------- 3. stale and missing sources

def _status_counts(docs: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, _, status in doc_rows(docs):
        counts[status] = counts.get(status, 0) + 1
    return counts


def _questions(docs: Path) -> str:
    return unescape_md((docs / "open-questions.md").read_text(encoding="utf-8"))


def test_edited_module_is_reported_changed_in_both_pages(pipeline):
    ledger = pipeline.project / "src" / PACKAGE / "ledger.py"
    ledger.write_text(ledger.read_text() + "\n# edited after intake\n", encoding="utf-8")
    result, docs = pipeline.document("docs-changed")
    assert result.rc == 0 and result.err == ""
    assert "5/7 byte snapshots match" in result.out
    assert _status_counts(docs) == {"matching_snapshot": 5, "changed": 2}
    ids = module_ids(pipeline.intake)
    ledger_rows = {a for a, loc, st in doc_rows(docs) if st == "changed"}
    assert ledger_rows >= {ids[f"{PACKAGE}.ledger"]}
    assert all("ledger.py" in loc for _, loc, st in doc_rows(docs) if st == "changed")
    page = (docs / "source-evidence.md").read_text()
    assert "Matching byte snapshots: 5" in page
    assert "Changed or missing/unreadable/invalid-span snapshots: 2" in page
    questions = _questions(docs)
    assert questions.count("Investigate changed source for") == 2
    assert f"src/{PACKAGE}/ledger.py." in questions
    assert "Investigate missing source" not in questions
    # The changed module is no longer a matching observed source for its component.
    provenance = [x for x in questions.splitlines() if "Confirm source provenance" in x]
    assert len(provenance) == 1
    assert provenance[0].endswith(f"components: {ids[f'{PACKAGE}.ledger']}, system")
    # Architecture status is untouched by stale evidence.
    assert ArchitectureSpec.model_validate_json(
        (pipeline.design / "architecture.json").read_text()).status == "incomplete_requires_review"


def test_deleted_module_is_reported_missing(pipeline):
    (pipeline.project / "src" / PACKAGE / "reports.py").unlink()
    result, docs = pipeline.document("docs-missing")
    assert result.rc == 0
    assert "4/7 byte snapshots match" in result.out
    assert _status_counts(docs) == {"matching_snapshot": 4, "missing": 3}
    assert all("reports.py" in loc for _, loc, st in doc_rows(docs) if st == "missing")
    questions = _questions(pipeline.base / "docs-missing")
    assert questions.count("Investigate missing source for") == 3
    ids = module_ids(pipeline.intake)
    assert ids[f"{PACKAGE}.reports"] in questions


def test_all_sources_deleted_marks_every_claim_missing(pipeline):
    shutil.rmtree(pipeline.project / "src")
    result, docs = pipeline.document("docs-all-missing")
    assert result.rc == 0
    assert "0/7 byte snapshots match" in result.out
    assert _status_counts(docs) == {"missing": 7}
    page = (docs / "source-evidence.md").read_text()
    assert "Matching byte snapshots: 0" in page
    assert page.count("Unavailable") == 7
    ids = module_ids(pipeline.intake)
    questions = _questions(docs)
    assert questions.count("Investigate missing source for") == 7
    for component_id in ids.values():
        assert component_id in questions.split("components:")[1]


@pytest.mark.parametrize("mode", ["changed", "missing", "all-missing"])
def test_strict_exits_two_but_still_writes_pack_for_stale_sources(pipeline, mode):
    src = pipeline.project / "src" / PACKAGE
    if mode == "changed":
        (src / "catalog.py").write_text("changed = True\n", encoding="utf-8")
    elif mode == "missing":
        (src / "catalog.py").unlink()
    else:
        shutil.rmtree(pipeline.project / "src")
    strict, strict_dir = pipeline.document("docs-strict", "--strict")
    lax, lax_dir = pipeline.document("docs-lax")
    assert strict.rc == 2 and lax.rc == 0
    assert strict.err == lax.err == ""
    assert {p.name for p in strict_dir.iterdir()} == DOC_FILES
    assert read_tree(strict_dir) == read_tree(lax_dir)
    assert "Investigate" in _questions(strict_dir)


def test_removed_source_root_fails_cleanly_without_output(pipeline):
    shutil.rmtree(pipeline.project)
    result, docs = pipeline.document("docs-no-root")
    assert_clean_failure(result, docs, needle="Source root must be an existing real directory")


def test_symlinked_module_is_unreadable_not_followed(pipeline, tmp_path):
    outside = tmp_path / "outside-target.py"
    outside.write_text("OUTSIDE_LINK_MARKER = 1\n", encoding="utf-8")
    ledger = pipeline.project / "src" / PACKAGE / "ledger.py"
    ledger.unlink()
    ledger.symlink_to(outside)
    result, docs = pipeline.document("docs-symlink")
    assert result.rc == 0
    assert _status_counts(docs) == {"matching_snapshot": 5, "unreadable": 2}
    assert "OUTSIDE_LINK_MARKER" not in "".join(read_tree(docs)[k].decode() for k in read_tree(docs))


def test_oversized_snapshot_limit_marks_claims_unreadable(pipeline):
    result, docs = pipeline.document("docs-small-limit", "--max-source-bytes", "10")
    assert result.rc == 0
    assert _status_counts(docs) == {"unreadable": 7}


def test_line_span_beyond_file_end_is_reported_out_of_range(pipeline, tmp_path):
    data = json.loads((pipeline.intake / "source-evidence.json").read_text())
    data["claims"][0]["line_start"] = 1
    data["claims"][0]["line_end"] = 9999
    evidence = tmp_path / "evidence-range.json"
    evidence.write_text(json.dumps(data), encoding="utf-8")
    result, docs = pipeline.document("docs-range", evidence=evidence)
    assert result.rc == 0
    assert _status_counts(docs) == {"matching_snapshot": 6, "line_out_of_range": 1}
    assert "Investigate line_out_of_range source" in _questions(docs)


# ------------------------------------------------------------ 4. unsupported inputs

def _project(tmp_path: Path, files: dict[str, bytes | str]) -> Path:
    root = tmp_path / "bad-project"
    root.mkdir()
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return root


INTAKE_CASES = {
    "non-python-only": ({"server.ts": "export const x = 1;", "main.go": "package main",
                         "README.md": "# docs", "ci.yml": "a: b", "data.json": "{}"},
                        "supports Python .py only", {}),
    "binary-py": ({"app.py": bytes(range(256)) * 4}, "Cannot safely parse Python module app.py", {}),
    "non-utf8-py": ({"app.py": b"# -*- coding: utf-8 -*-\nvalue = '\xff\xfe'\n"},
                    "Cannot safely parse Python module app.py", {}),
    "nul-byte-py": ({"app.py": b"x = 1\x00\n"}, "Cannot safely parse Python module app.py", {}),
    "syntax-error-py": ({"app.py": "def broken(:\n"}, "line 1", {}),
    "empty-requirement": ({"app.py": "x = 1\n"}, "Supply --system", {"requirements": [""]}),
    "blank-among-valid": ({"app.py": "x = 1\n"}, "Supply --system", {"requirements": ["ok", "   "]}),
    "empty-system": ({"app.py": "x = 1\n"}, "Supply --system", {"system": ""}),
    "blank-goal": ({"app.py": "x = 1\n"}, "Supply --system", {"goal": "   "}),
    "max-modules-zero": ({"app.py": "x = 1\n"}, "max_modules", {"extra": ("--max-modules", "0")}),
    "max-modules-51": ({"app.py": "x = 1\n"}, "max_modules", {"extra": ("--max-modules", "51")}),
    "max-files-zero": ({"app.py": "x = 1\n"}, "max_files", {"extra": ("--max-files", "0")}),
    "max-bytes-zero": ({"app.py": "x = 1\n"}, "max_bytes", {"extra": ("--max-file-bytes", "0")}),
    "only-oversized-py": ({"app.py": "x = 1\n" * 100}, "No Python source modules",
                          {"extra": ("--max-file-bytes", "10")}),
}


@pytest.mark.parametrize("case", sorted(INTAKE_CASES))
def test_unsupported_or_invalid_intake_inputs_fail_cleanly_without_output(tmp_path, case):
    files, needle, options = INTAKE_CASES[case]
    root = _project(tmp_path, files)
    out = tmp_path / "never-created"
    result = run_inproc(intake_argv(root, out, **options))
    assert_clean_failure(result, out, needle=needle)
    assert result.out == ""
    assert read_tree(root) == {k: (v if isinstance(v, bytes) else v.encode()) for k, v in files.items()}


@pytest.mark.parametrize("target", ["missing", "file"])
def test_intake_project_path_must_be_a_real_directory(tmp_path, target):
    path = tmp_path / "not-a-dir"
    if target == "file":
        path.write_text("x = 1\n")
    out = tmp_path / "never-created"
    assert_clean_failure(run_inproc(intake_argv(path, out)), out,
                         needle="Source root must be an existing real directory")


def test_failures_via_real_console_script_have_clean_stderr_and_exit_one(tmp_path):
    root = _project(tmp_path, {"app.py": bytes(range(256)) * 4})
    out = tmp_path / "never-created"
    result = run_script(intake_argv(root, out), tmp_path)
    assert_clean_failure(result, out, needle="Cannot safely parse Python module app.py")
    assert result.out == ""
    empty = run_script(intake_argv(root, out, requirements=[""]), tmp_path)
    assert_clean_failure(empty, out, needle="Supply --system")


def test_non_allowlisted_json_is_never_inventoried_or_leaked(tmp_path):
    root = _project(tmp_path, {
        "app.py": "x = 1\n",
        "data.json": '{"customer": "JSON_DATA_MARKER"}',
        "package.json": '{"name": "synthetic"}',
        "records/export.json": '{"row": "JSON_NESTED_MARKER"}',
    })
    pl = run_pipeline(tmp_path / "run", project_tree=root)
    inventory = SourceInventory.model_validate_json((pl.intake / "source-inventory.json").read_text())
    assert [f.path for f in inventory.files] == ["app.py", "package.json"]
    for name, data in pl.all_outputs().items():
        text = data.decode("utf-8")
        assert "JSON_DATA_MARKER" not in text and "JSON_NESTED_MARKER" not in text, name
        assert "data.json" not in text and "export.json" not in text, name


def _bad_text(path: Path, kind: str) -> None:
    if kind == "invalid-json":
        path.write_text("{not json", encoding="utf-8")
    elif kind == "empty":
        path.write_text("", encoding="utf-8")
    elif kind == "empty-object":
        path.write_text("{}", encoding="utf-8")
    elif kind == "json-list":
        path.write_text("[]", encoding="utf-8")
    elif kind == "non-utf8":
        path.write_bytes(b"\xff\xfe\x00{")
    elif kind == "directory":
        path.mkdir()
    elif kind == "truncated":
        path.write_text('{"brief": {"system": "x"', encoding="utf-8")
    else:  # pragma: no cover
        raise AssertionError(kind)


ARCH_KINDS = ["invalid-json", "empty", "empty-object", "json-list", "non-utf8", "directory", "truncated", "missing"]


@pytest.mark.parametrize("kind", ARCH_KINDS)
def test_malformed_architecture_fails_document_and_review_cleanly(pipeline, tmp_path, kind):
    bad = tmp_path / "bad-architecture.json"
    if kind != "missing":
        _bad_text(bad, kind)
    doc_out, rev_out = tmp_path / "doc-never", tmp_path / "rev-never"
    doc = run_inproc(["document", bad, "--output", doc_out])
    rev = run_inproc(["review", bad, "--output", rev_out])
    assert_clean_failure(doc, doc_out, needle="Error documenting architecture")
    assert_clean_failure(rev, rev_out, needle="Error reviewing architecture")


@pytest.mark.parametrize("kind", ["invalid-json", "empty", "empty-object", "non-utf8", "missing"])
def test_malformed_brief_or_fixture_fails_design_cleanly(pipeline, tmp_path, kind):
    bad = tmp_path / "bad.json"
    if kind != "missing":
        _bad_text(bad, kind)
    out1, out2 = tmp_path / "d1-never", tmp_path / "d2-never"
    bad_brief = run_inproc(["design", bad, "--fixture", pipeline.intake / "design.json", "--output", out1])
    bad_fixture = run_inproc(["design", pipeline.intake / "brief.json", "--fixture", bad, "--output", out2])
    assert_clean_failure(bad_brief, out1, needle="Error designing architecture")
    assert_clean_failure(bad_fixture, out2, needle="Error designing architecture")


@pytest.mark.parametrize("kind", ["invalid-json", "empty", "empty-object", "non-utf8", "directory"])
def test_malformed_review_config_and_review_input_fail_cleanly(pipeline, tmp_path, kind):
    bad = tmp_path / "bad-input.json"
    _bad_text(bad, kind)
    out1, out2 = tmp_path / "rc-never", tmp_path / "rd-never"
    cfg = run_inproc(["review", pipeline.design / "architecture.json", "--config", bad, "--output", out1])
    if kind == "empty-object":
        # "{}" is a valid (all-defaults) review config; it is not malformed.
        assert cfg.rc == 0
        shutil.rmtree(out1)
    else:
        assert_clean_failure(cfg, out1, needle="Error reviewing architecture")
    doc = run_inproc(["document", pipeline.design / "architecture.json", "--review", bad, "--output", out2])
    assert_clean_failure(doc, out2, needle="Error documenting architecture")


def _mutate_evidence(pipeline: Pipeline, tmp_path: Path, mutate: Callable[[dict], None]) -> Path:
    data = json.loads((pipeline.intake / "source-evidence.json").read_text())
    mutate(data)
    path = tmp_path / "mutated-evidence.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _set_claim(**fields) -> Callable[[dict], None]:
    def mutate(data: dict) -> None:
        data["claims"][0].update(fields)
    return mutate


EVIDENCE_CASES = {
    "unknown-architecture-id": (_set_claim(architecture_id="no-such-component"),
                                "unknown architecture ID: no-such-component"),
    "short-sha": (_set_claim(sha256="abc123"), "sha256"),
    "bad-basis": (_set_claim(basis="verified"), "basis"),
    "empty-assertion": (_set_claim(assertion=""), "assertion"),
    "reversed-lines": (_set_claim(line_start=5, line_end=2), "reversed"),
    "half-span": (_set_claim(line_start=3, line_end=None), "line_start and line_end"),
    "traversal": (_set_claim(source_path="../escape.py"), "traversal"),
    "absolute": (_set_claim(source_path="/etc/passwd.py"), "relative"),
    "dotenv": (_set_claim(source_path=".env"), "excluded by privacy policy"),
    "private-dir": (_set_claim(source_path="private/x.py"), "excluded by privacy policy"),
    "credentials-name": (_set_claim(source_path="src/pkg/credentials.yml"), "excluded by privacy policy"),
    "id-rsa": (_set_claim(source_path="id_rsa"), "excluded by privacy policy"),
    "non-allowlisted-json": (_set_claim(source_path="data.json"), "not an allowed"),
    "backslash": (_set_claim(source_path="src\\x.py"), "clean relative POSIX"),
    "bad-schema-version": (lambda d: d.update(schema_version=2), "schema_version"),
    "duplicate-claim": (lambda d: d["claims"].append(dict(d["claims"][0])), "Duplicate source claims"),
    "claims-not-a-list": (lambda d: d.update(claims="nope"), "claims"),
}


@pytest.mark.parametrize("case", sorted(EVIDENCE_CASES))
def test_invalid_source_evidence_fails_document_cleanly_without_output(pipeline, tmp_path, case):
    mutate, needle = EVIDENCE_CASES[case]
    evidence = _mutate_evidence(pipeline, tmp_path, mutate)
    result, out = pipeline.document("docs-never", evidence=evidence)
    assert_clean_failure(result, out, needle=needle)


@pytest.mark.parametrize("kind", ["invalid-json", "empty", "json-list", "non-utf8", "directory", "missing"])
def test_malformed_evidence_file_fails_document_cleanly(pipeline, tmp_path, kind):
    bad = tmp_path / "bad-evidence.json"
    if kind != "missing":
        _bad_text(bad, kind)
    result, out = pipeline.document("docs-never", evidence=bad)
    assert_clean_failure(result, out, needle="Error documenting architecture")


@pytest.mark.parametrize("omit", ["evidence", "root"])
def test_source_root_and_source_evidence_must_be_given_together(pipeline, tmp_path, omit):
    out = tmp_path / "docs-never"
    argv: list[object] = ["document", pipeline.design / "architecture.json", "--output", out]
    argv += ["--source-root", pipeline.project] if omit == "evidence" else [
        "--source-evidence", pipeline.intake / "source-evidence.json"]
    result = run_inproc(argv)
    assert_clean_failure(result, out, needle="--source-root and --source-evidence must be provided together")
    script = run_script(argv, tmp_path)
    assert_clean_failure(script, out, needle="must be provided together")


@pytest.mark.parametrize("limit", ["0", "-1", "5000001"])
def test_invalid_source_byte_limit_fails_cleanly(pipeline, limit):
    result, out = pipeline.document("docs-never", "--max-source-bytes", limit)
    assert_clean_failure(result, out, needle="Invalid source file size limit")


def test_review_from_another_system_is_refused_without_output(pipeline, tmp_path):
    other = run_pipeline(tmp_path / "other-system", project_name="other-app")
    other_review = tmp_path / "other-review"
    other_arch = tmp_path / "other-design"
    other_inputs = tmp_path / "other-inputs"
    assert run_inproc(intake_argv(other.project, other_inputs, system="A Different System")).rc == 0
    assert run_inproc(design_argv(other_inputs, other_arch)).rc == 0
    assert run_inproc(review_argv(other_arch, other_review)).rc == 0
    out = tmp_path / "mismatch-never"
    result = run_inproc(["document", pipeline.design / "architecture.json",
                         "--review", other_review / "architecture-review.json", "--output", out])
    assert_clean_failure(result, out, needle="Review system or source status does not match")


def test_evidence_from_a_different_project_run_is_refused_as_unknown_ids(pipeline, tmp_path):
    """Claim IDs are path-hashed; evidence for another module set cannot be attached."""
    other_root = _project(tmp_path, {"unrelated.py": "x = 1\n"})
    other_inputs = tmp_path / "other-inputs"
    assert run_inproc(intake_argv(other_root, other_inputs)).rc == 0
    result, out = pipeline.document("docs-never", evidence=other_inputs / "source-evidence.json")
    assert_clean_failure(result, out, needle="unknown architecture ID")


# ----------------------------------------------------------- 5. privacy exclusions

PRIVACY_FILES = {
    ".env": "PRIVMARK_ENV",
    ".git/config": "PRIVMARK_GITCONFIG",
    "private/x.py": "PRIVMARK_PRIVATE_DIR",
    "secrets/y.py": "PRIVMARK_SECRETS_DIR",
    f"src/{PACKAGE}/credentials.yml": "PRIVMARK_CREDENTIALS_YML",
    "id_rsa": "PRIVMARK_ID_RSA",
    "node_modules/z.js": "PRIVMARK_NODE_MODULES",
    f"src/{PACKAGE}/deploy_token.py": "PRIVMARK_TOKEN_PY",
    "my_secret_notes.md": "PRIVMARK_SECRET_NAME",
    "password_list.py": "PRIVMARK_PASSWORD_NAME",
    ".venv/site.py": "PRIVMARK_VENV",
    "dist/gen.py": "PRIVMARK_DIST",
    "build/gen.py": "PRIVMARK_BUILD",
    ".hidden/h.py": "PRIVMARK_HIDDEN_DIR",
}
PRIVACY_LEAK_STRINGS = [
    ".env", ".git", "private/x.py", "secrets/y.py", "credentials.yml", "id_rsa",
    "node_modules", "deploy_token", "my_secret_notes", "password_list", ".venv",
    "dist/gen.py", "build/gen.py", ".hidden", "linked_outside", "linked_dir",
    "outside_target", "outside_dir_file",
]


def _add_privacy_traps(project: Path) -> None:
    for rel, marker in PRIVACY_FILES.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{marker} = 'do-not-export'\n", encoding="utf-8")
    outside = project.parent / "outside-the-project"
    outside.mkdir()
    (outside / "outside_target.py").write_text("PRIVMARK_SYMLINK_FILE = 1\n", encoding="utf-8")
    (outside / "outside_dir_file.py").write_text("PRIVMARK_SYMLINK_DIR = 1\n", encoding="utf-8")
    (project / "src" / PACKAGE / "linked_outside.py").symlink_to(outside / "outside_target.py")
    (project / "linked_dir").symlink_to(outside, target_is_directory=True)


def test_privacy_excluded_files_never_appear_in_any_stage_output(tmp_path):
    clean = run_pipeline(tmp_path / "clean")
    trapped = run_pipeline(tmp_path / "trapped", prepare=_add_privacy_traps)
    files = trapped.all_outputs()
    markers = [*PRIVACY_FILES.values(), "PRIVMARK_SYMLINK_FILE", "PRIVMARK_SYMLINK_DIR"]
    for name, data in files.items():
        text = data.decode("utf-8")
        for marker in markers:
            assert marker not in text, f"{marker} leaked into {name}"
        for needle in PRIVACY_LEAK_STRINGS:
            assert needle not in text, f"excluded path fragment {needle!r} leaked into {name}"
    for stage, result in trapped.results.items():
        for marker in markers:
            assert marker not in result.out + result.err, stage
        for needle in PRIVACY_LEAK_STRINGS:
            assert needle not in result.out + result.err, (stage, needle)
    # Exclusions are complete: the observable outputs equal those of the untouched fixture.
    assert files == clean.all_outputs()
    obs = IntakeObservations.model_validate_json(
        (trapped.intake / "module-observations.json").read_text())
    assert len(obs.modules) == 4


@pytest.mark.parametrize("excluded", [
    ".env", "private/x.py", "secrets/y.py", f"src/{PACKAGE}/credentials.yml", "id_rsa",
    "node_modules/z.js", f"src/{PACKAGE}/deploy_token.py", ".git/config",
])
def test_excluded_file_cannot_be_cited_even_if_present_on_disk(tmp_path, excluded):
    pl = run_pipeline(tmp_path / "run", prepare=_add_privacy_traps)
    evidence = _mutate_evidence(pl, tmp_path, _set_claim(source_path=excluded))
    result, out = pl.document("docs-never", evidence=evidence)
    assert_clean_failure(result, out, needle="excluded by privacy policy")
    assert not re.search(r"PRIVMARK_\w+", result.out + result.err)


def test_symlink_to_outside_file_cited_by_valid_name_is_unreadable_and_not_read(tmp_path):
    pl = run_pipeline(tmp_path / "run", prepare=_add_privacy_traps)
    link_rel = f"src/{PACKAGE}/linked_outside.py"
    target = (pl.base / "outside-the-project" / "outside_target.py").read_bytes()
    import hashlib
    data = json.loads((pl.intake / "source-evidence.json").read_text())
    data["claims"].append({
        "architecture_id": "system", "source_path": link_rel,
        "sha256": hashlib.sha256(target).hexdigest(),  # would MATCH if the link were followed
        "assertion": "Synthetic claim citing a symlink that points outside the project",
        "basis": "observed",
    })
    evidence = tmp_path / "evidence-link.json"
    evidence.write_text(json.dumps(data), encoding="utf-8")
    result, out = pl.document("docs-link", evidence=evidence)
    assert result.rc == 0
    assert _status_counts(out)["unreadable"] == 1
    assert "7/8 byte snapshots match" in result.out
    assert "PRIVMARK" not in "".join(v.decode() for v in read_tree(out).values())


# ----------------------------------------------- 6. protection of existing outputs

STAGE_OWNER_FILE = {
    "project-intake": "brief.json", "design": "architecture.json",
    "review": "architecture-review.json", "document": "README.md",
}
STAGE_FILES = {
    "project-intake": INTAKE_FILES, "design": DESIGN_FILES,
    "review": REVIEW_FILES, "document": DOC_FILES,
}
DESIGN_REVIEW_BUG = {
    "design": "BUG: `design` writes into a non-empty/symlinked output dir and overwrites existing files (exporters.export_generation has no guard)",
    "review": "BUG: `review` writes into a non-empty/symlinked output dir and overwrites existing files (review_exporters.export_review has no guard)",
}


def _stage_params(bug_scope: str):
    params = []
    for stage in STAGE_OWNER_FILE:
        marks = ()
        if stage in DESIGN_REVIEW_BUG:
            marks = (pytest.mark.xfail(strict=True, reason=DESIGN_REVIEW_BUG[stage].replace(
                "non-empty/symlinked output dir and overwrites existing files",
                bug_scope)),)
        params.append(pytest.param(stage, id=stage, marks=marks))
    return params


def _stage_run(stage: str, pl: Pipeline, out: Path) -> Result:
    if stage == "project-intake":
        return run_inproc(intake_argv(pl.project, out))
    if stage == "design":
        return run_inproc(design_argv(pl.intake, out))
    if stage == "review":
        return run_inproc(review_argv(pl.design, out))
    return run_inproc(document_argv(pl.design, pl.review, pl.intake, pl.project, out))


@pytest.mark.parametrize("stage", _stage_params("overwrites owner files in an existing non-empty output dir"))
def test_existing_hand_edited_output_directory_is_never_overwritten_or_mixed(pipeline, tmp_path, stage):
    out = tmp_path / "owner-docs"
    out.mkdir()
    owner = {
        STAGE_OWNER_FILE[stage]: b"OWNER HAND-EDITED CONTENT - keep me\n",
        "owner-notes.md": b"OWNER NOTES - not produced by speccanopy\n",
    }
    for name, data in owner.items():
        (out / name).write_bytes(data)
    result = _stage_run(stage, pipeline, out)
    # Evaluate protection state first, then the exit code, so a failure shows what was clobbered.
    state = read_tree(out)
    assert state == owner, f"{stage} modified or added files in an existing non-empty directory"
    assert result.rc != 0, result
    assert result.err.startswith("Error") and "Traceback" not in result.err


@pytest.mark.parametrize("stage", _stage_params("writes through a symlinked output directory"))
def test_symlinked_output_directory_is_refused_and_nothing_is_written_through_it(pipeline, tmp_path, stage):
    real = tmp_path / "real-empty-dir"
    real.mkdir()
    link = tmp_path / "linked-output"
    link.symlink_to(real, target_is_directory=True)
    result = _stage_run(stage, pipeline, link)
    assert list(real.iterdir()) == [], f"{stage} wrote through a symlinked output directory"
    assert result.rc != 0, result
    assert result.err.startswith("Error") and "Traceback" not in result.err
    assert link.is_symlink()


@pytest.mark.parametrize("stage", list(STAGE_OWNER_FILE))
def test_existing_regular_file_as_output_path_is_not_touched(pipeline, tmp_path, stage):
    out = tmp_path / "owner-file"
    out.write_bytes(b"OWNER FILE, NOT A DIRECTORY\n")
    result = _stage_run(stage, pipeline, out)
    assert result.rc == 1 and result.err.startswith("Error") and "Traceback" not in result.err
    assert out.read_bytes() == b"OWNER FILE, NOT A DIRECTORY\n"


@pytest.mark.parametrize("stage", list(STAGE_OWNER_FILE))
def test_existing_empty_output_directory_is_accepted(pipeline, tmp_path, stage):
    out = tmp_path / "empty-ok"
    out.mkdir()
    result = _stage_run(stage, pipeline, out)
    assert result.rc == 0 and result.err == ""
    assert {p.name for p in out.iterdir()} == STAGE_FILES[stage]


@pytest.mark.parametrize("stage", ["project-intake", "document"])
def test_rerunning_a_guarded_stage_into_its_own_output_is_refused_and_idempotent(pipeline, stage):
    out = pipeline.intake if stage == "project-intake" else pipeline.docs
    before = read_tree(out)
    result = _stage_run(stage, pipeline, out)
    assert result.rc == 1 and result.err.startswith("Error")
    assert read_tree(out) == before


@pytest.mark.parametrize("stage", _stage_params("silently re-writes its own output on a re-run"))
def test_rerunning_any_stage_into_its_own_output_is_refused(pipeline, stage):
    out = {"project-intake": pipeline.intake, "design": pipeline.design,
           "review": pipeline.review, "document": pipeline.docs}[stage]
    owner_name = STAGE_OWNER_FILE[stage]
    (out / owner_name).write_bytes(b"OWNER EDITED AFTER GENERATION\n")
    result = _stage_run(stage, pipeline, out)
    assert (out / owner_name).read_bytes() == b"OWNER EDITED AFTER GENERATION\n"
    assert result.rc != 0


# ------------------------------------------------------------------- 7. no execution

CANARY_NAMES = {
    "boom_import_time": "canary-import-time",
    "boom_system_call": "canary-system-call",
    "boom_exec": "canary-exec",
    "setup": "canary-setup-py",
    "conftest": "canary-conftest",
}


def _add_execution_canaries(project: Path, marker_dir: Path) -> None:
    pkg = project / "src" / PACKAGE

    def marker(name: str) -> str:
        return repr(str(marker_dir / CANARY_NAMES[name]))

    (pkg / "boom_import_time.py").write_text(
        f"open({marker('boom_import_time')}, 'w').write('executed')\n"
        "raise RuntimeError('NOT SAFE TO EXECUTE: import-time failure')\n", encoding="utf-8")
    (pkg / "boom_system_call.py").write_text(
        "import os\n"
        f"os.system('touch ' + {marker('boom_system_call')})\n"
        "raise SystemExit(7)\n", encoding="utf-8")
    (pkg / "boom_exec.py").write_text(
        f"exec(\"open({marker('boom_exec')}, 'w').write('x')\")\n"
        "import this_module_does_not_exist_anywhere\n", encoding="utf-8")
    (project / "setup.py").write_text(
        f"open({marker('setup')}, 'w').write('setup executed')\n"
        "from setuptools import setup\nsetup()\n", encoding="utf-8")
    (project / "conftest.py").write_text(
        f"open({marker('conftest')}, 'w').write('conftest executed')\n", encoding="utf-8")


def test_no_stage_imports_or_executes_analyzed_sources(tmp_path):
    marker_dir = tmp_path / "canary-markers"
    marker_dir.mkdir()
    sys_modules_before = set(sys.modules)
    pl = run_pipeline(tmp_path / "run",
                      prepare=lambda p: _add_execution_canaries(p, marker_dir))
    # Also through the real console script (separate processes, fresh interpreters).
    scripted = run_pipeline(tmp_path / "scripted", runner=lambda a: run_script(a, tmp_path),
                            prepare=lambda p: _add_execution_canaries(p, marker_dir))

    assert list(marker_dir.iterdir()) == [], "analyzed source was executed"
    new_modules = set(sys.modules) - sys_modules_before
    for name in new_modules:
        assert not name.startswith(PACKAGE) and not name.startswith("boom_"), name
        assert name not in {"setup", "conftest"}
    for stage_pl in (pl, scripted):
        assert not list(stage_pl.project.rglob("__pycache__"))
        assert not list(stage_pl.project.rglob("*.pyc"))
        obs = IntakeObservations.model_validate_json(
            (stage_pl.intake / "module-observations.json").read_text())
        assert {m.module for m in obs.modules} >= {
            f"{PACKAGE}.boom_import_time", f"{PACKAGE}.boom_system_call",
            f"{PACKAGE}.boom_exec", "setup", "conftest",
        }
        text = "\n".join(v.decode() for v in stage_pl.all_outputs().values())
        assert "NOT SAFE TO EXECUTE" not in text
        assert "this_module_does_not_exist_anywhere" not in text
        assert "touch " not in text
        for filename in CANARY_NAMES.values():
            assert filename not in text
    # Both execution modes produce identical architecture artifacts.
    assert read_tree(pl.design) == read_tree(scripted.design)
    assert read_tree(pl.intake) == read_tree(scripted.intake)
