# Source inventory and source-linked architecture documentation

**Phase 9 prototype / Issue #5:** Speccanopy can inventory selected local project files and check **file snapshot provenance** for authored architecture claims. This is a privacy-conscious *metadata* and *change-detection* workflow, **not automatic code understanding** and **not architecture certification**.

Use the existing Claude Code subscription to inspect authorized project sources and author a draft `SystemBrief`, `FixtureDesign` and `SourceEvidence` map. The local Speccanopy commands do **not** call Anthropic's Messages API.

## Python shortcut: generate the source map from AST syntax

For supported Python projects, `speccanopy project-intake` drafts `brief.json`, `design.json`, `source-inventory.json`, `source-evidence.json`, `module-observations.json` and `intake-review.md` using bounded offline Python AST inspection and **your supplied real requirements**:

```bash
speccanopy project-intake ~/projects/my-app \
  --system "My App" \
  --goal "Document the current Python architecture" \
  --requirement "Users can create records" \
  --output out/my-app-inputs
```

Automatically generated source claims attest only to **Python module existence and import syntax**. They do NOT establish that user requirements are met. Read the [Python project intake guide](python-project-intake.md) for the complete workflow. The manual/Claude-guided mapping below remains appropriate for other languages and detailed claims.

## Input and output

**Input:** an authorized local application repository, a generated `architecture.json`, and optionally a human/Claude-authored evidence mapping from architecture IDs to source files.

**Output:** a metadata-only `source-inventory.json` and, when evidence is supplied, an additional `source-evidence.md` in your architecture-documentation pack.

### 1. Inventory permitted project files

From the Speccanopy repository:

```bash
speccanopy source-inventory ~/projects/my-app \
  --output out/myproject-inputs/source-inventory.json
```

The JSON inventory contains sorted, **project-relative** filenames, SHA-256 digests, byte counts, line counts, and coarse kinds (source, test, documentation, configuration, schema). **No file contents or absolute local paths are exported.** However, the command *reads* the selected files locally to calculate their digests, and filenames themselves may reveal private details.

The scanner skips symlinks, dot/hidden paths, common dependency/build/private folders, sensitive-looking names, non-allowlisted extensions, and oversized files. A narrow set of JSON filenames is included (such as `package.json`, not arbitrary data/credential JSON). The exclusions are **best-effort** and do not replace explicit authorization or confidentiality review. The tool does not parse `.gitignore`, copy source text, execute code, or transmit anything to a model.

Defaults: at most **2,000** allowlisted files, at most **1,000,000 bytes** per file; use `--max-files` (up to 10,000) and `--max-file-bytes` (up to 5,000,000) when authorized. Large files are skipped with a count. The scanner fails on an excessive file count rather than silently truncating selected file records. The output file must be **new**.

Each inventory also records its **scan scope** — `"scope": {"max_files": …, "max_file_bytes": …, "policy_sha256": …}` — where `policy_sha256` fingerprints Speccanopy's allowlist and privacy-exclusion rules (not any project file). It contains no host path. `speccanopy source-diff` uses it to warn when two inventories were taken under different rules. Inventories made before this field existed still load, with `scope` treated as unknown.

### 2. Link source snapshots to architecture claims

Ask Claude Code to inspect the source inventory and **the specific application source paths you authorize**. Ask it to create `out/myproject-inputs/source-evidence.json` in this strict format:

```json
{
  "schema_version": 1,
  "claims": [
    {
      "architecture_id": "FR-001",
      "source_path": "src/main.py",
      "sha256": "<REPLACE_WITH_64_CHARACTER_HASH_FROM_INVENTORY>",
      "assertion": "The observed CLI entrypoint dispatches the requested operation",
      "basis": "observed",
      "line_start": 10,
      "line_end": 22
    }
  ]
}
```

This example is **illustrative and invalid until the hash, paths, IDs and line range are replaced** with real values. The `sha256` field must be exactly 64 lowercase hexadecimal characters, taken from the inventory for that file snapshot.

- `architecture_id` must match a real functional/quality requirement ID, component ID, relationship, ADR, finding or verification-case ID in the generated `ArchitectureSpec`.
- `source_path` must be a canonical POSIX path *relative to the same application root*. Absolute paths, traversal, excluded secrets/private directories and disallowed file types are rejected.
- `basis` is an **authored label**: `observed`, `inferred`, or `proposed`. An AI calling something "observed" is **not independent proof** that it interpreted the code correctly.
- The optional `line_start` and `line_end` must both be supplied and form a valid positive range. Omit both if no stable lines apply.
- The `assertion` is a concise, source-specific explanation of what the file is believed to show. **Do not copy secrets, customer data, or code contents** into assertions.
- An empty `claims: []` is allowed; it reports all mandatory requirements and components as having no observed source link. Unsupported claims are **never silently credited**.

