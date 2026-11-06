# Compare static structure — `speccanopy structure-diff`

**Issue #5 follow-up.** `speccanopy structure-diff` compares two `project-intake` outputs by their **static module and import structure**, so that byte churn can be told apart from a change in which modules exist, which modules import which, and which top-level functions and classes they declare. It is **static-syntax comparison only**: it does not run, import or test anything, does not decide whether the architecture changed, and does not edit any documentation.

## 1. When to use it (versus `source-diff` / `source-impact`)

| Question | Command |
| --- | --- |
| Which files' bytes differ? | [`source-diff`](source-inventory-diff.md) |
| Which authored source claims cite files whose bytes differ? | [`source-impact`](source-claim-impact.md) |
| Did the module set, the import edges or the top-level names change, or only file contents? | `structure-diff` (this guide) |

Byte comparisons are deliberately strict: reformatting, a version-string bump or a comment edit changes a file's SHA-256 and marks every claim citing that file stale, even when the module/import structure is identical. A third-party release can change every module's bytes while its static structure stays the same (see [pilot-third-party-python.md](pilot-third-party-python.md) for a measured case). `structure-diff` lets you triage that: if `Structure changed: no`, the stale claims are not explained by any added, removed or re-wired module, and you can prioritise the claims for the modules or edges that did change. It does **not** make those claims safe: unchanged structure says nothing about behaviour.

## 2. Input

Run `speccanopy project-intake` on each version (it writes `module-observations.json`), then pass either the intake output directories or the `module-observations.json` files:

| Argument | Meaning |
| --- | --- |
| `BEFORE` | Earlier intake directory, or its `module-observations.json` |
| `AFTER` | Later intake directory, or its `module-observations.json` |
| `--output DIR` | **New or empty** directory; an existing non-empty directory, a file or a symlink is refused before anything is written |
| `--strict` | Exit `2` when the static structure changed |

Inputs are validated with the same strict model that `project-intake` writes. Observations that contradict themselves (duplicate module names or component IDs, an import of a module that was not observed, a module importing itself) are rejected rather than compared. No intake output needs to be kept private for this command to work, but module names, function names and paths can be sensitive: keep the results in a private location such as the ignored `out/` directory.

## 3. Walkthrough

Run as-is from an empty working folder (synthetic project). The output shown is real.

```bash
mkdir -p demo-app/src/demo
printf 'from demo import store\n\ndef handler():\n    return store.ROWS\n' > demo-app/src/demo/api.py
printf 'ROWS = []\n' > demo-app/src/demo/store.py
printf '' > demo-app/src/demo/__init__.py

speccanopy project-intake demo-app --system Demo --goal "Demo goal" \
  --requirement "Serve rows" --output out/intake-v1

# ... the code changes, but only inside function bodies and comments ...
printf '# reworded\nfrom demo import store\n\ndef handler():\n    return list(store.ROWS)\n' > demo-app/src/demo/api.py

speccanopy project-intake demo-app --system Demo --goal "Demo goal" \
  --requirement "Serve rows" --output out/intake-v2

speccanopy structure-diff out/intake-v1 out/intake-v2 --output out/structure-diff --strict
```

```text
Structure diff: modules 0 added, 0 removed, 3 kept; import edges 0 added, 0 removed, 1 kept
Structure changed: no
Static syntax only; renames not inferred; not behavioural or architectural verification
Artifacts: out/structure-diff/structure-diff.json, out/structure-diff/structure-diff.md
```

The exit code was `0` even with `--strict`, because the structure is unchanged although `demo.api`'s bytes changed. The report lists `demo.api` under "Kept modules with byte changes only".

Exit codes: `0` success; `2` only with `--strict` when `structure_changed` is true; `1` for invalid or missing input or an unsafe output location (nothing is written).

## 4. Outputs

`structure-diff.json` (deterministic, sorted keys) and `structure-diff.md`, both free of timestamps and host paths. The JSON is validated on load (`StructureDiff.model_validate_json`) and rejects forged reports, for example `structure_changed: false` with an added edge, lists that disagree with the per-module deltas, an edge touching a module of the wrong status, or an altered caveat.

The report contains:

- **Modules** added, removed and kept, matched by module name.
- **Import edges** (`source -> target`, static internal imports) added, removed and kept.
- For each kept module: top-level **functions and classes added/removed** (compared as name sets), whether `symbols_omitted` changed, whether the source path changed, and whether the module's bytes changed (`source_bytes_changed`; this alone is not a structural change).
- **Component ID mapping** for kept modules (before and after IDs, and whether they differ). IDs are derived from file paths by each intake run and may differ; they are never used for matching.
- `incomplete_symbol_modules`, `skipped oversized file` counts for both sides, and `structure_changed`.

`structure_changed` is true when any module was added or removed, any import edge was added or removed, or any kept module has added/removed function or class names, a changed `symbols_omitted` count or a changed source path. Byte-only changes, component-ID changes and reordering do not count.

## 5. Python API

```python
from speccanopy.structure_diff import (
    compare_module_observations, export_structure_diff,
    load_module_observations, render_structure_diff_markdown,
)

diff = compare_module_observations(load_module_observations("out/intake-v1"),
                                   load_module_observations("out/intake-v2"))
export_structure_diff(diff, "out/structure-diff")   # new or empty directory only
```

## 6. Limits (read before relying on the result)

- **Static syntax only.** Identical structure does not mean identical behaviour; changed structure does not mean changed architecture. Nothing is verified, and nothing here is an expert review.
- **Renames are not inferred.** A renamed or moved module is one removed module plus one added module, and its edges appear as removed and added.
- **Module names come from file paths** (`src/` prefix and `__init__` stripped by the intake). Moving `pkg.py` to `pkg/__init__.py` keeps the module name; it is reported as a changed source path and counts as a structural change.
- **Edges are static `import` declarations between observed modules only.** Conditional, dynamic, lazy and third-party imports are not represented, and an import that merely moved within a file is a `kept` edge.
- **Name sets only.** Signatures, bodies, decorators, nested definitions, ordering and duplicate names are invisible.
- **The intake caps recorded symbols at 30 functions and 30 classes per module**, counting the rest in `symbols_omitted`. Kept modules with omitted symbols on either side are listed under `incomplete_symbol_modules`; their name comparison is incomplete.
- **Scope is not verified.** The intakes carry no project identity and the command does not check that both used the same size limit, allowlist or module cap (`--max-modules`); a module that disappears because it crossed a limit looks like a removed module. Skipped-oversized counts are shown to help you spot this.
- Only Python modules analysed by `project-intake` are covered; other languages and non-Python files are invisible.
