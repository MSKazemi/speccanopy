# Review robustness: metamorphic analysis of the deterministic heuristics

> **Synthetic metamorphic analysis by the maintainers' tooling — not independent expert
> evaluation; does not satisfy Issue #2's human-review requirements.** It was produced by
> the project's own code on the project's own three examples. It involves no independent
> reviewer, no expert judgement and no ground-truth labels.

## Purpose

Issue #2 asks, among other things, for measurement of false positives and false negatives and
for tests with alternative node names and architecture styles. Only a small, mechanical part of
that can be automated without people: checking that the deterministic review heuristics
(`assess_architecture` in `src/speccanopy/review.py`, `evaluate_documentation_gate` in
`src/speccanopy/doc_gate.py`) behave consistently when an input is changed in a way that should
(or should not) matter. This document reports what that found. It does not replace, and makes no
progress toward, the independent human review the issue requires.

## Method

Metamorphic testing: instead of comparing output with a known-correct answer (we have none), we
transform an input and compare the output of the original and the transformed input.

All tests are in `tests/test_review_robustness.py`. Inputs are the three shipped examples
(`examples/generated/{cli-utility,ecommerce,file-transfer}/architecture.json`), each run **with**
its `examples/<name>.review.json` config and **without** a config (default `ReviewConfig`, no
drivers, no scenarios). Every transformed document is validated through
`ArchitectureSpec.model_validate` / `ReviewConfig.model_validate` before use. A helper applies an
ID map to every ID-bearing structured field (requirement, component, relationship, case,
decision and finding IDs; `requirement_ids`, `component_ids`, `parent_id`, `source_id`,
`target_id`, `quality_targets` keys; scenario IDs and their references). Review outputs are
compared through an order-insensitive signature (finding severity/category/linked IDs, statuses,
coverage, scenario assessments, style recommendation and scores) in which positional
`REVIEW-NNN` IDs are ignored.

| Relation | Transformation | Expected |
| --- | --- | --- |
| R1 | Bijective ID rename. Two maps: an order-preserving prefix (`Z_<id>`) and an order-scrambling opaque hash (`Q<hex>`) | Same counts, severities, categories, statuses, style recommendation; only IDs inside text differ. With the order-preserving map the full dump (including text and `REVIEW-NNN`) is identical after mapping IDs back |
| R2 | Replace human-readable wording (neutral labels such as "Component A"; synonyms; non-English; style names) | Observation only: record which results change |
| R3 | Shuffle every order-free list (components, relationships, requirements, cases, decisions, findings, interfaces, scenarios, drivers, candidates, ID lists; five seeds) | Same result (order independence) |
| R4 | Remove one verification case at a time; add a critical open finding | Findings never reduced; scenario/overall status never improved; overall status never improved |
| R5 | R1 and R3 on `evaluate_documentation_gate` (with and without a review), plus the R4 relations | Same outcome, category counts, blocking/attention counts |

## Results

Environment: `python -m pytest -q tests/test_review_robustness.py` gives
**303 passed, 5 xfailed**. The full-suite result is in the commit/report that accompanies this file.
"Pass" means the stated relation held on all three examples in both config modes (not on all
possible inputs).

| Relation | cli-utility | ecommerce | file-transfer | Notes |
| --- | --- | --- | --- | --- |
| R1 ID rename, review (prefix and scramble map) | pass | pass | pass | 12 signature cases + 6 exact-reversal cases |
| R2 neutral labels, structural results | pass | pass | pass | Only scenario-assessment descriptions (which quote scenario wording) differ |
| R2 style / data wording | n/a | see below | n/a | Heuristics are keyword/exact-text based; 5 strict xfails |
| R3 reordering, review (5 seeds) | pass | pass | pass | Finding texts are also string-identical after sorting |
| R4 remove a case: coverage, flagged requirements, scenario status, overall status, high-or-worse count | pass (4 cases) | pass (7 cases) | pass (5 cases) | Per case, both config modes |
| R4 remove a case: raw total finding count | pass | pass | pass | **Fails on a synthetic probe**, see below |
| R4 add a critical open finding | pass | pass | pass | Exactly +1 finding; all earlier findings preserved |
| R5 gate under ID rename | pass | pass | pass | Review supplied and not supplied |
| R5 gate under reordering | pass | pass | pass | Without a review (and config) the whole gate dump is identical |
| R5 gate monotonic under case removal / critical finding | pass | pass | pass | Blocking count never falls; outcome never improves |

### Violation of a stated relation (strict xfail)

