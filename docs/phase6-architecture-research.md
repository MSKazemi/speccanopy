# Phase 6 — Multi-alternative architecture research harness

**Status:** Executable research/evaluation **prototype**, using synthetic and maintainer-curated cases. **No independently expert-reviewed cases have been acquired or validated yet.**

**Confirmed product goal:** Speccanopy is an architecture *design* engine. It does not build, test, or deploy the target software applications.

## What this milestone addresses

The earlier `benchmark` command evaluates exact component IDs and relationships against a human-authored structural rubric. It is useful for regression tests but can unfairly penalize another reasonable architecture with different component names, boundaries, or an alternative style.

Phase 6 introduces a **separate, provenance-aware research harness**. Each `ResearchCase` binds to one immutable application brief and declares:

- A source and explicit origin: `synthetic_curated`, `published_source`, or `contributed` (source URL required for the latter two).
- A declared dataset split (`development` / `public_holdout`). The repository's publicly checked-in `public_holdout` cases are **not private, independent, or blind holdouts**; they only exercise the split-aware reporting code.
- **Common requirements** which every candidate architecture should satisfy.
- One or more **acceptable alternative design paths**, each with a permitted primary style family and its own explainable criteria. They are hypotheses, **not proven equivalent or valid designs**.
- Optional **self-declared** reviewer claims, with a source URL, method, review date, claimed expertise, independence declaration, and SHA-256 of the underlying research case. The system checks schema and content binding; it **cannot authenticate the person or prove their qualifications**.

The engine evaluates an `ArchitectureSpec` against common criteria and **all applicable alternatives**, then selects a diagnostic best path. It does **not** require the candidate's components to have the same IDs as the reference. It also refuses to infer an acceptable style when no family is recognizable or compatible.

## Check types and limitations

The rule-based research criteria are:

| Criterion | Signal checked (not semantic correctness) |
| --- | --- |
| `requirement_mapped` | At least one concrete non-root component claims responsibility for a requirement (single-node architectures can use the root) |
| `verification_link` | An architecture-level verification case references that requirement and a responsible component; may only be `planned` |
| `quality_target` | A requirement-owning component documents a quality-attribute target |
| `failure_contract` | An interface on a requirement-owning component states failure behavior |
| `interface_contract` | A requirement-owning component has a directional contract of the expected type |
| `typed_interaction` | A typed dependency/interaction traces to the requirement and touches a responsible component |
| `single_data_owner` | Exactly one requirement-owning component declares a specified data asset, matched by normalized *exact* label |

These conditions are **necessary evidence signals, not sufficient architecture quality checks**. Text can be imprecise or wrong; a declaration of “10 ms latency” is not a timing measurement; an interface marked “failure behavior” is not a proven safe failure mode. Exact data-label matching also misses synonyms and richer ownership semantics. Architecture-style family detection is a keyword heuristic, not deployment analysis.

### Safeguards

- The case brief must match the architecture's original `SystemBrief` exactly.
- Criterion IDs are unique, references must exist, quality targets must refer to quality requirements, irrelevant fields are rejected, and alternative style lists must be coherent.
- Reusable, bounded case/criterion schemas make evaluations reproducible.
- Alternatives with all **required** criteria satisfied take precedence over an alternative that merely scores higher on optional checks.
- Missing required common criteria, uncovered mandatory requirements, open high/critical source findings, and incompatible style families prevent a criteria-satisfied result.
- Even the strongest outcome is named `criteria_present_review_required`. **There is no “architecture approved”, “expert certified”, or “safe to deploy” result.**
- A review claim remains `self_declared_claims_unverified` even if it declares independence and its digest matches. SHA-256 checks integrity, **not the identity or independence of the claimant**.
- Results contain input case/architecture digests, criterion explanations, missing requirements, open high-severity risks and planned verification gaps.

## Commands

Install and test Speccanopy (Python 3.11+):

```bash
python -m pip install -e '.[dev]'
pytest -q
```

Evaluate one architecture against multiple acceptable paths:

```bash
speccanopy research-case \
  examples/research/cases/ecommerce.json \
  --architecture examples/research/candidates/ecommerce-distributed-unreviewed.json \
  --output out/research-ecommerce
```

Evaluate the full synthetic suite, preserving separate development and public-holdout counts:

```bash
speccanopy research-suite examples/research/suite.json \
  --output out/research-suite
```

Both commands offer `--strict`, which returns exit code **2** if documented criteria are incomplete, with outputs still written. Invalid source files/references return **1**. A strict success (0) indicates **criterion coverage**, never expert validation.

Output files are `research-case.json` / `research-case.md` and `research-suite.json` / `research-suite.md`. For transparency, the baseline suite and selected case results are checked in under [`examples/research/generated/`](../examples/research/generated/).

