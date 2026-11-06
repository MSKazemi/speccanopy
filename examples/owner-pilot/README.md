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

## Supported path: `speccanopy group`

`groups.json` in this folder expresses the same grouping as `apply_grouping.py`
(six groups over 27 modules, `decided_by: "owner_delegated"`), and
`speccanopy group` is now the supported way to apply it. It needs no hand-written
script and works for any intake, not only this one:

```bash
speccanopy project-intake CHECKOUT/src --system "Speccanopy (owner pilot)" --goal "..." \
  --requirement "..." --requirement "..." --requirement "..." --requirement "..." \
  --output work/intake
speccanopy group work/intake --groups examples/owner-pilot/groups.json --output work/grouped
speccanopy design work/grouped/brief.json --fixture work/grouped/design.json --output work/design
```

`tests/test_group_command.py` checks that this produces exactly the same tree as
`apply_grouping.py` (same IDs, group names, responsibilities and requirement
mapping). The groups file lists modules by name, so it only fits a source tree
that still has those 27 modules; it must be updated, not reused blindly, when
modules are added or renamed.

`group` does **not** add verification cases. `apply_grouping.py` still shows how
the pilot attached its four real, CI-backed cases; they remain owner-authored
input added to `design.json` after grouping (see
[the pilot report](../../docs/owner-pilot-speccanopy.md)). See
[Grouping modules](../../docs/grouping-modules.md).
