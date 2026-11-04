# ARAD MVP implementation plan

**Status:** Proposed next milestone  
**Created:** 2026-11-04  
**Source:** [ARAD design specification](adaptive-recursive-architecture-design.md)

## Objective

Build a small but executable **Adaptive Recursive Architecture Design (ARAD)** engine. It should accept one application brief plus structured requirements/constraints and generate:

1. A recursively decomposed component hierarchy with independent breadth and depth per branch.
2. A cross-component relationship graph and clear component contracts.
3. A traceability report mapping mandatory requirements to architecture elements.
4. An explicit list of risks, assumptions, blocked decisions, and validation findings.

The goal is a **reviewable architecture draft**, not a claim of universally correct architecture.

**Confirmed product scope (Option A):** Speccanopy is an architecture-design engine, not an automatic application builder. The engine may produce implementation instructions, testing strategies, and deployment designs, but it does not itself generate, build, test or deploy the applications being designed. Automated tests in this MVP evaluate **Speccanopy's engine**, not the generated application's code. See [the confirmed vision](vision-and-goal.md).

## First implementation decision

**Use Python for the initial CLI proof of concept**, keeping the AI/LLM provider behind an interface.

Suggested base stack:
- Python with type annotations
- Pydantic (or equivalent) for input/output schema validation
- pytest for deterministic tests
- JSON for exchange format; Mermaid or Graphviz for diagrams
- Pluggable `ComponentProposer` interface for a deterministic fixture proposer first, then an optional AI-backed proposer

Avoid a frontend, agent swarm, external database, deployment platform, or hard-coded microservice bias in the first iteration.

## Minimum input contract

Example `examples/ecommerce.json`:

```json
{
  "system": "E-commerce application",
  "goals": ["Sell products online"],
  "actors": ["Customer", "Administrator"],
  "functional_requirements": [
    {"id": "FR-001", "statement": "Customers can browse the catalog", "mandatory": true},
    {"id": "FR-002", "statement": "Customers can place an order", "mandatory": true},
    {"id": "FR-003", "statement": "Customers can pay for an order", "mandatory": true},
    {"id": "FR-004", "statement": "Customers can track an order", "mandatory": true}
  ],
  "quality_requirements": [
    {"id": "NFR-001", "attribute": "security", "statement": "Payment-related operations require authorization"}
  ],
  "constraints": {
    "preferred_architecture": null,
    "max_depth": 6,
    "max_nodes": 150,
    "max_refinement_rounds": 3
  }
}
```

The implementation must preserve all input IDs and should make assumptions explicit rather than fabricating facts.

## Minimum output contract

Output directory:

```text
out/
  architecture.json       # normalized components, hierarchy, relationships and selected style
  architecture.mmd        # diagram of component tree (initially) plus links when practical
  requirements-report.json # mandatory requirements mapped to components and validation results
  decisions.json          # architectural decisions, tradeoffs and unresolved questions
```

**Architecture schema:**
- `system`: name, goals, assumptions, selected style and considered candidates
- `components[]`: stable id, parent id, responsibility, relevant requirements, interface/contracts, dependencies, owned data, quality targets, risk, priority, status
- `relationships[]`: source, target, kind, protocol/semantics, relevant requirements
- `validation`: uncovered requirements, unresolved risks, warnings, validation status
- `generation`: limits, version, proposer identity, iteration count

Use separate IDs for requirements, components, edges, decisions, and tests. Do not duplicate node records in nested recursive JSON.

## Milestone 1: Core schema and recursion

**2026-11-04 progress:** Initial typed models, deterministic proposer, and contract tests implemented. 31 tests passed locally on Python 3.13; continuous integration was configured but its GitHub run has not yet been verified. The decomposer, priority queue, automatic stop logic, generated output, and full cross-domain fixtures are still pending.

Milestone 1: Core schema and recursion

**Implementation tasks (in recommended order):**