## Synthetic examples and reproducible observations

The suite currently includes **five synthetic application briefs**, with **six architecture candidate entries** because e-commerce has two intentionally different candidate styles and component IDs:

| Case | Split label | Evaluated primary style | Current outcome |
| --- | --- | --- | --- |
| Small file utility | Development | Single process | Criteria present, human review required |
| E-commerce | Development | Modular monolith | Criteria gaps: outbound order/payment contract missing |
| E-commerce hypothetical alternative | Development | Microservices | Alternative criteria present, human review required; distributed consistency unverified |
| Resumable file transfer | Public holdout (not blind) | Event-driven | Criteria gap: job intake event publisher contract missing |
| Embedded fluid controller | Public holdout (not blind) | Single process | Criteria present, human review required; actual timing and safety untested |
| Multi-tenant telemetry | Public holdout (not blind) | Event-driven | Criteria present, human review required; isolation and replay behavior untested |

**Important:** The invented distributed e-commerce alternative is a *test of design-path flexibility*, **not a production recommendation**. It introduces hypothetical event semantics and retains an open finding about consistency and duplicate handling. Its alternative passing does not make it equivalent to the modular design; the rules cannot prove that. All three public-holdout examples are visible in the source tree, so no blind generalization or model-training isolation is claimed.

### Mutation controls

The tests deliberately introduce errors that a brittle rubric might miss, including: removing a requirement from all concrete (non-root) owners, using unrelated components on a typed relationship, duplicating a single-owner data asset, deleting a quality target, changing to an incompatible style, and adding an open high-severity finding. Each is checked for a specific, explainable failure. **The mutation suite is not a comprehensive threat model or expert evaluation.**

The existing **Phase 5** benchmark remains available; `research-case` and `research-suite` do not change its schema, output or historical scores.

## Protocol for future independently reviewed reference cases

1. **Source and permission:** Obtain a permissible, de-identified application brief and a clear right to store/publish it; cite the source or label it synthetic. Keep private details out of public fixtures.
2. **Candidate alternatives:** Ask at least two independent qualified reviewers to specify responsibilities, interfaces, data ownership, quality scenarios, acceptable *alternative* architecture patterns, and explicit rejection conditions. Do not require the reviewers to agree on one hierarchy.
3. **Review evidence:** Record real reviewer identity/affiliation, area of expertise, date, the case-content SHA-256, review protocol, report URL/artifact, conflicts, and methodological limitations. Obtain appropriate publication consent.
4. **External verification:** Authenticate the review evidence **outside** the prototype (for example, through signed commits or organizational attestations). The current engine cannot do this. Only then should maintainers separately describe evidence as independently confirmed, and only for the scope actually reviewed. `ReviewClaim` remains unverified in machine output regardless.
5. **Freeze/hold out:** Reserve genuinely unseen private evaluation briefs with lawful access and avoid exposing them to model prompts, tuning or design-rubric iteration. The public examples are development demonstrations, not a test of out-of-distribution performance.
6. **Assess reliability:** Run multiple competing architectures and adversarial omissions. Measure inter-reviewer disagreement, false positives/negatives, domain-specific critical failures, score stability, and failure to identify unknowns. Publish both favorable and unfavorable results.
7. **Human decision:** Escalate security-critical, real-time, safety or compliance findings to qualified human specialists. No automated score should silently become a production-readiness certificate.

### How to record a reviewer claim (unverified)

The schema permits `provenance.review_claims[]` with `reviewer`, `expertise`, `reviewed_on` (ISO date), `method`, `report_url`, `subject_sha256`, `declares_independence` and `summary`. The digest is calculated by `ResearchCase.subject_digest()` from the case content **excluding** the review-claim list. A changed case invalidates the claim binding; a matching digest is still not an authenticated signature. No such expert claims are included in the present synthetic fixtures.

## What remains for true Phase 6 research completion

The **software infrastructure** for evaluating alternatives and receiving traceable expert-review claims is implemented. **Actual independent expert panel recruitment, authentication of evidence, a blind holdout set, domain-specific semantic adjudication, calibration against professional design reviews, and AI-driven automatic semantic critique remain outstanding.** This is an honest boundary, not a hidden background task.

Next work should recruit real reviewers and gather permissible cases, quantify cross-reviewer agreement, and use the evidence to improve the architecture critique/refinement model without overfitting a single decomposition tree.

## Phase 7 follow-on

A separate [expert panel review protocol](phase7-expert-panel.md) now prepares source-labeled-private packets from these public research cases, validates self-declared reviewer submissions against immutable packet hashes, and reports provisional agreement and disagreements. It does **not** authenticate experts, create private holdouts, or convert synthetic results into independent evidence. The original Phase 6 scores and limitations remain unchanged.
