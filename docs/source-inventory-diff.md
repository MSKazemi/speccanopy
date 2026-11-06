# Compare source inventories — `speccanopy source-diff`

**Issue #5 slice (2026-11-06).** `speccanopy source-diff` compares two existing `source-inventory.json` snapshots of the **same authorized local project** and reports which allowlisted files were **added, removed, changed or unchanged**. It answers "which files' bytes differ between these two snapshots?" — nothing more. It is **not** semantic code analysis, does **not** decide whether the architecture changed, and does **not** update or overwrite any documentation.

Use it when an application has changed since you generated its architecture documentation, to find out which files you need to re-inspect, which source claims may be stale, and which new files are not covered by any claim yet.

## 1. Prerequisites

- Python 3.11+ and Speccanopy installed from the repository root: `python -m pip install -e '.[dev]'`.
- Two inventories produced by `speccanopy source-inventory` (or by `speccanopy project-intake`, which writes `source-inventory.json`). The command never rescans or reads the project itself — it only reads the two JSON files.
- No network access, model API key or Claude account is needed. With Claude Code, the commands below run under your normal subscription session; they make no Anthropic API calls.

## 2. Input

| Argument | Meaning |
| --- | --- |
| `BEFORE` | Earlier inventory JSON (positional) |
| `AFTER` | Later inventory JSON (positional) |
| `--output DIR` | **New or empty** directory; an existing non-empty directory, a file or a symlink is refused before anything is written (best-effort: the final path component is checked for a symlink) |
| `--strict` | Exit `2` when the result requires review (see §5) |

Both inventories are validated with the same rules as everywhere else: canonical project-relative POSIX paths, sorted and unique, 64-character lowercase SHA-256 digests, no excluded/private paths. A hand-edited inventory whose digest matches but whose byte count, line count or kind disagrees is rejected as `inconsistent inventory metadata`.

