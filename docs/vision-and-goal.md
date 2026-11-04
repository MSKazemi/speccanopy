# Speccanopy vision and goal boundaries

**Status:** Final product goal confirmed by user — Option A (Universal Software Architect)  
**Confirmed:** 2026-11-04

## Final goal

**Speccanopy is a general-purpose, AI-assisted software architecture design engine — not an automatic software implementation or deployment system.**

Given an application idea, requirements, domain constraints and quality expectations, Speccanopy should produce a coherent, traceable, sufficiently detailed, and implementation-ready **architecture specification**. The goal is applicability across diverse kinds of software and architecture styles, while making uncertainties and validation limits explicit.

### Key capabilities

1. Understand requirements, stakeholders, core use cases, constraints and quality targets.
2. Compare and select appropriate architecture styles (for example: monolithic, modular monolith, microservices, layered, hexagonal, event-driven, serverless, and hybrids).
3. Apply **adaptive recursive decomposition**: for every relevant system/component, identify necessary children (conceptually X → Y → Z → Q → ...), selecting branch-specific breadth and depth.
4. Specify each component's responsibility, boundaries, interfaces, dependencies, data ownership, runtime behavior and relevant quality attributes.
5. Produce a **decomposition tree plus relationship graph**, with structural, runtime, data, deployment-design, and security/quality views.
6. Evaluate coverage, coupling, trade-offs, reliability, performance, security and operational constraints; revise affected architecture elements when gaps are found.
7. Stop refining a component when it is sufficiently specified for implementation, or explicitly report unresolved decisions, assumptions, risks and incomplete validation.
8. Deliver developer/agent-consumable specifications: machine-readable architecture, diagrams, interface contracts, design decisions, verification criteria, and implementation guidance.

### Explicitly out of scope for the final product

Speccanopy is **not** intended to autonomously write the application's production code, run its application-level build/test pipeline, or deploy the resulting application. It may describe implementation, test, and deployment architectures, but **designing** these is different from **executing** them.

Speccanopy's own code and automated tests are, of course, necessary to develop and validate the architecture engine itself; the exclusion above concerns the **applications that Speccanopy designs**.

## Meaning of universal

"Universal" expresses the target breadth of application domains and styles, **not** a promise that a finite recursive algorithm can guarantee universally correct or optimal architecture. Domain expertise, unresolved requirements and human review may remain essential.

A design should report evidence and gaps honestly, not claim completion solely because its decomposition reached a specified depth, breadth or time budget.

## Core innovation

The algorithm does not hard-code a universal X, Y, Z, Q or a fixed decomposition depth. It adapts the number of architectural components and the number of levels to each problem and each branch, subject to coverage, quality, explicit stop criteria and bounded refinement.

A tree alone is insufficient: interactions, quality attributes and multiple architecture views are part of the deliverable.

## Relationship to milestones

The [MVP implementation plan](mvp-implementation-plan.md) is a **first experimental slice of the architecture-design engine**, not the final capability set. It will prove typed models, recursion, stopping rules, requirements traceability, and validation across contrasting example applications.

See [ARAD design specification](adaptive-recursive-architecture-design.md) for the proposed method.

## Product success criterion

For a representative application brief, a reviewer should be able to understand why the selected style and component boundaries were chosen, trace mandatory requirements to architecture elements, inspect cross-component contracts and failure paths, identify known unknowns, and hand the output to software developers or coding agents for implementation without major unresolved architectural design work.
