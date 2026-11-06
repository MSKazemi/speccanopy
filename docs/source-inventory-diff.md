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
| `--output DIR` | **New or empty** directory; an existing non-empty directory, a file or a symlink is refused and nothing is written |
| `--strict` | Exit `2` when the result requires review (see §5) |

Both inventories are validated with the same rules as everywhere else: canonical project-relative POSIX paths, sorted and unique, 64-character lowercase SHA-256 digests, no excluded/private paths. A hand-edited inventory whose digest matches but whose byte count, line count or kind disagrees is rejected as `inconsistent inventory metadata`.

Inventories written since this release record a **scan scope**: `max_files`, `max_file_bytes` and `policy_sha256` (a SHA-256 of Speccanopy's file allowlist and privacy-exclusion rules — not of any project file). Older inventories without `scope` still load; their coverage is reported as `scope_unknown`.

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

## 4. Output files

`out/demo-source-diff/` contains exactly two files:

| File | Content |
| --- | --- |
| `source-diff.json` | Machine-readable `InventoryDiff`: `entries` (every path from either side with `status`, `kind`, before/after SHA-256, byte and line counts), the sorted `added` / `removed` / `changed` / `unchanged` path lists, `coverage`, `coverage_notes`, both scopes, both skipped-oversized counts, `caveat`, `schema_version: 1`. Keys are sorted; identical inputs give byte-identical output. |
| `source-diff.md` | Readable report: caveat, coverage and notes, counts, tables of added/removed/changed files with 12-character hash prefixes and byte counts, and the number of unchanged files. All paths are Markdown-escaped. |

Neither file contains file contents, absolute host paths or timestamps.

### Status meanings

| Status | Meaning |
| --- | --- |
| `added` | Path is in AFTER but not BEFORE |
| `removed` | Path is in BEFORE but not AFTER |
| `changed` | Path is in both; SHA-256 differs, so the bytes differ |
| `unchanged` | Path is in both with an identical SHA-256, byte count and line count |

### Coverage meanings

| `coverage` | Meaning |
| --- | --- |
| `comparable` | Both inventories record the same per-file size limit and the same privacy/allowlist policy |
| `scope_differs` | The size limit or policy differs, so an added/removed file may reflect the scan rules rather than the project |
| `scope_unknown` | At least one inventory predates scope recording |

A different `--max-files` alone is noted but keeps `comparable`: `source-inventory` fails instead of truncating at the file limit, so a completed inventory lists every eligible file.

## 5. Exit codes

| Code | When |
| --- | --- |
| `0` | Diff written (with or without differences, unless `--strict`) |
| `1` | Missing/unreadable/malformed inventory, inconsistent inventory metadata, or unsafe/non-empty output. **Nothing is written.** |
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
| A file you renamed shows as `removed` + `added` | Expected: renames and moves are not detected. |

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
- **No rename or move detection;** no Git integration — inventories record neither a commit nor a project identity, so the tool cannot confirm both describe the same project.
- **No automatic documentation update or conflict detection.** Mapping changed files to affected architecture claims remains a human/Claude-assisted step.
- Language-independent: works for any allowlisted file kind, not only Python.
- Tested with synthetic temporary projects only (`tests/test_source_diff.py`, `tests/test_source_diff_cli.py`); no externally permissioned real-world application has been evaluated.
