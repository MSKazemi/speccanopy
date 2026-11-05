# Speccanopy architecture research suite

**Public fixtures are not an independent holdout or an expert-reviewed evaluation.**

Suite: Phase 6 public synthetic research fixtures — NOT independent holdout  
Cases evaluated: 6

| Split | Count | Criteria present, review needed | Criteria gaps | No compatible style | Mean common coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| development | 3 | 2 | 1 | 0 | 100.00% |
| public_holdout | 3 | 2 | 1 | 0 | 100.00% |

## Cases

| Entry | Case | Result | Best alternative | Review status |
| --- | --- | --- | --- | --- |
| CLI-BASE | cli_utility | criteria_present_review_required | single_process_solution | curated_unreviewed |
| ECOM-MODULAR | ecommerce | criteria_gaps | modular_monolith_path | curated_unreviewed |
| ECOM-DISTRIBUTED | ecommerce | criteria_present_review_required | distributed_event_path | curated_unreviewed |
| TRANSFER-BASE | file_transfer | criteria_gaps | event_worker_path | curated_unreviewed |
| EMBEDDED-BASE | embedded_controller | criteria_present_review_required | local_control | curated_unreviewed |
| TELEMETRY-BASE | telemetry_ingestion | criteria_present_review_required | async_pipeline | curated_unreviewed |

## Limitations

Public synthetic fixtures are not an independent holdout or professional review set. Aggregate counts are diagnostic, not architecture correctness rates.

