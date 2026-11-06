# Documentation review gate

**Issue #5 / P0:** the documentation gate puts the gaps in a generated architecture-documentation pack in one prominent report: uncovered requirements, unsupported or self-reported claims, unknown source mappings and the manual decisions that remain.

It is a **deterministic completeness check of authored data**. It is not expert review, not certification, and it never upgrades a status. A human must review the findings and sign off.

## Purpose

The [architecture documentation renderer](architecture-documentation-renderer.md) lists open questions as a checklist. The gate turns the same facts into a classified result with a single outcome, so a reader cannot miss that, for example, no source evidence was supplied, or that a "verified" verification case rests on text the author typed.

The gate is a pure function over objects you have already loaded. It reads no project source files, calls no network or model, and gives byte-identical output for identical inputs.

## Inputs

| Input | Required | Meaning |
| --- | --- | --- |
| `architecture.json` | yes | The authored `ArchitectureSpec`. |
| `architecture-review.json` | no | An advisory rule-based review from `speccanopy review`. It must be for the same system and authored architecture status, or the gate records a **blocking** item and ignores it. |
| Source assessment | no | The result of checking a [source-evidence map](source-evidence-workflow.md) against local files. Without it, every factual claim is unmapped. |

Library use:

```python
from speccanopy.doc_gate import (
    evaluate_documentation_gate,
    render_documentation_gate_markdown,
    export_documentation_gate,
)

gate = evaluate_documentation_gate(spec, review=review, sources=assessment)
print(render_documentation_gate_markdown(gate))
export_documentation_gate(gate, "out/doc-gate")   # NEW or empty directory only
```

## Command

The CLI wraps the functions above; `speccanopy doc-gate --help` lists the flags.

```bash
speccanopy doc-gate architecture.json \
  [--review architecture-review.json] \
  [--source-root PROJECT --source-evidence source-evidence.json] \
  --output NEW_DIR [--strict]
```

- Exit code `0` after writing the report, whatever the outcome.
- Exit code `1` for unreadable or malformed inputs, `--source-root` without `--source-evidence` (or the reverse), a source claim with an unknown architecture ID, or an unsafe/non-empty output. Nothing is written in these cases.
- With `--strict`, exit code `2` when the outcome is `requires_review`.
- `--output` must be a new or empty directory; existing files are never overwritten (same guard as `document`).

## Output files

`NEW_DIR/documentation-gate.json` holds the machine-readable result: `outcome`, `counts` per category, `blocking_count`, `attention_count`, the sorted `items` (each with `category`, `severity`, `subject_id`, `message`) and a fixed `caveat`. `NEW_DIR/documentation-gate.md` is the human report: the outcome and a per-category count table at the top, then one section per category, categories that hold blocking items first and blocking items before attention items within a section. All authored text is escaped.

## Categories and severities

Every item is **blocking** (the gate will not reach `ready_for_human_signoff`) or **attention** (a human should look, but it does not by itself block).

| Category | Blocking | Attention |
| --- | --- | --- |
| `uncovered_requirement` | A mandatory requirement with no verification case linked to an owning component, or mapped to no component at all. | none |
| `planned_only_requirement` | none | A mandatory requirement whose only verification is planned, not recorded as verified. |
| `unsupported_claim` | A source claim whose snapshot is `changed`, `missing`, `unreadable` or `line_out_of_range`. | A matching claim with basis `inferred` or `proposed`; any verification case marked `verified` (its evidence is authored text, not independently checked). |
| `unknown_source_mapping` | No source evidence supplied (one item); mandatory requirements and components without a matching **observed** source link. | none |
| `manual_decision` | Open `critical`/`high` findings; components `needs_decomposition`, `blocked` or `requires_review`; spec status `incomplete_requires_review`; an advisory review whose overall status is `requires_review`; a supplied review for a different system or status (it is ignored). | `proposed` ADRs; open `medium`/`low` findings; components still `proposed`; spec status `draft`; non-blocking advisory review findings. |
| `status_claim` | none | The spec claims `validated_for_scope`. |

Notes:

- Verification cases marked `verified` are flagged whether or not sources are supplied, because the gate cannot check the evidence text.
- A matching SHA-256 only shows that a cited local file has the recorded bytes. It does not show the author's claim is true, which is why `inferred` and `proposed` claims are also surfaced.
- The advisory review's own findings are listed with the review's severities. A review is optional; its absence is not itself reported.

## Outcome

`outcome` is one of two values:

- `requires_review`: at least one blocking item.
- `ready_for_human_signoff`: zero blocking items.

There is deliberately **no** `validated` or `approved` outcome. The gate output model rejects an outcome, counts or caveat that disagree with its items.

### What `ready_for_human_signoff` means

Within the data you supplied, none of the blocking conditions above was found, so it is now reasonable to put the pack in front of a qualified human.

### What it does NOT mean

- It does not mean the architecture is correct, validated, secure, or implemented as described.
- It does not verify evidence text, ADR rationale, or what any source file does.
- It does not authenticate any reviewer or turn an AI critique into a human sign-off.
- Attention items can remain; read them.
- A spec that claims `validated_for_scope` is reported with an attention item and is never promoted or confirmed by the gate. The gate does not change `spec.status`.

## Limits

- Pure and offline: freshness of the review and source evidence is not checked beyond system name and status; confirm they were created from this exact revision.
- Unlinked components are blocking because the gate cannot tell a deliberately unimplemented component from an unmapped one. Map them, or accept `requires_review`.
- Only structural facts in the inputs are examined. Failure, data and deployment analysis still needs human or expert reading.