- [x] Create package structure (`src/speccanopy/`) and test runner.
- [x] Define typed `SystemBrief`, `Requirement`, `Component`, `Relationship`, `Decision`, and `ValidationFinding` models.
- [x] Implement a `ComponentProposer` protocol, initially backed by deterministic in-memory fixtures.
- [ ] Implement a priority queue for nodes needing decomposition; support independent child counts and depths.
- [ ] Implement loop termination: sufficiently specified, blocked, budget exceeded, cycle/duplicate found.
- [ ] Implement stable component IDs, local coverage checks and parent-child consistency checks.
- [ ] Generate normalized JSON and Mermaid tree output from one input file.
- [ ] Add basic mandatory-requirement coverage checks and report missing coverage.
- [ ] Add structured traces explaining why each component was expanded or stopped.
- [ ] Add CLI: `speccanopy design examples/ecommerce.json --output out`.

**Initial stop predicate:** a node has well-defined scope, necessary interface contracts, dependencies/data ownership (or explicit N/A), relevant quality targets, and implementation/test readiness evidence. If a decision cannot be resolved, label the node `blocked` or `requires_review`. Never mark a node `ready` merely because a depth or token budget was hit.

**Guardrails:** start with a preferred breadth of 3–7 and a display cap of 10 children, with documented exceptions for mandatory coverage. Set bounded depth, node count, and refinement iterations. Prevent self-links, cycles in containment, and duplicate/conflicting component IDs. Relationship cycles are allowed when intentional and documented.

## Milestone 2: Architecture reasoning and validation

- [ ] Add optional architecture-style candidates with justification: modular monolith, microservices, event-driven, layered, hexagonal, or hybrid.
- [ ] Introduce a configurable design priority score (value, risk, dependency, quality impact, uncertainty); do not treat the score as permission to omit required functionality.
- [ ] Add relationship graph modeling: calls, events, data ownership and trust boundaries.
- [ ] Add quality-attribute and end-to-end scenario validation.
- [ ] Record ADR-style decisions and tradeoffs.
- [ ] Implement a bounded targeted-refinement loop.

## Milestone 3: AI-backed component proposer

- [ ] Use a provider interface rather than direct dependencies throughout core logic.
- [ ] Require model outputs to validate against typed schemas.
- [ ] Distinguish model-proposed facts from user-provided requirements.
- [ ] Detect overlap, missing coverage, and unsupported assertions.
- [ ] Preserve traces and support human review/overrides.
- [ ] Evaluate variability across repeated runs with the same input.

The AI provider may propose components, but deterministic code enforces budgets, schema consistency, mandatory coverage and stop status.

## Acceptance tests for first executable slice

Test against at least three contrasting applications:

1. **E-commerce** — catalog, ordering, payment and inventory, plus authorization.
2. **File transfer** — protocol adapters, retries, metadata and security.
3. **Simple CLI utility** — should stop early rather than create unnecessary services.

**Definition of done:**
- All three inputs generate schema-valid output with a rooted, acyclic containment tree.
- Every mandatory requirement is either traced to a component and verification case or explicitly reported as uncovered (never silently dropped).
- Each expanded node contains its selected children; leaf nodes have zero children.
- Breadth and depth vary by branch based on evidence, not fixed X/Y/Z/Q values.
- Budgets always terminate; exhausted budgets produce an explicit incomplete status.
- Relationships refer only to valid component IDs.
- Repeated deterministic fixture runs produce the same architecture and trace.
- Unit tests cover invalid input, absent requirements, duplicate IDs, self-references, uncovered coverage, and budget exhaustion.
- The output includes a list of assumptions, decisions and unresolved risks.

## Repository layout target

```text
README.md
docs/
  adaptive-recursive-architecture-design.md
  mvp-implementation-plan.md
examples/
  ecommerce.json
  file-transfer.json
  cli-utility.json
src/speccanopy/
  models.py
  scoring.py
  proposer.py
  decomposer.py
  validator.py
  exporters.py
  cli.py
tests/
  test_models.py
  test_decomposer.py
  test_coverage.py
  test_exporters.py
pyproject.toml
```

## Deliberately deferred

UI, hosted workflows, PR automation, production infrastructure, optimization claims, universal architecture correctness, and detailed deployment/service discovery. These should be considered after the engine passes cross-domain acceptance tests.

## First coding action

**Create `src/speccanopy/models.py`, `src/speccanopy/proposer.py`, and `tests/test_models.py` together.** Define validated models and a deterministic proposer fixture before adding recursive AI prompting. This creates a testable foundation and constrains the rest of the system.
