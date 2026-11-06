# Map source changes to affected claims — `speccanopy source-impact`

**Issue #5 slice.** `speccanopy source-impact` takes two `source-inventory.json` snapshots, the `source-evidence.json` map that was authored against the earlier one, and optionally the `architecture.json`, and reports **which authored source claims — and therefore which architecture IDs — may be out of date** because the files they cite changed, disappeared or were never visible. It also lists new and changed files that **no claim cites**.

It is a **metadata comparison of file paths and SHA-256 digests**. It does **not** read source files, does **not** decide whether the architecture or the meaning of a claim changed, does **not** mark any claim verified and does **not** edit or regenerate documentation.

> **CLI status.** `speccanopy source-impact` is available; `speccanopy source-impact --help` lists the flags in section 3. The module API is `speccanopy.source_impact` (`assess_claim_impact`, `render_claim_impact_markdown`, `export_claim_impact`).

Use it after [`source-diff`](source-inventory-diff.md): the diff tells you which *files* differ, this report tells you which *claims and IDs* depended on them.

## 1. Prerequisites

- Python 3.11+ and Speccanopy installed from the repository root: `python -m pip install -e '.[dev]'`.
- Two inventories from `speccanopy source-inventory` (or `project-intake`): the one taken when the documentation and `source-evidence.json` were produced (`BEFORE`), and a fresh one (`AFTER`).
- The `source-evidence.json` map (see the [source evidence workflow](source-evidence-workflow.md)).
- Optionally the `architecture.json` the claims refer to.
- No network access, model API key or Claude account is needed. The command never touches the application project, only the JSON files you name.

## 2. How a claim is classified

Every claim is bound to the SHA-256 of the file it cites. Each claim is compared with the diff entry for its `source_path` and gets exactly one status:

| Status | Rule | Meaning |
| --- | --- | --- |
| `unaffected` | Path is `unchanged` in the diff **and** the claim digest equals the (identical) digest | The cited bytes are the same in both snapshots and the claim was authored against them. **Not** verification of the assertion. |
| `stale_changed` | Path is `changed` and the claim digest equals the **before** digest | The claim describes bytes that no longer exist. It may still be true; someone has to re-read the file. |
| `stale_removed` | Path is `removed` | The cited file is gone from the later inventory. A rename or move also lands here (the new path shows up under *uncited added files*); renames are not detected. A file that grew past the size limit also appears as `removed`. |
| `not_bound_to_before` | Path is in the diff, but the claim digest equals neither the before nor the after digest (or, for an `unchanged` path, differs from its digest) | The claim was authored against some other snapshot, or the evidence map was edited by hand. Its relationship to these inventories is unknown. |
| `rebound_to_after` | Path is `changed` or `added` and the claim digest equals the **after** digest | The claim was authored or refreshed against the newer bytes. |
| `not_in_inventory` | Path appears in neither inventory | Excluded by the privacy filters, the extension allowlist or the size limit, or never scanned. Its state is unknown. |

### Decision: `rebound_to_after` needs review

A claim whose digest already equals the new bytes has *probably* been updated, but a digest cannot show that its assertion was re-read: the digest may have been refreshed mechanically (for example by re-running intake) while the wording still describes the old behaviour. So `rebound_to_after` is **review-required, never `unaffected`**, it counts toward `affected_architecture_ids`, and it does **not** count as current evidence for a mandatory requirement. Once you have re-read the file and the claim, regenerate the documentation with the owner's approval; a later comparison between that new inventory and an identical one then reports `unaffected`.

Nothing is ever marked verified: even `unaffected` only says the cited bytes match.

## 3. CLI

```bash
speccanopy source-impact BEFORE.json AFTER.json \
  --evidence source-evidence.json \
  [--architecture architecture.json] \
  --output NEW_DIR [--strict]
```

| Argument | Meaning |
| --- | --- |
| `BEFORE.json`, `AFTER.json` | The earlier and later `source-inventory.json` (positional) |
| `--evidence FILE` | The `source-evidence.json` claim map |
| `--architecture FILE` | Optional. Enables validation that every claim's `architecture_id` is known (an unknown ID is an error, as in `speccanopy document`) and the mandatory-requirement check below |
| `--output DIR` | **New or empty** directory; a non-empty directory, a file or a symlink is refused before anything is written |
| `--strict` | Exit `2` when the report requires review (section 5) |

