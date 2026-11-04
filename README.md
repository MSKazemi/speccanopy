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

**Phase 3 architecture review guide:** [docs/phase3-review.md](docs/phase3-review.md).

## Status

**Phases 1–3 are implemented:** validated architecture models, the deterministic recursive generator, and a separate rule-based architecture review CLI. Phase 3 compares primary architecture style candidates using explicit drivers, explains trade-offs, audits quality scenarios and interface/data risks, and records open evidence gaps. **91 tests passed locally.** Reviews do not automatically approve or alter a design. **AI-generated proposals and real-world architecture certification are not implemented yet.**

## Next implementation steps

1. Add an optional, provider-neutral AI proposer for architectural component candidates, with schema checks and provenance.
2. Evaluate proposed designs with human review and targeted refinement; keep acceptance separate from heuristic scores.
3. Expand held-out benchmarks, domain-specific quality rules, and support for hybrid architectural patterns.

## Run Speccanopy

Requires Python 3.11+ and Pydantic 2:

```bash
python -m pip install -e '.[dev]'
pytest -q
speccanopy design examples/ecommerce.json --output out/ecommerce
speccanopy design examples/file-transfer.json --output out/file-transfer
```

Run an **advisory architecture review** on an existing draft:

```bash
speccanopy review out/ecommerce/architecture.json \
  --config examples/ecommerce.review.json \
  --output out/ecommerce-review
```

This produces architecture-style comparisons, quality scenario findings, coverage reports and a Markdown review packet. Without explicit style drivers the reviewer abstains from style selection.

Alternatively run `PYTHONPATH=src python -m speccanopy.cli design examples/cli-utility.json --output out/cli-utility` without installing a console script.

**Important:** The `design` command uses curated `<brief>.design.json` proposal fixtures; it does **not** independently design arbitrary applications from prose. The new `review` command uses explicit `<brief>.review.json` drivers and quality scenarios; its recommendations are heuristic, not certifications. The included architectures remain `draft` and require human approval.

## Background

Documented from the architecture-design discussion on 2026-11-04.
