# Speccanopy documentation

**Maintenance status:** [Repository-wide audit (2026-11-06)](REPOSITORY_AUDIT_2026-11-06.md), including open GitHub issues, incomplete product features, tests, release readiness and recommended next sprint.

**New to Speccanopy?** Read the [complete Claude Code user guide](USER_GUIDE.md). It explains **what input you give, exact commands, what output files you receive, and troubleshooting**.

## Using Speccanopy

| Guide | Purpose |
| --- | --- |
| [Python project intake — start here for Python](python-project-intake.md) | Complete input → offline AST draft → design/review/document with source hashes and Claude Code |
| [Claude Code prompt for Python](../prompts/claude-code-python-intake.md) | Copy-paste guided project documentation instructions for Python source |
| [User guide — start here](USER_GUIDE.md) | Complete existing/new-project walkthrough, Claude Code subscription, JSON inputs, output files, troubleshooting |
| [Short quick start](claude-code-quickstart.md) | Minimal copy/paste terminal and prompt instructions |
| [Project documentation readiness](project-documentation-readiness.md) | Detailed existing-repository workflow and missing product features |
| [Claude Code vs Anthropic API](claude-integration.md) | Subscription workflow vs separate API billing |
| [Source inventory and evidence mapping](source-evidence-workflow.md) | Inventory local source metadata, check SHA-256-backed citations, report changed/missing files |
| [Compare source inventories](source-inventory-diff.md) | `source-diff`: added/removed/changed/unchanged files between two inventories, coverage warnings, exit codes |
| [Map source changes to affected claims](source-claim-impact.md) | `source-impact`: which authored claims and architecture IDs may be stale after files change; uncited new files |
| [Documentation review gate](documentation-review-gate.md) | `doc-gate`: uncovered requirements, unsupported claims, unmapped sources and open human decisions before owner sign-off |
| [Review heuristic robustness (synthetic)](review-robustness.md) | Metamorphic tests of review/doc-gate heuristics: ID renaming, rewording, reordering, monotonicity; keyword-sensitive heuristics found. **Not** independent expert evaluation |
| [Structural comparison of two intakes](structure-diff.md) | `structure-diff`: modules, static import edges and top-level symbols added/removed between two `project-intake` runs; separates byte churn from structural change |
| [Pilot on a real third-party Python package](pilot-third-party-python.md) | Measured pipeline results on itsdangerous 2.2.0 and its real 2.1.2 → 2.2.0 release change; **not** owner-confirmed or expert evaluation |
| [End-to-end acceptance walkthrough](end-to-end-acceptance.md) | Run intake → design → review → document → change detection on the committed **synthetic** example; what the acceptance tests check |
| [Markdown architecture renderer](architecture-documentation-renderer.md) | Turn an existing architecture JSON into thirteen Markdown pages (including data-flow, trust-boundary, deployment and runtime views) and two Mermaid diagrams |
| [CLI design engine](phase2-engine.md) | JSON/Mermaid outputs and structural readiness |
| [Architecture review](phase3-review.md) | Rule-based design and quality review |
| [Component proposals with AI](phase4-ai-proposals.md) | Optional direct model API and human acknowledgement |
| [Architecture contract](architecture-contract.md) | Source-of-truth schemas, requirement traceability, statuses |

## Developing Speccanopy in parallel

- [Claude Code parallel-development guide](parallel-development.md) — model selection, subscription use, isolated worktrees, file ownership and review boundaries.
- [Ready-to-run Issue #5 implementation prompt](../prompts/claude-code-parallel-issue5.md) — one integration lead and two scoped workers, tested code changes, clear usage docs, no direct pushes to main or artificial closure of research issues.

These are handoff instructions, not a claim that parallel workers have been launched or their tasks completed.

## Research and development

- [Vision and goal](vision-and-goal.md)
- [Architecture design method (ARAD)](adaptive-recursive-architecture-design.md)
- [Execution roadmap](execution-roadmap.md)
- [MVP plan](mvp-implementation-plan.md)
- [Controlled refinement](phase5-refinement-evaluation.md)
- [Multiple-alternative research](phase6-architecture-research.md)
- [AI-only sample critique](ai-assisted-case-review.md)
- [External reviewer protocol](phase7-expert-panel.md)
- [Benchmark and expert-review progress](https://github.com/MSKazemi/speccanopy/issues/2)
- [Project documentation product-readiness backlog](https://github.com/MSKazemi/speccanopy/issues/5)

**Evidence boundary:** Passing tests and an AI critique do not certify any real-world architecture. Speccanopy is an architecture **design and documentation** project, not an application builder.
