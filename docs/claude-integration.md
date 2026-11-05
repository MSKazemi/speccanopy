# Claude integration and AI-only architecture review

**Implementation status:** Speccanopy supports Anthropic's Messages API for
schema-constrained **component proposals**, and Claude Code can use this repository
through \`CLAUDE.md\`. Live Claude network calls require the user's own API access
and have **not been performed in this milestone**. Mocked transport tests are not
a live provider compatibility or design-quality benchmark.

## Two different ways to use Claude

### A. Claude Code in a cloned repository

Open the repository with Claude Code:

\`\`\`bash
git clone https://github.com/MSKazemi/speccanopy.git
cd speccanopy
python -m pip install -e '.[dev]'
pytest -q
claude
\`\`\`

Claude Code automatically reads the root \`CLAUDE.md\` as project instructions.
It can inspect architecture files, run the local CLI, write reports and propose
edits **with your approval**. The local \`review\` and \`research-case\` commands
are deterministic and do **not** make model API requests:

\`\`\`bash
speccanopy review examples/generated/ecommerce/architecture.json \
  --config examples/ecommerce.review.json --output out/ecommerce-review

speccanopy research-case examples/research/cases/ecommerce.json \
  --architecture examples/generated/ecommerce/architecture.json \
  --output out/research-ecommerce
\`\`\`

Suggested Claude Code task:

> Inspect the e-commerce requirements, generated architecture and review
> findings. Perform an AI-assisted **adversarial architecture critique**.
> For each concern cite real requirement/component/relationship IDs, describe
> a concrete failure scenario, give an alternative and a validation method.
> Keep all unresolved items open. Do not create verified evidence, claim to
> be a human expert, edit private review records or automatically approve a
> revision. Save the report as an AI-only draft and run the tests.

This workflow can provide **substantive AI review** when professional reviewers
are unavailable, but it cannot measure independent expert agreement.

### B. Live Claude API component proposals

This is an **additional, billed API integration**, distinct from the Claude
Code interface. It uses Anthropic's Messages API with an API key from an
authorized Anthropic API project:

\`\`\`bash
export ANTHROPIC_API_KEY='YOUR_SECRET_KEY'
# Some multi-workspace keys also need ANTHROPIC_WORKSPACE_ID.
speccanopy propose-ai examples/cli-utility.json \
  --backend claude \
  --model YOUR_AVAILABLE_CLAUDE_MODEL_ID \
  --max-model-calls 20 \
  --output out/claude-cli
\`\`\`

Use a model identifier available to your particular account; the repository
does not hardcode or assume any model entitlement. Inspect
\`out/claude-cli/proposal-review.md\`, \`ai-proposals.json\` and \`architecture.json\`
before approving even the component hierarchy. Any release of a proposal
fixture requires a **real person** to acknowledge what they reviewed:

\`\`\`bash
speccanopy approve-ai out/claude-cli/ai-proposals.json \
  --reviewer YOUR_REVIEWER_ID --acknowledge-review \
  --output out/claude-cli/approved.design.json

speccanopy design examples/cli-utility.json \
  --fixture out/claude-cli/approved.design.json \
  --output out/claude-cli/approved-draft
\`\`\`

The second command still produces an incomplete architecture when design
contracts, relationships, decision evidence and validation are absent.
**An AI cannot approve its own output in place of a human.** Do not run the
approval command merely to satisfy the demo.

For a fully **offline** demonstration, use:

\`\`\`bash
speccanopy propose-ai examples/cli-utility.json \
  --backend scripted --responses examples/ai-scripted-cli.json \
  --output out/offline
\`\`\`

The scripted backend contains authored test responses — **not Claude inference**.

## Implementation details and fail-closed behavior

- Adapter: \`src/speccanopy/claude.py\`; CLI: \`--backend claude\`.
- Fixed HTTPS endpoint: \`https://api.anthropic.com/v1/messages\`.
- Uses \`anthropic-version: 2026-10-21\`, \`x-api-key\` and (when configured)
  \`anthropic-workspace-id\`, plus \`output_config.format.type=json_schema\`.
- The same \`AI_RESPONSE_SCHEMA\` is sent as for OpenAI; responses pass the
  existing Pydantic component/requirement/ID/recursion-budget checks.
- Only one complete assistant JSON text block is accepted. Incomplete,
  refused, tool-use, malformed or oversized provider replies fail closed.
- API keys never enter input briefs, prompt hashes, trace files, logs or the
  exported \`AIProposalBundle\`.
- The full brief, current parent component and requirement IDs **are sent
  to Anthropic** for live proposal requests. Obtain permission before
  transmitting any private requirements. Provider retention and account
  policies should be reviewed separately.

API references (verify against current versions before a live production rollout):
[Claude API versioning](https://platform.claude.com/docs/en/api/versioning),
[Messages API](https://platform.claude.com/docs/en/api/overview),
[structured JSON output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
and [Claude Code CLAUDE.md](https://code.claude.com/docs/en/memory).

## Why AI review is not a replacement for independent expert validation

Two model runs, or ChatGPT plus Claude, may produce useful independent
**analytical perspectives**, but they are **not independent human experts**.
Models can share training distributions and blind spots; prompt variations
are not evidence of professional qualifications, consent, real production
feasibility or independent reviewer agreement.

Speccanopy therefore keeps the external human-review Issue #2 open.
Do not inject AI desk reviews into \`ReviewerSubmission\`,
\`ReviewClaim\` or the "expert quorum" aggregation. The
[worked AI critique](ai-assisted-case-review.md) identifies concrete
questions worth resolving but does not certify the architectures.

When human reviewers are unavailable, the responsible workflow is to
collect AI critiques, design/test plans and explicit unresolved findings,
and **abstain** from independent correctness or safety claims.
