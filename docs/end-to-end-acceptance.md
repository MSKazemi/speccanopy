# End-to-end acceptance walkthrough — intake → design → review → document

**Issue #5 slice (2026-11-06).** This page shows the complete offline Speccanopy pipeline on a small committed example and explains what the automated acceptance tests check. The example is **synthetic**: it was written for Speccanopy's tests, has no real users, data or owner, and running it is **not** an independent or real-world evaluation. An acceptance test on an externally permissioned real application is still an open Issue #5 milestone.

## 1. Prerequisites

- Python 3.11+; from the Speccanopy repository root: `python -m pip install -e '.[dev]'`.
- A POSIX shell (Bash/Zsh). No network, model API key, Claude account or target-application execution is needed: Speccanopy reads the example's files as bytes and parses Python with `ast`; nothing is imported or run.

## 2. Input

[`examples/acceptance/synthetic-inventory-app/`](../examples/acceptance/synthetic-inventory-app/): four Python modules in the package `inventory_ledger_demo` with three static internal imports, a `README.md` and a non-Python `scripts/seed_demo.sh` (inventoried, not analyzed). The system name, goal and two requirements below are **synthetic placeholders** you supply on the command line — Speccanopy never infers requirements from code.

## 3. Copyable commands

Run from the repository root. The commands work on a **copy** in a fresh temporary folder, because every output folder must be new or empty.

```bash
WORK=$(mktemp -d)
cp -r examples/acceptance/synthetic-inventory-app "$WORK/app"
cd "$WORK"

speccanopy project-intake app \
  --system "Synthetic Inventory Ledger" \
  --goal "SYNTHETIC: document the module boundaries of the acceptance fixture" \
  --requirement "SYNTHETIC: the demo ledger records stock movements for catalog items" \
  --requirement "SYNTHETIC: the demo reports summarize ledger balances" \
  --output work/intake

speccanopy design work/intake/brief.json --fixture work/intake/design.json --output work/design

speccanopy review work/design/architecture.json --output work/review

speccanopy document work/design/architecture.json \
  --review work/review/architecture-review.json \
  --source-root app --source-evidence work/intake/source-evidence.json \
  --output work/docs
```

Observed output (2026-11-06, `Artifacts:` lines omitted); every command exited `0`:

```text
Python source intake: 4 modules, 3 static import edges
PROVISIONAL: owner must check module boundaries and map requirements; no code executed
Architecture: Synthetic Inventory Ledger
Status: incomplete_requires_review
Components: 5; max depth: 1
Mandatory requirements: 0 verified, 0 planned, 2 uncovered
Review: Synthetic Inventory Ledger
Status: requires_review
Advisory style: abstain
Quality findings: 3
Documentation: Synthetic Inventory Ledger
Source architecture status: incomplete_requires_review — no independent approval inferred
Source citations: 7/7 byte snapshots match; not proof of architectural correctness
```

## 4. Output files

```text
work/
├── intake/   brief.json  design.json  source-evidence.json  source-inventory.json
│             module-observations.json  intake-review.md
├── design/   architecture.json  architecture.mmd  relationships.mmd
│             requirements-report.json  decisions.json  generation-trace.json
├── review/   architecture-review.json  architecture-review.md
│             style-comparison.json  quality-review.json
└── docs/     README.md  overview.md  requirements.md  components.md  interactions.md
              data-security.md  decisions.md  quality-risks.md  open-questions.md
              source-evidence.md  architecture.mmd  relationships.mmd
```

Read `work/intake/intake-review.md` and `work/docs/open-questions.md` first. The architecture stays `incomplete_requires_review`: the two requirements are not mapped to any module (`2 uncovered`), and the root `system` component has no observed source link. That is the expected, honest result — the tool reports module/import syntax, not behaviour.

## 5. See change detection

Continue in the same folder:

```bash
printf '\n# synthetic edit\n' >> app/src/inventory_ledger_demo/ledger.py

speccanopy document work/design/architecture.json \
  --review work/review/architecture-review.json \
  --source-root app --source-evidence work/intake/source-evidence.json \
  --output work/docs2 --strict

speccanopy source-inventory app --output work/source-inventory-v2.json
speccanopy source-diff work/intake/source-inventory.json work/source-inventory-v2.json \
  --output work/source-diff
speccanopy source-impact work/intake/source-inventory.json work/source-inventory-v2.json \
  --evidence work/intake/source-evidence.json \
  --architecture work/design/architecture.json \
  --output work/claim-impact
```

