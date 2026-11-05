# Phase 4 — AI-assisted component proposals and human approval

**Status:** Implemented, test-driven prototype. The live Responses API adapter has **mocked transport tests**, but no real paid model invocation has been performed by this repository milestone.

**Goal:** From a `SystemBrief`, obtain candidate architecture component boundaries from an optional AI model; reuse the bounded Phase 2 generator; retain provenance, unresolved questions, and a separate human review gate. Speccanopy remains an **architecture design engine**, not an automatic application builder.

## How it works

1. The user supplies a validated brief with functional requirements, quality requirements, and depth/node limits.
2. The `OpenAIResponsesClient` sends parent-specific requests to the OpenAI **Responses API** using a strict JSON Schema (`text.format.type=json_schema`, `strict=true`, and `store=false`). The model ID is explicitly selected by the user, and the API key comes from `OPENAI_API_KEY`. A `ScriptedProposalClient` provides an offline stand-in for deterministic testing, **not AI inference**.
3. `AIComponentProposer` validates every response against typed Pydantic models and rejects unknown/unaligned requirement references, duplicate IDs, unexpected fields, and inconsistent expand/stop decisions. Invalid output may be retried only up to the brief's `max_refinement_rounds`, subject to `--max-model-calls`.
4. The existing Phase 2 priority-first generator controls the recursive component hierarchy. Missing information, exhausted request limits and depth/node budgets result in explicit gaps or review requirements; no model-supplied text is accepted as verified design evidence.
5. The resulting `ai-proposals.json` bundle contains the input brief and proposal fixture, plus hashes and model-call provenance. A `proposal-review.md` packet summarizes candidates, rationales, assumptions, risks, and open questions.
6. **Only after human inspection**, `approve-ai` can release the proposed hierarchy as a fixture for further architecture design. This requires an explicit reviewer identifier and `--acknowledge-review`. The accompanying approval receipt ties the approved fixture to the original brief and the bundle hash. The `design` command checks brief/fixture hashes when a matching approval receipt is present.
7. Use Phase 3's `review` command to assess the draft against explicit drivers and quality scenarios. Structural readiness, model suggestions, heuristic style scores, and a proposal acknowledgement are **not proof of architectural correctness**.

## Offline end-to-end demonstration (no API credentials)

```bash
python -m pip install -e '.[dev]'
pytest -q

speccanopy propose-ai examples/cli-utility.json \
  --backend scripted \
  --responses examples/ai-scripted-cli.json \
  --output out/ai-cli

# Inspect out/ai-cli/proposal-review.md and out/ai-cli/ai-proposals.json.
speccanopy approve-ai out/ai-cli/ai-proposals.json \
  --reviewer architecture-reviewer \
  --acknowledge-review \
  --output out/ai-cli/approved.design.json

speccanopy design examples/cli-utility.json \
  --fixture out/ai-cli/approved.design.json \
  --output out/ai-cli/approved-design

speccanopy review out/ai-cli/approved-design/architecture.json \
  --config examples/ai-scripted-cli.review.json \
  --output out/ai-cli/architecture-quality-review
```

**Expected:** Four components, depth one, four scripted requests, an explicitly `pending_human_review` AI bundle, and an `incomplete_requires_review` architecture. The quality reviewer highlights unresolved interface/data, requirement verification and quality-scenario gaps. The output is *not* certified.

A reproducible, pre-approval snapshot is checked in under [`examples/ai-drafts/cli-utility/`](../examples/ai-drafts/cli-utility/). The example uses scripted model-like responses, not a real API call. An approval receipt is intentionally **not** pre-generated or committed, because human approval cannot be inferred from a fixture.

## Live model option

The real API requires separate API access and billing. Select a model available in your OpenAI API project:

```bash
export OPENAI_API_KEY='your-api-key'  # environment only; never commit
speccanopy propose-ai examples/cli-utility.json \
  --backend openai --model YOUR_AVAILABLE_MODEL \
  --max-model-calls 20 --output out/live-ai-cli
```

