# Synthetic inventory ledger (acceptance-test fixture)

This is a **synthetic** Python project written only for Speccanopy's offline
acceptance tests. It is **not a real application**: it has no real users, no real
data, no deployment, and was not supplied by any external owner. Using it is
**not an independent or real-world evaluation** of Speccanopy.

Layout (4 Python modules, a few static internal imports, nothing executed):

- `src/inventory_ledger_demo/__init__.py` - package marker
- `src/inventory_ledger_demo/catalog.py` - item records
- `src/inventory_ledger_demo/ledger.py` - stock movements (absolute import of `catalog`)
- `src/inventory_ledger_demo/reports.py` - balance summaries (relative import of `ledger`, absolute import of `catalog`)
- `scripts/seed_demo.sh` - a non-Python file that intake lists as "not analyzed"

Speccanopy only reads these files as bytes and parses them with `ast`; it never
imports or runs them. Do not add secrets or credential-like files here: the
tests create privacy traps dynamically in temporary directories.
