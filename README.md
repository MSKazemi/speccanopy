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

## Status

**Phase 1 executable foundation is implemented:** typed application and architecture schemas, a deterministic component-proposer interface, an example architecture fixture, and 31 locally passing contract tests. **The adaptive recursive architecture generator is not implemented yet.** Its scoring weights, depth guidelines, and stopping conditions remain heuristics to evaluate on real-world examples.

## Next implementation steps

1. Define a machine-readable schema for requirements, architecture nodes, relationships, and validation evidence.
2. Implement candidate-style evaluation, priority scoring, and adaptive decomposition.
3. Generate structural, runtime, data, deployment, and security/quality views.
4. Add requirement coverage checks, architecture decision records, and quality-attribute validation.
5. Test against contrasting applications: simple utility, modular monolith, event-driven system, microservices platform, and embedded system.

## Run the Phase 1 foundation

Python 3.11+:

```bash
python -m pip install -e '.[dev]'
pytest -q
```

Validate the example input and architecture draft:

```bash
python -c "from pathlib import Path; from speccanopy.models import SystemBrief, ArchitectureSpec; brief=SystemBrief.model_validate_json(Path('examples/cli-utility.json').read_text()); arch=ArchitectureSpec.model_validate_json(Path('examples/cli-utility-architecture.json').read_text()); print(brief.system, arch.status, arch.coverage_report().model_dump())"
```

The local tests were run with Python 3.13 and Pydantic v2; the GitHub Actions workflow tests Python 3.11 and 3.13.

## Background

Documented from the architecture-design discussion on 2026-11-04.
