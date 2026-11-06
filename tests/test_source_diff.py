"""Source inventory comparison tests.

All projects are temporary synthetic files. Hash comparison proves byte
equality only; nothing here asserts architectural or behavioural equivalence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.source_diff import (
    InventoryDiff, SourceFileDelta, compare_inventories, export_inventory_diff,
    render_inventory_diff_markdown,
)
from speccanopy.source_evidence import (
    InventoryScope, SourceFile, SourceInventory, inventory_policy_digest,
    scan_sources,
)

SECRET_TEXT = "SECRET_CREDENTIAL-must-not-appear"


def _project(tmp_path: Path, name: str = "app") -> Path:
    root = tmp_path / name
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "README.md").write_text("# Demo\n\nText.\n", encoding="utf-8")
    (root / "src" / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (root / "tests" / "test_main.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    return root


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _file(path: str, text: str = "x\n", kind: str = "source") -> SourceFile:
    data = text.encode()
    return SourceFile(
        path=path, sha256=hashlib.sha256(data).hexdigest(),
        byte_count=len(data), line_count=len(data.splitlines()), kind=kind,
    )


def _scope(max_files=2000, max_file_bytes=1_000_000, policy=None) -> InventoryScope:
    return InventoryScope(
        max_files=max_files, max_file_bytes=max_file_bytes,
        policy_sha256=policy or inventory_policy_digest(),
    )


def _inv(files=(), *, scope="default", skipped=0) -> SourceInventory:
    return SourceInventory(
        files=sorted(files, key=lambda f: f.path), skipped_oversized=skipped,
        scope=_scope() if scope == "default" else scope,
    )


# ---- core semantics -------------------------------------------------------

def test_identical_snapshots_are_all_unchanged_and_need_no_review(tmp_path):
    root = _project(tmp_path)
    diff = compare_inventories(scan_sources(root), scan_sources(root))
    assert diff.added == diff.removed == diff.changed == []
    assert diff.unchanged == ["README.md", "src/main.py", "tests/test_main.py"]
    assert diff.coverage == "comparable"
    assert not diff.requires_review
    assert all(e.status == "unchanged" for e in diff.entries)


def test_added_removed_and_changed_files_from_real_scans(tmp_path):
    root = _project(tmp_path)
    before = scan_sources(root)
    (root / "src" / "new.py").write_text("x = 1\n", encoding="utf-8")
    (root / "README.md").unlink()
    (root / "src" / "main.py").write_text("def main():\n    return 2\n", encoding="utf-8")
    diff = compare_inventories(before, scan_sources(root))
    assert diff.added == ["src/new.py"]
    assert diff.removed == ["README.md"]
    assert diff.changed == ["src/main.py"]
    assert diff.unchanged == ["tests/test_main.py"]
    assert diff.requires_review
    by_path = {e.path: e for e in diff.entries}
    assert by_path["src/new.py"].before_sha256 is None
    assert by_path["src/new.py"].after_byte_count == 6
    assert by_path["README.md"].after_sha256 is None
    assert by_path["README.md"].kind == "documentation"
    assert by_path["src/main.py"].before_sha256 != by_path["src/main.py"].after_sha256
    assert by_path["tests/test_main.py"].kind == "test"


def test_rename_is_reported_as_removed_plus_added(tmp_path):
    root = _project(tmp_path)
    before = scan_sources(root)
    (root / "src" / "main.py").rename(root / "src" / "app.py")
    diff = compare_inventories(before, scan_sources(root))
    assert diff.removed == ["src/main.py"]
    assert diff.added == ["src/app.py"]
    assert diff.changed == []


def test_equal_hash_with_different_metadata_fails_closed():
    base = _file("a.py", "one\ntwo\n")
    for tampered in (
        base.model_copy(update={"line_count": 9}),
        base.model_copy(update={"byte_count": 99}),
        base.model_copy(update={"kind": "schema"}),
    ):
        with pytest.raises(ValueError, match="inconsistent inventory metadata"):
            compare_inventories(_inv([base]), _inv([tampered]))


def test_empty_inventories_on_one_or_both_sides():
    empty = _inv()
    both = compare_inventories(empty, empty)
    assert both.entries == [] and both.coverage == "comparable" and not both.requires_review
    one = compare_inventories(empty, _inv([_file("a.py")]))
    assert one.added == ["a.py"] and one.requires_review
    other = compare_inventories(_inv([_file("a.py")]), empty)
    assert other.removed == ["a.py"]


def test_changed_entry_keeps_path_derived_kind():
    diff = compare_inventories(
        _inv([_file("a.py", "1\n")]), _inv([_file("a.py", "2\n")]))
    assert diff.changed == ["a.py"] and diff.entries[0].kind == "source"


# ---- determinism ----------------------------------------------------------

def test_deterministic_and_input_order_independent(tmp_path):
    root = _project(tmp_path)
    before = scan_sources(root)
    (root / "src" / "z.py").write_text("z\n", encoding="utf-8")
    (root / "src" / "a.py").write_text("a\n", encoding="utf-8")
    after = scan_sources(root)
    first = compare_inventories(before, after)
    second = compare_inventories(
        SourceInventory.model_validate_json(before.model_dump_json()),
        SourceInventory.model_validate_json(after.model_dump_json()),
    )
    assert first.model_dump_json() == second.model_dump_json()
    assert render_inventory_diff_markdown(first) == render_inventory_diff_markdown(second)
    assert first.added == ["src/a.py", "src/z.py"]
    # input order independence: build with reversed file iteration
    shuffled = SourceInventory.model_construct(
        schema_version=1, files=list(reversed(after.files)),
        skipped_oversized=0, scope=after.scope, caveat=after.caveat,
    )
    third = compare_inventories(before, shuffled)
    assert third.model_dump_json() == first.model_dump_json()


def test_export_bytes_are_identical_across_runs(tmp_path):
    root = _project(tmp_path)
    before = scan_sources(root)
    (root / "src" / "n.py").write_text("n\n", encoding="utf-8")
    diff = compare_inventories(before, scan_sources(root))
    one = export_inventory_diff(diff, tmp_path / "o1")
    two = export_inventory_diff(diff, tmp_path / "o2")
    for name in one:
        assert one[name].read_bytes() == two[name].read_bytes()
    text = one["source-diff.json"].read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert str(tmp_path) not in text and str(tmp_path) not in one["source-diff.md"].read_text()


# ---- invalid inputs -------------------------------------------------------

@pytest.mark.parametrize("path", [
    "../a.py", "/abs/a.py", "a\\b.py", "src//a.py", "./a.py", ".hidden/a.py",
    "secrets/a.py", "token_store.py", "notes.txt", "", "a\x00.py",
])
def test_unsafe_paths_are_rejected_by_delta_and_inventory(path):
    with pytest.raises(ValidationError):
        SourceFileDelta(
            path=path, status="added", kind="source",
            after_sha256=_sha("x"), after_byte_count=1, after_line_count=1,
        )
    with pytest.raises(ValidationError):
        SourceInventory.model_validate({"files": [{
            "path": path, "sha256": _sha("x"), "byte_count": 1,
            "line_count": 1, "kind": "source"}]})


def test_duplicate_and_unsorted_inventory_paths_are_rejected():
    entry = {"sha256": _sha("x"), "byte_count": 1, "line_count": 1, "kind": "source"}
    with pytest.raises(ValidationError):
        SourceInventory.model_validate({"files": [
            {"path": "a.py", **entry}, {"path": "a.py", **entry}]})
    with pytest.raises(ValidationError):
        SourceInventory.model_validate({"files": [
            {"path": "b.py", **entry}, {"path": "a.py", **entry}]})


# ---- scope / coverage -----------------------------------------------------

def test_scope_unknown_when_either_or_both_missing():
    a, b = _inv(scope=None), _inv()
    both = compare_inventories(a, a)
    assert both.coverage == "scope_unknown" and both.requires_review
    assert "Neither" in both.coverage_notes[0]
    one = compare_inventories(a, b)
    assert one.coverage == "scope_unknown" and "before inventory records no scan scope" in one.coverage_notes[0]
    other = compare_inventories(b, a)
    assert other.coverage == "scope_unknown" and "after inventory records no scan scope" in other.coverage_notes[0]
    assert one.before_scope is None and one.after_scope is not None


def test_old_inventory_json_without_scope_loads_and_is_scope_unknown():
    legacy = json.loads(_inv([_file("a.py")]).model_dump_json())
    del legacy["scope"]
    old = SourceInventory.model_validate(legacy)
    assert old.scope is None
    assert compare_inventories(old, _inv([_file("a.py")])).coverage == "scope_unknown"


def test_policy_difference_is_scope_differs():
    diff = compare_inventories(_inv(), _inv(scope=_scope(policy="0" * 64)))
    assert diff.coverage == "scope_differs" and diff.requires_review
    assert any("policy differs" in n for n in diff.coverage_notes)


def test_max_file_bytes_difference_is_scope_differs():
    diff = compare_inventories(_inv(), _inv(scope=_scope(max_file_bytes=10)))
    assert diff.coverage == "scope_differs"
    assert any("size limit differs" in n for n in diff.coverage_notes)


def test_max_files_only_difference_stays_comparable_with_note():
    diff = compare_inventories(_inv(), _inv(scope=_scope(max_files=5)))
    assert diff.coverage == "comparable" and not diff.requires_review
    assert any("file-count limit differs" in n for n in diff.coverage_notes)


def test_max_files_limit_fails_closed_instead_of_truncating(tmp_path):
    root = _project(tmp_path)
    with pytest.raises(ValueError, match="file limit"):
        scan_sources(root, max_files=2)
    assert len(scan_sources(root, max_files=3).files) == 3


@pytest.mark.parametrize("side", ["before", "after"])
def test_oversized_skipped_on_either_side_requires_review(side):
    skipped, plain = _inv(skipped=2), _inv()
    pair = (skipped, plain) if side == "before" else (plain, skipped)
    diff = compare_inventories(*pair)
    assert diff.coverage == "comparable" and diff.requires_review
    assert getattr(diff, f"{side}_skipped_oversized") == 2
    assert any(f"The {side} inventory skipped 2 oversized" in n for n in diff.coverage_notes)


def test_file_growing_past_limit_shows_as_removed_and_requires_review(tmp_path):
    root = _project(tmp_path)
    before = scan_sources(root, max_bytes=100)
    (root / "src" / "main.py").write_text("x = 1\n" * 100, encoding="utf-8")
    after = scan_sources(root, max_bytes=100)
    assert after.skipped_oversized == 1
    diff = compare_inventories(before, after)
    assert diff.removed == ["src/main.py"] and diff.changed == []
    assert diff.coverage == "comparable" and diff.requires_review
    assert any("may only have crossed the size limit" in n for n in diff.coverage_notes)


def test_identity_note_is_always_present():
    for diff in (compare_inventories(_inv(), _inv()), compare_inventories(_inv(scope=None), _inv())):
        assert any("no project identity" in n for n in diff.coverage_notes)


# ---- privacy --------------------------------------------------------------

def test_secret_marker_files_never_appear(tmp_path):
    root = _project(tmp_path)
    before = scan_sources(root)
    (root / "private").mkdir()
    (root / "private" / "plan.py").write_text(SECRET_TEXT)
    (root / ".env").write_text(SECRET_TEXT)
    (root / "src" / "credentials.yml").write_text(SECRET_TEXT)
    (root / "src" / "new.py").write_text("ok = 1\n", encoding="utf-8")
    diff = compare_inventories(before, scan_sources(root))
    blob = diff.model_dump_json() + render_inventory_diff_markdown(diff)
    for marker in (SECRET_TEXT, ".env", "private/", "credentials"):
        assert marker not in blob
    assert diff.added == ["src/new.py"]


# ---- Markdown -------------------------------------------------------------

def test_markdown_structure_and_escaping():
    weird = "docs/a_b*c[d]e.md"
    changed_before = _file(weird, "1\n", "documentation")
    changed_after = _file(weird, "22\n", "documentation")
    diff = compare_inventories(
        _inv([changed_before, _file("gone.py"), _file("same.py")]),
        _inv([changed_after, _file("same.py"), _file("new.py")]),
    )
    md = render_inventory_diff_markdown(diff)
    assert md.startswith("# Source inventory comparison\n")
    assert md.endswith("\n") and not md.endswith("\n\n")
    assert "Metadata comparison only" in md and "not semantic or architectural verification" in md
    assert "docs/a\\_b\\*c\\[d\\]e.md" in md
    assert weird not in md
    assert "- Added: 1" in md and "- Removed: 1" in md
    assert "- Changed: 1" in md and "- Unchanged: 1" in md
    assert _file("new.py").sha256[:12] in md
    assert _file("new.py").sha256[:13] not in md
    assert "source-diff.json" in md
    assert "same.py" not in md  # unchanged files are counted, not listed
    assert md.count("## Added files") == md.count("## Removed files") == 1


def test_markdown_for_empty_diff_says_none():
    md = render_inventory_diff_markdown(compare_inventories(_inv(), _inv()))
    assert md.count("None.") == 3 and "Requires review: **no**" in md


# ---- export ---------------------------------------------------------------

def test_export_writes_exactly_two_files_to_new_directory(tmp_path):
    diff = compare_inventories(_inv(), _inv([_file("a.py")]))
    out = tmp_path / "nested" / "out"
    paths = export_inventory_diff(diff, out)
    assert set(paths) == {"source-diff.json", "source-diff.md"}
    assert sorted(p.name for p in out.iterdir()) == ["source-diff.json", "source-diff.md"]
    loaded = InventoryDiff.model_validate_json(paths["source-diff.json"].read_text())
    assert loaded == diff
    assert paths["source-diff.json"].read_text() == (
        json.dumps(diff.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    assert paths["source-diff.md"].read_text() == render_inventory_diff_markdown(diff)


def test_export_accepts_existing_empty_directory(tmp_path):
    out = tmp_path / "empty"
    out.mkdir()
    export_inventory_diff(compare_inventories(_inv(), _inv()), out)
    assert len(list(out.iterdir())) == 2


def test_export_refuses_unsafe_destinations_without_writing(tmp_path):
    diff = compare_inventories(_inv(), _inv())
    full = tmp_path / "full"
    full.mkdir()
    (full / "keep.txt").write_text("keep")
    with pytest.raises(ValueError):
        export_inventory_diff(diff, full)
    assert [p.name for p in full.iterdir()] == ["keep.txt"]

    file_dest = tmp_path / "file"
    file_dest.write_text("x")
    with pytest.raises(ValueError):
        export_inventory_diff(diff, file_dest)
    assert file_dest.read_text() == "x"

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        export_inventory_diff(diff, link)
    assert list(target.iterdir()) == []

    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "nowhere")
    with pytest.raises(ValueError):
        export_inventory_diff(diff, dangling)
    assert not (tmp_path / "nowhere").exists()


# ---- model validation -----------------------------------------------------

def _sample_diff() -> InventoryDiff:
    return compare_inventories(
        _inv([_file("a.py", "1\n"), _file("b.py"), _file("c.py")]),
        _inv([_file("a.py", "2\n"), _file("b.py"), _file("d.py")]),
    )


def test_diff_round_trips_through_json():
    diff = _sample_diff()
    assert InventoryDiff.model_validate_json(diff.model_dump_json()) == diff
    assert "requires_review" not in diff.model_dump()  # a property, not a field


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(added=[]),
    lambda d: d.update(removed=["a.py"]),
    lambda d: d.update(unchanged=["a.py", "b.py"]),
    lambda d: d.update(entries=list(reversed(d["entries"]))),
    lambda d: d.update(entries=d["entries"] + [d["entries"][0]]),
    lambda d: d.update(coverage="scope_unknown"),
    lambda d: d.update(unexpected=1),
    lambda d: d["entries"][0].update(status="unchanged"),
    lambda d: d["entries"][1].update(after_sha256=_sha("zz")),
])
def test_tampered_diffs_are_rejected(mutate):
    data = json.loads(_sample_diff().model_dump_json())
    mutate(data)
    with pytest.raises(ValidationError):
        InventoryDiff.model_validate(data)


def test_delta_status_consistency_validator():
    sha, other = _sha("a"), _sha("b")
    ok = dict(kind="source", before_sha256=sha, after_sha256=other,
              before_byte_count=1, after_byte_count=1, before_line_count=1, after_line_count=1)
    SourceFileDelta(path="a.py", status="changed", **ok)
    bad = [
        dict(status="added", **ok),
        dict(status="removed", **ok),
        dict(status="changed", **{**ok, "after_sha256": sha}),
        dict(status="unchanged", **ok),
        dict(status="changed", **{**ok, "after_sha256": None}),
        dict(status="unchanged", **{**ok, "after_sha256": sha, "after_byte_count": 2}),
        dict(status="added", kind="source"),
    ]
    for kwargs in bad:
        with pytest.raises(ValidationError):
            SourceFileDelta(path="a.py", **kwargs)
    with pytest.raises(ValidationError):
        SourceFileDelta(path="a.py", status="changed", **{**ok, "before_sha256": "ABC"})
    with pytest.raises(ValidationError):
        SourceFileDelta(path="a.py", status="changed", **{**ok, "before_byte_count": -1})


def test_requires_review_property_truth_table():
    clean = compare_inventories(_inv([_file("a.py")]), _inv([_file("a.py")]))
    assert not clean.requires_review
    assert compare_inventories(_inv(), _inv([_file("a.py")])).requires_review
    assert compare_inventories(_inv([_file("a.py")]), _inv()).requires_review
    assert compare_inventories(_inv([_file("a.py", "1")]), _inv([_file("a.py", "2")])).requires_review


def test_empty_inventory_is_called_out_in_notes():
    diff = compare_inventories(_inv(), _inv([_file("a.py")]))
    assert any("before inventory lists no files" in n for n in diff.coverage_notes)
    assert not any("after inventory lists no files" in n for n in diff.coverage_notes)
    both = compare_inventories(_inv(), _inv())
    assert sum("lists no files" in n for n in both.coverage_notes) == 2
