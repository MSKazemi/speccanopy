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

**Phase 4 AI-assisted proposals and approval:** [docs/phase4-ai-proposals.md](docs/phase4-ai-proposals.md).

## Status

**Phases 1–4 are implemented as prototypes:** typed architecture contracts, deterministic recursive generation, advisory style/quality review, and an optional AI-assisted component proposer with strict schema validation, bounded model calls, provenance and explicit human-acknowledgement workflow. **120 tests passed locally** (including the existing 91 tests). A scripted offline example is reproducible. **The live Responses API adapter has mocked transport tests only—no paid model call has been performed in this milestone.** AI outputs remain incomplete architecture drafts and need human review; independently validated architecture generation and full design refinement are not implemented.

## Next implementation steps

1. Evaluate AI-generated component boundaries against expert-reviewed benchmark architectures across additional application domains.
2. Add bounded targeted architectural critique and refinement based on Phase 3 review findings, not merely schema repair.
3. Add provenance and human review for interfaces, data ownership, integration contracts and quality-attribute decisions.

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

Draft **model-proposed component boundaries** from a validated brief:

```bash
export OPENAI_API_KEY='your-api-key'
speccanopy propose-ai examples/cli-utility.json \
  --model YOUR_AVAILABLE_MODEL --output out/ai-cli

# Inspect out/ai-cli/proposal-review.md and ai-proposals.json first.
speccanopy approve-ai out/ai-cli/ai-proposals.json \
  --reviewer architecture-reviewer --acknowledge-review \
  --output out/ai-cli/approved.design.json
speccanopy design examples/cli-utility.json \
  --fixture out/ai-cli/approved.design.json --output out/ai-cli/approved-design
```

For offline testing without an API key, add `--backend scripted --responses examples/ai-scripted-cli.json` to `propose-ai`. This uses authored test responses, **not** a real AI model. The resulting architecture is still `incomplete_requires_review`: proposal approval is not architecture certification. See the Phase 4 guide for privacy and scope limitations.

Alternatively run `PYTHONPATH=src python -m speccanopy.cli design examples/cli-utility.json --output out/cli-utility` without installing a console script.

**Important:** The `design` command uses curated `<brief>.design.json` proposal fixtures; it does **not** independently design arbitrary applications from prose. The new `review` command uses explicit `<brief>.review.json` drivers and quality scenarios; its recommendations are heuristic, not certifications. The included architectures remain `draft` and require human approval.

## Background

Documented from the architecture-design discussion on 2026-11-04.
