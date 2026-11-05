# Copy/paste into Claude Code — Document my existing application

Replace `~/projects/my-app` with the actual application directory. Launch Claude from the Speccanopy checkout with access to that folder (see [the user guide](../docs/USER_GUIDE.md)).

---

Read `CLAUDE.md` and `docs/USER_GUIDE.md` before acting.

My existing application repository is `~/projects/my-app`. I want accurate, reviewable **architecture documentation for the CURRENT application**. Do not implement a new application or modify its source code.

1. Inspect only authorized paths: README, source modules, entry points, tests, configuration and API/data definitions. Exclude `.env`, credentials, private keys, real user data, production dumps and other secrets. Ask if access to a sensitive area is necessary.
2. Identify system purpose, actors, functions, quality requirements, component boundaries, dependencies, data ownership, trust boundaries and meaningful design trade-offs. Clearly distinguish **observed source facts**, **inferences**, **proposals** and **unknowns**.
3. Create schema-valid `out/myproject-inputs/brief.json` (SystemBrief) and `out/myproject-inputs/design.json` (FixtureDesign). Look at `examples/cli-utility.json` and `examples/cli-utility.design.json` for structure. Use stable requirement IDs and real component IDs. Do not add arbitrary unsupported fields to the strict JSON schemas.
4. Record paths/line references and outstanding assumptions separately in `out/myproject-inputs/source-evidence.md`. Never fabricate validation evidence, expert reviews, API contracts or undocumented runtime behavior.
5. From the **Speccanopy** repo root, run:
   ```bash
   speccanopy design out/myproject-inputs/brief.json --fixture out/myproject-inputs/design.json --output out/myproject
   speccanopy review out/myproject/architecture.json --output out/myproject-review
   speccanopy document out/myproject/architecture.json --review out/myproject-review/architecture-review.json --output out/myproject-docs
   ```
   Fix schema errors by correcting the actual input; do not bypass validation.
6. Use the baseline docs from `out/myproject-docs/` as a starting point. Reconcile the pages with actual code paths, then after obtaining my permission to write in the application repository, create a readable `docs/architecture/` directory there: `README.md`, `overview.md`, `requirements.md`, `components.md`, `interactions.md`, `data-security.md`, `decisions.md`, `quality-risks.md`, `open-questions.md`. Embed Mermaid diagrams, cite actual source references, and keep uncertainty visible.
7. Do not claim independent certification, readiness for production or actual implementation tests. Do not edit my application code.
8. Conclude with: **files created**, **documented system overview**, **high-risk assumptions**, and **questions I need to answer**.

**My extra project constraints (optional):** [Insert your architecture constraints, important quality goals and desired documentation depth here.]

---

**Notes:** The CLI now emits `out/myproject/`, `out/myproject-review/` and baseline Markdown pages in `out/myproject-docs/`. Final application docs under `docs/architecture/` still require Claude Code's source-grounded reconciliation and my approval. No extra Anthropic API key is needed for this interactive subscription-backed workflow.
