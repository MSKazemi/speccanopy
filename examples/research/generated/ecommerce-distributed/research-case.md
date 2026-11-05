# Architecture research evaluation

**Curated criteria, NOT expert certification or semantic proof.**

Case: ecommerce — E-commerce payment and inventory design  
Split: development  
Origin: synthetic_curated  
Review status: curated_unreviewed (claims: 0)  
Selected style: microservices  
Detected family: microservices  
Common criterion coverage: 100.00%  
Overall result: **criteria_present_review_required**  
Best diagnostic alternative: distributed_event_path

## Cross-cutting requirements

| Criterion | Required | Present | Reason |
| --- | --- | --- | --- |
| EC-MAP-1 | yes | yes | Requirement is linked to an architecture component |
| EC-MAP-2 | yes | yes | Requirement is linked to an architecture component |
| EC-MAP-3 | yes | yes | Requirement is linked to an architecture component |
| EC-MAP-4 | yes | yes | Requirement is linked to an architecture component |
| EC-MAP-5 | yes | yes | Requirement is linked to an architecture component |
| EC-Q-AUTH | yes | yes | Responsible component has an authored quality target |
| EC-Q-IDEMP | yes | yes | Responsible component has an authored quality target |
| EC-VERIFY | yes | yes | Linked design verification case (may be planned only) |
| EC-OWNER | yes | yes | Matching data owners: service_orders; require one responsible owner |

## Multiple acceptable alternatives

### modular_monolith_path: Modular monolith with transactions and asynchronous notifications

Compatible family: mismatched (modular_monolith)  
Criterion coverage: 77.78%  
Missing required criteria: EC-M-OUT

| Criterion | Present | Reason |
| --- | --- | --- |
| EC-M-CHARGE | yes | Matching typed relationship traces to requirement |
| EC-M-STOCK | yes | Matching typed relationship traces to requirement |
| EC-M-AUTH | yes | Matching typed relationship traces to requirement |
| EC-M-OUT | no | Missing directional interface for requirement |

### distributed_event_path: Service-oriented event-driven payment processing

Compatible family: matched (microservices, event_driven)  
Criterion coverage: 100.00%  
Missing required criteria: none

| Criterion | Present | Reason |
| --- | --- | --- |
| EC-D-PAY | yes | Matching typed relationship traces to requirement |
| EC-D-OUT | yes | Matching directional interface exists on a requirement owner |
| EC-D-IN | yes | Matching directional interface exists on a requirement owner |
| EC-D-AUTH | yes | Matching typed relationship traces to requirement |

## Outstanding evidence

Uncovered mandatory: none  
Verification only planned: FR-001, FR-002, FR-003, FR-004, FR-005, NFR-001, NFR-002  
Open high/critical findings: none

## Limits

Requirement-linked structural/documentation signals only. A full score does NOT verify semantic correctness, independent expert review, security or deployability. Reviews listed here, if any, are self-declared and NOT authenticated.

