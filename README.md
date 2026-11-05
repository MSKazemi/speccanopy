# Speccanopy

**START HERE — [Complete Claude Code user guide](docs/USER_GUIDE.md)**: what input to provide, exact commands, generated outputs, subscription vs. API billing, new vs. existing projects, and troubleshooting. [Browse all documentation](docs/README.md).


**Independent architecture reviewers wanted:** Help critically evaluate two **public synthetic** designs in a voluntary research pilot. [Volunteer as a reviewer](https://github.com/MSKazemi/speccanopy/issues/3) · [Suggest a rights-cleared benchmark case](https://github.com/MSKazemi/speccanopy/issues/4) · [Contribution guide](CONTRIBUTING.md).

*There are no independently authenticated expert reviews or permissioned real-world benchmark cases in the repository yet. Do not share private materials through public issues or pull requests.*

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

**Phase 7 external reviewer protocol:** [docs/phase7-expert-panel.md](docs/phase7-expert-panel.md).

**Claude Code and Claude API integration:** [docs/claude-integration.md](docs/claude-integration.md). **AI-only case review:** [docs/ai-assisted-case-review.md](docs/ai-assisted-case-review.md).

**Phase 5 controlled refinement and reference evaluation:** [docs/phase5-refinement-evaluation.md](docs/phase5-refinement-evaluation.md).

**Phase 6 architecture research and multiple alternatives:** [docs/phase6-architecture-research.md](docs/phase6-architecture-research.md).

## Status

**Phases 1–6 are implemented as prototypes:** typed contracts, deterministic recursion, rule-based style and quality review, optional AI candidate proposals with human acknowledgement, controlled refinement, and multi-alternative synthetic research evaluation.

**Phase 7 has a reviewer-coordination workflow:** the `speccanopy-experts` CLI creates candidate-source-blinded architecture packets, blank expert review templates, a restricted private source manifest and an aggregation of self-declared reviews. Evidence is bound to case and packet SHA-256 digests, and disagreements are reported without automatic architectural certification. **There are no independently authenticated expert assessments or genuinely private holdout results yet.** Test status is reported by the GitHub Actions workflow.

**Quick start for Claude Code:** [What input to give and which files you receive](docs/claude-code-quickstart.md). Includes copyable commands for a separate existing app and a full output directory tree.

## Document a real project

**Partially ready:** Speccanopy can generate a reviewable structured architecture, two Mermaid views, requirement coverage and an architecture review; it does **not** yet scan an arbitrary source repo or generate a full Markdown architecture documentation pack automatically.

Follow the [practical project-documentation guide](docs/project-documentation-readiness.md) to use Claude Code for requirements/source discovery, Speccanopy for validated structure and review, and Claude Code again for narrative documents. [Issue #5](https://github.com/MSKazemi/speccanopy/issues/5) tracks the missing one-command documentation workflow.

**Claude Code subscription users:** You can use Speccanopy from the Claude Code terminal **without buying a separate API key**. Claude Code can create the structured inputs and run local `speccanopy design` / `review` under your subscription. Only the optional direct `propose-ai --backend claude` HTTP integration requires Anthropic API access. [Subscription vs API guide](docs/claude-integration.md#claude-subscription-versus-anthropic-api-key). To avoid unintended API charges when using Claude Code, keep `ANTHROPIC_API_KEY` unset.

## Using Speccanopy with Claude

Speccanopy is compatible with **Claude Code**: open this repository using `claude` and the checked-in `CLAUDE.md` explains the project rules, test commands and evidence-bound AI architecture review. No Anthropic API key is required for local deterministic reviews.

To generate model-proposed components through the separate **Claude Messages API**, set `ANTHROPIC_API_KEY` and use a model available to your account:

```bash
speccanopy propose-ai examples/cli-utility.json \
  --backend claude --model YOUR_CLAUDE_MODEL_ID \
  --output out/claude-draft
```

**AI review is useful but not equivalent to an independently authenticated expert review.** The worked [AI desk critique](docs/ai-assisted-case-review.md) makes concrete, source-linked observations on e-commerce, CLI and file-transfer architecture drafts; it is not production certification and does not fulfill human-research Issue #2. Live Claude API behavior has mocked transport coverage only.

## Participate in independent architecture research

Speccanopy needs **real human evaluation**, not just additional synthetic scores. The public calls below are open:

- [Volunteer as an independent architecture reviewer](https://github.com/MSKazemi/speccanopy/issues/3) — start with a nonconfidential synthetic e-commerce pilot.
- [Propose a permissioned real-world or public-source case](https://github.com/MSKazemi/speccanopy/issues/4) — links and non-sensitive metadata only.

Read the [reviewer recruitment guide](docs/reviewer-recruitment.md), [case permissions and intake](docs/benchmark-case-intake.md), and [public research source triage](docs/public-case-source-triage.md). Ready-to-adapt [outreach messages](docs/outreach-messages.md) are available.

**Status:** Invitations have been posted in this repository; there are **no verified independent expert submissions or accepted real-world cases recorded here**. Volunteering, identity/consent verification and any secure case sharing require follow-through by human participants and the study coordinator. **Never submit private personal or customer details in public GitHub issues.**

## Next research actions

1. Recruit qualified independent software architects for Issue #2 and obtain lawful de-identified real-world cases.
2. Verify reviewers' identities, competence, independence and consent **outside the software**; do not treat declared IDs or hashes as signatures.
3. Collect at least two independently verified reviews per candidate, preserve disagreements and domain-specific failures, and calibrate rule-based evaluations against these assessments without exposing the private holdout.
4. Only then claim evidence of improvement in semantic architectural quality; never claim universal optimality.

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

## Prepare independent architecture review packets

```bash
speccanopy-experts prepare examples/expert-review/ecommerce-study.json \
  --output out/ecommerce-panel
speccanopy-experts aggregate out/ecommerce-panel/private/manifest.json \
  --submissions out/ecommerce-panel/submissions \
  --output out/ecommerce-panel/report
```

The example contains no genuine reviewer assessments; the aggregate must remain `awaiting_reviewers`. Keep private manifests, submissions and holdouts outside GitHub. See the [expert-panel protocol](docs/phase7-expert-panel.md).

## Background

Documented from the architecture-design discussion on 2026-11-04.
