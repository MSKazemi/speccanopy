# Architecture research evaluation

**Curated criteria, NOT expert certification or semantic proof.**

Case: embedded_controller — Embedded fluid controller  
Split: public_holdout  
Origin: synthetic_curated  
Review status: curated_unreviewed (claims: 0)  
Selected style: single-process embedded controller  
Detected family: single_process  
Common criterion coverage: 100.00%  
Overall result: **criteria_present_review_required**  
Best diagnostic alternative: local_control

## Cross-cutting requirements

| Criterion | Required | Present | Reason |
| --- | --- | --- | --- |
| EM-SENSOR | yes | yes | Requirement is linked to an architecture component |
| EM-CONTROL | yes | yes | Requirement is linked to an architecture component |
| EM-ACT | yes | yes | Requirement is linked to an architecture component |
| EM-DIAG | yes | yes | Linked design verification case (may be planned only) |
| EM-TIMING | yes | yes | Responsible component has an authored quality target |
| EM-SAFETY | yes | yes | Responsible component has an authored quality target |
| EM-OWNER | yes | yes | Matching data owners: sensor; require one responsible owner |

## Multiple acceptable alternatives

### local_control: Single-process controller modules

Compatible family: matched (single_process)  
Criterion coverage: 100.00%  
Missing required criteria: none

| Criterion | Present | Reason |
| --- | --- | --- |
| EM-FLOW | yes | Matching typed relationship traces to requirement |
| EM-BOUND | yes | Matching typed relationship traces to requirement |
| EM-FAIL | yes | At least one responsible interface describes failure behavior |

## Outstanding evidence

Uncovered mandatory: none  
Verification only planned: FR-001, FR-002, FR-003, FR-004, NFR-001, NFR-002  
Open high/critical findings: none

## Limits

Requirement-linked structural/documentation signals only. A full score does NOT verify semantic correctness, independent expert review, security or deployability. Reviews listed here, if any, are self-declared and NOT authenticated.

