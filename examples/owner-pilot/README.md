# Owner pilot grouping script

`apply_grouping.py` is the reviewed grouping step of the
[owner pilot](../../docs/owner-pilot-speccanopy.md): it turns the `design.json`
written by `speccanopy project-intake` on Speccanopy's own source into a grouped
fixture, maps the four owner-confirmed requirements onto the groups, and adds a
verification case per requirement citing real test files and CI run 42156490953.

The grouping is **assistant-proposed and owner-delegated**, not owner-confirmed.
It is specific to Speccanopy at `main` `0e0cf40`; it fails if a module is left
ungrouped or grouped twice.

```bash
python examples/owner-pilot/apply_grouping.py work/intake/design.json work/design-grouped.json
```
