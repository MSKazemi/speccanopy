# Acceptance example (synthetic)

`synthetic-inventory-app/` is a tiny **synthetic** Python project written only
for Speccanopy's offline acceptance tests (`tests/test_acceptance_pipeline.py`).
It is not a real application, has no real users or data, and running the
pipeline on it is **not an independent or real-world evaluation**. The
`--requirement` texts below are synthetic placeholders chosen for this fixture,
not requirements of any real owner.

Speccanopy only reads the files as bytes and parses them with `ast`; nothing is
imported or executed, and no network or model API is used.

## Run the full pipeline

Work on a COPY in a scratch directory (outputs must go to new or empty
directories and are never overwritten). From the repository root, with
Speccanopy installed (`python -m pip install -e '.[dev]'`):

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

Expected: every command exits 0 (add `--strict` to `design`, `review` or
`document` to get exit code 2, because the draft stays
`incomplete_requires_review`). `document` reports `7/7 byte snapshots match`;
the two `FR-USER-*` requirements and the root `system` component remain
unlinked, and nothing is ever promoted to `validated_for_scope`.

To see stale-source detection, edit a module in `app/src/inventory_ledger_demo/`
and run `document` again into a NEW output directory (for example `work/docs2`):
the affected claims become `changed` in `source-evidence.md` and
`open-questions.md`.

To see changes to **every** inventoried file (including new files no claim
cites), compare the intake inventory with a fresh one:

```bash
speccanopy source-inventory app --output work/source-inventory-v2.json
speccanopy source-diff work/intake/source-inventory.json work/source-inventory-v2.json \
  --output work/source-diff
```

Full walkthrough with observed output, exit codes and test coverage:
[`docs/end-to-end-acceptance.md`](../../docs/end-to-end-acceptance.md).
