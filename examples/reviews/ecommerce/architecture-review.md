# Architecture review: E-commerce order platform

**Source architecture status:** draft  
**Review status:** requires_review  
**Important:** Structural checks and heuristic style fit do not constitute architecture approval.

## Style comparison

**Authored style:** modular monolith  
**Recommendation:** modular_monolith  
**Result:** recommendation — Highest weighted fit to explicitly supplied drivers; recommendation is advisory only.

| Candidate | Score (0-10) | Trade-off |
| --- | ---: | --- |
| modular_monolith | 9.47 | Clear internal boundaries and simple transactions, but modules share a deployment lifecycle. |
| single_process | 8.0 | Minimal operational overhead, but one deployment unit and limited independent scaling. |
| event_driven | 5.47 | Loose asynchronous coupling and buffering, but ordering, replay and delivery semantics need explicit design. |
| serverless | 5.47 | Managed execution and elastic capacity, but platform limits, cold starts and state handling require review. |
| microservices | 5.26 | Service-level deployment and scaling at the cost of distributed coordination, observability and consistency. |

Scores use explicitly supplied drivers and heuristic profiles, **not measured benchmarks**.

## Quality and traceability review

**Status:** requires_review  
**Mandatory requirements:** 0 verified-evidence-linked, 7 planned only, 0 uncovered.

### Quality scenarios

| Scenario | Quality requirement | Assessment | Evidence |
| --- | --- | --- | --- |
| SC-EC-AUTH | NFR-001 | verification_pending | planned_only |
| SC-EC-IDEMPOTENCY | NFR-002 | verification_pending | planned_only |

### Findings

**REVIEW-001 — medium / verification_pending**

Verification is planned but not evidenced for: ['FR-001', 'FR-002', 'FR-003', 'FR-004', 'FR-005', 'NFR-001', 'NFR-002']

Action: Review the architecture and record credible, requirement-linked evidence.

**REVIEW-002 — medium / scenario_evidence**

Scenario SC-EC-AUTH lacks documented completed architectural verification.

Action: Carry out the stated architecture review or analysis and attach evidence.

**REVIEW-003 — medium / scenario_evidence**

Scenario SC-EC-IDEMPOTENCY lacks documented completed architectural verification.

Action: Carry out the stated architecture review or analysis and attach evidence.

**REVIEW-004 — medium / interaction_contract**

REL-EC-02 lacks outbound contract on orders.

Action: Specify directional contracts, message semantics and failure behavior.

**REVIEW-005 — medium / interaction_contract**

REL-EC-03 lacks outbound contract on orders and inbound contract on inventory.

Action: Specify directional contracts, message semantics and failure behavior.

**REVIEW-006 — medium / interaction_contract**

REL-EC-06 lacks outbound contract on order_lifecycle and inbound contract on order_tracking.

Action: Specify directional contracts, message semantics and failure behavior.


Source architecture open findings: FIND-EC-01

## Provenance and limitations

Heuristic style profiles plus explicit reviewer drivers/scenarios. No LLM inference, production-code generation, or independent expert signoff.

Independent deterministic checks assess documentation/traceability only; authored evidence and scenarios require expert scrutiny. No application implementation was tested.
