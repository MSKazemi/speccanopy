# Phase 2 — Deterministic adaptive architecture generation engine

**Status:** Implemented prototype, **not** an AI or universal architecture designer.  
**Scope:** Design architectures, not target application code, builds, tests or deployments.

This document extends the [Phase 1 architecture contract](architecture-contract.md). It follows the [confirmed vision](vision-and-goal.md) and the [execution roadmap](execution-roadmap.md).

## What is implemented

1. **Provider-neutral proposals:** `ComponentProposer.propose(parent, brief)` returns candidate child components. `FixtureComponentProposer` uses human-curated, machine-readable fixture data; an AI-backed proposer is a later milestone.
2. **Adaptive recursive decomposition:** a priority queue expands each node independently. A node can have zero to many children, with different branches stopping at different depths. The 3–7 / 10-child guidance is heuristic; when >10 are proposed, the engine warns instead of dropping required responsibilities.
3. **Explicit priority factors:** user/fixture-authored values for user value, risk, dependency, quality impact and uncertainty combine into a score using the *unvalidated* heuristic `0.30V + 0.25R + 0.20D + 0.15Q + 0.10U`. No provided factors yields a neutral score of 0 rather than made-up importance.
4. **Fail-safe limits:** `max_depth` and `max_nodes` bound expansion; each parent's entire candidate set is either accepted or marked blocked if it exceeds the budget. Blocked subtrees, unmaterialized edges and verification cases, and missing requirement coverage are reported. `max_refinement_rounds` is reserved for a later validation/refinement loop.
5. **Evidence-based leaf and parent readiness:** interface specification or an explicit reason to omit it, data ownership or explicit N/A, evidence and a stop rationale are required before a component is `ready`. Parents can become `ready` only when all children are also `ready`. This is **structural readiness**, not proof of real-world design quality.
6. **Containment and relationship views:** the engine validates component IDs, parent/child relationships and graph edges, and exports a separate Mermaid diagram for each.
7. **Requirement traceability:** mandatory functional and quality requirements map to component owners and planned or verified architecture *verification cases*. The engine never invents verified evidence: the included examples have only **planned** verification. Missing evidence means `uncovered` rather than success.
8. **Audit trace:** all expansion and stopping decisions are recorded, including each fixture-authored child rationale, priority-dependent traversal, budget blocks and final status.

## Getting started

Python 3.11+ and Pydantic 2 are required. The project provides an optional `speccanopy` CLI entrypoint:

```bash
python -m pip install -e '.[dev]'
pytest -q
speccanopy design examples/ecommerce.json --output out/ecommerce
```

Without installation, from the repository root:

```bash
PYTHONPATH=src python -m speccanopy.cli design examples/file-transfer.json --output out/file-transfer
```

The tool discovers `examples/ecommerce.design.json` from the name of the input brief; it can be overridden with `--fixture path/to/proposals.json`. The fixture is **required**: in this deterministic version the engine cannot infer architecture from arbitrary prose alone.

`--strict` returns exit code 2 when the generated architecture has `incomplete_requires_review` status; it still writes reports. Input/schema failures return code 1.

## Outputs

Every run writes six files into the selected output directory:

| File | Meaning |
| --- | --- |
| `architecture.json` | Normalized, Pydantic-validated `ArchitectureSpec` (rooted tree and typed relationship graph) |
| `architecture.mmd` | Mermaid **containment** tree |
| `relationships.mmd` | Mermaid **interaction/dependency** graph |
| `requirements-report.json` | Mandatory requirement coverage, component ownership and status |
| `decisions.json` | Selected style, authored ADRs and validation findings |
| `generation-trace.json` | Deterministic processing order, authored proposal rationales, stopping and budget events |

These outputs are **design drafts**. A JSON-valid or structurally `ready` component does not imply the system is correct, secure or fully validated. This prototype does not automatically set `validated_for_scope`.

## Three reproducible examples

The examples contain briefs (`*.json`), curated proposal mappings (`*.design.json`) and checked-in output snapshots (`examples/generated/<name>/`).

| Example | Components | Max depth from root | Root children | Status | Mandatory requirement coverage |
| --- | ---: | ---: | ---: | --- | --- |
| Text normalization CLI | 4 | 1 | 3 | `draft` | 4 planned, 0 uncovered |
| E-commerce | 13 | 3 | 5 | `draft` | 7 planned, 0 uncovered |
| File transfer | 13 | 4 | 4 | `draft` | 5 planned, 0 uncovered |

Different branches require different depth (for example S3 multipart and credential handling reach depth 4, while other transfer branches stop at depth 1). The examples deliberately include non-microservice designs.

## Test and review expectations

- `pytest -q` runs Phase 1 and Phase 2 tests: type/ID validation, priority ranking, variable depth and breadth, no duplicate/cyclic containment, evidence-based stopping, no false validated status, node/depth limits, uncovered requirements, deterministic output, CLI error handling and export snapshots.
- GitHub Actions runs the tests on Python 3.11 and 3.13.
- A reviewer still needs to examine architectural soundness: requirements completeness, style appropriateness, cohesion/coupling, concurrency, data consistency, security, availability and real-world feasibility.

## Deliberately postponed

- An AI proposer that can infer components from open-ended software requirements.
- Independent architecture quality or threat-analysis reasoning and targeted refinement loops.
- Automated style comparison/selection, beyond a user-/fixture-authored style and ADR.
- Full runtime, data, deployment and security multi-view generation. Phase 2 covers **structural and typed relationship views** only.
- Universal optimality/correctness claims and autonomous application implementation.

These are future milestones, not hidden features of the current generator.