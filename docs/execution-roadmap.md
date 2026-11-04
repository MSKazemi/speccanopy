# Speccanopy execution roadmap — Universal Software Architect

**Status:** Active roadmap; Phases 1–3 (contract, deterministic recursion, advisory quality/style review) implemented on 2026-11-04  
**Date:** 2026-11-04  
**Product boundary:** Speccanopy designs and validates architecture; it does not autonomously implement, build, test or deploy the software applications being designed.

Read alongside [vision-and-goal.md](vision-and-goal.md), [adaptive-recursive-architecture-design.md](adaptive-recursive-architecture-design.md), and [mvp-implementation-plan.md](mvp-implementation-plan.md).

## North-star outcome

Given a software application brief, Speccanopy produces a **reviewable, traceable, implementation-ready architecture specification** and explicitly identifies any assumptions, unresolved requirements, accepted risks or validation gaps.

A successful result consists of a requirements map, component decomposition, interactions/dependency graph, architecture-style decision with tradeoffs, major data and security boundaries, runtime/deployment *design* views, validation findings, and human-readable architecture documents. The target is broad applicability across domains, not guaranteed optimal or automatically correct architectures.

## Ordered roadmap and exit gates

### 1 — Define the architecture contract and evaluation rubric (do this first)

Deliver:
- Input schema: goals, actors, functional and quality requirements, constraints, assumptions and priorities.
- Output schema: architecture options/decision, nodes, typed edges, interfaces, data ownership, runtime and deployment views, quality targets, trace links, open questions and status.
- Readiness/stop states: `proposed`, `needs_decomposition`, `ready`, `blocked`, `requires_review`.
- Rules: required requirement IDs are never silently dropped; every claim can be traced to input evidence, model proposal or human decision; `ready` requires positive evidence.
- A small expert-review rubric: requirements coverage, responsibility coherence, coupling/dependency quality, quality-attribute tradeoffs, interaction completeness, unnecessary complexity and unresolved risks.

**Gate:** The schema can represent a small monolith and a distributed/event-driven system without hard-coding one architecture style. There is an unambiguous definition of a reviewable result and an incomplete result.

### 2 — Build a reproducible benchmark fixture set

Start with three contrasting cases:
1. Simple CLI utility: should require little or no nesting and no unnecessary services.
2. E-commerce: catalog, orders, payment authorization, inventory, consistency and failure paths.
3. File transfer: protocol adapters, retries, metadata, access control and recovery.

Later extend to event-driven processing, real-time/embedded systems, AI applications, and regulated/high-availability systems. For each fixture, provide requirements, constraints, expected critical responsibilities, acceptable alternative designs and known architecture risks. Avoid declaring a single reference tree uniquely correct.

**Gate:** Every case has a rubric and at least one critical omission the engine should detect. Different valid styles can be scored fairly.

### 3 — Implement the deterministic recursive core

Use Python with typed models and a replaceable `ComponentProposer` interface, initially backed by deterministic fixture proposals. Implement:
- Root creation, stable IDs, parent-child invariants and bounded priority queue.
- `k(v)` adaptive children per node, using a target of 3–7 and display cap around 10 as heuristics, **not mandatory coverage limits**.
- Stop/refine/blocked decisions based on evidence, not fixed depth.
- Containment-cycle prevention and relationship-reference checks.
- Local requirement coverage, traceability and explicit unresolved status on budget exhaustion.
- JSON output, simple Mermaid tree, and audit trace for node ranking/refinement.

**Gate:** All three fixtures produce schema-valid and deterministic artifacts; branching and depth vary; no infinite recursion; incomplete results are labeled correctly.

### 4 — Add style selection, dependency graph and architectural views

**Progress (2026-11-04):** Primary style comparison and deterministic quality-scenario/interaction checks are available through `speccanopy review`. The authored architecture is not overridden. Complete runtime, deployment, threat-analysis and data consistency views are still pending. See [Phase 3 review](phase3-review.md).

Compare candidate architecture styles based on functional constraints, team/operational complexity, data consistency, scaling, reliability and costs. Allow hybrid choices and decisions at subsystem level. Add:
- Typed dependencies (calls, events, shared resources and trust boundaries).
- Interface and data ownership contracts.
- Structural, runtime, data, deployment-*design* and quality/security views.
- Architecture Decision Records (ADRs) explaining choices and rejected alternatives.

**Gate:** A reviewer can identify critical integration points, data ownership, failure behavior and architecture rationale without relying on the hierarchy alone.

### 5 — Add AI proposals with controlled validation and human review

Introduce a provider-neutral AI adapter that proposes requirements questions, style candidates, component boundaries and targeted refinements. Apply schema validation and deterministic coverage/integrity checks to every proposal. Record provenance and confidence/uncertainty where meaningful.

Do **not** use an LLM's self-assessment as the only evidence of completeness. Treat controversial or high-risk decisions as reviewable. Limit all refinement cycles and report unresolved areas instead of fabricating success.

**Gate:** AI proposals improve the benchmark rubric scores versus deterministic fixtures, or clearly expose uncertainties, without erasing required coverage or breaking invariants.

### 6 — Cross-domain evaluation and first public release

Evaluate on held-out application briefs and expert-reviewed scenarios across different sizes and styles. Track:
- Mandatory requirement traceability/coverage rate.
- Critical gaps and risk findings found by review.
- Dependency consistency and interface specificity.
- Style-choice justification quality and excess architectural complexity.
- Ability to terminate and correctly flag unresolved work.
- Repeatability, cost and time to a reviewable design.

The first release should provide a CLI and structured artifacts. Only after the engine is proven useful should an interactive interface or broader integrations be prioritized.

**Gate:** Report strengths and limitations transparently and show evidence across multiple application types. Do not claim universal correctness.

## First coding ticket: Schema + fixture + test

**Recommended next executable slice:**
1. Add `pyproject.toml` with a minimal package and test runner.
2. Add `src/speccanopy/models.py`: typed `SystemBrief`, `Requirement`, `Component`, `Relationship`, `ArchitectureDecision` and `ValidationFinding`.
3. Add `src/speccanopy/proposer.py`: `ComponentProposer` protocol and deterministic fixture proposer.
4. Add `examples/cli-utility.json`: one minimal input.
5. Add `tests/test_models.py`: valid/invalid requirements, duplicate IDs, dangling parent IDs, invalid edges, and status/readiness validation.

**Acceptance:** `pytest` passes locally; example input validates; invalid inputs fail with understandable errors; outputs are JSON-serializable; the model is architecture-style-agnostic. No AI calls are required.

## Things not to build yet

- Autonomous application source-code generation, compilation, application tests or deployment.
- A polished website or broad integrations.
- A mandatory four-level hierarchy (X/Y/Z/Q).
- A fixed branch count or priority scoring formula treated as a universal law.
- Claims of correctness based on a diagram alone.

## Risks to track

- **Underspecified requirements:** ask focused questions or explicitly document assumptions.
- **Structural reductionism:** supplement containment tree with graph and runtime behavior.
- **AI hallucination and circular validation:** enforce schemas, provenance, independent checks and human review.
- **Overengineering:** avoid forcing distributed complexity onto small systems.
- **Benchmark bias:** use varied domains, requirements and acceptable alternative architectures.

## Decision summary

**Completed:** architecture contracts, three curated recursive architecture fixtures, and an advisory style/quality reviewer with explicit driver scoring, scenario checks and auditable outputs. **Next:** a schema-constrained AI component proposer, source provenance, targeted refinement and human approval. The goal remains architecture design, not autonomous application building. See [Phase 3 review](phase3-review.md).
