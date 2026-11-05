# Claude Code + Speccanopy — exact inputs and outputs

**For all guidance and troubleshooting see the [complete user guide](USER_GUIDE.md).**

**Status (2026-11-05): Guided architecture-documentation workflow, NOT a one-command repo-to-doc generator.** Claude Code authors the project-specific inputs and readable narrative; the Speccanopy CLI validates structure, generates diagrams, and performs rule-based review. A Claude Code subscription suffices for the interactive workflow. The optional direct `propose-ai --backend claude` API endpoint needs its own Anthropic API key; do not use that command for this subscription-based tutorial.

## Input — what you supply

For an **existing project**, you need only:
- A local readable application repository, e.g. `~/projects/my-app`.
- The project purpose and any known requirements, constraints, user roles or architectural expectations (README, issue descriptions, spec or a short message). Claude can infer candidate requirements from the *available* source, but cannot reliably discover unstated business requirements.
- Clear scope: which folders Claude may inspect, which secrets/private files to exclude, and where it may write documentation.
- A project owner who will review the provisional assumptions and make design decisions.

For a **new project without source code**, provide its purpose, actors, features, reliability/security/performance needs, deployment constraints, preferred technologies if any and known unknowns. Claude must label everything as a **proposed design**, not an observed implementation.

### Terminal setup (Bash or Zsh)

Assume Speccanopy and your application reside at `~/projects/speccanopy` and `~/projects/my-app`, respectively. Replace `my-app` with your own application directory. The app directory must already exist.

```bash
mkdir -p ~/projects
git clone https://github.com/MSKazemi/speccanopy.git ~/projects/speccanopy
cd ~/projects/speccanopy
python -m pip install -e '.[dev]'
pytest -q

# Use an eligible Claude Code subscription, not direct API billing.
unset ANTHROPIC_API_KEY
claude --add-dir ~/projects/my-app
```