Exit codes: `0` report written; `1` unreadable or malformed input, unknown architecture ID, or an unsafe/non-empty output (detected before anything is written); `2` only with `--strict` and the report requires review.

## 4. Output files

The output directory contains exactly two files:

| File | Content |
| --- | --- |
| `claim-impact.json` | Machine-readable `ClaimImpactReport`: `entries` (one per claim with `architecture_id`, `source_path`, `assertion`, `basis`, line span, the claim / before / after SHA-256, `status`, `reason`), `status_counts`, `affected_architecture_ids`, `uncited_added_paths`, `uncited_changed_paths`, `mandatory_requirements_without_current_observed_evidence` (`null` when no architecture was supplied), `diff_requires_review`, `diff_coverage`, `diff_coverage_notes`, `caveat`, `schema_version: 1`. Keys are sorted. |
| `claim-impact.md` | Readable report: caveat, summary, claim table, the status meanings in use, possibly affected IDs, uncited added and changed files, and mandatory requirements lacking current observed evidence. All authored text (assertions, paths) is Markdown-escaped. |

Entries are sorted by architecture ID, source path and line span. Identical inputs give byte-identical output; there are no timestamps, host paths or file contents.

### Other report sections

- **`affected_architecture_ids`** — every architecture ID that has at least one claim that is not `unaffected`. This lists IDs to re-inspect, not IDs that are wrong.
- **`uncited_added_paths`** — files added since BEFORE that no claim cites. An observation, not an inference: they may be a new undocumented component, a renamed file, a test or noise.
- **`uncited_changed_paths`** — files whose bytes changed and that no claim cites.
- **`mandatory_requirements_without_current_observed_evidence`** — with `--architecture`: mandatory requirement IDs that have no `unaffected` claim with `basis: "observed"`. Inferred and proposed claims never count.

## 5. When review is required

The report `requires_review` unless **all** of these hold: there is at least one claim (an empty evidence map is never an all-clear); every claim is `unaffected`; no uncited added or changed files; the source diff itself does not require review; and, when an architecture was given, every mandatory requirement has current observed evidence. The diff's own review flag (any file added, removed or changed; coverage other than `comparable`; skipped oversized files) is propagated as `diff_requires_review`, so any difference between the snapshots, even in a file no claim cites, keeps the report in the review state. This is deliberately conservative. `requires_review` is computed from the stored fields and is shown in the Markdown and through `--strict`; it is not a separate JSON key. Reloading `claim-impact.json` rejects an entry whose status contradicts its recorded digests, or an altered reason or caveat text; this guards against hand edits, not against a deliberately recomputed forgery.

## 6. Limits

- **No semantics.** The tool compares bytes. A whitespace edit and a redesign look identical, and an unchanged file does not prove its claim is true.
- **No rename or move detection.** A rename is `stale_removed` for its claims plus an uncited added file. Update the evidence map by hand.
- **No project identity.** Inventories contain no project name or commit, so the tool cannot detect that you compared inventories (or an evidence map) from different projects. A claim whose digest matches neither snapshot is flagged `not_bound_to_before`, which is the usual symptom.
- **Invisible files.** Files excluded by the privacy filters, the allowlist or the size limit are not in the inventories; claims citing them are `not_in_inventory`.
- **Line spans are not re-checked.** A line range is reported as authored; the digest, not the range, decides the status.
- **Does not regenerate or edit documentation.** To update documentation, re-inspect the affected IDs and files, then run `speccanopy document` into a new folder with the owner's approval.
- Tested with synthetic in-memory and temporary inventories only (`tests/test_source_impact.py`); no externally permissioned real-world application has been evaluated.

## 7. Privacy

The report contains project-relative file paths, claim assertions you authored, architecture IDs and SHA-256 digests (and 12-character prefixes). It contains no source text, no absolute host paths and no timestamps. File **names** and assertion text alone can be sensitive: keep the output in Speccanopy's ignored `out/` directory or another private location, and do not publish it without review.

## 8. With Claude Code

Under your normal subscription session you can ask: *"Read `claim-impact.md`. For each architecture ID listed as possibly affected, inspect only the allowlisted files I authorize and tell me what question the owner should answer. Do not edit my documentation or source code."* The reading is an AI-assisted desk review, not independent expert evaluation and not verification.
