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

**Phase 5 controlled refinement and reference evaluation:** [docs/phase5-refinement-evaluation.md](docs/phase5-refinement-evaluation.md).

**Phase 6 architecture research and multiple alternatives:** [docs/phase6-architecture-research.md](docs/phase6-architecture-research.md).

## Status

**Phases 1–6 are implemented as research prototypes:** typed architecture contracts, bounded recursive generation, advisory style/quality reviews, structured AI proposals with human acknowledgement, targeted refinement, and a provenance-aware multi-alternative research evaluator. **178 tests passed locally** on Python 3.13 before committing.

**Phase 6 evaluation boundaries:** The suite uses five synthetic application briefs and six candidate architectures spanning CLI, e-commerce, file transfer, embedded control and telemetry. Criteria refer to requirement ownership, interfaces, data and interactions rather than exact component IDs. **There are no independently authenticated expert reviews or genuinely blind held-out cases.** Source-bound review claims are self-declared and remain unverified. No live paid-model API call or empirical correctness certificate is claimed.

## Next implementation steps

1. Recruit independent qualified reviewers and gather permissible architecture briefs and multiple acceptable design alternatives with verifiable evidence.
2. Build a genuinely unseen evaluation set and compare semantic quality, security, distributed consistency, resilience and safety/timing failures against professional judgments.
3. Calibrate the critique/refinement engine on reviewer disagreements without relaxing deterministic validation, provenance or human decision gates.

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

Preview a **human-authored, two-round refinement** and compare it to a curated structural rubric:

```bash
speccanopy refine-plan examples/generated/ecommerce/architecture.json \
  --config examples/ecommerce.review.json \
  --edits examples/refinement/ecommerce.edits.json \
  --output out/refinement-preview
speccanopy benchmark examples/generated/ecommerce/architecture.json \
  --candidate out/refinement-preview/candidate-preview.json \
  --config examples/ecommerce.review.json \
  --rubric examples/refinement/ecommerce.rubric.json \
  --output out/refinement-benchmark
```

The preview is **not** approved. Releasing a revision requires `speccanopy refine-apply ... --reviewer YOUR_ID --acknowledge-review`; this records a self-declared review acknowledgement, not independent architecture certification.

Evaluate competing architectural alternatives and the synthetic research suite:

```bash
speccanopy research-case examples/research/cases/ecommerce.json --architecture examples/research/candidates/ecommerce-distributed-unreviewed.json --output out/research-ecommerce
speccanopy research-suite examples/research/suite.json --output out/research-suite
```

The research cases are **curated and unreviewed**. The public_holdout partition is a visible regression fixture, not an independent blind benchmark. These commands check architecture documentation signals, not architectural correctness.

Alternatively run `PYTHONPATH=src python -m speccanopy.cli design examples/cli-utility.json --output out/cli-utility` without installing a console script.

**Important:** The `design` command uses curated `<brief>.design.json` proposal fixtures; it does **not** independently design arbitrary applications from prose. The new `review` command uses explicit `<brief>.review.json` drivers and quality scenarios; its recommendations are heuristic, not certifications. The included architectures remain `draft` and require human approval.

## Background

Documented from the architecture-design discussion on 2026-11-04.