Observed: `document` prints `Source citations: 5/7 byte snapshots match` and exits `2` (because of `--strict`; the pack is still written); the two claims citing `ledger.py` are `changed` in `work/docs2/source-evidence.md`. `source-diff` prints `Source diff: 0 added, 0 removed, 1 changed, 5 unchanged` and exits `0`. `source-diff` also lists **new uncited files**, which `document` cannot see — see [Compare source inventories](source-inventory-diff.md). `source-impact` prints `Claim impact: 7 claims (5 unaffected, 2 stale_changed)` and exits `0` (`2` with `--strict`); the two `ledger.py` claims and their architecture IDs are listed as possibly affected in `work/claim-impact/claim-impact.md` ([guide](source-claim-impact.md)).

Before the edit, the documentation gate summarizes what still needs a human:

```bash
speccanopy doc-gate work/design/architecture.json \
  --review work/review/architecture-review.json \
  --source-root app --source-evidence work/intake/source-evidence.json \
  --output work/doc-gate
```

Observed on the unedited copy: `Outcome: requires_review (15 blocking, 7 attention)`, exit `0`. Blocking items include the unlinked `FR-USER-*` requirements and root `system` component and the `incomplete_requires_review` status; see [Documentation review gate](documentation-review-gate.md).

## 6. Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Artifacts written |
| `1` | Invalid/unsupported input or an existing non-empty/symlinked output folder; these are detected **before anything is written**, and a one-line `Error ...` goes to stderr. (An operating-system failure in the middle of writing, such as a full disk, can still leave a partial folder.) |
| `2` | Only with `--strict` (`design`, `review`, `document`, `source-diff`, `source-impact`, `doc-gate`): artifacts written but review is still required |

## 7. What the acceptance tests check

`python -m pytest -q tests/test_acceptance_pipeline.py tests/test_source_diff_cli.py tests/test_new_cli_commands.py` runs fully offline in temporary folders (they never write inside the repository):

- **Exact artifacts and statuses** for every stage, through both the installed `speccanopy` console script and the in-process CLI; nothing becomes `validated_for_scope`.
- **Repeatability:** the whole pipeline run from two different absolute locations (and with relative paths) produces byte-identical files, with no host path or username in any output.
- **Stale and missing sources:** edited files → `changed`; deleted → `missing`; all deleted → all `missing`; symlinked → `unreadable`; out-of-range line spans; `--strict` exit `2` with output still written.
- **Unsupported inputs:** non-Python-only projects, binary/non-UTF-8/NUL-byte `.py` files, empty requirements, malformed briefs, fixtures, architectures, reviews and evidence, unknown IDs, mismatched systems — each exits `1` with no traceback and no output folder.
- **Privacy exclusions:** `.env`, `.git/`, `private/`, `secrets/`, credential/token-named files, `id_rsa`, `node_modules/` and an outside symlink — none of their marker contents or paths appear in any stage's output, and they cannot be cited.
- **Protection of existing documentation:** each stage refuses a non-empty, symlinked or file output path and leaves owner files byte-identical. These tests found that `design` and `review` (and therefore `propose-ai`) previously overwrote such folders; that is fixed in this release, `propose-ai` now refuses before making any model request, and the same guard now covers `refine-*`, `benchmark`, `research-*`, `approve-ai` and `speccanopy-experts` (`tests/test_output_guards.py`). The guard is best-effort: it checks the final path component for a symlink and cannot exclude a concurrent local writer.
- **No execution:** modules that write marker files or raise at import time are never executed.

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `speccanopy: command not found` | Activate the environment where you ran `pip install -e '.[dev]'`. |
| `output must be a new or empty directory` | Use a new `--output` folder, or a new `$WORK`. |
| `Python source modules ... exceeding --max-modules` | Not expected for this example; for larger projects pass a narrower folder or raise `--max-modules` (≤ 50). |
| `document` exits `2` | Only with `--strict`: unresolved review or source issues remain. Read `open-questions.md`. |

## 9. Scope and limitations

- Synthetic example and self-dogfooding only; **not** an externally permissioned real-application acceptance, an expert review or proof of architectural correctness.
- Python only for intake; requirements must come from the owner; module grouping and import edges are syntax observations.
- Matching hashes prove byte equality, not that an assertion is true.
