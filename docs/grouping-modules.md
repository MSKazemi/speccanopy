# Grouping intake modules into components

`speccanopy project-intake` writes one component per source module. That is a
faithful starting point, but a flat list of modules is rarely the architecture an
owner wants to review. `speccanopy group` lets the owner (or an assistant, or the
owner by delegation) say which modules belong together and which requirements each
group serves, **without hand-writing a Pydantic fixture or a script**. The result
feeds straight into `speccanopy design`.

## When to use it

Use it after `project-intake` and before `design`, when you want a tree of
`system -> groups -> modules` instead of `system -> modules`. It works for Python
and JavaScript/TypeScript intakes alike; only the module names differ.

It restructures and maps requirements. It does **not** decide whether the grouping
is good, and it does not produce evidence.

## Command

```bash
speccanopy group INTAKE_DIR --groups groups.json --output NEW_DIR [--allow-ungrouped]

speccanopy design NEW_DIR/brief.json --fixture NEW_DIR/design.json --output design-out
```

`INTAKE_DIR` is the `project-intake` output directory. It is read, never modified.
`NEW_DIR` must be absent or empty; an existing non-empty directory or a symlink is
refused, so edited files are never overwritten. On any validation failure the
command prints `Error grouping modules: ...`, exits 1 and writes nothing.

## `groups.json`

```json
{
  "schema_version": 1,
  "decided_by": "owner_delegated",
  "groups": [
    {
      "id": "grp_core",
      "name": "Core",
      "responsibility": "Schemas and export.",
      "modules": ["speccanopy.models", "speccanopy.exporters"],
      "requirement_ids": ["FR-USER-001"]
    }
  ]
}
```

| Field | Rule |
| --- | --- |
| `schema_version` | Must be `1`. |
| `decided_by` | `owner`, `owner_delegated` or `assistant_proposed`. Required. |
| `groups[].id` | A valid identifier, unique, and not equal to any existing component or relationship ID (including `system` and the intake's `mod_...` IDs). |
| `groups[].name`, `responsibility` | Non-empty text. |
| `groups[].modules` | At least one module **name** exactly as in `module-observations.json` (for example `speccanopy.models`; JavaScript names are extensionless paths). No module may appear in two groups. |
| `groups[].requirement_ids` | Optional. Each must exist in the intake `brief.json`. A requirement may be mapped to several groups. |

Unknown fields are rejected. The file is limited to 1 MB.

Validation fails closed on: an unknown module; a module in two groups; an unknown
requirement ID; duplicate or invalid group IDs; a group ID that collides with an
existing ID; an empty group; and any module left in no group (unless
`--allow-ungrouped`, which keeps those modules directly under the root and lists
them in the review).

## What `decided_by` means

It is recorded verbatim in `grouping-review.md` and in each group's rationale and
assumptions. **Only `owner` means owner-confirmed**, and even then Speccanopy cannot
verify who wrote the file; it records the declaration.

| Value | Meaning |
| --- | --- |
| `owner` | The file declares the owner confirmed this grouping. |
| `owner_delegated` | The owner delegated the decision; the groups were not individually confirmed. |
| `assistant_proposed` | An assistant proposed the groups; not confirmed by the owner. |

## Outputs

| File | Content |
| --- | --- |
| `brief.json` | Copied unchanged from the intake. |
| `design.json` | A `FixtureDesign`: root, then groups, then modules. Module proposals and relationships are unchanged. |
| `grouping-review.md` | Who decided and what that means, each group with its modules and requirements, ungrouped modules, requirements mapped to no group, and what remains owner work. |

## Budgets

The grouped tree has `1 + groups + modules` components and depth 2. If that exceeds
the brief's `constraints.max_nodes` or `max_depth`, the command fails with the
numbers rather than raising a budget; change the brief yourself if you decide to.
Intake's default `max_nodes` already allows one group per module.

## Limits

- No verification cases, evidence, interfaces, data ownership, quality targets or
  `ready` status are added. A mandatory requirement is reported as planned or
  verified only once a verification case links it to a component that owns it, so
  mapped requirements still show as **uncovered** in `design` until the owner adds
  those cases. Components will be `requires_review`.
- Groups are logical groupings of source modules, not deployment or runtime
  boundaries. Static imports remain the only relationships.
- The design must be a flat intake design (modules directly under the root). A
  design that is already grouped or hand-edited into nesting is refused.
- One grouping level. Deeper nesting is hand-authored fixture work.
- A group (or the root) with more than 10 children gets a medium finding from
  `design`; the review lists such cases.
- `groups.json` refers to modules by name, so it must be revised when modules are
  added, removed or renamed.
- Grouping is not an architecture review and not independent expert evaluation.

The owner pilot's grouping is reproduced by `examples/owner-pilot/groups.json`; see
[its README](../examples/owner-pilot/README.md).
