# AI-assisted desk review of three synthetic Speccanopy designs

**Classification:** AI-authored desk critique, 2026-11-05. **NOT** a
professional, independently authenticated expert review, real-world
validation, external Claude API run or production-readiness certificate.

**Inputs inspected:** The checked-in \`examples/generated/*/architecture.json\`
files; \`examples/reviews/*/architecture-review.md\`; requirement briefs.
I did **not** execute or deploy any described target application.
The observations below are evidence-linked **design questions and risk
hypotheses**. Absence of an explicit detail in an illustrative design
does not mean the real application is vulnerable.

## 1. E-commerce architecture — modular monolith

Source: \`examples/generated/ecommerce/architecture.json\`.
Authored style: \`modular monolith\`, status \`draft\`. All seven mandatory
requirements have *planned*, not verified, architecture review cases.
A modular monolith is a defensible low-operations starting point;
switching to microservices does **not** inherently solve consistency.

| ID | Priority for review | Evidence and scenario | Concrete next verification |
| --- | --- | --- | --- |
| AI-EC-01 | High | \`NFR-002\`, \`payments\`, \`payment_gateway\`, \`REL-EC-02\`: the quality targets mention idempotency keys, but do not define persistent uniqueness, concurrent deduplication or reconciliation if the payment provider commits and the call times out. A retry could cause an incorrect outcome if the provider and local records diverge. | Specify durable payment-intent identity, deduplication scope and status reconciliation. Walk through success, timeout-after-charge, concurrent retry and delayed webhook. |
| AI-EC-02 | High | \`FR-005\`, \`REL-EC-03\`, \`inventory\`, \`orders\`: reservation is an event from orders to inventory, but delivery/ordering, duplicate reservation, outbox and compensation after failed payment are unspecified. This overlaps \`FIND-EC-01\`. | Define reservation state machine, idempotent event handling, retry/replay policy and stock-release compensation; verify order/payment/inventory race scenarios. |
| AI-EC-03 | Medium | \`FR-002\`, \`FR-003\`, \`REL-EC-02\`, \`REL-EC-03\`, \`REL-EC-06\`: the interface descriptions are generic placeholders, without payload schema, versioning, timeout, backpressure or end-to-end failure semantics. The Phase 3 review also flags absent directional contracts. | Document producer/consumer message contracts, failure responses, transaction boundaries and retry limits per edge; use a contract review checklist. |
| AI-EC-04 | Medium | \`NFR-001\`, \`orders\`, \`payment_auth\`, \`identity\`, \`REL-EC-04\`: roles and trust boundaries are named, but the allowed actions and enforcement points for order changes versus payment initiation remain underspecified. | Produce an authorization matrix, check object-level ownership for order updates, and review deny-by-default paths and audit requirements. |
| AI-EC-05 | Medium | \`FR-002\`, \`orders\`, \`order_lifecycle\`: \`Order records\` and \`Order state changes\` are named as separate owned data; whether that is one transactional authority, an append-only event log or a separate projection is unclear. | State the single source of truth, permitted writers, concurrency mechanism and state transition invariants. |

**Alternative worth comparing:** keep a modular monolith with an
explicit transaction/outbox boundary and idempotent payment adapter;
compare it with event-driven services only after showing a real
need for independent scaling or deployment. The alternative involves
more operational complexity and distributed failure modes. Neither
has been evaluated by an external architect here.

**Hold point:** Resolve AI-EC-01 and AI-EC-02 through defensible design
contracts and reviewable scenarios before claiming the design is
implementation-ready.

## 2. CLI text normalizer — single process

Source: \`examples/generated/cli-utility/architecture.json\`. Four nodes,
one level of children; the simple shape appropriately avoids
unnecessary distributed services. Four mandatory requirements are
planned-only. \`FIND-CLI-01\` already flags atomic replacement semantics.

| ID | Priority | Evidence and scenario | Concrete next verification |
| --- | --- | --- | --- |
| AI-CLI-01 | Medium | \`NFR-001\`, \`FR-003\`, \`output\`: "preserve original" is stated but the temporary-file/rename/flush/cleanup sequence is not specified. In-place output, disk-full errors or a crash during write may violate the requirement. | Specify safe write to destination filesystem, fsync/atomic replacement assumptions, rename failure and cleanup; walk through crash and insufficient-space cases. |
| AI-CLI-02 | Low | \`FR-001\`, \`FR-002\`, \`input\`, \`normalize\`: invalid UTF-8, huge inputs and normalization semantics (trailing newline, Unicode whitespace, CRLF) are not fully specified. | Define strict decoding/size policy and table-driven input/output examples. |
| AI-CLI-03 | Low | \`FR-003\`, \`output\`: destination/source aliasing, symlinks and overwriting existing files require an explicit CLI policy. | Write acceptance criteria for overwrite prompts/flags and same-file path resolution. |

**Hold point:** Preserve the small single-process design; improve file
failure contracts rather than adding more architectural layers.

## 3. Multi-backend file-transfer service — event-driven modular

Source: \`examples/generated/file-transfer/architecture.json\`. Thirteen
components; five mandatory requirements are planned-only. A queue or
event signal can separate intake and long-running transfer execution,
but delivery guarantees are not yet specified.

| ID | Priority | Evidence and scenario | Concrete next verification |
| --- | --- | --- | --- |
| AI-FT-01 | High | \`FR-003\`, \`FR-004\`, \`job_store\`, \`recovery\`: both "Checkpoint records" and "Recovery checkpoints" appear as owned data. Whether they are redundant caches or competing writers is unclear; interrupted resume could read stale or inconsistent progress. | Define one durable checkpoint authority, atomic update/version rules and lease/worker ownership; test worker crash at checkpoint boundaries. |
| AI-FT-02 | High | \`FR-003\`, \`multipart\`, \`recovery\`, \`REL-FT-06\`: multipart completion after timeout may be ambiguous. The existing \`FIND-FT-01\` calls out idempotency of interrupted completions. | Define completion idempotency, remote object verification, orphan multipart cleanup and retry/backoff; review exactly- vs at-least-once assumptions. |
| AI-FT-03 | Medium | \`FR-001\`, \`FR-002\`, \`intake\`, \`planner\`, \`REL-FT-02\`: event publishing and subscription contracts are not specified; Phase 3 detects a missing outbound intake and inbound planner contract. | Specify event payload, delivery/duplicate semantics, correlation IDs, failure responses and dead-letter handling. |
| AI-FT-04 | Medium | \`NFR-001\`, \`access\`, \`s3_credentials\`, \`REL-FT-05\`: scoped credentials and non-logging are declared targets, not verified security controls. Credential renewal during an active multipart transfer is unresolved. | Document least-privilege scopes, secret-handling boundaries, credential rotation/expiry, log redaction and denial behavior. |

**Alternative worth comparing:** a modular single-worker scheduler with
a persistent queue may be simpler than independent services per backend.
The architecture needs operational assumptions (throughput, failure
frequency, concurrency, security boundaries) to justify the deployment
view. No production performance measurements are included.

## Cross-case limits and next checks

1. All three source specs are \`draft\`; none includes verified-evidence-linked
   mandatory requirements. **Do not change their status based on this review.**
2. Generic interface "Return an explicit error" text is not a complete
   contract for retries, timeouts, compensation, observability or security.
3. Prioritize concrete failure scenarios and ADR trade-offs before
   increasing recursive decomposition depth.
4. Any new evidence must be attributable to a real test, verified design
   review, documented system constraint or separately authenticated
   qualified reviewer—not an AI assertion.
5. Compare these hypotheses with both deterministic reviewer outputs
   and a second *AI-only* critique in Claude Code if desired. Two AI
   opinions are not two independent human reviewers.

**Suggested next work:** Resolve the e-commerce payment and reservation
scenarios first; then specify file-transfer checkpoint/replay semantics
and CLI crash-safe writes. Use the [Claude Code workflow](claude-integration.md)
to iterate. [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2)
remains open for genuinely independent human evidence.
