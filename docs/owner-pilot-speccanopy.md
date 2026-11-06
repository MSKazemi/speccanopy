# Owner pilot: documenting Speccanopy with Speccanopy

**Run 2026-11-06 on `main` at `0e0cf40`.** This is the first Issue #5 pilot in which the **project owner** took part. It is still not independent expert review.

## What the owner confirmed, and what they delegated

| Item | Status |
| --- | --- |
| Mandatory requirements R1–R4 below | **Owner-confirmed** as-is |
| Excluding the synthetic test fixture `examples/acceptance/...` from the architecture | Decided by the assistant; the owner delegated technical choices ("do the most professional thing") |
| Grouping 27 modules into six components, and mapping R1–R4 onto them | **Assistant-proposed, owner-delegated**, not individually confirmed by the owner |

Requirements (from [`vision-and-goal.md`](vision-and-goal.md) and Issue #5):

- **FR-USER-001** Turn a requirements brief and curated design into a rooted component tree plus typed relationship graph.
- **FR-USER-002** Review an architecture for coverage, style trade-offs and quality risks without claiming validation.
- **FR-USER-003** Render reviewable Markdown documentation with requirement traceability and evidence status.
- **FR-USER-004** Draft provisional architecture inputs from an existing project's source without executing it.

## Steps

From a clean checkout of `main` (the owner's working copy was not touched):

```bash
speccanopy project-intake CHECKOUT/src --system "Speccanopy (owner pilot)" \
  --goal "Produce traceable architecture specifications and documentation with explicit uncertainty (docs/vision-and-goal.md)" \
  --requirement "Turn a requirements brief and curated design into a rooted component tree plus typed relationship graph (vision capability 3, 5)" \
  --requirement "Review an architecture for coverage, style trade-offs and quality risks without claiming validation (vision capability 2, 6)" \
  --requirement "Render reviewable Markdown documentation with requirement traceability and evidence status (vision capability 8)" \
  --requirement "Draft provisional architecture inputs from an existing project's source without executing it (Issue #5)" \
  --output work/intake
python examples/owner-pilot/apply_grouping.py work/intake/design.json work/design-grouped.json
# raise brief.constraints.max_nodes from 28 to 34 in a copy: work/brief-grouped.json
speccanopy design work/brief-grouped.json --fixture work/design-grouped.json --output work/design
speccanopy review work/design/architecture.json --output work/review
speccanopy doc-gate work/design/architecture.json --review work/review/architecture-review.json \
  --source-root CHECKOUT/src --source-evidence work/intake/source-evidence.json --output work/gate
speccanopy document work/design/architecture.json --review work/review/architecture-review.json \
  --source-root CHECKOUT/src --source-evidence work/intake/source-evidence.json --output work/docs
```

`apply_grouping.py` is the review step done as a reproducible script. It places each module under one of six groups, maps one requirement per group, and adds a verification case per requirement citing the real test files and CI run (see below). It fails if a module is left ungrouped or grouped twice.

| Group | Modules | Requirement |
| --- | --- | --- |
| Core schema and export | `speccanopy`, `models`, `exporters` | — |
| Architecture generation | `decomposer`, `fixtures`, `proposer`, `ai`, `ai_exporters`, `claude` | FR-USER-001 |
| Review, refinement and research | `review`, `review_exporters`, `scoring`, `benchmark`, `refinement`, `refinement_exporters`, `research`, `research_exporters`, `expert_review` | FR-USER-002 |
| Documentation rendering and gate | `documentation`, `doc_gate` | FR-USER-003 |
| Source evidence and project intake | `source_evidence`, `source_diff`, `source_impact`, `structure_diff`, `project_intake`, `js_intake` | FR-USER-004 |
| Command-line entry point | `cli` | — |

## Measured results

| Stage | Before grouping (intake only) | After grouping |
| --- | --- | --- |
| Intake on the repository root | 31 modules: the default `--max-modules 30` refused it, and 4 of the 31 belonged to the synthetic test fixture | with `--exclude examples`: 27 modules, 109 edges |
| Intake on `src/` | 27 modules, 109 static import edges | same input |
| `design` | 28 components, depth 1; mandatory requirements **0 verified, 4 uncovered** | 34 components, depth 2; **4 verified, 0 uncovered** |
| Status | `incomplete_requires_review` | `incomplete_requires_review` (never promoted) |
| `document` source snapshots | 136/136 match | 136/136 match |
| `doc-gate` | `requires_review` | `requires_review` (46 blocking, 41 attention) |

**The first `design` run on the grouped fixture built only 28 of 34 components.** Intake sets the brief's node budget to modules + 1 (28). The engine blocked `grp_source`, wrote `blocked_nodes` and one `unmaterialized_link` event per relationship it could not emit, and did not drop them silently. Raising `max_nodes` to 34 in a copy of the brief fixed it. Budgets behave as specified; the intake's default budget does not leave room for a later grouping step.

**Verification evidence is real but narrow.** Each requirement's case cites test files that passed in [GitHub Actions run 42156490953](https://github.com/MSKazemi/speccanopy/actions/runs/42156490953) on `0e0cf40`. Passing tests show implemented behaviour, not architecture quality, and the gate correctly lists every `verified` case as self-reported.

**Why the gate still blocks** (by category):

| Category | Blocking | Attention |
| --- | --- | --- |
| Remaining manual decisions | 35 | 37 |
| Unknown source mappings | 11 | 0 |
| Unsupported or self-reported claims | 0 | 4 |

- 34 components are still `requires_review`, as intake creates them. Marking a component `ready` needs interfaces, data ownership, validation evidence and a stop reason, none of which a static import scan observes.
- The 6 groups and the 4 requirements have no **observed** source claim. A grouping is a judgement, not an observation, so this is correct.
- The `incomplete_requires_review` status blocks until the owner decides otherwise.

## Findings for Issue #5

1. **Fixed in this change:** intake had no way to leave out test fixtures. `project-intake --exclude PATH` (repeatable) now does; on the repository root, `--exclude examples` gives the same 27 modules and 109 edges as running on `src/`, within the default `--max-modules 30`, and records the exclusion in `module-observations.json` and `intake-review.md`.
2. Intake's default node budget (modules + 1) leaves no room for grouping; the user has to raise `max_nodes` by hand.
3. Going from 4 uncovered to 4 verified requirements took one scripted review step plus real CI evidence; reaching `ready_for_human_signoff` would need per-component interface and data decisions by the owner.

## Limits

One repository, written by the same maintainers who built the tool; the grouping is not owner-confirmed; nothing here is independent expert review or certification.
