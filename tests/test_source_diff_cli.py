"""CLI integration of `speccanopy source-diff` (exit codes, outputs, refusal).

Synthetic temporary projects only. A byte-level inventory comparison is not
semantic or architectural verification, and these tests do not claim it is.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from speccanopy.cli import main
from speccanopy.source_diff import InventoryDiff

OUTPUTS = {"source-diff.json", "source-diff.md"}


def _project(root: Path) -> Path:
    (root / "src" / "app").mkdir(parents=True)
    (root / "README.md").write_text("# Synthetic app\n", encoding="utf-8")
    (root / "src" / "app" / "api.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    (root / "src" / "app" / "store.py").write_text("ROWS = []\n", encoding="utf-8")
    (root / ".env").write_text("TOKEN=DIFF_SECRET_MARKER", encoding="utf-8")
    return root


def _inventory(root: Path, path: Path, *extra: str) -> Path:
    assert main(["source-inventory", str(root), "--output", str(path), *extra]) == 0
    return path


def _snapshots(tmp_path: Path) -> tuple[Path, Path]:
    root = _project(tmp_path / "app")
    before = _inventory(root, tmp_path / "inv" / "before.json")
    (root / "src" / "app" / "api.py").write_text("def handler():\n    return 2\n", encoding="utf-8")
    (root / "src" / "app" / "store.py").unlink()
    (root / "src" / "app" / "queue.py").write_text("JOBS = []\n", encoding="utf-8")
    after = _inventory(root, tmp_path / "inv" / "after.json")
    return before, after


def test_source_diff_cli_reports_changes_and_strict_exit(tmp_path, capsys):
    before, after = _snapshots(tmp_path)
    out = tmp_path / "diff"
    assert main(["source-diff", str(before), str(after), "--output", str(out)]) == 0
    stdout = capsys.readouterr().out
    assert "Source diff: 1 added, 1 removed, 1 changed, 1 unchanged" in stdout
    assert "Coverage: comparable; requires review: yes" in stdout
    assert "not semantic or architectural verification" in stdout
    assert {p.name for p in out.iterdir()} == OUTPUTS
    diff = InventoryDiff.model_validate_json((out / "source-diff.json").read_text())
    assert diff.added == ["src/app/queue.py"]
    assert diff.removed == ["src/app/store.py"]
    assert diff.changed == ["src/app/api.py"]
    assert diff.unchanged == ["README.md"]
    for name in OUTPUTS:
        text = (out / name).read_text()
        assert "DIFF_SECRET_MARKER" not in text and ".env" not in text
        assert str(tmp_path) not in text
    strict = tmp_path / "diff-strict"
    assert main(["source-diff", str(before), str(after), "--output", str(strict), "--strict"]) == 2
    assert (strict / "source-diff.json").read_bytes() == (out / "source-diff.json").read_bytes()


def test_source_diff_cli_identical_snapshots_exit_zero_even_strict(tmp_path, capsys):
    root = _project(tmp_path / "app")
    a = _inventory(root, tmp_path / "a.json")
    b = _inventory(root, tmp_path / "b.json")
    assert main(["source-diff", str(a), str(b), "--output", str(tmp_path / "d"), "--strict"]) == 0
    assert "requires review: no" in capsys.readouterr().out


def test_source_diff_cli_scope_differs_and_legacy_scope_unknown(tmp_path, capsys):
    root = _project(tmp_path / "app")
    a = _inventory(root, tmp_path / "a.json")
    b = _inventory(root, tmp_path / "b.json", "--max-file-bytes", "4096")
    assert main(["source-diff", str(a), str(b), "--output", str(tmp_path / "d1"), "--strict"]) == 2
    assert "Coverage: scope_differs" in capsys.readouterr().out
    legacy = json.loads(a.read_text())
    del legacy["scope"]
    old = tmp_path / "legacy.json"
    old.write_text(json.dumps(legacy), encoding="utf-8")
    assert main(["source-diff", str(old), str(a), "--output", str(tmp_path / "d2")]) == 0
    assert "Coverage: scope_unknown; requires review: yes" in capsys.readouterr().out


def test_source_diff_cli_errors_exit_one_without_writing(tmp_path, capsys):
    before, after = _snapshots(tmp_path)
    missing = tmp_path / "missing-out"
    assert main(["source-diff", str(tmp_path / "nope.json"), str(after),
                 "--output", str(missing)]) == 1
    assert not missing.exists()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main(["source-diff", str(bad), str(after), "--output", str(missing)]) == 1
    assert not missing.exists()
    tampered = json.loads(after.read_text())
    first = json.loads(before.read_text())["files"][0]
    tampered["files"] = [dict(first, line_count=first["line_count"] + 7)] + [
        f for f in tampered["files"] if f["path"] != first["path"]
    ]
    tampered["files"].sort(key=lambda f: f["path"])
    edited = tmp_path / "tampered.json"
    edited.write_text(json.dumps(tampered), encoding="utf-8")
    assert main(["source-diff", str(before), str(edited), "--output", str(missing)]) == 1
    assert "inconsistent inventory metadata" in capsys.readouterr().err
    assert not missing.exists()


def test_source_diff_cli_never_overwrites_existing_output(tmp_path, capsys):
    before, after = _snapshots(tmp_path)
    owned = tmp_path / "owner-docs"
    owned.mkdir()
    (owned / "source-diff.md").write_text("OWNER NOTES", encoding="utf-8")
    assert main(["source-diff", str(before), str(after), "--output", str(owned)]) == 1
    assert (owned / "source-diff.md").read_text() == "OWNER NOTES"
    assert sorted(p.name for p in owned.iterdir()) == ["source-diff.md"]
    assert "existing files not overwritten" in capsys.readouterr().err
    link = tmp_path / "linked"
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert main(["source-diff", str(before), str(after), "--output", str(link)]) == 1
    assert not (tmp_path / "elsewhere").exists()


ACCEPTANCE_APP = (
    Path(__file__).resolve().parents[1] / "examples" / "acceptance" / "synthetic-inventory-app"
)


def test_intake_inventory_then_change_is_visible_in_diff_and_stale_document(tmp_path):
    """Synthetic committed fixture; integration of intake, source-diff and document."""
    app = tmp_path / "app"
    shutil.copytree(ACCEPTANCE_APP, app)
    intake, design = tmp_path / "intake", tmp_path / "design"
    assert main([
        "project-intake", str(app), "--system", "Synthetic Inventory Ledger",
        "--goal", "SYNTHETIC: document module boundaries",
        "--requirement", "SYNTHETIC: the demo ledger records stock movements",
        "--output", str(intake),
    ]) == 0
    assert main(["design", str(intake / "brief.json"), "--fixture",
                 str(intake / "design.json"), "--output", str(design)]) == 0
    ledger = app / "src" / "inventory_ledger_demo" / "ledger.py"
    ledger.write_text(ledger.read_text() + "\n# synthetic edit\n", encoding="utf-8")
    (app / "src" / "inventory_ledger_demo" / "audit.py").write_text("LOG = []\n", encoding="utf-8")
    after = tmp_path / "inventory-v2.json"
    assert main(["source-inventory", str(app), "--output", str(after)]) == 0
    diff_dir = tmp_path / "diff"
    assert main(["source-diff", str(intake / "source-inventory.json"), str(after),
                 "--output", str(diff_dir), "--strict"]) == 2
    diff = InventoryDiff.model_validate_json((diff_dir / "source-diff.json").read_text())
    assert diff.changed == ["src/inventory_ledger_demo/ledger.py"]
    assert diff.added == ["src/inventory_ledger_demo/audit.py"]
    assert diff.removed == [] and diff.coverage == "comparable"
    docs = tmp_path / "docs"
    assert main(["document", str(design / "architecture.json"), "--source-root", str(app),
                 "--source-evidence", str(intake / "source-evidence.json"),
                 "--output", str(docs), "--strict"]) == 2
    evidence = (docs / "source-evidence.md").read_text()
    assert "| changed |" in evidence and "ledger.py" in evidence
    # The new, uncited module is only visible through source-diff, not document.
    assert "audit" not in evidence


def test_installed_console_script_exit_codes(tmp_path):
    before, after = _snapshots(tmp_path)
    exe = Path(sys.executable).parent / "speccanopy"
    ok = subprocess.run([str(exe), "source-diff", str(before), str(after),
                         "--output", str(tmp_path / "s1")], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    strict = subprocess.run([str(exe), "source-diff", str(before), str(after),
                             "--output", str(tmp_path / "s2"), "--strict"],
                            capture_output=True, text=True)
    assert strict.returncode == 2
    again = subprocess.run([str(exe), "source-diff", str(before), str(after),
                            "--output", str(tmp_path / "s1")], capture_output=True, text=True)
    assert again.returncode == 1
    assert "Error comparing source inventories" in again.stderr
    assert "Traceback" not in again.stderr
