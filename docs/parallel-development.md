# Working on Speccanopy with Claude Code in parallel

**Checked 2026-11-06. Scope: development of Speccanopy, not execution/deployment of an application it documents.** This is a delegation plan; no Claude Code session, worker, or background task was launched by preparing it.

## Recommendation

Use **Claude Code for local implementation and terminal tests**, with a lead that integrates changes, and use a separate ChatGPT review of the resulting PR/diff when it is available. Avoid having two assistants modify the same core modules simultaneously. A single accountable integrator, limited scope and full combined tests are more important than the number of agents.

Focus this iteration on engineering work under [Issue #5](https://github.com/MSKazemi/speccanopy/issues/5), not on declaring all issues complete. The inspected main baseline was `cf29646ccaa805732afdf6159d5960f4d66009cc`; it already implements Python AST intake, source inventory, source snapshot checks, architecture generation/review and Markdown documentation. Recheck the live baseline rather than rebuilding completed features.

**Use the full ready-to-run assignment:** [Claude Code parallel Issue #5 prompt](../prompts/claude-code-parallel-issue5.md).

## Model names

Suggested allocation:

| Role | Recommended model | Explicit Claude Code ID |
| --- | --- | --- |
| Lead planning, integration and final review | Claude Opus 5.5 | `claude-opus-5-5` |
| Bounded coding and test workers | Claude Sonnet 5.5 | `claude-sonnet-5-5` |

These model IDs are listed in [Anthropic's current Claude Code model guide](https://support.claude.com/en/articles/11940350-claude-code-model-configuration). Anthropic recommends Sonnet for most coding and Opus for harder architecture/debugging decisions; see [model/usage guidance](https://support.claude.com/en/articles/14552983-models-usage-and-limits-in-claude-code). The allocation above is our workflow recommendation, not a comparative Speccanopy benchmark.

Check `/model` for what your account actually permits, and `/status` for the session configuration. If Opus is unavailable, use an available Sonnet and keep the task smaller. Do not silently switch to paid direct API access to bypass plan limits. `claude update` can update a supported CLI installation; current official documentation says Opus 5.5 requires v2.1.280+ and Sonnet 5.5 v2.1.284+. Verify installed-version support and entitlement before relying on either. [Model configuration reference](https://code.claude.com/docs/en/model-config).

Start with one lead and **no more than two workers**. Parallel sessions consume usage; they are not free extra capacity. Sequential execution is a reasonable fallback under tight limits.

## Start the lead session

From an existing Speccanopy checkout, in Bash/Zsh, first inspect `git status --short`. Preserve uncommitted work. On a clean checkout of the intended baseline, pull the latest changes and launch an isolated session:

```bash
git pull --ff-only
claude update
unset ANTHROPIC_API_KEY
claude --worktree issue5-integration --model claude-opus-5-5
```

Use a fresh worktree name if `issue5-integration` already belongs to unrelated work. If the directory has not been trusted by Claude Code yet, start `claude` once and complete its normal trust/authentication flow, then launch the worktree session.

The `--worktree` flag creates an isolated checkout/branch for that session. Each writing worker must have its **own** worktree, branch and Python virtual environment, not just a separate chat. Ask the lead to verify all worker base commit SHAs; worker worktrees can otherwise start from the default remote branch rather than an in-progress integration branch. See [Anthropic's worktree guide](https://code.claude.com/docs/en/worktrees) and [subagent isolation](https://code.claude.com/docs/en/sub-agents).

Keeping `ANTHROPIC_API_KEY` unset avoids the documented environment-key override when you intend to use an eligible Claude Code subscription. Verify the actual authentication with `/status`; never paste or expose credentials. See [Anthropic's authentication guidance](https://support.claude.com/en/articles/12304248-manage-api-key-environment-variables-in-claude-code). None of Speccanopy's local deterministic commands needs a paid model API request.

Inside Claude Code, paste:

> Read `CLAUDE.md`, `docs/parallel-development.md`, and `prompts/claude-code-parallel-issue5.md`. Execute that bounded implementation assignment. Use at most two writing workers in separate verified Git worktrees; use Sonnet 5.5 for workers if available. You are the lead and own shared CLI/schema/documentation integration. Recheck the latest code and Issue #5, run a baseline test, preserve all uncommitted work, implement the change-reporting and acceptance-test slices, update user documentation with tested commands, and run the full integrated test suite. Work on feature branches only. Ask before publishing a branch/PR; do not push directly to main, merge, close issues or claim human/expert verification. If worktree-isolated delegation is unavailable, continue sequentially and say so.

## File ownership and deliverables

| Owner | Initial scope | Boundaries |
| --- | --- | --- |
| Worker A | A new pure inventory comparison module and its focused tests | Added/removed/changed/unchanged source snapshots; no writes to target application; no automatic overwrite of documents |
| Worker B | New offline end-to-end acceptance/regression tests and a dedicated walkthrough | Test current intake → design → review → document, missing evidence, stale files and privacy; don't modify production modules owned by A/the lead |
| Lead | CLI integration, public contract compatibility, combined review/tests and shared usage documentation | Only the lead edits shared CLI/models/renderer/source-reader, README, CLAUDE.md, common docs, packaging and CI |

Freeze the small API contract and ownership plan **before** delegating. Integrate worker commits one at a time. Two independently passing branches may still fail together. Worktrees reduce concurrent edit collisions; they do not make incompatible changes merge automatically.

Every feature change must ship with installation/prerequisite notes, exact inputs and outputs, copyable working commands, exit codes, safe reruns, privacy boundaries and honest supported/unsupported scope. Record results observed, not hoped-for results.

## What stays blocked by real-world evidence

[Issue #2](https://github.com/MSKazemi/speccanopy/issues/2) needs actual independent review evidence; [Issue #3](https://github.com/MSKazemi/speccanopy/issues/3) and [Issue #4](https://github.com/MSKazemi/speccanopy/issues/4) concern human participants and permissioned cases. AI code, generated sample cases and self-declared reviews cannot replace those facts. A missing repository license is also an owner decision, not permission for an agent to select one unilaterally.

A genuine external application acceptance test needs an actually authorized application. Without one, label tests as synthetic or self-dogfooding and keep that milestone open. Do not download/republish external code merely because it is publicly visible.

## Handoff back for review

Return the feature branch/PR or diff, baseline/final commits, exact test output, new usage commands and remaining questions. Another ChatGPT/Claude session can review those artifacts when explicitly given access; no automatic cross-product coordination or background review is implied.

**This guide and prompt do not implement the new diff feature or close any issue.** They establish a safe, bounded implementation handoff for the user's Claude Code environment.
