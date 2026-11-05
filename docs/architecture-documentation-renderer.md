# Markdown architecture documentation renderer

**Implemented prototype:** `speccanopy document` renders an existing `ArchitectureSpec` JSON into **nine Markdown pages and two Mermaid files**. It does **not** inspect an application repository, prove design correctness, or call a paid model API. The authored input remains a draft unless independently supported.

## Run from an existing architecture JSON

Use the checked-in example (no fixture generation or Claude account needed):

```bash
python -m pip install -e '.[dev]'
speccanopy document examples/generated/cli-utility/architecture.json \
  --output out/cli-documentation
```

Alternatively, generate the architecture and an optional **heuristic** review first:

```bash
speccanopy design examples/ecommerce.json --output out/ecommerce
speccanopy review out/ecommerce/architecture.json \
  --config examples/ecommerce.review.json --output out/ecommerce-review

speccanopy document out/ecommerce/architecture.json \
  --review out/ecommerce-review/architecture-review.json \
  --output out/ecommerce-docs
```

The `--review` argument is optional. When present, it adds style recommendations, rule-based findings and quality scenarios to the documentation, **without** claiming independent expert approval.

## What is generated

```text
out/ecommerce-docs/
├── README.md             # Index, statuses and evidence limitations
├── overview.md           # Goals, actors, style and constraints
├── requirements.md       # Requirements, owners and evidence/coverage
├── components.md         # Component tree, boundaries, contracts and Mermaid
├── interactions.md       # Interaction graph, authored dependency edges
├── data-security.md      # Data ownership, trust boundaries, security goals
├── decisions.md          # Authored ADRs, alternatives and trade-offs
├── quality-risks.md      # Quality targets, cases, risks and optional review
├── open-questions.md     # Review tasks for missing or uncertain information
├── architecture.mmd      # Containment diagram source
└── relationships.mmd     # Interaction diagram source
```

Content is deterministic for the same parsed input, based on existing schema fields. Missing requirements, interfaces, data owners, trust boundaries, design decisions and verification evidence are exposed as gaps. Authored free text is escaped for Markdown tables and headings, and Mermaid code fences adapt to backticks in labels.

## Output safety and exit codes

- The `--output` directory **must be new or empty**. Existing files, even a previous run's documentation, are not silently overwritten. For a changed design generate to a new folder and compare it with the old docs before replacing human-approved pages.
- Normal successful rendering returns exit code **0** even for a `draft`; look at its status and `open-questions.md`.
- Use `--strict` to return exit code **2** when the architecture status is not `validated_for_scope`, or when the optional supplied review is `requires_review`. Documents are still written so you can fix the gaps.
- Input/schema mismatch, unreadable files and a nonempty output folder return exit code **1**.
- When `--review` is given, the CLI checks matching **system name and architecture status**. The review schema does **not** include an exact architecture-content digest; its freshness relative to the source revision cannot be proven by this command. Confirm you used a review for the same file.

**Caveat:** Even `validated_for_scope` is a *schema* state backed by author-provided verification evidence. This renderer does not run tests, authenticate experts, prove observed production behavior, or establish code provenance. It never promotes an architecture's status.

## Optional source-file provenance

The `source-inventory` command creates local, allowlisted file metadata; Claude Code can use the real hashes to author a separate claim map. The Markdown renderer accepts this **optional pair**:

```bash
speccanopy source-inventory ~/projects/my-app \
  --output out/myproject-inputs/source-inventory.json
# After a valid out/myproject-inputs/source-evidence.json is authored:
speccanopy document out/myproject/architecture.json \
  --source-root ~/projects/my-app \
  --source-evidence out/myproject-inputs/source-evidence.json \
  --output out/myproject-source-docs
```

It then produces a tenth Markdown page (`source-evidence.md`) listing digest-bound source references, missing/changed/unreadable file status and unlinked architecture IDs. **This is file-byte checking, not source-code semantic verification.** Read the [source evidence workflow guide](source-evidence-workflow.md) for map format and limitations.

## From a Python application folder

The new [Python project intake](python-project-intake.md) prepares the initial brief, fixture, inventory and evidence map **without executing the application**. Then use `design`, `review`, and `document` as below. The resulting source-linked Markdown represents provisional module/import observations, not verified business behavior.

## How Claude Code uses this renderer

When documenting a **real existing project**, Claude Code can inspect only authorized files, prepare `SystemBrief` and `FixtureDesign`, and run:

```bash
speccanopy design out/myproject-inputs/brief.json \
  --fixture out/myproject-inputs/design.json --output out/myproject
speccanopy review out/myproject/architecture.json --output out/myproject-review
speccanopy document out/myproject/architecture.json \
  --review out/myproject-review/architecture-review.json \
  --output out/myproject-docs
```

Review the Markdown baseline in `out/myproject-docs/`. Claude Code may then, with your approval, **reconcile** the generated draft with observed source files and commit-linked references, and copy enriched pages into your application's `docs/architecture/`. Source-aware extraction is still a separate guided step, not built into Speccanopy.

This is the first completed engineering slice of [documentation readiness Issue #5](https://github.com/MSKazemi/speccanopy/issues/5). Remaining: source-aware intake and provenance, real-application end-to-end evidence tests, source drift/update reconciliation, and richer runtime/deployment security views.

See also [the full user guide](USER_GUIDE.md), [Claude Code quickstart](claude-code-quickstart.md), and [architecture contract](architecture-contract.md).