**Privacy:** This command sends the full application brief, the current parent component and allocated requirement IDs to the selected model provider. Do not send private/customer requirements without authorization and applicable controls. The repo does not collect or store API keys; the API call uses `store=false`. The provenance log saves SHA-256 prompt/response digests and optional provider response IDs, not raw prompts or raw provider replies. The resulting proposal artifacts **do** contain system requirements and model-authored architecture candidate text; handle them as sensitive project documents where appropriate.

The integration uses the standard library HTTP client and a fixed HTTPS Responses API endpoint. Live API compatibility, model permissions, availability and pricing must be verified in the user's own API project. Unit tests intercept the HTTP request; **no live model output is claimed or tested**.

## Output files

`propose-ai` produces nine files:

| File | Purpose |
|---|---|
| `architecture.json` | Structural draft from bounded recursion |
| `architecture.mmd` | Containment diagram |
| `relationships.mmd` | Typed relationship graph (empty of substantive edges until supplied) |
| `requirements-report.json` | Planned/verified/uncovered mandatory requirements |
| `decisions.json` | Style from input if given, authored/engine findings |
| `generation-trace.json` | Deterministic expansion trace labeled `ai-assisted-draft` |
| `ai-proposals.json` | Pending-review proposal bundle, brief+fixture hashes |
| `ai-provenance.json` | Model-call hashes, accepted/rejected results, budgets, open warnings |
| `proposal-review.md` | Human inspection checklist and proposal rationale |

`approve-ai` writes a standalone `<name>.design.json` fixture and `<name>.design.approval.json` receipt. An approved proposal fixture is suitable as **input for further architecture elaboration**, not proof of design completion. Unlike a real architectural sign-off, the command records a **user-declared** reviewer identifier; it is not a cryptographic identity/approval service.

## Trust boundaries and limitations

- Model responses cannot set `ready`, `validated_for_scope`, architecture verification evidence, accepted ADRs, or asserted interface contracts. They propose hierarchy, responsibilities, boundary descriptions, assumptions, risks, and requirement links only.
- Local validation checks structure and requirement IDs. It cannot determine whether semantic model reasoning, security, cohesion or performance is genuinely correct.
- An invalid structured response triggers a bounded retry using a local validation error. **This is schema repair, not a full architectural critique/redesign loop.** Model/network failures fail closed with a nonzero CLI exit code.
- The request budget includes validation retries. When a call or depth budget is exhausted, the draft records warnings and high-severity findings, and never upgrades to verified status.
- Manual edits to `ai-proposals.json` invalidate its digests. To use adjusted designs, create/review a new bundle; do not blindly recompute hashes and claim the original model output was unchanged.
- An `approved.design.json` with a matching receipt is checked against the original brief and approval hash before using it in `design`. This is integrity checking, not a substitute for access control or authenticated approvals.
- The engine does not yet generate complete inter-component interaction contracts, verification cases or ADRs from the model. The current AI-stage draft is intentionally incomplete pending deliberate architecture elaboration and review.
- Architectural style *comparison* remains an advisory Phase 3 review; no AI-generated style choice is silently substituted.

## Next milestone

Integrate independent architecture review findings with **bounded targeted redesign**, not just schema repair. Build benchmark cases of varying styles/domains and measure whether AI proposals improve quality over the deterministic fixture baseline. Add optional human-in-the-loop editing and explicit provenance for reviewed interface/data contracts, while preserving the architecture-only product boundary.

## Claude provider integration (2026-11-05)

The same `ComponentProposer` pipeline now accepts an Anthropic Messages API adapter, activated with `--backend claude --model YOUR_AVAILABLE_CLAUDE_MODEL_ID`. See [Claude integration](claude-integration.md) and the repository's `CLAUDE.md`. It uses schema-constrained `output_config.format` and the same local component/provenance/requirement checks, budgets and explicit human acknowledgement as OpenAI. **The Claude transport is mocked in CI; no live Claude API request or independent human design review is claimed.** Existing `--backend openai` and `--backend scripted` are retained.
