# Speccanopy vision and goal boundaries

**Status:** Working interpretation of the user's stated goal; final scope not yet confirmed  
**Updated:** 2026-11-04

## Established long-term objective

Build a general-purpose, architecture-style-independent software architecture design system. Starting from an application idea, requirements and constraints, it should derive a coherent, sufficiently detailed, and reviewable software architecture.

Its distinctive mechanism is **adaptive recursive decomposition**: each component is examined for its most important necessary subcomponents (conceptually X → Y → Z → Q → ...), but the number of children and decomposition depth vary across branches. There is no fixed universal number of layers.

The architecture engine should select or compare suitable styles (monolith, modular monolith, microservices, event-driven, serverless, hybrid, etc.), define interfaces and component interactions, model data and deployment boundaries, analyze security and other quality attributes, validate requirement coverage, and identify when a component is ready for implementation or needs review.

The output is more than a tree or a diagram. It should comprise structured architectural elements and relationships, assumptions, open decisions, validation evidence, and implementation guidance.

## Important limitation

“Universal” describes the intended *breadth of applicability* of the method. It does not mean the algorithm is proven to solve all architectural problems or that a finite decomposition guarantees correctness. Strong domain-specific analysis and human validation may remain necessary.

## Scope needing confirmation

**Unanswered question:** Is the ultimate deliverable (A) an architecture that developers/agents can implement, or (B) an end-to-end system that also generates, tests, and deploys working software?

Previous statements establish **architecture generation**. They do not yet establish **fully automatic software implementation and deployment**. Do not represent option B as an agreed requirement until confirmed.

## Relationship to MVP

The current [MVP implementation plan](mvp-implementation-plan.md) is a first experimental slice, not the final product goal. It tests typed architecture models, recursive decomposition, stopping rules, traceability and validation on multiple application classes.

See also [ARAD design specification](adaptive-recursive-architecture-design.md).
