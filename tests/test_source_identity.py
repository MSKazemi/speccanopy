"""Rename candidates in source-diff and optional git revision binding.

All projects and fake `.git` directories are synthetic temporary files. Identical
digests prove identical *bytes* only; nothing here asserts that a rename happened
or that an architecture is unchanged. No git executable is ever run.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.cli import main
from speccanopy.source_diff import (
    InventoryDiff, compare_inventories, export_inventory_diff,
    render_inventory_diff_markdown,
)
from speccanopy.source_evidence import (
    InventoryScope, SourceFile, SourceInventory, SourceRevision,
    inventory_policy_digest, read_git_revision, scan_sources,
)

C1 = "a" * 40
C2 = "b" * 40
C64 = "c" * 64


def _file(path: str, text: str = "x = 1\n", kind: str = "source") -> SourceFile:
    data = text.encode()
    return SourceFile(
        path=path, sha256=hashlib.sha256(data).hexdigest(), byte_count=len(data),
        line_count=len(data.splitlines()), kind=kind,
    )


def _inv(files=(), *, revision=None) -> SourceInventory:
    return SourceInventory(
        files=sorted(files, key=lambda f: f.path),
        scope=InventoryScope(max_files=2000, max_file_bytes=1_000_000,
                             policy_sha256=inventory_policy_digest()),
        revision=revision,
    )


def _rev(commit: str = C1, ref: str | None = "refs/heads/main") -> SourceRevision:
    return SourceRevision(status="recorded", commit=commit, ref=ref)


# ---- Part 1: rename candidates ---------------------------------------------

def test_identical_bytes_moved_is_paired_as_candidate_not_as_rename():
    before = _inv([_file("src/old_name.py", "def f():\n    return 1\n"), _file("keep.py")])
    after = _inv([_file("src/new_name.py", "def f():\n    return 1\n"), _file("keep.py")])
    diff = compare_inventories(before, after)
    # The existing lists and statuses are unchanged (backwards compatible).
    assert diff.removed == ["src/old_name.py"] and diff.added == ["src/new_name.py"]
    assert diff.unchanged == ["keep.py"] and diff.changed == []
    assert len(diff.rename_candidates) == 1
    cand = diff.rename_candidates[0]
    assert (cand.removed, cand.added) == ("src/old_name.py", "src/new_name.py")
    assert cand.sha256 == before.files[1].sha256 and cand.byte_count == 22
    assert "identical bytes" in cand.observation.lower()
    assert diff.ambiguous_rename_digests == []
    assert diff.requires_review


def test_candidates_sorted_and_deterministic():
    before = _inv([_file("b_old.py", "bb\n"), _file("a_old.py", "aa\n")])
    after = _inv([_file("z_new.py", "aa\n"), _file("y_new.py", "bb\n")])
    diff = compare_inventories(before, after)
    assert [(c.removed, c.added) for c in diff.rename_candidates] == [
        ("a_old.py", "z_new.py"), ("b_old.py", "y_new.py")]
    again = compare_inventories(before, after)
    assert json.dumps(diff.model_dump(mode="json")) == json.dumps(again.model_dump(mode="json"))


def test_two_removed_same_digest_is_ambiguous_not_paired():
    before = _inv([_file("one.py", "same\n"), _file("two.py", "same\n")])
    after = _inv([_file("moved.py", "same\n")])
    diff = compare_inventories(before, after)
    assert diff.rename_candidates == []
    assert len(diff.ambiguous_rename_digests) == 1
    group = diff.ambiguous_rename_digests[0]
    assert group.removed == ["one.py", "two.py"] and group.added == ["moved.py"]
    assert group.sha256 == before.files[0].sha256


def test_two_added_same_digest_is_ambiguous_not_paired():
    before = _inv([_file("orig.py", "same\n")])
    after = _inv([_file("copy_a.py", "same\n"), _file("copy_b.py", "same\n")])
    diff = compare_inventories(before, after)
    assert diff.rename_candidates == []
    group = diff.ambiguous_rename_digests[0]
    assert group.removed == ["orig.py"] and group.added == ["copy_a.py", "copy_b.py"]
    assert "ambiguous" in render_inventory_diff_markdown(diff).lower()


def test_rename_with_edit_is_not_paired():
    before = _inv([_file("old.py", "def f():\n    return 1\n")])
    after = _inv([_file("new.py", "def f():\n    return 2\n")])
    diff = compare_inventories(before, after)
    assert diff.removed == ["old.py"] and diff.added == ["new.py"]
    assert diff.rename_candidates == [] and diff.ambiguous_rename_digests == []


def test_empty_files_are_never_paired():
    before = _inv([_file("a/__init__.py", "")])
    after = _inv([_file("b/__init__.py", "")])
    diff = compare_inventories(before, after)
    assert diff.rename_candidates == []
    assert diff.ambiguous_rename_digests == []


def test_unrelated_digest_in_unchanged_file_flags_copy_possibility():
    before = _inv([_file("old.py", "dup\n"), _file("stays.py", "dup\n")])
    after = _inv([_file("new.py", "dup\n"), _file("stays.py", "dup\n")])
    cand = compare_inventories(before, after).rename_candidates[0]
    assert cand.digest_also_in_other_paths is True
    plain = compare_inventories(_inv([_file("old.py", "u\n")]), _inv([_file("new.py", "u\n")]))
    assert plain.rename_candidates[0].digest_also_in_other_paths is False


def test_equal_digest_inconsistent_metadata_fails_closed():
    good = _file("old.py", "same\n")
    bad = good.model_copy(update={"path": "new.py", "line_count": good.line_count + 3})
    with pytest.raises(ValueError, match="inconsistent inventory metadata"):
        compare_inventories(_inv([good]), _inv([bad]))


def test_markdown_possible_renames_section():
    diff = compare_inventories(_inv([_file("old.py", "q\n")]), _inv([_file("new.py", "q\n")]))
    md = render_inventory_diff_markdown(diff)
    assert "## Possible renames (identical bytes)" in md
    assert "`old.py`" in md or "old.py" in md
    assert "not asserted renames" in md.lower() or "not asserted" in md.lower()
    none = render_inventory_diff_markdown(compare_inventories(_inv([_file("a.py")]), _inv([_file("a.py")])))
    assert "## Possible renames (identical bytes)" in none and "No removed and added paths share identical bytes." in none


def test_validator_rejects_forged_candidates():
    diff = compare_inventories(_inv([_file("old.py", "q\n")]), _inv([_file("new.py", "q\n")]))
    data = diff.model_dump(mode="json")

    def forged(**changes) -> dict:
        d = json.loads(json.dumps(data))
        d["rename_candidates"][0].update(changes)
        return d

    InventoryDiff.model_validate(forged())  # control: untouched data is valid
    with pytest.raises(ValidationError):
        InventoryDiff.model_validate(forged(removed="ghost.py"))
    with pytest.raises(ValidationError):
        InventoryDiff.model_validate(forged(added="old.py"))
    with pytest.raises(ValidationError):
        InventoryDiff.model_validate(forged(sha256="0" * 64))
    with pytest.raises(ValidationError):
        InventoryDiff.model_validate(forged(byte_count=999))
    dup = json.loads(json.dumps(data))
    dup["rename_candidates"].append(dup["rename_candidates"][0])
    with pytest.raises(ValidationError):
        InventoryDiff.model_validate(dup)
    # Omitting candidates stays valid: diffs written before this feature never had them.
    omitted = json.loads(json.dumps(data))
    omitted["rename_candidates"] = []
    assert InventoryDiff.model_validate(omitted).rename_candidates == []
    ambiguous = json.loads(json.dumps(data))
    ambiguous["ambiguous_rename_digests"] = [{
        "sha256": data["rename_candidates"][0]["sha256"],
        "removed": ["old.py"], "added": ["new.py"]}]
    with pytest.raises(ValidationError):
        InventoryDiff.model_validate(ambiguous)  # a 1:1 group is not ambiguous


# ---- back-compat -----------------------------------------------------------

# Produced by the code at e648df2 (before this change) from two synthetic files.
OLD_INVENTORY = {
    "caveat": "Metadata only. Files excluded by privacy filters or size limits are not "
              "inventoried. File hashes do not establish architecture semantics or "
              "guarantee absence of secrets in allowed source files.",
    "files": [
        {"byte_count": 4, "kind": "source", "line_count": 1, "path": "a.py",
         "sha256": "98752ee28d5484bdc2814fb70adb6a0b2fb31f6a9b8ee7ae81fd2fc9cf300b3b"},
        {"byte_count": 4, "kind": "source", "line_count": 1, "path": "b.py",
         "sha256": "8d4fcaba37762a136956fa1c4d68af2caef50ccdbc0ebe930b05168657afbe29"},
    ],
    "schema_version": 1,
    "scope": {"max_file_bytes": 1000000, "max_files": 2000,
              "policy_sha256": "caee91336f6ff03912e5005441f12756415b3c2ff65e75cad0c81a6acd382a9a"},
    "skipped_oversized": 0,
}
OLD_DIFF = {
    "added": ["c.py"], "removed": [], "changed": [], "unchanged": ["a.py", "b.py"],
    "after_scope": OLD_INVENTORY["scope"], "before_scope": OLD_INVENTORY["scope"],
    "after_skipped_oversized": 0, "before_skipped_oversized": 0,
    "caveat": "This compares metadata-only snapshots.",
    "coverage": "comparable",
    "coverage_notes": ["Inventories record no project identity; this comparison cannot "
                       "verify that both inventories describe the same project."],
    "entries": [
        {"after_byte_count": 4, "after_line_count": 1, "path": "a.py", "status": "unchanged",
         "after_sha256": "98752ee28d5484bdc2814fb70adb6a0b2fb31f6a9b8ee7ae81fd2fc9cf300b3b",
         "before_byte_count": 4, "before_line_count": 1, "kind": "source",
         "before_sha256": "98752ee28d5484bdc2814fb70adb6a0b2fb31f6a9b8ee7ae81fd2fc9cf300b3b"},
        {"after_byte_count": 4, "after_line_count": 1, "path": "b.py", "status": "unchanged",
         "after_sha256": "8d4fcaba37762a136956fa1c4d68af2caef50ccdbc0ebe930b05168657afbe29",
         "before_byte_count": 4, "before_line_count": 1, "kind": "source",
         "before_sha256": "8d4fcaba37762a136956fa1c4d68af2caef50ccdbc0ebe930b05168657afbe29"},
        {"after_byte_count": 4, "after_line_count": 1, "path": "c.py", "status": "added",
         "after_sha256": "06e14e72c627e4c283ee89728dca4bf0e6ff1c6172495895633e62503c9ae421",
         "before_byte_count": None, "before_line_count": None, "kind": "source",
         "before_sha256": None},
    ],
    "schema_version": 1,
}


def test_pre_change_inventory_and_diff_json_still_load():
    inv = SourceInventory.model_validate(OLD_INVENTORY)
    assert inv.revision is None
    diff = InventoryDiff.model_validate(OLD_DIFF)
    assert diff.rename_candidates == [] and diff.ambiguous_rename_digests == []
    assert diff.before_revision is None and diff.after_revision is None
    # A pre-change inventory compared with itself still works and notes the missing revision.
    again = compare_inventories(inv, inv)
    assert again.unchanged == ["a.py", "b.py"]
    assert any("no project revision" in n for n in again.coverage_notes)


# ---- Part 2: revision model ------------------------------------------------

def test_revision_model_validation():
    assert _rev(C64, None).commit == C64
    for bad in ("g" * 40, "A" * 40, "a" * 39, "a" * 41, "", "../" + "a" * 37):
        with pytest.raises(ValidationError):
            SourceRevision(status="recorded", commit=bad)
    with pytest.raises(ValidationError):
        SourceRevision(status="recorded")  # recorded needs a commit
    with pytest.raises(ValidationError):
        SourceRevision(status="unknown", commit=C1, reason="x")
    with pytest.raises(ValidationError):
        SourceRevision(status="unknown")  # unknown needs a reason
    for bad_ref in ("main", "refs/heads/../x", "refs//x", "/abs/path", "refs/heads/a b",
                    "refs/heads/x.lock", "https://example.com/r.git"):
        with pytest.raises(ValidationError):
            SourceRevision(status="recorded", commit=C1, ref=bad_ref)
    assert "clean" in _rev().caveat.lower() and "dirty" in _rev().caveat.lower()


# ---- Part 2: reading a fake .git -------------------------------------------

def _repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "proj"
    git = root / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    return root, git


def test_branch_ref_loose(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("ref: refs/heads/feature/x\n")
    (git / "refs" / "heads" / "feature").mkdir()
    (git / "refs" / "heads" / "feature" / "x").write_text(C1 + "\n")
    rev = read_git_revision(root)
    assert (rev.status, rev.commit, rev.ref) == ("recorded", C1, "refs/heads/feature/x")


def test_branch_ref_via_packed_refs_and_loose_takes_precedence(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted \n"
        f"{C2} refs/heads/other\n{C1} refs/heads/main\n^{'d' * 40}\n")
    rev = read_git_revision(root)
    assert (rev.status, rev.commit, rev.ref) == ("recorded", C1, "refs/heads/main")
    (git / "refs" / "heads" / "main").write_text(C2 + "\n")
    assert read_git_revision(root).commit == C2


def test_detached_head_sha1_and_sha256(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text(C1 + "\n")
    rev = read_git_revision(root)
    assert (rev.status, rev.commit, rev.ref) == ("recorded", C1, None)
    (git / "HEAD").write_text(C64 + "\n")
    assert read_git_revision(root).commit == C64


def test_unborn_branch_unknown(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    rev = read_git_revision(root)
    assert rev.status == "unknown" and rev.commit is None and rev.reason


@pytest.mark.parametrize("head", [
    "g" * 40 + "\n", "a" * 39 + "\n", "A" * 40 + "\n", "ref: refs/heads/../../etc/passwd\n",
    "ref: heads/main\n", "ref: refs/heads/a b\n", "garbage\n", "", "\xff\xfe\n",
])
def test_malformed_head_rejected(tmp_path, head):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_bytes(head.encode("latin-1"))
    rev = read_git_revision(root)
    assert rev.status == "unknown" and rev.commit is None and rev.ref is None
    assert head.strip() not in (rev.reason or "") or head.strip() == ""


def test_malformed_loose_ref_does_not_fall_through_to_packed(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text("not-a-hash\n")
    (git / "packed-refs").write_text(f"{C1} refs/heads/main\n")
    assert read_git_revision(root).status == "unknown"


def test_malformed_packed_hash_rejected(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "packed-refs").write_text(f"{'z' * 40} refs/heads/main\n")
    assert read_git_revision(root).status == "unknown"


def test_symlinked_dotgit_refused_and_not_followed(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text(C1 + "\n")
    real = tmp_path / "elsewhere"
    git.rename(real)
    git.symlink_to(real, target_is_directory=True)
    rev = read_git_revision(root)
    assert rev.status == "unknown" and "symbolic link" in rev.reason
    assert str(tmp_path) not in (rev.reason or "")


def test_symlinked_head_and_ref_refused(tmp_path):
    root, git = _repo(tmp_path)
    outside = tmp_path / "outside-head"
    outside.write_text(C1 + "\n")
    (git / "HEAD").symlink_to(outside)
    assert read_git_revision(root).status == "unknown"
    (git / "HEAD").unlink()
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").symlink_to(outside)
    assert read_git_revision(root).status == "unknown"


def test_symlinked_refs_directory_refused(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    other = tmp_path / "otherheads"
    other.mkdir()
    (other / "main").write_text(C1 + "\n")
    (git / "refs" / "heads").rmdir()
    (git / "refs" / "heads").symlink_to(other, target_is_directory=True)
    assert read_git_revision(root).status == "unknown"


def test_gitdir_file_is_unknown_and_not_followed(tmp_path):
    root = tmp_path / "wt"
    root.mkdir()
    real = tmp_path / "main-repo" / ".git" / "worktrees" / "wt"
    real.mkdir(parents=True)
    (real / "HEAD").write_text(C1 + "\n")
    (root / ".git").write_text(f"gitdir: {real}\n")
    rev = read_git_revision(root)
    assert rev.status == "unknown" and rev.commit is None
    assert "gitdir" in rev.reason and str(tmp_path) not in rev.reason


def test_missing_dotgit_unknown(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    rev = read_git_revision(root)
    assert rev.status == "unknown" and ".git" in rev.reason


def test_oversized_head_rejected(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("a" * 100_000)
    assert read_git_revision(root).status == "unknown"


def test_remote_urls_users_and_paths_never_recorded(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text(C1 + "\n")
    (git / "config").write_text(
        '[remote "origin"]\n\turl = https://user:pw@example.com/org/repo.git\n'
        "[user]\n\tname = Secret Person\n\temail = secret@example.com\n")
    inv = scan_sources(root, record_revision=True)
    text = json.dumps(inv.model_dump(mode="json"))
    for needle in ("example.com", "Secret Person", "secret@", "pw@", str(tmp_path), "proj/", "/proj"):
        assert needle not in text
    assert inv.revision.commit == C1


# ---- scan_sources / CLI ----------------------------------------------------

def test_scan_sources_default_records_no_revision_and_is_deterministic(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text(C1 + "\n")
    assert scan_sources(root).revision is None
    a = scan_sources(root, record_revision=True)
    b = scan_sources(root, record_revision=True)
    assert a.model_dump_json() == b.model_dump_json()
    assert [f.path for f in a.files] == ["app.py"]  # .git stays excluded from files


def test_cli_record_git_revision(tmp_path, capsys):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text(C1 + "\n")
    plain = tmp_path / "plain.json"
    rec = tmp_path / "rec.json"
    assert main(["source-inventory", str(root), "--output", str(plain)]) == 0
    assert json.loads(plain.read_text())["revision"] is None
    capsys.readouterr()
    assert main(["source-inventory", str(root), "--output", str(rec), "--record-git-revision"]) == 0
    out = capsys.readouterr().out
    assert C1[:12] in out and "not recorded" in out.lower() and str(tmp_path / "proj") not in out.split("Artifact:")[0]
    data = json.loads(rec.read_text())
    assert data["revision"]["commit"] == C1 and data["revision"]["ref"] == "refs/heads/main"
    assert str(tmp_path) not in rec.read_text()


def test_cli_record_git_revision_unknown_still_succeeds(tmp_path, capsys):
    root = tmp_path / "nogit"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    out = tmp_path / "inv.json"
    assert main(["source-inventory", str(root), "--output", str(out), "--record-git-revision"]) == 0
    assert json.loads(out.read_text())["revision"]["status"] == "unknown"
    assert "unknown" in capsys.readouterr().out.lower()


# ---- source-diff and revisions ----------------------------------------------

def test_equal_commit_but_different_files_notes_uncommitted_changes():
    before = _inv([_file("a.py", "1\n")], revision=_rev(C1))
    after = _inv([_file("a.py", "2\n")], revision=_rev(C1))
    diff = compare_inventories(before, after)
    assert diff.before_revision == before.revision and diff.after_revision == after.revision
    note = next(n for n in diff.coverage_notes if "same commit" in n.lower())
    assert C1[:12] in note and "uncommitted" in note.lower()
    md = render_inventory_diff_markdown(diff)
    assert "## Project revisions" in md and C1[:12] in md and "refs/heads/main" in md
    assert diff.changed == ["a.py"] and diff.coverage == "comparable"


def test_equal_commit_and_identical_files_has_no_uncommitted_warning():
    both = _inv([_file("a.py")], revision=_rev(C1))
    diff = compare_inventories(both, both)
    assert not any("uncommitted" in n.lower() for n in diff.coverage_notes)
    assert not diff.requires_review


def test_different_commits_shown_and_never_fail_closed():
    before = _inv([_file("a.py", "1\n")], revision=_rev(C1))
    after = _inv([_file("a.py", "2\n")], revision=_rev(C2, None))
    diff = compare_inventories(before, after)
    assert any(C1[:12] in n and C2[:12] in n for n in diff.coverage_notes)
    assert not any("uncommitted" in n.lower() for n in diff.coverage_notes)
    identical_files = compare_inventories(
        _inv([_file("a.py")], revision=_rev(C1)), _inv([_file("a.py")], revision=_rev(C2)))
    assert not identical_files.requires_review  # revisions alone never force review


@pytest.mark.parametrize("which", ["before", "after", "both"])
def test_missing_revision_noted(which):
    rev = _rev()
    b = _inv([_file("a.py")], revision=None if which in ("before", "both") else rev)
    a = _inv([_file("a.py")], revision=None if which in ("after", "both") else rev)
    diff = compare_inventories(b, a)
    notes = [n for n in diff.coverage_notes if "no project revision" in n]
    assert len(notes) == 1
    if which == "both":
        assert "neither" in notes[0].lower()
    else:
        assert which in notes[0].lower()


def test_unknown_revision_reason_surfaces_in_notes_and_markdown():
    unk = SourceRevision(status="unknown", reason="the .git entry is a gitdir pointer file; not followed")
    diff = compare_inventories(_inv([_file("a.py")], revision=unk), _inv([_file("a.py")], revision=_rev()))
    assert any("gitdir pointer" in n for n in diff.coverage_notes)
    assert "gitdir pointer" in render_inventory_diff_markdown(diff)


def test_identity_note_still_always_present_with_revisions():
    inv = _inv([_file("a.py")], revision=_rev())
    diff = compare_inventories(inv, inv)
    assert any("no project identity" in n for n in diff.coverage_notes)


def test_export_roundtrip_and_no_absolute_path_leak(tmp_path):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text(C1 + "\n")
    before = scan_sources(root, record_revision=True)
    (root / "moved.py").write_text("x = 1\n", encoding="utf-8")
    (root / "app.py").unlink()
    after = scan_sources(root, record_revision=True)
    diff = compare_inventories(before, after)
    assert [(c.removed, c.added) for c in diff.rename_candidates] == [("app.py", "moved.py")]
    paths = export_inventory_diff(diff, tmp_path / "out")
    for p in paths.values():
        assert str(tmp_path) not in p.read_text()
    assert InventoryDiff.model_validate_json(paths["source-diff.json"].read_text()) == diff
    again = export_inventory_diff(diff, tmp_path / "out2")
    assert again["source-diff.json"].read_bytes() == paths["source-diff.json"].read_bytes()
    assert again["source-diff.md"].read_bytes() == paths["source-diff.md"].read_bytes()


def test_cli_source_diff_end_to_end_shows_rename_and_revisions(tmp_path, capsys):
    root, git = _repo(tmp_path)
    (git / "HEAD").write_text(C1 + "\n")
    b = tmp_path / "b.json"
    a = tmp_path / "a.json"
    assert main(["source-inventory", str(root), "--output", str(b), "--record-git-revision"]) == 0
    (root / "app.py").rename(root / "renamed.py")
    assert main(["source-inventory", str(root), "--output", str(a), "--record-git-revision"]) == 0
    capsys.readouterr()
    assert main(["source-diff", str(b), str(a), "--output", str(tmp_path / "d")]) == 0
    md = (tmp_path / "d" / "source-diff.md").read_text()
    assert "Possible renames (identical bytes)" in md and "renamed.py" in md
    assert "uncommitted" in md.lower()
