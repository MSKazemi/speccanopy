# Speccanopy for documenting a real software project

**Assessed 2026-11-05. Current readiness: usable as a guided architecture-documentation prototype, NOT a complete automatic project-documentation generator.**

Speccanopy's product scope is **software architecture design and architecture documentation**, not implementing, compiling, testing, operating, or deploying the applications being described. It is not a replacement for a user guide, automatically extracted API reference, installation manual or full operations handbook.

## What you can use today

| Need | Available now? | Important limits |
| --- | --- | --- |
| Describe a proposed system with a structured brief | Yes | Write or manually/Claude-assisted produce a valid `SystemBrief` JSON |
| Generate a curated architecture | Yes | `speccanopy design` requires an existing `FixtureDesign` (`*.design.json`) for **the specific system** |
| Generate candidate components with Claude | Yes, via API | `propose-ai --backend claude` requires a separate `ANTHROPIC_API_KEY`; live API requests have NOT been validated in this milestone, only mocked calls |
| Evaluate existing `ArchitectureSpec` | Yes | `speccanopy review` produces heuristic rules and a review report, not correctness certification |
| Trace requirements to components and planned evidence | Yes | Claims about coverage cannot turn planned reviews into verified real-world evidence |
| Create containment and interaction diagrams | Yes | Mermaid `.mmd`, not always a complete runtime, data-flow or deployment architecture |
| Render an architecture Markdown pack from `ArchitectureSpec` | **Yes, baseline** | `speccanopy document --output EMPTY_DIRECTORY` produces nine Markdown pages and two Mermaid files, without inspecting application code |
| Generate complete, source-verified docs for arbitrary real applications | **Not built in** | Claude-assisted intake, source provenance, owner review and drift detection are still required |
| Inventory allowlisted local source files and check citations | **Yes** | `source-inventory` and optional `document --source-root --source-evidence` compare byte hashes, not architectural meaning |
| Draft structure from Python source modules/imports | **Yes, provisional Python-only** | `project-intake` parses bounded Python AST, produces valid brief/fixture plus source map; user supplies real requirements, and module roles are unverified |
| Automatically infer architecture semantics from source code | **Not built in** | Claude Code can inspect authorized source, but Speccanopy does not infer implemented behavior or business requirements |
| Regenerate verified documentation after code/requirement changes | **Partial** | Changed/missing **cited** source-file bytes are flagged by `document`; `source-diff` lists added/removed/changed **inventoried** files between two snapshots ([guide](source-inventory-diff.md)); `source-impact` maps those changes onto authored claims by digest and lists possibly affected architecture IDs ([guide](source-claim-impact.md)). Semantic drift and doc updates still require owner reconciliation |
| Report documentation gaps before owner sign-off | **Yes, deterministic** | `doc-gate` lists uncovered requirements, unsupported/self-reported claims, unmapped sources and open decisions ([guide](documentation-review-gate.md)); its strongest outcome is `ready_for_human_signoff`, never validation |
| Generate all kinds of project documentation (end-user help, API reference, deployment runbook) | **No** | Out of the current tool's automatic scope |

Neither expert recruitment nor an independent benchmark is a prerequisite for **using** Speccanopy to draft private architecture documentation. It is required before claiming experimentally demonstrated expert-level architecture quality; see [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2).

**Python project shortcut:** The [project-intake guide](python-project-intake.md) covers direct `project-intake` → `design` → `review` → `document`, producing draft module-boundary documentation without a separate model API. Claude Code can then refine the design after owner review.

**New source snapshot workflow:** Follow [source inventory and evidence mapping](source-evidence-workflow.md) to connect your authored requirement/component IDs to live local file hashes and surface missing/changed files. This is not a proof of application behavior.

