# User guide — Document a software project with Speccanopy + Claude Code

**Start here.** Speccanopy is currently a **guided architecture-documentation prototype**, not a one-command source-to-documentation product. With your Claude Code subscription, Claude helps gather project facts, build inputs, and write readable Markdown; the Speccanopy CLI validates a structured architecture and generates diagrams and advisory reviews. You decide which architecture assertions and decisions to accept.

**Scope:** Speccanopy designs and documents **software architecture**. It does not implement, build, test or deploy the application that it describes.

## 1. Input and output at a glance

| You have | You provide | What you receive |
| --- | --- | --- |
| **An existing application** | The local folder containing code, README, tests, config and available requirements; permission to inspect relevant files | A draft architecture model, component/dependency diagrams, requirement coverage, review findings, and optional readable Markdown architecture documentation |
| **A new application idea** | Goal, intended users, features, security/reliability goals, technology and deployment constraints | A **proposed** architecture with diagrams, decisions and unresolved assumptions; not a description of already-existing code |
| **No Claude Code** | A valid `SystemBrief` JSON and project-specific `FixtureDesign` JSON | The same deterministic CLI-generated architecture files and optional rule-based review, but no automatic repository analysis or complete narrative handbook |

The CLI does **not** scan an application repository. In the guided workflow **Claude Code** prepares the two JSON inputs from sources you authorize, and **you review the assumptions**.

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

## 3. Give Claude Code this instruction (existing project)

Paste this into the interactive Claude Code terminal after replacing the folder path:

> Read `CLAUDE.md` and `docs/USER_GUIDE.md`. My existing application is at `~/projects/my-app`. I want **architecture documentation for the current implementation**, not changes to application source code. Inspect authorized source files, README, tests, configs, API and database definitions; do not read `.env`, secrets, keys or private production data. Identify system goals, actors, requirements, components, component boundaries, interactions, data ownership, key decisions and quality risks. Produce schema-valid `out/myproject-inputs/brief.json` (SystemBrief) and `out/myproject-inputs/design.json` (FixtureDesign), using Speccanopy's examples. Store file/line references for source-derived claims separately in `out/myproject-inputs/source-evidence.md`, without inventing unsupported JSON fields. Label uncertainties and proposed changes clearly; do not invent test evidence, expert approval or a validated status. Run `speccanopy design` and `speccanopy review` as specified below. With my approval, write readable Markdown into my application's `docs/architecture/` directory, including overview, requirements, components, interactions, data/security, decisions, quality risks and open questions. Include Mermaid diagrams, cite actual source files for observed facts, and do not edit application code. Finish by listing files created, critical findings and questions for me to resolve.

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
```

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
    │   └── source-evidence.md        # Optional: source references and unknowns
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

**The second set is NOT automatically created by the current Speccanopy CLI.** Claude Code writes it from the generated data and the original application's evidence. The exact document filenames may vary according to the project and your instructions. Speccanopy's own `out/` is ignored by Git; keep versioned application documentation under the application repository if desired.

### Understanding the results

- `architecture.json` is a **draft**—not proof that the code implements all requirements.
- `architecture.mmd` shows containment; `relationships.mmd` shows directed interactions. They are Mermaid **source text**, which a Markdown renderer can display using ```mermaid fences.
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
| Worried about direct API charges | Use Claude Code with subscription authentication; leave `ANTHROPIC_API_KEY` unset, and avoid the separate `propose-ai --backend claude` HTTP client. |
| Claude cannot see your app folder | Check the path and access permissions; restart with `claude --add-dir PATH_TO_APP` if appropriate. |

## 8. Current limitations and next development work

**Available as prototypes:** validated architecture schemas; fixture-driven recursive decomposition; Claude Code-assisted input drafting; JSON + Mermaid exports; requirement coverage; heuristic review; explicit uncertain statuses.

**Not built in:** automatic repo-to-brief intake, one-command complete Markdown handbook, documentation synchronization with source changes, complete runtime/deployment/data views, and independently expert-validated architecture quality. [Issue #5](https://github.com/MSKazemi/speccanopy/issues/5) tracks documentation product readiness; [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2) tracks human-review evidence. You do **not** need external expert reviewers merely to draft your own project documentation, but you must not imply AI/heuristics provide independent certification.

**Recommended first run:** start with one small existing project, inspect the draft and traceability outputs, and have Claude Code write source-linked `docs/architecture/` pages for your approval.

## 9. Related documentation

- [Short inputs/outputs quick start](claude-code-quickstart.md)
- [Claude subscription versus API billing](claude-integration.md)
- [Real-project readiness and detailed walkthrough](project-documentation-readiness.md)
- [Architecture contract and statuses](architecture-contract.md)
- [Example AI-only critique](ai-assisted-case-review.md)
- [Contributing](../CONTRIBUTING.md)
