# Architecture research evaluation

**Curated criteria, NOT expert certification or semantic proof.**

Case: file_transfer — Secure resumable file transfer architecture  
Split: public_holdout  
Origin: synthetic_curated  
Review status: curated_unreviewed (claims: 0)  
Selected style: event-driven modular service  
Detected family: event_driven  
Common criterion coverage: 100.00%  
Overall result: **criteria_gaps**  
Best diagnostic alternative: event_worker_path

## Cross-cutting requirements

| Criterion | Required | Present | Reason |
| --- | --- | --- | --- |
| FT-MAP-1 | yes | yes | Requirement is linked to an architecture component |
| FT-MAP-2 | yes | yes | Requirement is linked to an architecture component |
| FT-MAP-3 | yes | yes | Requirement is linked to an architecture component |
| FT-MAP-4 | yes | yes | Requirement is linked to an architecture component |
| FT-CRED | yes | yes | Responsible component has an authored quality target |
| FT-VERIFY | yes | yes | Linked design verification case (may be planned only) |
| FT-OWNER | yes | yes | Matching data owners: access; require one responsible owner |

## Multiple acceptable alternatives

### event_worker_path: Event-triggered transfer worker

Compatible family: matched (event_driven)  
Criterion coverage: 69.23%  
Missing required criteria: FT-E-CONTRACT

| Criterion | Present | Reason |
| --- | --- | --- |
| FT-E-JOB | yes | Matching typed relationship traces to requirement |
| FT-E-AUTH | yes | Matching typed relationship traces to requirement |
| FT-E-CONTRACT | no | Missing directional interface for requirement |

### modular_worker_path: Modular single-deployment transfer worker

Compatible family: mismatched (modular_monolith)  
Criterion coverage: 100.00%  
Missing required criteria: none

| Criterion | Present | Reason |
| --- | --- | --- |
| FT-M-JOB | yes | Matching typed relationship traces to requirement |
| FT-M-CRED | yes | Matching typed relationship traces to requirement |
| FT-M-FAIL | yes | At least one responsible interface describes failure behavior |

## Outstanding evidence

Uncovered mandatory: none  
Verification only planned: FR-001, FR-002, FR-003, FR-004, NFR-001  
Open high/critical findings: none

## Limits

Requirement-linked structural/documentation signals only. A full score does NOT verify semantic correctness, independent expert review, security or deployability. Reviews listed here, if any, are self-declared and NOT authenticated.

