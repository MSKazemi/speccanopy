# Python project intake — from a source folder to architecture documentation

**New in Speccanopy (2026-11-06):** `speccanopy project-intake` performs **offline, bounded static Python AST analysis** to prepare initial architecture-design inputs for a real local project.

**Important:** This is a **provisional technical inventory**, not an AI architect, application builder, verified code-to-architecture analyzer, or automatic business-requirement extractor. The project owner supplies real requirements. Speccanopy identifies Python source modules, top-level class/function names, and import declarations **without executing application code**. Claude Code can help review and refine the draft using your existing Claude subscription.

## 1. What you provide (input)

| Input | Example | Required? |
| --- | --- | --- |
| Local Python application folder | `~/projects/my-app` | Yes |
| Project name | `My Inventory App` | Yes, `--system` |
| Project goal | `Document the architecture of our existing app` | Yes, `--goal` |
| At least one **actual business function** | `Users can create inventory records` | Yes, repeat `--requirement` |
| Authorized source scope | Point the command only at a folder you are authorized to analyze | Yes |
| Claude Code | Used for semantic review/refinement, but **not required** for the offline intake command | Optional |

**Language scope:** The first version analyzes only allowlisted **Python `.py` files**. It ignores JavaScript, TypeScript, Go, Rust, SQL, configuration, tests and other languages for architectural extraction. Those files can still be present in the metadata inventory. **Do not** treat this as complete architecture extraction for a mixed-language system.

The supplied requirement is included as a **human-authored requirement**, not silently mapped to a module. Use a real feature or obligation of your app, not merely a generic statement that you want documentation.

## 2. Install and run (no paid model API)

From a Bash/Zsh terminal:

```bash
mkdir -p ~/projects
git clone https://github.com/MSKazemi/speccanopy.git ~/projects/speccanopy
cd ~/projects/speccanopy
python -m pip install -e '.[dev]'
pytest -q

speccanopy project-intake ~/projects/my-app \
  --system "My Inventory App" \
  --goal "Document the architecture of the current application" \
  --requirement "Users can create inventory records" \
  --requirement "Users can view their existing inventory records" \
  --output out/my-app-inputs
```

If you already cloned Speccanopy, skip `git clone` and run `git pull --ff-only` if appropriate.

The intake runs **locally** and does not request an Anthropic/OpenAI key, access the network, or execute Python target modules. It reads allowlisted local files and parses their Python AST syntax. The existing sensitive-path exclusions in `source-inventory` apply; these are **best-effort**, so ensure the selected application folder is permitted for analysis. It does not read `.gitignore` or guarantee that allowed files contain no secrets.

### Output immediately after intake

```text
speccanopy/out/my-app-inputs/
├── brief.json                 # Schema-valid human goals and requirements
├── design.json                # Provisional root + one component per Python module,
│                               # with candidate static import relationships
├── source-evidence.json       # Byte-hash-linked AST module/import observations
├── source-inventory.json      # Allowlisted file paths, sizes, line counts, SHA-256
├── module-observations.json   # Modules, top-level names, import links and gaps
└── intake-review.md           # Readable analysis summary and owner checklist
```

The generated evidence map links **syntactically observed** Python modules and static import declarations to file hashes. It does **not** claim that any module implements the user-supplied requirements. Class/function names are output as names only, not source bodies. However filenames and symbol names may still be confidential—do not publish the output without reviewing it.

## 3. Generate the draft architecture, review and readable documentation

Run the following commands from the Speccanopy checkout:

