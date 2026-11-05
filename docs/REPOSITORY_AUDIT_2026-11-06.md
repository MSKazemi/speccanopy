# Repository audit — 2026-11-06

**Repository:** [MSKazemi/speccanopy](https://github.com/MSKazemi/speccanopy)  
**Baseline examined:** `main` at `95df9a4a9eb071d6a2998f7f02e93bea6d0e45dd` (before this audit-document commit).  
**Purpose:** Identify outstanding, actionable work for Speccanopy as a **software architecture design/documentation tool used with Claude Code**, not as an application builder.

**Method / scope:** Read GitHub repository metadata, open issues and pull requests, workflow runs/jobs/logs, the full recursive repository tree (147 files: 19 source, 12 test, 22 docs, 84 examples, 10 other), all 19 source modules, 12 test modules, architecture/research sample outputs, the roadmap, MVP checklist, and documentation. Checked the local relative Markdown link destinations against the repository tree. Compared direct Claude API request structure with current [Anthropic structured-output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) and [versioning](https://platform.claude.com/docs/en/api/versioning) documentation. This was a **remote static/repository audit plus existing CI evidence**, not a fresh independent security penetration test or live model/real-app exercise.

**Post-audit progress (2026-11-06):** The first deterministic Markdown renderer slice of Issue #5 has now been implemented as `speccanopy document` (see [renderer guide](architecture-documentation-renderer.md)). The gaps below describe the original audit baseline; source-aware intake, evidence reconciliation, documentation drift controls and an actual-app pilot remain open.

## Observed repository state

| Check | Evidence at baseline | Interpretation |
| --- | --- | --- |
| Open GitHub issues | **4**: [#2](https://github.com/MSKazemi/speccanopy/issues/2), [#3](https://github.com/MSKazemi/speccanopy/issues/3), [#4](https://github.com/MSKazemi/speccanopy/issues/4), [#5](https://github.com/MSKazemi/speccanopy/issues/5) | Research and documentation productization are outstanding |
| Open pull requests | **0** | No pending PR to merge |
| Latest `main` CI | [Success, 225 passed on Python 3.11 and 3.13](https://github.com/MSKazemi/speccanopy/actions/runs/42122694150) | The current **unit/integration fixture suite** passes; it is not production readiness |
| Test workflow | [`.github/workflows/tests.yml`](../.github/workflows/tests.yml) installs `.[dev]` and runs only `pytest -q` | No configured type/lint/coverage/build/security checks |
| Project version | `pyproject.toml` = `0.8.0` | Versioned Python prototype |
| GitHub Releases | **0** | No published GitHub release / release procedure shown |
| LICENSE / COPYING file | **Absent** from tracked tree; repository metadata has no recognized license | Repository is public, but explicit reuse/contribution licensing is unresolved. **Maintainer must choose the license** |
| `SECURITY.md` file | **Absent** | No documented private vulnerability-reporting policy |
| `main` protection | Branch listing reports `protected: false` | Recommend checking branch rulesets and enabling appropriate protections; branch-protection details API was not accessible |
| GitHub issue #3 / #4 responses | Both have **zero public comments** | No publicly recorded volunteer / case-proposal responses |
| Internal Markdown links | No missing relative file targets detected by static scan | Positive documentation hygiene check; external links/anchor correctness were not exhaustively validated |

## P0 — Remaining work to achieve the user's main goal

Goal: **give Claude Code an existing application directory and receive accurate, maintainable architecture documentation with minimal manual preparation.**

| Order | Gap | Current code evidence | Completion / acceptance criteria | Tracker |
| --- | --- | --- | --- | --- |
| **1** | **Existing-project intake is manual** | `speccanopy design` requires a system-specific `SystemBrief` and `FixtureDesign`; no `scan`, `import-repo`, or `document-project` command exists in [CLI](../src/speccanopy/cli.py) | Claude Code-assisted or native import captures scoped source paths, stable requirement/component IDs, provenance and unsupported claims without reading secrets. Works on a permitted example app. | [#5](https://github.com/MSKazemi/speccanopy/issues/5) |
| **2** | **No complete documentation renderer** | [`exporters.py`](../src/speccanopy/exporters.py) writes six JSON/Mermaid files; [`review_exporters.py`](../src/speccanopy/review_exporters.py) writes a review Markdown file. Neither writes `docs/architecture/*.md` | Add a deterministic `document`/render command for architecture overview, requirements, components, interactions, data/security, ADRs, quality/risk and unknowns; preserve `draft` status and show missing evidence | [#5](https://github.com/MSKazemi/speccanopy/issues/5) |
| **3** | **No code↔documentation drift/provenance gate** | Strict [architecture schema](../src/speccanopy/models.py) validates IDs, hierarchy, relationships and evidence markers, **not** source-code truth. Current user guide relies on a separately authored source-evidence note | Link every observed architecture fact to repository source (path + revision when available). Explicitly separate `observed`, `inferred`, `proposed`, `verified`, `unknown`; detect stale references after changes | [#5](https://github.com/MSKazemi/speccanopy/issues/5) |
| **4** | **No real application end-to-end documentation test** | 225 passing tests primarily cover fixtures, snapshots, mocked API calls and schema checks; no actual target-repo-to-doc-pack golden test | With a permissively shared non-sensitive demo app, test intake → valid JSON → diagrams/review → Markdown pack → update/diff and absence of fabricated evidence on Python 3.11/3.13 | [#5](https://github.com/MSKazemi/speccanopy/issues/5) |

**What already works:** Claude Code can inspect a permitted application, prepare the project-specific JSON inputs and then run `speccanopy design` and `speccanopy review`; the user can ask Claude Code to author Markdown afterward. See [User Guide](USER_GUIDE.md). This is **guided**, not automatically wired together.

## P1 — Product/release hardening and architectural depth

| Gap | Evidence | Action |
| --- | --- | --- |
| **No explicit license** | No `LICENSE` / `COPYING`; GitHub license metadata absent | Maintainer selects and adds a license appropriate to desired distribution and contributor terms before promoting public reuse as fully open-source |
| **Minimal CI quality gates** | `.github/workflows/tests.yml` has pytest only | Add package build check, lint/format, type checks, test-coverage reporting and dependency/security scanning with measured adoption; avoid making a coverage percentage an architectural-quality score |
| **No formal release** | No GitHub releases; `pyproject.toml` version 0.8.0 | Document release/versioning procedure, test install-from-built-wheel and publish a tagged release if maintainer wants easy adoption |
| **No security reporting instructions** | No `SECURITY.md` | Add appropriate private vulnerability-reporting and scope guidance; do not request public exploits |
| **Weak default-branch governance signal** | GitHub branches API: `main.protected=false` | Review branch rulesets, require PR review and CI checks for main if collaboration expands |
| **Missing deeper architecture views** | [Vision](vision-and-goal.md) and [roadmap](execution-roadmap.md) aim for runtime/data/deployment/trust-boundary views; current default exports are a containment tree and typed interaction graph | Add auditable runtime scenarios, data ownership/consistency, deployment-*design* and security/trust views rather than generating guessed diagrams |
| **Older roadmap checkboxes are stale** | [MVP plan](mvp-implementation-plan.md) lines under milestones 2–3 still show unchecked ADR/refinement/scenario items, while later phase modules implement parts of them | Reconcile with current code and mark each item `implemented`, `partial` or `not started`; don't blindly flip old boxes |
| **Live Claude API compatibility unproven** | [`claude.py`](../src/speccanopy/claude.py) uses an Anthropic API schema matching current documented request structure; [tests](../tests/test_claude.py) mock network | Make an opt-in, credentialed integration smoke test using a supported model, with safeguards for billing/secrets; keep it out of ordinary CI and don't conflate with Claude Code subscription mode |

**Not necessarily bugs:** absence of these safeguards/features does not establish that the current prototypes malfunction. No `TODO`/`FIXME` or intentionally unimplemented method stub was identified in the core Python module scan. Passing unit tests, however, cannot prove semantic architecture correctness.

## P2 — Independent research and sample-design evidence

- **[Issue #2](https://github.com/MSKazemi/speccanopy/issues/2):** There are no authenticated independent human reviews or permissioned genuinely private holdout cases recorded. The expert panel can collect **self-declared** reviews only, and cannot authenticate human identity/qualification itself.
- **[Issue #3](https://github.com/MSKazemi/speccanopy/issues/3):** Reviewer recruitment call open; **0 public responses** at audit time.
- **[Issue #4](https://github.com/MSKazemi/speccanopy/issues/4):** Rights-cleared benchmark case call open; **0 public responses** at audit time.
- **Synthetic examples still have open questions.** In the three committed generated architecture examples (CLI/e-commerce/file-transfer), overall status is `draft`, all mandatory verification cases are `planned`, and each retains an open source finding. The six-entry synthetic research suite records **two cases with structural criteria gaps**, and the remaining four still require review. This is expected for examples, not a regression failure.
- **AI critique** in [`ai-assisted-case-review.md`](ai-assisted-case-review.md) raises payment/inventory consistency, durable transfer checkpointing and crash-safe file replacement questions; none is independently confirmed on a real target application.

**Distinction:** Independent research evidence is a long-term claim-quality gate. It need **not** block using Claude Code + Speccanopy to draft and review architecture documents on one's own project.

## Recommended next sprint (goal-oriented)

1. Select one small, rights-cleared existing application. Produce the **current guided** `docs/architecture/` output with Claude Code; log exactly where manual intervention was necessary.
2. Implement the **deterministic Markdown documentation renderer** from an `ArchitectureSpec` with explicit gaps. Add tests and a CLI entrypoint. This makes the output repeatable without Claude prose for every file.
3. Add a **Claude Code-assisted source intake** workflow that reliably creates valid input schemas, preserves source provenance and refuses secret paths. Include the project-owner review gate.
4. Run one end-to-end demo, compare regenerated docs after a small source change, and validate false/evidence claims before promoting "automatic documentation".
5. In parallel, resolve the owner-only **license** choice and add the small CI/release/security hygiene steps.

## Audit limitations

The audit used GitHub file content, metadata, issues, CI logs and static link checking. It **did not** run new application-level acceptance tests, exercise a live Anthropic API account, use real customer repositories, independently verify reviewers, or execute a comprehensive security audit. The next `main` revision should be re-evaluated after material code changes. GitHub rulesets/branch protection may have nuances inaccessible to the connected integration.

**Audit disposition:** **No current failing CI/blocking pull request detected. Product completeness, release readiness and independent evidence remain open.** Do not close Issues #2–#5 based on this audit.
