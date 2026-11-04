# Phase 3 — Advisory architecture-style comparison and independent quality rules

**Status:** Implemented rule-based review prototype, not an AI architect or an architecture-certification tool.  
**Scope:** Evaluate architectural *design artifacts*, not generate, build, test or deploy target application code.  
**Prerequisites:** [Phase 1 contract](architecture-contract.md) and [Phase 2 generator](phase2-engine.md).

## Purpose

Phase 2 generates schema-valid architecture drafts using curated proposals. Phase 3 **separately** evaluates them using two independent modules:

1. **Architecture-style comparison** — ranks candidate style families against *explicit* user/reviewer drivers, identifies trade-offs, and abstains when evidence is missing or ambiguous.
2. **Cross-cutting design-quality checks** — inspects mandatory requirement traceability, review evidence, quality-attribute scenarios, component interface directions, data ownership overlap, and unresolved high-risk findings.

Neither module mutates the architecture under review or marks it `validated_for_scope`. The original, potentially hybrid, authored architecture style remains intact even if a different candidate ranks higher. Style recommendations are **advisory**.

## Run it

Requires Python 3.11+, Pydantic 2, and the Speccanopy package (or `PYTHONPATH=src`).

```bash
python -m pip install -e '.[dev]'
pytest -q

# Generate a draft using the existing deterministic, curated fixture:
speccanopy design examples/ecommerce.json --output out/ecommerce

# Review the resulting architecture with explicit architecture drivers and quality scenarios:
speccanopy review out/ecommerce/architecture.json \
  --config examples/ecommerce.review.json \
  --output out/ecommerce-review
```

Run the already-checked-in example directly:

```bash
speccanopy review examples/generated/file-transfer/architecture.json \
  --config examples/file-transfer.review.json \
  --output out/transfer-review
```

A review config is optional. Without drivers, Speccanopy reports **insufficient drivers** and **does not recommend an architecture style**; quality checks still run and report missing scenarios. With `--strict`, the CLI returns exit code 2 for a result requiring review while writing its reports. Invalid input/config references return exit code 1.

## Review configuration contract

Review inputs are validated with Pydantic (`ReviewConfig`). The three examples are in:

- [`examples/cli-utility.review.json`](../examples/cli-utility.review.json)
- [`examples/ecommerce.review.json`](../examples/ecommerce.review.json)
- [`examples/file-transfer.review.json`](../examples/file-transfer.review.json)

A configuration declares:

- `drivers[]`: distinct architecture drivers, each with `key`, `importance` (1–5), `desired` fit level (1–5), and a written `rationale`.
- `candidates[]`: optional subset of at least two candidate styles; default is all five supported comparison profiles.
- `scenarios[]`: a quality requirement ID, stimulus, expected response, measure, focus component IDs, and optional expected typed interactions (source/target/kind).

Every scenario must point to a **known quality requirement and known components** in the architecture. Expectations are written by a reviewer; the engine does not invent security controls, performance targets or external requirements.

### Style comparison model

The initial profiles are `single_process`, `modular_monolith`, `microservices`, `event_driven`, and `serverless`. They cover common *primary deployment/interaction approaches*, **not all possible architecture patterns**. Layered, clean, hexagonal, CQRS and event-driven patterns can be combined with other styles; the ranking is not an exclusive taxonomy.

Profiles use **heuristic** 1–5 fitness levels for seven attributes: operational simplicity, independent deployment, elastic scaling, strong consistency, asynchronous workflows, fault isolation, and modular boundaries. They are **not measured performance or cost data**.

For driver `d` and candidate `s`:

```text
compatibility(d, s) = 2 × (5 - abs(desired_d - heuristic_profile_s,d))
score(s) = sum(importance_d × compatibility(d, s)) / sum(importance_d)
```

A score is between 2 and 10. No drivers means **no score/no recommendation**. If the top two candidates differ by less than 0.5 points, the system **abstains** rather than manufacturing precision. Alternatives and their trade-offs are always visible. When the authored style differs from the advisory recommendation, the review raises a trade-off finding; it **never silently rewrites** the user's decision.

### Quality rules

The current deterministic checks identify:

1. Mandatory requirements with no linked verification case, and those with **planned-only** rather than authored verified evidence.
2. Mandatory quality requirements with no component owner, quality target or explicit review scenario.
3. Scenario focus components that do not claim the relevant quality requirement or its target.
4. Missing exact typed interactions requested by a scenario, including interactions present without the required quality-requirement trace link.
5. `synchronous_call` and `event` edges whose source/target interfaces lack the appropriate outbound/inbound contract types.
6. Sibling components claiming the same normalized owned-data name, suggesting unclear ownership.
7. Missing selected architecture style and open **high/critical** findings from the source architecture.
8. Conflicts between an existing, authored style family and a heuristic recommendation.

These are **review findings, not necessarily errors**. A rule may flag a deliberate pattern; a human should evaluate and document exceptions. Conversely, zero findings never proves security, performance, resilience or fitness for purpose. Scenarios describe how to review a design but are not automatically executed tests.

## Output files

Every `review` command writes:

| File | Contents |
| --- | --- |
| `architecture-review.json` | Combined advisory style comparison and quality evaluation, including provenance and limitations |
| `style-comparison.json` | Candidate ranking, weighted driver-fit explanations and trade-offs |
| `quality-review.json` | Requirement coverage, scenario checks, findings and open source finding IDs |
| `architecture-review.md` | Human-readable review packet for architects or developers |

The review uses statuses `requires_review` or `candidate_for_human_review`, **not** `validated_for_scope`. A scenario with authored verification evidence is described as `evidence_documented`, not as independently certified.

## Three reproducible example evaluations

The checked-in outputs are under [`examples/reviews/`](../examples/reviews/). All three start with Phase 2 draft artifacts and **planned**, not completed, verification cases.

| Example | Advisory recommendation | Why this appears in the fixture | Final review status |
| --- | --- | --- | --- |
| Text normalization CLI | `single_process` | Operational simplicity, local processing, one deployment unit | `requires_review` |
| E-commerce | `modular_monolith` | Cohesive domain modules and straightforward transactions prioritized | `requires_review` |
| Multi-backend file transfer | `event_driven` | Queued asynchronous jobs and variable transfer capacity prioritized | `requires_review` |

The fixture inputs are explicitly curated to exercise the methodology; three examples do **not** establish generalization. A future evaluation set should include deliberately conflicting architecture drivers, alternative valid designs and held-out application domains.

## What is not implemented yet

- AI-generated architecture candidates from arbitrary requirements or prose.
- Full design verification via load tests, threat modeling, deployment experiments or independent expert reviews.
- Automatic acceptance of a style recommendation, generating accepted ADRs, or modifying the source design.
- Real-time deployment, operational cost estimates, benchmarking or target application code execution.
- Complete architecture taxonomies and calibrated domain-specific scoring.

**Next engineering milestone:** integrate an optional AI-backed `ComponentProposer` with schema validation, provenance, constrained refinement, and human approval. Do not confuse LLM proposals with independent verification.
