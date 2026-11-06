# User guide — Document a software project with Speccanopy + Claude Code

**Start here.** Speccanopy is currently a **guided architecture-documentation prototype**, not a one-command source-to-documentation product. With your Claude Code subscription, Claude helps gather project facts and inputs; Speccanopy validates a structured architecture, generates diagrams, performs advisory reviews, **and renders a baseline Markdown architecture pack**. Claude Code can reconcile it with actual project sources. You decide which architecture assertions and decisions to accept.

**Scope:** Speccanopy designs and documents **software architecture**. It does not implement, build, test or deploy the application that it describes.

## 1. Input and output at a glance

| You have | You provide | What you receive |
| --- | --- | --- |
| **An existing application** | The local folder containing code, README, tests, config and available requirements; permission to inspect relevant files | A draft architecture model, component/dependency diagrams, requirement coverage, review findings, and optional readable Markdown architecture documentation |
| **A new application idea** | Goal, intended users, features, security/reliability goals, technology and deployment constraints | A **proposed** architecture with diagrams, decisions and unresolved assumptions; not a description of already-existing code |
| **No Claude Code** | A valid `SystemBrief` JSON and project-specific `FixtureDesign` JSON | The same deterministic CLI-generated architecture files and optional rule-based review, but no automatic repository analysis or complete narrative handbook |

Speccanopy's `source-inventory` lists allowlisted file metadata, and the new `project-intake` command additionally analyzes bounded **Python AST module/import declarations** to draft a valid brief/fixture/source map from your supplied requirements. It still does **not** infer actual business behavior or architectural correctness. For non-Python projects, Claude Code prepares those project-specific inputs from approved files. **You review the assumptions and semantic claims.** [Source evidence workflow](source-evidence-workflow.md).

## 2. Set up once — Claude Code subscription, no extra API key