**Use your Claude Code subscription for the guided workflow:** launch the unmodified `claude` terminal in the Speccanopy checkout after authenticating to your eligible paid plan. You do **not** need a Console API key for Claude Code to inspect your approved project files, author a `SystemBrief` / fixture, and execute local `speccanopy design` and `speccanopy review` commands. The `propose-ai --backend claude` option is a **different, direct API** integration requiring `ANTHROPIC_API_KEY`. If that environment variable is set while using Claude Code, Anthropic says it takes precedence over subscription billing, so remove it before starting a subscription session. See [subscription-versus-API instructions](claude-integration.md#claude-subscription-versus-anthropic-api-key).

## Prerequisites

- Python **3.11+** and a checkout of [Speccanopy](https://github.com/MSKazemi/speccanopy).
- A project goal, functional requirements, quality expectations, constraints and, for an existing application, authorized access to relevant source files.
- For the recommended guided workflow: **Claude Code** and a human project owner to resolve uncertainties. Claude Code's interactive account is different from the separate Anthropic **API key** needed by `propose-ai --backend claude`.
- Do not upload or commit passwords, customer data, private code or secrets without a separate permission/data-handling decision. Model inference may send supplied source/context to a provider; consult your Claude account's data policies.

### Smoke test — entirely local, no model/API key

```bash
git clone https://github.com/MSKazemi/speccanopy.git
cd speccanopy
python -m pip install -e '.[dev]'
pytest -q
speccanopy design examples/cli-utility.json --output out/demo
speccanopy review out/demo/architecture.json \
  --config examples/cli-utility.review.json --output out/demo-review
```

The first command uses the **included curated fixture**, not autonomous architecture inference. The outputs are a proof that the installed CLI works on an example, not verification of another project's design.

`design` exports six files:

- `architecture.json`: structured system, components, interface/data declarations, relationships, decisions, findings and verification cases.
- `architecture.mmd` and `relationships.mmd`: Mermaid containment and interaction diagrams.
- `requirements-report.json`: requirements mapped to components, and planned/verified/uncovered status.
- `decisions.json`: authored style, design decisions and findings.
- `generation-trace.json`: how the recursive engine expanded/stopped components.

`review` additionally emits `architecture-review.md`, `architecture-review.json`, `style-comparison.json`, `quality-review.json`. The Markdown file is a **review**, not a complete architecture document. An optional review config adds explicit style drivers and quality scenarios; without it the reviewer may abstain from style selection.

## Path A — Document an EXISTING project, recommended with Claude Code

This is a **guided multi-step workflow**, not an implemented one-click integration.

1. Open the Speccanopy checkout in Claude Code (`claude` from its root) so it can read [`CLAUDE.md`](../CLAUDE.md). Give it **authorized, deliberate access** to the separate target repository as appropriate; don't assume it can access other directories automatically.
2. Ask Claude to inspect the existing README, architecture docs, configuration, API definitions, database schemas, source-tree entry points and tests. Explicitly exclude `.env`, credentials, private keys, production data and any disallowed paths.
3. Ask Claude to create `myproject.brief.json` in the exact `SystemBrief` schema below. Link each observed requirement or assertion to a project source path (and line when available); mark unclear business requirements as questions, not facts.
4. Ask Claude to prepare a **provisional** `myproject.design.json` following [the example fixture](../examples/cli-utility.design.json): a `root`, `proposals_by_parent` (component responsibilities and boundaries), and evidence-bound relationships, decisions, quality targets and verification cases. Record assumptions and gaps. **Do not fabricate test evidence or mark unreviewed components validated.**
5. Run:

```bash
speccanopy design myproject.brief.json \
  --fixture myproject.design.json --output out/myproject

speccanopy review out/myproject/architecture.json \
  --output out/myproject-review

speccanopy document out/myproject/architecture.json \
  --review out/myproject-review/architecture-review.json \
  --output out/myproject-docs
```

6. Speccanopy now renders a draft baseline in `out/myproject-docs/`. Ask Claude Code to **review and reconcile** that baseline, then assemble your application's `docs/architecture/` from the **structured design** plus **actual source evidence**: `overview.md`, `requirements.md`, `components.md`, `interactions.md`, `data-security.md`, `decisions.md`, `quality-risks.md` and `open-questions.md`. Include or embed the Mermaid diagrams; cite requirement IDs and original source files. State which parts are **observed**, **inferred/proposed**, **verified**, and **unknown**.
7. You, as project owner, check important contracts and business rules, resolve open questions and accept/reject design decisions. Save the documents with your project's code and repeat when sources change. There is **no automatic drift detector** yet.

A suitable Claude Code instruction is:

> Read `CLAUDE.md` and `docs/project-documentation-readiness.md` in Speccanopy. Inspect my separate application repository only within the source paths I authorize, excluding secrets. Produce a valid project `SystemBrief` and draft `FixtureDesign` with requirement IDs, component boundaries, data ownership, interactions and provenance linked to observed files. Run `speccanopy design` and `speccanopy review`; then write a readable `docs/architecture/` set with Mermaid diagrams, ADRs, risks and open questions. Do not invent evidence, claim independent expert approval, or modify application code. Ask me to resolve material uncertainty.

**This is an effective workaround**, not built-in automatic source analysis. The review can improve documentation even with no external expert panel.

## Path B — Design a NEW project from its requirements

First prepare a `SystemBrief` JSON. This compact illustration is a **proposed sample**, not a validated system:

```json
{
  "system": "My project",
  "goals": ["Explain the intended application architecture"],
  "actors": ["End user", "Administrator"],
  "functional_requirements": [
    {"id": "FR-001", "statement": "Users authenticate and access their records", "mandatory": true},
    {"id": "FR-002", "statement": "Users can view their records", "mandatory": true}
  ],
  "quality_requirements": [
    {"id": "NFR-001", "attribute": "security", "statement": "Access is restricted to authorized users", "mandatory": true}
  ],
  "constraints": {"max_depth": 5, "max_nodes": 60, "max_refinement_rounds": 2}
}
```

Let Claude propose a preliminary component tree using your **Anthropic API account**:

```bash
# Set your own key securely in your shell/secret manager. Do not commit it.
export ANTHROPIC_API_KEY='YOUR_API_KEY'
speccanopy propose-ai myproject.brief.json \
  --backend claude --model YOUR_AVAILABLE_CLAUDE_MODEL_ID \
  --output out/myproject-draft

speccanopy review out/myproject-draft/architecture.json \
  --output out/myproject-draft-review
```

Inspect `out/myproject-draft/proposal-review.md`, `ai-proposals.json`, `architecture.json`, diagrams and review findings.

**Critical limit:** The AI proposer outputs mainly a **proposed hierarchy**. It does **not** automatically fill accurate interaction graphs, runtime/deployment views, ADRs, verification cases or complete interface/data ownership contracts. The resulting architecture often has status `incomplete_requires_review`; this is intentional.

After YOU inspect the proposed component hierarchy, you may release it for further work with:

```bash
speccanopy approve-ai out/myproject-draft/ai-proposals.json \
  --reviewer YOUR_ID --acknowledge-review \
  --output out/myproject-approved.design.json

speccanopy design myproject.brief.json \
  --fixture out/myproject-approved.design.json \
  --output out/myproject-approved-draft
```

Approval here means **you reviewed the candidate hierarchy**. It does **not** make its engineering correctness certified or complete; add missing relationships, contracts, ADRs and plans to the design input and regenerate/review. Do not approve solely to satisfy a command.

If you only use **Claude Code**, you do **not** need a separate Anthropic API key to use its interactive assistance or run the deterministic Speccanopy commands. You can have Claude Code author a fixture directly instead.

## What must be built before calling this documentation-ready for arbitrary projects

Tracked in [Issue #5 — project architecture documentation workflow](https://github.com/MSKazemi/speccanopy/issues/5).

### Priority 0: minimum viable documentation product

1. **Project intake (initial Python structural extraction implemented):** `speccanopy project-intake` now parses bounded Python module declarations/imports and drafts valid design inputs from user-provided requirements; `source-inventory` captures hashes. Still needed: semantic extraction/verification of real requirements, runtime boundaries and other languages/frameworks. [Python instructions](python-project-intake.md). A Claude Code helper is a reasonable first integration; there is no reason to assume a scanner can infer every architectural decision from code.
2. **Architecture-document renderer (initial implementation complete):** `speccanopy document` now emits a deterministic baseline architecture pack from `ArchitectureSpec`, preserving missing information as gaps. Remaining: source-backed claims, appropriate design completeness and actual application verification.
3. **Review and provenance gates (partial):** `document --source-root --source-evidence` checks authored file hashes and missing observed links, but cannot prove semantic architecture claims or user approval. Continue separating actual implementation from proposals and keep source/decision signoff with the owner.
4. **Real-project end-to-end example and CI:** start from a permissible small application repository, extract a brief, design/review it and render a source-linked documentation pack; test reproducibility and invalid/missing evidence.

### Priority 1: maintainability and breadth

5. **Change detection:** reconcile existing docs when requirements, code or decisions change, preserving human-approved text and warning about drift.
6. **Richer architecture views:** runtime sequences, data consistency, security/trust boundaries, deployment-*design* views and trace links. Optional MkDocs/site/PDF export can follow, but a trustworthy Markdown pack should come first.

### Acceptance criteria

A developer points the tool at an authorized application repository, reviews a structured brief, receives consistent `docs/architecture/*.md` documents and Mermaid diagrams, and can identify which statements were observed versus proposed or unknown. The output must be reproducible, source-linked and candid about unresolved requirements. It need not claim independent expert certification.

**For today:** use the guided Claude Code workflow for a real project's **draft architecture documentation**. Do not present the existing CLI as one-command complete project documentation generation.

Related: [architecture contract](architecture-contract.md), [Claude integration](claude-integration.md), [Phase 2 generator](phase2-engine.md), and [execution roadmap](execution-roadmap.md).