```bash
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

Now read `out/my-app-docs/README.md`, `source-evidence.md`, `requirements.md`, `components.md`, `interactions.md`, and `open-questions.md`. The full output also contains `overview.md`, `decisions.md`, `data-security.md`, `quality-risks.md`, and two Mermaid `.mmd` diagrams.

**Expected:** the generated architecture will normally have status `incomplete_requires_review`; its business requirements will be **uncovered** until you map them to real implementation modules and add appropriate plans/evidence. Module interfaces, data ownership, architectural style, deployment choices and ADRs are **not automatically inferred**. That is the correct conservative behavior, not a broken generator.

`--strict` can be used with the `document` command to return exit code **2** for unresolved status/evidence while still writing the draft. An error gives exit code **1**.

## 4. Work with your Claude Code subscription

You **do not need a separate Anthropic API key** for this workflow. With an eligible Claude Code subscription:

```bash
cd ~/projects/speccanopy
unset ANTHROPIC_API_KEY
claude --add-dir ~/projects/my-app
```

Paste this into Claude Code (change the application path and business requirements):

> Read `CLAUDE.md`, `docs/python-project-intake.md`, `docs/USER_GUIDE.md`, and `docs/source-evidence-workflow.md`. I authorize you to inspect only the necessary, non-sensitive files in `~/projects/my-app` for architecture documentation. Do not inspect `.env`, private keys, production data, or other secrets, and do not change app source code. Use `speccanopy project-intake` with my real project name, goal and requirements to prepare draft inputs; open `intake-review.md` first. Run design/review/document, keep their incomplete statuses, and examine the project source to identify where the preliminary component grouping or import edges are misleading. With my approval, refine `brief.json`, `design.json`, and the **authored** `source-evidence.json` only when actual source supports a claim. Map each requirement to an actual component, specify real interfaces/data/risks, and record unresolved questions. Re-run each command in new empty output folders and show me the Markdown pack and outstanding questions. Never invent tests, independent reviewers, runtime calls or business behavior.

A standalone reusable version is also at [`prompts/claude-code-python-intake.md`](../prompts/claude-code-python-intake.md).

**Distinction:** Claude Code is the interactive assistant on your subscription. The optional `speccanopy propose-ai --backend claude` CLI is a **separate** direct Anthropic API integration requiring its own authorized API key and billing. You do not need it here.

## 5. What Speccanopy actually analyzes

- Creates one **candidate** component per allowlisted Python source module, with a stable path-derived component ID (until the path changes).
- Uses the built-in Python `ast` parser to list top-level class/function names and explicit imports of **other modules present in the selected source scope**.
- Supports common absolute imports and relative imports such as `from .service import Service`. Records static import declarations as **dependency candidates**, not confirmed runtime calls.
- Excludes test modules from proposed application components. Keeps an inventory of allowed documentation/tests/config files but **does not** infer their semantics.
- Uses a SHA-256 digest of each local source file; source hashes are rechecked when you run `document --source-root ... --source-evidence ...`.
- Never executes imported application modules or builds/deploys the described application.
- Does not invent functional requirements, verified test results, data ownership, architecture style, interface contracts or ADR acceptance.

**Limitations:** dynamic imports, runtime dependency injection, network/queue/data flows, framework registrations, external APIs and infrastructure are not extracted. Python static imports may be conditional or used only for type checking. AST syntax checks are **not** a substitute for code review.

## 6. Bounds, privacy and common errors

| Problem or setting | Behavior |
| --- | --- |
| One component per module is too fine-grained | Write a `groups.json` and run `speccanopy group` ([guide](grouping-modules.md)); the intake budget leaves room for one grouping layer |
| Test fixtures or examples are counted as modules | Add `--exclude examples` (repeatable; a project-relative directory or file). A prefix that matches nothing is an error, and exclusions are recorded in `module-observations.json` and `intake-review.md` |
| No Python files in the selected folder | Command fails with a scope message. For JavaScript/TypeScript use `--language javascript` ([guide](javascript-project-intake.md)); for other languages use Claude Code-assisted manual intake |
| Python syntax error in an allowed file | Command fails before writing partial artifacts; choose a correct subtree or fix the source separately |
| More than 30 eligible Python modules | Command fails with an explicit count; select a smaller source folder or use `--max-modules` up to **50** |
| Too many files | Max 2,000 allowlisted files by default; `--max-files` up to 10,000 |
| Oversized files | Per-file limit 1,000,000 bytes by default; `--max-file-bytes` up to 5,000,000. Oversized files are counted/skipped, so inspect the omissions |
| Symlinks/private-looking paths | Symlinks, dot/hidden paths and known sensitive directories/filenames are excluded or rejected, best effort |
| Existing nonempty output | Rejected rather than silently overwriting previous or approved docs |
| Duplicate resolved module names | Fails closed instead of guessing which module is meant |
| Changed/removed file after intake | The subsequent `source-evidence.md` reports changed/missing hashes; regenerate to a **new empty output folder**. To list every added/removed/changed file (not only cited ones), compare `<intake-output>/source-inventory.json` with a new inventory using `speccanopy source-diff` ([guide](source-inventory-diff.md)) |
| Unsupported JavaScript/TypeScript/etc. | Listed under non-Python sources not analyzed; do not infer them as missing runtime components |
| Want production certification | Source syntax and matching hashes **do not** authenticate behavior, safety, expert agreement or production quality |

The tool writes no raw source contents into its outputs, but **filenames, exported symbols, user-provided requirements and assertions may be sensitive**. Do not commit generated files for private applications to a public repository without permission.

## 7. Next steps still open

This milestone completes an initial **Python-only source-structure intake** plus an offline synthetic-project end-to-end test. It **does not** complete [Issue #5](https://github.com/MSKazemi/speccanopy/issues/5): meaningful automatic semantic extraction across languages/frameworks, evaluation on an actual rights-cleared application, change-aware source-to-document reconciliation and full architectural review gates remain open.

See also [the full project user guide](USER_GUIDE.md), [source evidence workflow](source-evidence-workflow.md), and [Markdown renderer guide](architecture-documentation-renderer.md).