Example folder layout (replace `my-app` with your application's actual directory):

```text
~/projects/
├── speccanopy/       # Speccanopy tool
└── my-app/            # Your existing application
```

From a Bash/Zsh terminal, with Python 3.11+:

```bash
git clone https://github.com/MSKazemi/speccanopy.git ~/projects/speccanopy
cd ~/projects/speccanopy
python -m pip install -e '.[dev]'
pytest -q

# Use an eligible Claude Code subscription instead of API-key billing:
unset ANTHROPIC_API_KEY
claude --add-dir ~/projects/my-app
```

If Speccanopy is already cloned, skip `git clone`. The `--add-dir` option grants access to a separate application folder; accept only the access you intend. Claude Code reads the Speccanopy root [CLAUDE.md](../CLAUDE.md). You can check your Claude Code authentication with `/status`.

**Billing distinction:** This workflow runs **inside Claude Code** with your eligible subscription and executes local Speccanopy commands. It does **not** use `speccanopy propose-ai --backend claude`: that is a **separate** Anthropic Messages API integration requiring `ANTHROPIC_API_KEY` and an API-enabled account. Do not reuse subscription/session credentials in it. On PowerShell, instead of `unset`, use `Remove-Item Env:\ANTHROPIC_API_KEY -ErrorAction SilentlyContinue`.

## 2A. Recommended shortcut for an existing Python application

For a Python application, Speccanopy now prepares the **initial JSON inputs automatically**, without an Anthropic API key and without executing target application code. Provide an application directory, system name, goal, and at least one real functional requirement:

```bash
speccanopy project-intake ~/projects/my-app \
  --system "My App" \
  --goal "Document the architecture of the existing application" \
  --requirement "Users can create records" \
  --output out/my-app-inputs

speccanopy design out/my-app-inputs/brief.json \
  --fixture out/my-app-inputs/design.json \
  --output out/my-app-architecture

speccanopy review out/my-app-architecture/architecture.json \
  --output out/my-app-review

speccanopy document out/my-app-architecture/architecture.json \
  --review out/my-app-review/architecture-review.json \
  --source-root ~/projects/my-app \
  --source-evidence out/my-app-inputs/source-evidence.json \
  --output out/my-app-docs
```

**Input:** an authorized Python folder + your actual goals/requirements. **Output:** six intake artifacts (`brief.json`, `design.json`, `source-inventory.json`, `source-evidence.json`, `module-observations.json`, `intake-review.md`), then architecture JSON/diagrams/reviews and ten baseline Markdown pages (the tenth is `source-evidence.md`) plus two Mermaid files.

**Expected:** the resulting architecture is **incomplete/requires review**. Python source modules and import statements have been found, but requirements are not automatically mapped to modules, and real interfaces, data ownership, runtime behavior and architecture style are still open. Open `out/my-app-inputs/intake-review.md` and `out/my-app-docs/open-questions.md` first. For more details, limits and a ready-to-copy Claude prompt, use the [Python project intake guide](python-project-intake.md) and [Claude Code Python prompt](../prompts/claude-code-python-intake.md).

For projects using other languages or more modules than the supported cap, use the guided Claude Code workflow below. No output should be treated as independent production certification.

## 3. Give Claude Code this instruction (existing project)

Paste this into the interactive Claude Code terminal after replacing the folder path:

> Read `CLAUDE.md`, `docs/USER_GUIDE.md` and `docs/source-evidence-workflow.md`. First inventory my authorized project file metadata with `speccanopy source-inventory`. My existing application is at `~/projects/my-app`. I want **architecture documentation for the current implementation**, not changes to application source code. Inspect authorized source files, README, tests, configs, API and database definitions; do not read `.env`, secrets, keys or private production data. Identify system goals, actors, requirements, components, component boundaries, interactions, data ownership, key decisions and quality risks. Produce schema-valid `out/myproject-inputs/brief.json` (SystemBrief) and `out/myproject-inputs/design.json` (FixtureDesign), using Speccanopy's examples. Use real SHA-256 file hashes from the inventory and known architecture IDs to prepare `out/myproject-inputs/source-evidence.json` with paths, lines and observed/inferred/proposed assertions. Keep extra notes separately in `source-notes.md`; do not invent unsupported JSON fields. Label uncertainties and proposed changes clearly; do not invent test evidence, expert approval or a validated status. Run `speccanopy design`, `speccanopy review` and `speccanopy document` as specified below; optionally include the source-root and evidence-map flags and show the resulting source report. With my approval, write readable Markdown into my application's `docs/architecture/` directory, including overview, requirements, components, interactions, data/security, decisions, quality risks and open questions. Include Mermaid diagrams, cite actual source files for observed facts, and do not edit application code. Finish by listing files created, critical findings and questions for me to resolve.

A reusable copy of this prompt is in [prompts/claude-code-document-project.md](../prompts/claude-code-document-project.md).

**Important input details:** Claude can infer *candidate* requirements from the code, but it cannot recover every unstated business decision. Give it a README, project goal, known requirements and constraints where you have them. You approve which design is accurate. Check applicable privacy policies before allowing source material to be sent to Claude.

### Two machine-readable inputs prepared by Claude

- `out/myproject-inputs/brief.json`: goals, actors, functional and quality requirement IDs, constraints. Follow [examples/cli-utility.json](../examples/cli-utility.json).
- `out/myproject-inputs/design.json`: proposed component tree, interfaces, relationships, data ownership, decisions and any **planned** verification cases. Follow [examples/cli-utility.design.json](../examples/cli-utility.design.json).

The schemas are strict: source paths and evidence notes that do not have defined JSON fields belong in a separate document; do not add arbitrary unsupported properties. Optionally create `out/myproject-inputs/review.json` from [examples/cli-utility.review.json](../examples/cli-utility.review.json) for quality scenarios and style drivers.

## 4. Commands Claude Code runs after preparing the inputs

These commands run from the **Speccanopy checkout**:

```bash
speccanopy design out/myproject-inputs/brief.json \
  --fixture out/myproject-inputs/design.json \
  --output out/myproject

speccanopy review out/myproject/architecture.json \
  --output out/myproject-review

speccanopy document out/myproject/architecture.json \
  --review out/myproject-review/architecture-review.json \
  --output out/myproject-docs
```

For **source-linked documentation**, first run the local inventory and ask Claude to author a valid source map based on real file hashes. Render to a **different empty folder** from the preceding basic example:

```bash
speccanopy source-inventory ~/projects/my-app \
  --output out/myproject-inputs/source-inventory.json

# After Claude Code creates out/myproject-inputs/source-evidence.json:
speccanopy document out/myproject/architecture.json \
  --review out/myproject-review/architecture-review.json \
  --source-root ~/projects/my-app \
  --source-evidence out/myproject-inputs/source-evidence.json \
  --output out/myproject-source-docs
```

This adds `source-evidence.md` and source questions; byte-matching does not prove the author's claim. [Full source evidence guide](source-evidence-workflow.md).

**After the application changes**, keep the old inventory, make a new one and compare them. This lists every added, removed, changed and unchanged allowlisted file — including new files no source claim cites yet:

```bash
speccanopy source-inventory ~/projects/my-app \
  --output out/myproject-inputs/source-inventory-v2.json
speccanopy source-diff out/myproject-inputs/source-inventory.json \
  out/myproject-inputs/source-inventory-v2.json \
  --output out/myproject-source-diff
```

It writes `source-diff.json` and `source-diff.md`; exit `0`, or `2` with `--strict` when anything differs. Removed and added files with identical bytes are listed as **possible renames**; add `--record-git-revision` to `source-inventory` to record the commit each inventory was taken from (read from `.git` files, no git command run; an unauthenticated hint). It compares file bytes only and never edits documentation. [Inventory comparison guide](source-inventory-diff.md).

To see **which authored source claims — and therefore which architecture IDs — may now be out of date**, run `source-impact` with the same two inventories and your evidence map:

```bash
speccanopy source-impact out/myproject-inputs/source-inventory.json \
  out/myproject-inputs/source-inventory-v2.json \
  --evidence out/myproject-inputs/source-evidence.json \
  --architecture out/myproject/architecture.json \
  --output out/myproject-claim-impact
```

It writes `claim-impact.json` and `claim-impact.md`, classifying every claim as `unaffected`, `stale_changed`, `stale_removed`, `not_bound_to_before`, `rebound_to_after` or `not_in_inventory`, and lists added/changed files no claim cites. Exit `0`, or `2` with `--strict` when anything requires review. It compares digests only, marks nothing verified and never edits documentation. [Claim impact guide](source-claim-impact.md).

**Before you hand the pack to the owner**, run the documentation review gate. It lists uncovered requirements, unsupported or self-reported claims, unmapped sources and decisions that still need a human:

```bash
speccanopy doc-gate out/myproject/architecture.json \
  --review out/myproject-review/architecture-review.json \
  --source-root ~/projects/my-app \
  --source-evidence out/myproject-inputs/source-evidence.json \
  --output out/myproject-doc-gate
```

It writes `documentation-gate.json` and `documentation-gate.md`. The strongest outcome is `ready_for_human_signoff` (no blocking items); there is no "validated" outcome, and the gate never changes the architecture status. Exit `0`, or `2` with `--strict` when the outcome is `requires_review`. [Documentation gate guide](documentation-review-gate.md).

An optional `review --config out/myproject-inputs/review.json` adds scenario and style assumptions. Without supplied style drivers, Speccanopy may abstain from recommending a style. This is legitimate rather than a failure.

**Smoke test without Claude or a real project:**

```bash
speccanopy design examples/cli-utility.json --output out/demo
speccanopy review out/demo/architecture.json \
  --config examples/cli-utility.review.json \
  --output out/demo-review
```

That example uses a **curated fixture**, not automatic inference.

## 5. Exact output file structure

**Automatically emitted by Speccanopy after Claude prepares the inputs:**

```text
speccanopy/
└── out/
    ├── myproject-inputs/             # Claude Code-prepared inputs (not CLI exports)
    │   ├── brief.json
    │   ├── design.json
    │   ├── source-inventory.json    # Optional allowlisted file metadata/hashes
    │   ├── source-evidence.json     # Optional authored source-claim map
    │   └── source-notes.md         # Optional extra research notes
    ├── myproject/                    # speccanopy design outputs
    │   ├── architecture.json         # Normalized draft architecture
    │   ├── architecture.mmd          # Mermaid containment tree
    │   ├── relationships.mmd         # Mermaid dependency graph
    │   ├── requirements-report.json # Requirements mapped to components and status
    │   ├── decisions.json            # Authored decisions and findings
    │   └── generation-trace.json     # Expansion decisions, limits, warnings
    └── myproject-review/             # speccanopy review outputs
        ├── architecture-review.md    # Readable heuristic findings
        ├── architecture-review.json
        ├── style-comparison.json
        └── quality-review.json
```

**New built-in baseline Markdown output:** `speccanopy document` automatically produces `out/myproject-docs/` with thirteen Markdown pages (`README.md`, `overview.md`, `requirements.md`, `components.md`, `interactions.md`, `data-security.md`, `decisions.md`, `quality-risks.md`, `open-questions.md`, plus the focused views `view-data-flow.md`, `view-trust-boundaries.md`, `view-deployment.md` and `view-runtime.md`) and two Mermaid files (`architecture.mmd` and `relationships.mmd`). These pages describe the supplied architecture, not verified facts about a repository. With the paired source options, a tenth `source-evidence.md` page is generated and `open-questions.md` identifies missing/changed files and unlinked IDs. See [renderer documentation](architecture-documentation-renderer.md).

**Additionally written by Claude Code if you ask it to generate readable docs** (with your approval to write in the app):

```text
my-app/
└── docs/
    └── architecture/
        ├── README.md                 # Docs index
        ├── overview.md               # Purpose and system context
        ├── requirements.md           # Requirements and provenance
        ├── components.md             # Responsibilities and boundaries
        ├── interactions.md           # APIs/events and Mermaid diagrams
        ├── data-security.md          # Data ownership and trust boundaries
        ├── decisions.md              # ADRs, alternatives and trade-offs
        ├── quality-risks.md          # Quality scenarios and review gaps
        └── open-questions.md         # Unknown or unapproved decisions
```

**The version in the application repository is not created there automatically.** Speccanopy writes the baseline pages into `out/myproject-docs/`; Claude Code can then reconcile them with the actual source and, with your approval, create or update the application's `docs/architecture/`. The exact document filenames may vary according to the project and your instructions. Speccanopy's own `out/` is ignored by Git; keep versioned application documentation under the application repository if desired.

### Understanding the results

- `architecture.json` is a **draft**—not proof that the code implements all requirements.
- `architecture.mmd` shows containment; `relationships.mmd` shows directed interactions. They are Mermaid **source text**, which a Markdown renderer can display using a fenced code block labeled `mermaid`.
- `requirements-report.json` distinguishes verified-evidence-linked, planned-only and uncovered requirements. AI-authored claims alone do **not** independently establish verified coverage.
- `architecture-review.md` is a **heuristic review**, not external expert certification. A source architecture can remain `draft` or `incomplete_requires_review`.
- `open-questions.md` should be reviewed by you, the project owner; unresolved facts should not be silently treated as accepted design.

## 6. If the project does not exist yet

Start `claude` from the Speccanopy checkout; no extra project folder is required. Provide requirements in ordinary language, for example:

> I want to design a simple internal task tracker. Users create tasks, assign owners, view due dates and receive reminders. It needs sign-in, permission checks and a single low-cost server. Usage scale, backup requirements and privacy constraints are still unknown. Create proposed `out/myproject-inputs/brief.json` and `design.json`, run `speccanopy design` and `review`, and write a draft architecture guide to `out/myproject-docs/` with Mermaid diagrams and open questions. Do not claim an implementation or validation already exists.

The output is a **proposed design**, not documentation of actual implemented components.

## 7. Troubleshooting

| Problem | What to do |
| --- | --- |
| `claude: command not found` | Install and authenticate the [official Claude Code CLI](https://code.claude.com/docs/en/setup). |
| `speccanopy: command not found` | From the Speccanopy checkout, run `python -m pip install -e '.[dev]'` in the active Python environment. |
| `design` cannot find a fixture | Claude must create the **project-specific** `design.json`; pass it explicitly as `--fixture`. The demo fixture is only for the demo. |
| Pydantic rejects JSON | Compare keys/IDs to the linked examples; correct unknown fields, dangling component relationships, invalid requirement IDs and missing required fields. Do **not** disable validation. |
| No readable `docs/architecture/` was created | The CLI produces JSON/Mermaid/review outputs. Ask Claude Code separately to write Markdown into the app folder and approve file writes. |
| Diagram lacks edges | No relationships were supplied; document real interactions in the fixture and regenerate, rather than inventing edges. |
| `requires_review`, `planned_only`, `uncovered` | These indicate uncertainty or lack of verification, not necessarily an error. Keep them visible until supported by real evidence. |
| Review abstains on architecture style | Add an explicit `review.json` with style drivers, then pass `--config`. |
| Return code `2` from `--strict` | The command intentionally flags unresolved review work; artifacts may still have been written. |
| `output must be a new or empty directory; existing files not overwritten` | Every `speccanopy` and `speccanopy-experts` command that writes output refuses an existing non-empty folder, a file or a symlink before writing anything (`source-inventory` and `approve-ai` write files and refuse existing ones, including the `.approval.json` receipt). Re-run into a new path such as `out/myproject-v2`. Since this release `design`, `review`, `propose-ai`, `refine-plan`, `refine-apply`, `benchmark`, `research-case`, `research-suite`, `approve-ai` and `speccanopy-experts aggregate` enforce this too (previously they silently replaced files), and `propose-ai` refuses before any model request. The check is best-effort: it inspects the final path component and cannot exclude a concurrent local writer. |
| `source-diff` reports `scope_differs` or `scope_unknown` | The two inventories used different size limits/privacy rules, or one predates scope recording. Re-inventory both states the same way; see the [inventory comparison guide](source-inventory-diff.md#6-troubleshooting). |
| Worried about direct API charges | Use Claude Code with subscription authentication; leave `ANTHROPIC_API_KEY` unset, and avoid the separate `propose-ai --backend claude` HTTP client. |
| Claude cannot see your app folder | Check the path and access permissions; restart with `claude --add-dir PATH_TO_APP` if appropriate. |

## 8. Current limitations and next development work

**Available as prototypes:** validated architecture schemas; fixture-driven recursive decomposition; Claude Code-assisted input drafting; JSON + Mermaid exports; requirement coverage; heuristic review; explicit uncertain statuses; offline Python `project-intake`; the `document` Markdown pack; allowlisted `source-inventory` with SHA-256-bound source claims; `source-diff` comparison of two inventories; `source-impact` mapping of file changes onto authored source claims; and the `doc-gate` documentation review gate. An offline acceptance suite exercises intake → design → review → document on a committed **synthetic** example ([walkthrough](end-to-end-acceptance.md)).

**Not built in:** semantic (behavioural) architecture extraction, intake for languages other than Python and JavaScript/TypeScript (the JS/TS intake is a lexical scan without alias resolution), semantic judgement of whether a changed file invalidates a claim (`source-impact` maps changes by digest only), automatic documentation synchronization with source changes, rename detection beyond identical-byte candidates in `source-diff`, complete runtime/deployment/data views, an owner-confirmed acceptance test on a real application (a [maintainer-run pilot on a permissively licensed package](pilot-third-party-python.md) exists, without owner confirmation), and independently expert-validated architecture quality. [Issue #5](https://github.com/MSKazemi/speccanopy/issues/5) tracks documentation product readiness; [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2) tracks human-review evidence. You do **not** need external expert reviewers merely to draft your own project documentation, but you must not imply AI/heuristics provide independent certification.

**Recommended first run:** start with one small existing project, inspect the draft and traceability outputs, and have Claude Code write source-linked `docs/architecture/` pages for your approval.

## 9. Related documentation

- [Short inputs/outputs quick start](claude-code-quickstart.md)
- [Compare source inventories (`source-diff`)](source-inventory-diff.md)
- [Map source changes to affected claims (`source-impact`)](source-claim-impact.md)
- [Compare module structure between two intakes (`structure-diff`)](structure-diff.md)
- [JavaScript/TypeScript project intake (`--language javascript`)](javascript-project-intake.md)
- [Documentation review gate (`doc-gate`)](documentation-review-gate.md)
- [End-to-end acceptance walkthrough (synthetic example)](end-to-end-acceptance.md)
- [Pilot on a real third-party Python package (measured, not owner-confirmed)](pilot-third-party-python.md)
- [Owner pilot on Speccanopy itself (owner-confirmed requirements)](owner-pilot-speccanopy.md)
- [Claude subscription versus API billing](claude-integration.md)
- [Real-project readiness and detailed walkthrough](project-documentation-readiness.md)
- [Architecture contract and statuses](architecture-contract.md)
- [Example AI-only critique](ai-assisted-case-review.md)
- [Contributing](../CONTRIBUTING.md)
