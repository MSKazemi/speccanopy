# Claude Code prompt — Prepare architecture docs from an existing Python project

**Replace the project path, name, goal, and real business requirements below.** Launch Claude Code from the Speccanopy checkout with access only to the approved application folder. Use your Claude Code subscription, **not** a separate Anthropic Messages API key.

---

Read `CLAUDE.md`, `docs/python-project-intake.md`, `docs/USER_GUIDE.md` and `docs/source-evidence-workflow.md`.

My authorized Python application is at `~/projects/my-app`. I want **architecture documentation for its current implementation**, not a new implementation.

- **System name:** My Inventory App
- **Goal:** Explain the current implementation and its architecture boundaries
- **Actual user requirement 1:** Users can create inventory records
- **Actual user requirement 2:** Users can view existing inventory records

Follow these rules:

1. Do not inspect `.env`, hidden/private paths, secrets, credentials, production user data, private keys or other prohibited materials. Do not modify my application code. Ask me before accessing files outside the authorized scope or writing into the application repository.
2. From the Speccanopy directory, **run** the offline static intake with the supplied real requirements:

   ```bash
   speccanopy project-intake ~/projects/my-app \
     --system "My Inventory App" \
     --goal "Explain the current implementation and its architecture boundaries" \
     --requirement "Users can create inventory records" \
     --requirement "Users can view existing inventory records" \
     --output out/my-app-inputs
   ```

3. Open `out/my-app-inputs/intake-review.md`, `module-observations.json`, `brief.json`, `design.json` and `source-evidence.json`. Identify which Python modules and source-level import declarations were observed. **Do not treat module names as proven responsibilities**, import edges as runtime calls, or a matching hash as proof of semantic correctness. Highlight any ignored non-Python code.
4. Run the local CLI pipeline with the original preliminary inputs:

   ```bash
   speccanopy design out/my-app-inputs/brief.json \
     --fixture out/my-app-inputs/design.json \
     --output out/my-app-design
   speccanopy review out/my-app-design/architecture.json \
     --output out/my-app-review
   speccanopy document out/my-app-design/architecture.json \
     --review out/my-app-review/architecture-review.json \
     --source-root ~/projects/my-app \
     --source-evidence out/my-app-inputs/source-evidence.json \
     --output out/my-app-docs
   ```

5. **Ask me which uncertain decisions to accept.** Review the actual authorized source files to refine the design fixture: map each user requirement to real responsible components, specify observed interfaces/data boundaries, record assumptions and uncertainty, and add only honestly *planned* verification cases. Do not invent execution results, external expert signoff, accepted ADRs, verified coverage, or implementation behavior not observable in files.
6. Save proposed refinements in a **new** inputs directory rather than silently overwriting existing inputs. Re-run the design, review and document commands into **new empty output directories**. Review the generated `source-evidence.md`, `requirements.md`, `quality-risks.md`, and `open-questions.md` and flag any stale/missing file references.
7. If a part of the system uses TypeScript, JavaScript or other unsupported languages, analyze it manually with explicit permission and label it **outside the Python AST intake coverage**. Do not imply it was verified by Speccanopy.
8. With my final approval, place source-reconciled Markdown pages and Mermaid diagrams under the application's `docs/architecture/`. Never overwrite existing human-written documentation without showing a diff and asking me.
9. Finish with (a) the exact inputs/outputs created, (b) architecture summary, (c) observed versus inferred claims, (d) changed/unverified sources and requirement gaps, and (e) concise questions for me.

**No target application implementation, deployment, API billing, private data publishing or artificial expert certification is authorized.**

---

For other languages or source trees larger than the documented intake bounds, use the [manual Claude-assisted workflow](claude-code-document-project.md) instead. The Python-intake command is a candidate generator, not a comprehensive automatic architecture analyzer.