If the clone already exists, skip `git clone`; run `git pull --ff-only` from the Speccanopy checkout if appropriate. Claude Code reads the root Speccanopy `CLAUDE.md`. The `--add-dir` flag extends access to the separate application directory; approve only access you intend to grant. Documentation: [Anthropic's multi-repository Claude Code tips](https://support.claude.com/en/articles/14554000-claude-code-power-user-tips).

### What to paste into Claude Code

> Read `CLAUDE.md` and `docs/project-documentation-readiness.md`. My existing application is at `~/projects/my-app`. Inspect only its authorized source code, README, configuration, tests and API/data definitions; do not read secrets, `.env`, private keys, or production data. Document its **current** architecture, separate from possible future redesign. Prepare a `SystemBrief` at `out/myproject-inputs/brief.json` and a `FixtureDesign` at `out/myproject-inputs/design.json` using this repository's valid Pydantic schemas/examples. Include requirements with stable IDs, component boundaries, owned data, and only relationships supported by project evidence. Keep uncertain details as explicit questions; do not fabricate verification evidence. Run the exact CLI design and review commands below. Then write a human-readable `docs/architecture/` Markdown set in the app directory based on the source and generated architecture, including context, requirements, components, interactions, data/security, ADRs, risks, and questions. Include Mermaid diagrams and cite source paths for observed details. Don't change application source code. Ask for approval before writing into the app repository. End with the paths created, a short summary, and remaining questions.

**Inputs Claude creates for the CLI** (under the Speccanopy checkout):
- `out/myproject-inputs/brief.json` — typed goals, actors, functional and quality requirements, constraints (from `SystemBrief`).
- `out/myproject-inputs/design.json` — a **provisional**, reviewed-by-owner fixture with root, `proposals_by_parent`, and any well-founded relationships, decisions and verification plans.

These input files are authored/inferred by Claude Code. **They are not evidence that Speccanopy autonomously scanned or inferred the real project.** The `out/` directory is gitignored in the Speccanopy repository.

## Exact CLI commands Claude should run

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

`review --config path/to/review.json` is optional. Without explicit style drivers, style selection can be abstention. Incomplete or unresolved input is still exported and marked for review, not silently certified.

## Output — what you receive

**Speccanopy's generated files** (deterministic from accepted inputs):

```text
speccanopy/
└── out/
    ├── myproject-inputs/
    │   ├── brief.json                # Claude-authored input
    │   └── design.json               # Claude-authored provisional fixture
    ├── myproject/
    │   ├── architecture.json         # ArchitectureSpec, components and relationships
    │   ├── architecture.mmd          # Mermaid component hierarchy
    │   ├── relationships.mmd         # Mermaid dependency/interaction graph
    │   ├── requirements-report.json # Coverage and component ownership
    │   ├── decisions.json            # ADRs and open findings in structured form
    │   └── generation-trace.json     # Generator decisions and limitations
    └── myproject-review/
        ├── architecture-review.md    # Human-readable rule-based review
        ├── architecture-review.json
        ├── style-comparison.json
        └── quality-review.json
```

**New built-in baseline Markdown output:** `speccanopy document` automatically produces `out/myproject-docs/` with nine Markdown pages (`README.md`, `overview.md`, `requirements.md`, `components.md`, `interactions.md`, `data-security.md`, `decisions.md`, `quality-risks.md`, `open-questions.md`) and two Mermaid files (`architecture.mmd` and `relationships.mmd`). These pages describe the supplied architecture, not verified facts about a repository. See [renderer documentation](architecture-documentation-renderer.md).

**Claude Code's optional additional documentation**, if you request it and authorize writes in the app:

```text
my-app/
└── docs/
    └── architecture/
        ├── README.md                # Architecture documentation index
        ├── overview.md              # Purpose, actors, context, observed design
        ├── requirements.md          # Requirement IDs and source references
        ├── components.md            # Boundaries and responsibilities
        ├── interactions.md          # Interfaces, data and event flows + Mermaid
        ├── data-security.md         # Data ownership and trust boundaries
        ├── decisions.md             # ADRs and alternatives
        ├── quality-risks.md         # Reliability, security, risks, validation gaps
        └── open-questions.md        # Unresolved items requiring user decisions
```

**Important:** The baseline `out/myproject-docs/` directory is now generated by Speccanopy, but does not include verified source-code provenance. Claude Code must reconcile it and, with your permission, place the final Markdown pages in the application's `docs/architecture/`.

## Reading a result

- `architecture.json`: authoritative **structured draft of the stated architecture**, not proof that the app implements every claimed behavior.
- `architecture.mmd`: hierarchy; `relationships.mmd`: directed dependencies. Mermaid files can be pasted into compatible Markdown renderers as fenced `mermaid` blocks.
- `requirements-report.json`: `verified` means evidence was supplied and accepted by the schema; do not trust AI-authored evidence as independent verification. `planned_only` and `uncovered` are not complete.
- `architecture-review.md`: heuristic contract/requirement quality findings; not an expert sign-off.
- `open-questions.md` (Claude-authored): the project owner must resolve factual uncertainty and approve architectural decisions.

No target application code, build, test, or deployment is produced. No independent human expert is required just to draft documentation, but an AI critique does not constitute independent expert validation.

## Without an existing application

Start `claude` from the Speccanopy checkout and give it a **requirements description**, not a repository path. For example:

> Design architecture documentation for an internal task tracker: users create tasks, assign owners, see due dates and receive reminders. Must require account sign-in, enforce owner-based access and run on one low-cost server. State unknown capacity, operational and privacy constraints. Create a proposed `brief.json` and `design.json`, run `speccanopy design` and `speccanopy review`, and author a provisional `docs/architecture/` set. Do not claim any code exists or the design is verified.

Your outputs are **proposals** until you, the owner, decide the requirements and design.

## What is not automatic yet

Repository-to-brief extraction, full Markdown documentation rendering, source-aware drift detection, richer runtime/deployment/data diagrams, and end-to-end real-project tests are outstanding development tasks under [Issue #5](https://github.com/MSKazemi/speccanopy/issues/5).

For more information: [project documentation readiness](project-documentation-readiness.md), [Claude subscription versus API](claude-integration.md), and [source-of-truth architecture contract](architecture-contract.md).