**R4, count monotonicity.** `test_r4_count_monotonic_on_aggregation_probe`. Input: the ecommerce
example reduced to one planned-only requirement (FR-001, one planned case) and several
uncovered requirements. Removing FR-001's only case lowers the finding count from 7 to 6. Cause
(`review_quality`, `review.py` lines 282-287): findings aggregate requirement lists, so
`verification_pending` (medium) disappears while the already-present `requirement_coverage`
(high) finding absorbs FR-001 into its list. The situation got worse and is reported at higher
severity, but the raw count dropped. The per-requirement and per-severity forms of the relation
do hold (`test_r4_aggregation_probe_is_still_monotonic_per_requirement_and_severity`), so this is
most likely a property of aggregation rather than a defect; whether to treat counts as a metric
is a maintainer decision. No shipped example triggers it.

### Name- and keyword-sensitive heuristics found

These are observations about what the code reads, not automatically bugs.

| Heuristic | Location | Concrete example | Effect |
| --- | --- | --- | --- |
| Style-family detection by substring | `_style_family`, `review.py` 192-206 | `"Layered design for the client portal"` -> `single_process` because `"cli" in "client"`; `"... customer portal"` -> `None`. (Also `"clinic management"` -> `single_process`) | On ecommerce (recommendation `modular_monolith`) the client wording adds one `style_tradeoff` finding (`test_r2_observation_family_change_adds_a_style_tradeoff_finding_end_to_end`). Likely false positive. Strict xfail |
| Style-family detection by literal English words | same | `"Modularer Monolith"` and `"EDA (message-driven)"` -> `None` | Style-trade-off check silently skipped. Strict xfail (2) |
| Style-family case/separator tolerance | same | `Modular-Monolith`, `modular_monolith`, `Event Driven architecture`, `MODULAR MONOLITH (python packages)` all resolve | Works as intended (9 passing cases) |
| Data-ownership conflict by exact text | review.py 354-362 | Sibling claims `order RECORDS` next to `Order records` -> conflict. `Orders`, `Order record`, `Bestellungen` -> no conflict. `Order  records` (two spaces) -> no conflict (strict xfail) | Different wording of the same data is a false negative of this check; the model already strips leading/trailing whitespace. Whether the plural/translated names are "the same data" is not decidable without a labelled corpus |
| Review is ignored if `system` text differs | `doc_gate.py` 221-224 | Renaming `brief.system` in the spec only adds a blocking "different system" item | By design (stale-review guard); renaming must be applied to the spec and its review together |
| Review text quotes authored wording | `review.py` 294-296, 343 | Open high source finding text and scenario descriptions are copied verbatim | Text changes, structure does not |
| `REVIEW-NNN` IDs are positional | `review.py` 273-280 | On ecommerce the id->finding assignment differs for all 5 shuffle seeds | The set of findings is stable, the IDs are not; the gate's `subject_id` for review findings inherits this. Do not use `REVIEW-NNN` as a cross-run key |
| Order of joined issue text | `review.py` 345-347 | Reversing `expected_interactions` reorders the text of `missing_design_elements` | Cosmetic; sorted comparison is equal |
| Interface-kind matching (an enum, not a name) | `review.py` 369 | Only `api`, `function`, `other` count as contracts for `synchronous_call` | Not exercised by renaming; noted for completeness |

Names that no heuristic reads: component `name`, `responsibility`, `boundary`, interface names and
descriptions, relationship descriptions, requirement statements. Replacing all of them with neutral
labels changed no finding (R2 pass). That is a robustness result, but also means these heuristics
cannot detect poor or misleading wording.

## Limits

- Three synthetic examples written by the maintainers, none with an open high/critical source
  finding, none reaching `candidate_for_human_review`. (A tiny hand-made validated fixture is used to
  show that the monotonicity tests are not vacuous.)
- No ground truth. **False-positive and false-negative rates cannot be measured here** and
  nothing in this document estimates them: that needs independently labelled cases from
  independently qualified reviewers, which is what Issue #2 still requires.
- Passing a metamorphic relation shows consistency, not correctness. A heuristic can be
  consistently wrong; renaming-invariance says nothing about whether a finding is useful.
- The examples exercise few scenario interactions (0 or 1 per scenario), so R3 on
  `expected_interactions` ordering is covered by one synthetic probe only.
- Only the relations listed above were tried; five shuffle seeds are not exhaustive.
- The gate was run with a review produced by the same code and never with source evidence.

## Rerun

```bash
python -m pip install -e '.[dev]'
python -m pytest -q tests/test_review_robustness.py
python -m pytest -q tests/test_review_robustness.py -rx   # list the xfail reasons
```

`xfail(strict=True)` tests fail the suite if the behaviour is fixed (the test then passes
unexpectedly), prompting an update of this document.
