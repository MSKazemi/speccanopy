# Speccanopy execution roadmap — Universal Software Architect

**Status:** Active roadmap; Phases 1–6 have executable research prototypes, with Phase 6 multi-alternative evaluation and an outstanding independent expert review milestone (2026-11-05).  
**Date:** 2026-11-04  
**Product boundary:** Speccanopy designs and validates architecture; it does not autonomously implement, build, test or deploy the software applications being designed.

Read alongside [vision-and-goal.md](vision-and-goal.md), [adaptive-recursive-architecture-design.md](adaptive-recursive-architecture-design.md), and [mvp-implementation-plan.md](mvp-implementation-plan.md).

## Immediate next milestone — first external review pilot (checked 2026-11-05)

**Current evidence gate:** The Phase 7 reviewer collection tooling, recruitment forms and GitHub invitations exist. [Reviewer Issue #3](https://github.com/MSKazemi/speccanopy/issues/3) and [benchmark case Issue #4](https://github.com/MSKazemi/speccanopy/issues/4) currently have **zero public responses**. [Research Issue #2](https://github.com/MSKazemi/speccanopy/issues/2) remains open. No real independent-review or permissioned-real-case results should be claimed.

**The next meaningful result is human evidence, not another synthetic score.**

1. **Recruit:** the maintainer shares the [volunteer call](https://github.com/MSKazemi/speccanopy/issues/3) with suitable architects. Privately screen and obtain informed consent from at least **two independently verified qualified people** for each candidate. A public GitHub comment does not count as verification or consent.
2. **Pilot:** once reviewers genuinely agree, use the public synthetic [e-commerce study](../examples/expert-review/ecommerce-study.json) and [Phase 7 protocol](phase7-expert-panel.md) to distribute candidate-source-blinded packets, receive private assessments and record disagreement. The pilot is **not** a truly blinded holdout, because the candidate architectures are public.
3. **Report:** evaluate whether reviewers consistently identify missing interface/data-consistency/security risks, report disagreement and false positives/negatives, and publish only anonymized, permissioned findings. If no reviewers participate, report "not started" rather than inventing results.
4. **Real-world evidence:** in parallel, source one non-sensitive or de-identified application brief with written rights for review; prepare a genuinely unseen holdout under access controls only after lawful permission and a frozen protocol.
5. **Optional technical parallel track:** improve explicit runtime/data/deployment-*design* views and semantic review prompts, but do not treat those as evidence of architecture correctness until independently assessed.

**Exit criterion:** at least two actually verified, consented, independent reviewer reports for each pilot candidate, with issues/disagreements preserved and a limitations report; then seek a separately permissioned, unseen real-world evaluation. The review software's passing tests are not substitutes for those reports.

## Documentation productization track (2026-11-05)

**Assessment:** The prototype is usable for guided architecture documentation on a real project but **not** ready as an autonomous documentation generator. `design` requires a per-project fixture; `propose-ai` only proposes component hierarchies; `review` emits advisory review Markdown; `document` now emits a baseline architecture Markdown pack. Source-code inspection, factual provenance and ongoing synchronization are still not built in.

**Priority P0:** a source-aware Claude Code intake with provenance, **extension of the implemented baseline documentation renderer**, explicit observed/proposed/unknown status gates, and a tested end-to-end application example. **Priority P1:** change-aware regeneration, richer runtime/data/deployment views and optional alternate publishing formats.

Use [the realistic getting-started guide](project-documentation-readiness.md) today. [Issue #5](https://github.com/MSKazemi/speccanopy/issues/5) tracks the full backlog. This usability track can proceed **in parallel** with independent research Issue #2; absence of external experts does not prevent drafting personal project documentation, but it limits claims of architecture quality.

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

**Progress (2026-11-05):** A provider-neutral, Responses API structured-output adapter now proposes component boundaries from a `SystemBrief`; strict local schema and requirement-ID checks, bounded model requests/schema repairs, SHA-256 provenance, explicit `pending_human_review` output and an approval receipt are implemented. The offline scripted path and mocked transport have tests; a live paid model call has **not** been made. Approval releases a hierarchy for further design, never marks it architecturally validated. Semantic critique-driven redesign, source-quality evaluations and authenticated review are still pending. See [Phase 4 guide](phase4-ai-proposals.md).

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

**Completed as test-driven prototypes:** architecture contracts, bounded recursive generator, advisory style/quality reviewer, and model-backed component *proposals* with structured output, provenance and an explicit human acknowledgement gate. **Next:** empirical benchmarking and bounded targeted *architectural* refinement, plus richer runtime, data and deployment-design views. The goal remains architecture design, not application building. See [Phase 4](phase4-ai-proposals.md).

## Phase 5 implementation update (2026-11-05)

**Implemented:** finding-specific, human-authored patch requests, bounded refinement simulation, integrity-checked review previews, per-round quality re-review, invalidation of affected prior verification evidence, an explicit reviewer acknowledgement gate and weighted structural reference rubrics. See [Phase 5 refinement and evaluation](phase5-refinement-evaluation.md).

**Measured only on curated fixtures:** The e-commerce two-round preview addresses three deterministic interaction-contract findings and changes the authored structural rubric from 51.22% to 100% (11/11 criteria). This does **not** prove real-world architectural correctness or expert review. The CLI baseline scores 100% (7/7) on its narrow curated rubric; file transfer scores 79.31% (6/8). All rubrics remain **curated_unreviewed**.

**Next:** obtain independently expert-reviewed reference architectures across several domains and design alternatives, calibrate semantic quality reviews and evaluate optional AI-generated targeted proposals under the existing approval gates. No target application code generation is planned.

## Phase 6 implementation update (2026-11-05)

**Implemented:** Five curated synthetic application briefs and six candidate architecture entries; alternative-style matching without exact component ID dependence; requirement-linked documentation criteria; provenance and content-digest review claims; split-aware non-certifying reports; adversarial tests for missing owners, invalid links, duplicated data and unsupported styles. See [Phase 6 research evaluation](phase6-architecture-research.md).

**Not yet accomplished:** Real externally authenticated expert assessments, blind held-out comparisons, calibrated semantic correctness metrics, professional review of security/safety/operational trade-offs. Public holdout fixtures are visible and are not genuine independent holdouts. All reviewer claims remain unauthenticated self-declarations.

**Next:** Recruit independent experts and collect non-sensitive or licensed design cases with alternative acceptable solutions; record provenance, review disagreements and false-positive/false-negative rates; perform genuinely withheld tests. Maintain architecture-only product scope and human decision controls.

## Phase 7 — Collect authentic external evaluations

**Software status:** Candidate-blinded packet preparation, response schema/consent/conflict validation and provisional disagreement aggregation implemented. Study and packets are bound to the original Phase 6 research case and candidate digests. See [Phase 7 protocol](phase7-expert-panel.md).

**Research status:** No independently verified human reviews, licensed real-world benchmark set or genuinely hidden holdout has been collected. The code **cannot** verify an expert's identity or competence; that work requires people and an offline attestation process. Keep [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2) open until authentic reviews and evidence exist.
