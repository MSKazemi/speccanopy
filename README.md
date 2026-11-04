# Speccanopy

**Speccanopy** aims to become a **universal, AI-assisted software architecture design engine** that turns requirements into coherent, validated, implementation-ready architecture specifications across application types and architecture styles.

**Confirmed product boundary:** Speccanopy designs software architecture; it does **not** autonomously implement, build, test, or deploy the software applications it designs.

## Adaptive Recursive Architecture Design (ARAD)

ARAD is a proposed, architecture-style-independent method for developing software architecture by recursively identifying and specifying the most important subcomponents of a system.

The algorithm is **adaptive in breadth and depth**: a component may be decomposed into zero to ten children, and decomposition stops when a component is sufficiently specified, not when an arbitrary number of levels has been reached.

The decomposition tree is complemented by a dependency/interaction graph, multiple architecture views, explicit quality-attribute analysis, validation, and an implementation roadmap.

**Read the complete design proposal:** [docs/adaptive-recursive-architecture-design.md](docs/adaptive-recursive-architecture-design.md).

**Vision and scope:** [docs/vision-and-goal.md](docs/vision-and-goal.md).

**MVP delivery plan:** [docs/mvp-implementation-plan.md](docs/mvp-implementation-plan.md).

**Execution roadmap:** [docs/execution-roadmap.md](docs/execution-roadmap.md).

**Executable architecture contract:** [docs/architecture-contract.md](docs/architecture-contract.md).

**Phase 2 recursive engine guide:** [docs/phase2-engine.md](docs/phase2-engine.md).

## Status

**Phases 1–2 are implemented:** validated architecture contracts and a deterministic recursive generator using curated proposal fixtures. It supports variable depth/breadth, priority scoring, budget-aware stopping, requirement traceability, typed relationships, Mermaid diagrams, CLI exports, and 57 locally passing tests. **AI-driven proposals, independent architecture-quality evaluation, and automatic style selection are not implemented yet.**

## Next implementation steps

1. Add architecture-style comparisons and explicit quality-attribute review beyond structural validation.
2. Introduce an AI-backed proposer behind the existing `ComponentProposer` interface with provenance, schema checks and human review.
3. Benchmark on additional held-out application types; calibrate priority heuristics and quality scores.

## Run Speccanopy

Requires Python 3.11+ and Pydantic 2:

```bash
python -m pip install -e '.[dev]'
pytest -q
speccanopy design examples/ecommerce.json --output out/ecommerce
speccanopy design examples/file-transfer.json --output out/file-transfer
```

Alternatively run `PYTHONPATH=src python -m speccanopy.cli design examples/cli-utility.json --output out/cli-utility` without installing a console script.

**Important:** The current `design` command reads a brief plus a curated `<brief>.design.json` proposal fixture; it does **not** independently design arbitrary new applications from prose. Each run writes `architecture.json`, two Mermaid diagrams, a requirement coverage report, an ADR/findings report, and a generation trace. The included examples remain `draft` rather than being independently verified.

## Background

Documented from the architecture-design discussion on 2026-11-04.