Inventories written since this release record a **scan scope**: `max_files`, `max_file_bytes` and `policy_sha256` (a SHA-256 of Speccanopy's file allowlist and privacy-exclusion rules — not of any project file). Older inventories without `scope` still load; their coverage is reported as `scope_unknown`. An inventory whose files exceed its own recorded scope (more files than `max_files`, or a file larger than `max_file_bytes`) is rejected as edited or corrupt.

## 3. Copyable walkthrough

This complete example creates a throwaway synthetic project, so it is safe to run as-is from any empty working folder. It was run verbatim for this guide; the output shown is the real output.

```bash
mkdir -p demo-app/src/demo
printf 'def handler():\n    return "v1"\n' > demo-app/src/demo/api.py
printf 'ROWS = []\n' > demo-app/src/demo/store.py
printf '# Demo app\n' > demo-app/README.md

speccanopy source-inventory demo-app --output out/demo-inputs/inventory-v1.json

# ... the application changes ...
printf 'def handler():\n    return "v2"\n' > demo-app/src/demo/api.py
rm demo-app/src/demo/store.py
printf 'JOBS = []\n' > demo-app/src/demo/queue.py

speccanopy source-inventory demo-app --output out/demo-inputs/inventory-v2.json

speccanopy source-diff out/demo-inputs/inventory-v1.json out/demo-inputs/inventory-v2.json \
  --output out/demo-source-diff
```

Output of the last command (exit code `0`):

```text
Source diff: 1 added, 1 removed, 1 changed, 1 unchanged
Coverage: comparable; requires review: yes
Byte-level metadata comparison only; not semantic or architectural verification
Artifacts: out/demo-source-diff/source-diff.json, out/demo-source-diff/source-diff.md
```

For a real project, replace `demo-app` with your authorized application folder (for example `~/projects/my-app`) and keep the inventories in Speccanopy's ignored `out/` directory or another private location — file **names** alone can be sensitive.

To gate a script or CI job on any difference, add `--strict` (exit `2` above). Re-running into the same `--output` exits `1`:

```text
Error comparing source inventories: Source diff output must be a new or empty directory; existing files not overwritten
```

### Optional revision binding and rename observations (Issue #5)

Two additions close earlier limits; both are **optional and backwards compatible** (older inventories and diffs still load; the new fields default to "absent"/empty):

- **`source-inventory --record-git-revision`** also records the project's commit and branch ref in the inventory (`"revision": {"status": "recorded", "commit": "<40 or 64 hex>", "ref": "refs/heads/main", ...}`). It reads `<project>/.git/HEAD` and the matching `refs/heads/...` file or `packed-refs` **directly as files**: no `git` executable is run, nothing is fetched, no remote URL, user name, e-mail or absolute path is recorded. If `.git` is a symbolic link, is a file (a worktree or submodule `gitdir:` pointer), is missing, or holds malformed content, the inventory records `"status": "unknown"` with a short generic reason instead of following anything; the scan itself still succeeds. A **branch name is recorded** (it can be sensitive; keep inventories private). Without the flag, `"revision"` is `null`.
- **Rename candidates.** `source-diff` lists, in `rename_candidates`, each removed path paired with an added path that has the **identical SHA-256 and byte size**. This is a labelled observation ("identical bytes moved"), not an asserted rename; the `added` / `removed` lists and statuses are unchanged, so a claim citing the old path is still reported as removed by `source-impact`.

## 4. Output files

`out/demo-source-diff/` contains exactly two files:

| File | Content |
| --- | --- |
| `source-diff.json` | Machine-readable `InventoryDiff`: `entries` (every path from either side with `status`, `kind`, before/after SHA-256, byte and line counts), the sorted `added` / `removed` / `changed` / `unchanged` path lists, `coverage`, `coverage_notes`, both scopes, both skipped-oversized counts, `before_revision` / `after_revision` (or `null`), `rename_candidates`, `ambiguous_rename_digests`, `caveat`, `schema_version: 1`. Keys are sorted; identical inputs give byte-identical output. |
| `source-diff.md` | Readable report: caveat, coverage and notes, counts, a "Project revisions" section, tables of added/removed files, a "Possible renames (identical bytes)" section, changed files with 12-character hash prefixes and byte counts, and the number of unchanged files. All paths are Markdown-escaped. |

Neither file contains file contents, absolute host paths or timestamps.

### Status meanings

| Status | Meaning |
| --- | --- |
| `added` | Path is in AFTER but not BEFORE |
| `removed` | Path is in BEFORE but not AFTER |
| `changed` | Path is in both; SHA-256 differs, so the bytes differ |
| `unchanged` | Path is in both with an identical SHA-256, byte count and line count |

### Rename candidates

| Situation | Reported as |
| --- | --- |
| One removed and one added path share a SHA-256 (and byte size) | One `rename_candidates` entry: `removed`, `added`, `sha256`, `byte_count`, `line_count`, both kinds, `observation` text and `digest_also_in_other_paths` (`true` when another path in either inventory has the same bytes, so the file may have been **copied** rather than moved) |
| More than one removed **or** more than one added path share a digest | **Not paired.** Listed in `ambiguous_rename_digests` (`sha256`, `removed` paths, `added` paths) so you can decide manually |
| Moved **and** edited | Not detected: the digest changed, so it stays one `removed` plus one `added` |
| Zero-byte files | Never paired (empty content does not identify a file) |

Equal digests but different byte or line counts across a removed/added pair are treated as a corrupt inventory and fail closed (`inconsistent inventory metadata`). A loaded `source-diff.json` is validated: every candidate must reference real removed/added entries whose digest, size and kinds match, and a digest listed as ambiguous must match the entries exactly. Candidates never affect `requires_review`.

### Revisions in the comparison

When an inventory carries a revision, `source-diff` shows both revisions in the report and adds coverage notes:

- **Same commit but different files:** noted as a hint of uncommitted working-tree changes (or a different tree at one scan). The working-tree state itself is **not recorded**; the file digests are the content binding.
- **Different commits:** shown; differing files are expected.
- **Either revision missing or `unknown`:** noted (with the generic reason for `unknown`).

Revisions never change `coverage`, never trigger `--strict` exit `2` by themselves and never make the comparison fail. A commit is an unauthenticated hint read from files; it is **not proof** that two inventories describe the same project, so the "no project identity" note stays.

### Coverage meanings

| `coverage` | Meaning |
| --- | --- |
| `comparable` | Both inventories record the same per-file size limit and the same privacy/allowlist policy |
| `scope_differs` | The size limit or policy differs, so an added/removed file may reflect the scan rules rather than the project |
| `scope_unknown` | At least one inventory predates scope recording |

An inventory with **no files** gets a note asking you to check the project root and exclusions; an empty-versus-empty comparison is otherwise `comparable` and does not require review. A different `--max-files` alone is noted but keeps `comparable`: `source-inventory` fails instead of truncating at the file limit, so a completed inventory lists every eligible file.

## 5. Exit codes

| Code | When |
| --- | --- |
| `0` | Diff written (with or without differences, unless `--strict`) |
| `1` | Missing/unreadable/malformed inventory, inconsistent inventory metadata, or unsafe/non-empty output. These are detected **before anything is written**; only an operating-system failure in the middle of writing (such as a full disk) could leave a partial folder. |
| `2` | Only with `--strict`: diff written and it **requires review** — any file added, removed or changed, coverage not `comparable`, or either inventory skipped oversized files |

## 6. Troubleshooting

| Message / symptom | Fix |
| --- | --- |
| `existing files not overwritten` | Choose a new `--output` directory, e.g. `out/demo-source-diff-2`. Speccanopy never replaces existing reports. |
| `inconsistent inventory metadata for '<path>'` | One inventory was edited by hand or corrupted. Regenerate it with `source-inventory`. |
| `Source inventory paths must be unique and sorted` / validation errors | The file is not a valid Speccanopy inventory; regenerate it rather than editing JSON. |
| `Coverage: scope_unknown` | One inventory was made before scope recording. Re-inventory both snapshots with the current version if you still have both project states (for example in two Git checkouts). |
| `Coverage: scope_differs` | Re-run `source-inventory` for both states with the same `--max-file-bytes`, using the same Speccanopy version. |
| A file you edited is listed as `removed` | It may have grown past `--max-file-bytes`; check the skipped-oversized note in the report. |
| A file you renamed shows as `removed` + `added` | Expected; if the bytes are identical it also appears under "Possible renames (identical bytes)". A rename with edits is not detected. |
| `revision` is `unknown` | `.git` is missing, a symlink, a `gitdir:` pointer file (linked worktree/submodule) or malformed. These are deliberately not followed; scan from the main checkout, or accept that no revision is recorded. |

## 7. Use with source evidence and documentation

The diff covers the **whole inventory**, including files that no source claim cites — this complements `speccanopy document --source-root ... --source-evidence ...`, which only checks the files cited in `source-evidence.json` ([source evidence workflow](source-evidence-workflow.md)). A practical update loop:

1. Keep the inventory from the time the documentation was generated (for Python intake: `<intake-output>/source-inventory.json`).
2. After the application changes, create a new inventory and run `source-diff`.
3. Re-run `speccanopy document` with the **old** `source-evidence.json` and a **new empty** output folder; cited files appear as `changed` or `missing`.
4. Inspect `changed` and `added` files, update the brief/design/evidence map with the owner's approval, then regenerate into a new folder. Speccanopy never edits existing documentation for you.

With Claude Code you can ask: *"Run `speccanopy source-diff` on these two inventories, then inspect only the added and changed allowlisted files I authorize and tell me which architecture claims or components may be affected. Do not edit my documentation or source code."* Claude's interpretation is an AI-assisted reading, not verification.

## 8. Supported scope and limitations

- **Byte equality only.** `changed` means different bytes — a whitespace edit and a redesign look the same. `unchanged` means identical bytes, not that behaviour or deployment is unchanged.
- **Invisible to the diff:** files excluded by the privacy filters, the extension allowlist, symlinks, oversized files, and file mode/owner/timestamp changes.
- **Renames are observations only.** Identical bytes at a removed and an added path are paired as candidates; ambiguous digests, zero-byte files, and rename-with-edit are not paired. Nothing is asserted as a rename.
- **Revision binding is optional, unauthenticated and file-based.** With `--record-git-revision` the inventory carries a commit/ref read from `.git` files (no git is run; linked worktrees, symlinks and malformed data give `unknown`). Dirty/clean working-tree state is not recorded, remote and user identity are not recorded, and a commit hint is not proof that two inventories describe the same project.
- `requires_review` is reported on stdout and through the `--strict` exit code; it is not stored as a field in `source-diff.json` (scripts can recompute it from `added`/`removed`/`changed`, `coverage` and the skipped-oversized counts, or use `--strict`).
- **No automatic documentation update or conflict detection.** Mapping changed files to affected architecture claims remains a human/Claude-assisted step.
- Language-independent: works for any allowlisted file kind, not only Python.
- Tested with synthetic temporary projects and fake `.git` directories only (`tests/test_source_diff.py`, `tests/test_source_diff_cli.py`, `tests/test_source_identity.py`); no externally permissioned real-world application has been evaluated.