Store these JSON files under Speccanopy's `out/` directory or another approved private workspace; the repository ignores `out/` by default. Review file names and claims before publishing anything.

### 3. Generate a source-aware documentation pack

First run `speccanopy design` and optionally `speccanopy review` to generate a current architecture. Then:

```bash
speccanopy document out/myproject/architecture.json \
  --review out/myproject-review/architecture-review.json \
  --source-root ~/projects/my-app \
  --source-evidence out/myproject-inputs/source-evidence.json \
  --output out/myproject-docs
```

Omit `--review` if you have no review file. `--source-root` and `--source-evidence` are an **optional pair**: supply **both** to include source verification, or neither to use the normal nine-page documentation pack.

With a source map, the pack adds **`source-evidence.md`** (ten Markdown pages + two Mermaid files). Its table records claim IDs, relative paths and optional lines, the authored evidence statement/basis, expected and current SHA-256 digests, and one of these statuses:

| Status | Meaning |
| --- | --- |
| `matching_snapshot` | The cited local file's **bytes** still match the authored SHA-256; not proof of the claim |
| `changed` | The local file exists but its bytes differ from the earlier digest |
| `missing` | The referenced local file does not exist |
| `line_out_of_range` | The byte hash matches but the authored line span exceeds the file's current line count |
| `unreadable` | The file could not be safely read (e.g. symlink, inaccessible file or size limit) |

The report also identifies **mandatory requirements and components with no matching `observed` source link**. The `open-questions.md` page explicitly lists missing/changed citations and unlinked architecture IDs.

Using `--strict` returns exit code **2** when the architecture/review is unresolved **or** when source claims remain unsupported, unlinked, stale, inferred or proposed. The documents still render for review. Exit **1** indicates malformed input, unsupported IDs, missing paired options or another hard failure. An existing nonempty destination cannot be overwritten.

### 4. Change detection and regeneration

Keep the original source map. After editing the application, run `document` again with the **same source evidence JSON** and a **new empty output directory**, for example `out/myproject-docs-v2`. Existing cited file hashes will show `changed` when their bytes differ. Compare the reports, confirm implications, and only then update the source map and reviewed architecture.

To see changes in **every inventoried file**, including new files that no claim cites yet, keep the earlier `source-inventory.json`, create a new one, and compare them:

```bash
speccanopy source-inventory ~/projects/my-app --output out/myproject-inputs/source-inventory-v2.json
speccanopy source-diff out/myproject-inputs/source-inventory.json \
  out/myproject-inputs/source-inventory-v2.json --output out/myproject-source-diff
```

This writes `source-diff.json` and `source-diff.md` listing added, removed, changed and unchanged files. See [Compare source inventories](source-inventory-diff.md).

**Limit:** `document` detects changes to **cited files**; `source-diff` detects byte changes to **inventoried files**. Neither detects architectural behavior, deployed infrastructure, renames, files excluded by the privacy filters, or an entire Git revision. The inventory itself does not record the application's Git commit; matching SHA-256 records a file snapshot, **not signed provenance, consent, expert agreement, or architecture correctness**.

### 5. Claude Code subscription workflow

With Claude Code opened in Speccanopy and granted approved access to `~/projects/my-app`, ask:

> Read `CLAUDE.md`, `docs/USER_GUIDE.md` and `docs/source-evidence-workflow.md`. Run `speccanopy source-inventory` on my authorized application directory, saving metadata under Speccanopy's ignored `out/`. Inspect only relevant allowlisted source files, not `.env`, secrets or production data. Draft schema-valid `SystemBrief` and `FixtureDesign` inputs, and keep true facts separate from inferred/proposed decisions. Run `speccanopy design`, then author `source-evidence.json` with real architecture IDs and SHA-256 hashes copied from the inventory. Never invent source lines or claim independent verification. Run `speccanopy review` and `speccanopy document --source-root ... --source-evidence ...`. Show me the resulting `source-evidence.md` and `open-questions.md`; request my review before copying documentation into my application's repository.

See [the reusable full prompt](../prompts/claude-code-document-project.md).

## What remains for Issue #5

Completed for this slice: allowlisted local source metadata inventory, snapshot-bound source ID references, missing/changed/invalid-line status, explicit unlinked requirement/component reporting, deterministic Markdown integration, recorded inventory scan scope and whole-inventory `source-diff` comparison, all covered by offline tests.

Still open: **semantic source-to-architecture extraction** that does not fabricate functionality; real application end-to-end validation; mapping changed files to affected architecture claims and accurate, safe **code-change-to-documentation** reconciliation; more comprehensive runtime, data-consistency, security and deployment design views. The documented source workflow is **guided**, not a one-click architecture analyzer.

**Research integrity:** Neither a matching file hash nor agreement among AI assistants counts as an independent professional architecture review. [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2) remains a separate research milestone.
