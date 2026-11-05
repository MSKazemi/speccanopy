# Phase 7 — Independent architecture review collection protocol

**Status:** Review logistics, blinding, response validation and provisional aggregation implemented. **No independent expert assessments have been collected or authenticated.** The repository's examples remain synthetic and public. This is the software part of [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2), not completion of its human-research requirements.

## Purpose and limits

Speccanopy designs architecture; it does **not** generate or deploy applications. Phase 6 can evaluate requirement-linked structural criteria for multiple hypothetical architecture styles, but those checks cannot establish semantic correctness. Phase 7 prepares a path toward **independently assessed** architecture quality by enabling separate human reviewers to evaluate the same candidate architectures, compare their ratings and describe disagreements.

**Do not describe any result from these tools as an independent expert certification.** Both the stated expertise and independence of a reviewer are self-declarations. Cryptographic digests detect accidental or deliberate changes to packets but are **not digital signatures** and do not authenticate people. A reviewer identifier is not proof of a distinct individual. The aggregation report retains this limitation even when the required self-declared reviewer count is reached.

## Protocol

1. **Permission and case selection.** Obtain explicit authorization to distribute each research brief and candidate architecture. Avoid confidential or identifying production details in public datasets. A study file must affirm distribution permission, reference a Phase 6 `ResearchCase`, and name at least two alternative architecture candidates with the **same** immutable brief. The example is synthetic with rights confirmed by its curator, not a real-world independent benchmark.
2. **Blinded candidate assignment.** `prepare` validates the case and architecture models, creates unpredictable opaque candidate labels, removes generator priority scores and component validation/provenance text from distributable packets, and saves a private mapping with case/packet/source digests. This hides explicit source labels on a **best-effort** basis; structure, choices or decision records might still identify an author. It is not a guaranteed double-blind trial.
3. **Independent review.** Send only `packets/C-*.json` and matching blank templates to qualified reviewers. Use a fixed, precommitted 1–5 rubric covering responsibilities, interfaces, requirements, data consistency, security, reliability and justified complexity. Instruct reviewers to cite concrete requirement/component IDs, describe missing information, and independently judge viability. Reviewers must disclose professional qualifications, affiliation or other relevant conflicts to the human coordinator. **Do not show reviewers the source-label manifest or other reviewers' feedback.**
4. **Collect submissions.** Each reviewer removes the template's `instructions` key, fills their own pseudonymous reviewer identifier, expertise, ISO submission date, independence/conflict declaration, publication permission, dimension scores with textual evidence, verdict rationale and any findings. Submit completed files over a secure, privately approved channel as `*.submission.json`; never commit reviews, identifying data, or private cases to GitHub.
5. **Validate and aggregate.** `aggregate` rechecks the original packet hashes, submission digests, exact rubric dimensions, and evidence anchors. It rejects duplicate self-reported reviewer IDs per candidate and distinguishes self-reported independent, consented submissions from conflicts or withheld publication consent. It reports the median, min/max and range for each dimension only when the minimum count is met; differences of at least 2 points flag material disagreement. It **never** selects an architectural winner or assigns verified independence.
6. **External verification and adjudication.** The study coordinator must separately verify identity, independence, expertise, and consent using a documented process, keep signed attestations and raw records in access-controlled storage, resolve or preserve disagreements, and obtain domain-specialist review for high-risk safety, privacy, consistency or timing claims. **This authentication and adjudication is not automated by Speccanopy.**
7. **Holdout control.** Real blinded holdout cases, provenance, source-to-label mapping and reviewer submissions must remain outside public GitHub and model prompts. A `private_holdout` field only labels an intended partition; it does not establish secrecy. Do not train/tune on evaluation cases or share them with model providers without permission.

## Commands

Install Python 3.11+ and the project as usual:

```bash
python -m pip install -e '.[dev]'
pytest -q

# Generate two distributable architecture packets plus a PRIVATE source mapping.
speccanopy-experts prepare examples/expert-review/ecommerce-study.json \
  --output out/expert-ecommerce

# Inspect public packet and blank template, then obtain genuine human submissions.
# For a demonstration with NO submissions, the result must remain awaiting_reviewers.
speccanopy-experts aggregate out/expert-ecommerce/private/manifest.json \
  --submissions out/expert-ecommerce/submissions \
  --output out/expert-ecommerce/report
```

The two commands are also available with `python -m speccanopy.expert_review prepare ...` and `aggregate ...`. Both return 0 for successfully performed operations, even if **no human reviews exist**; 0 is not a success grade for an architecture. Invalid files or digest mismatches return 1.

`prepare` writes `private/manifest.json` with restricted file permissions and `packets/C-*.json` plus `templates/C-*.template.json`. A template contains intentionally blank ratings and is **not** a submission. Do not combine outputs of separate studies in one directory. `aggregate` emits `expert-review-summary.json` and `.md` containing only anonymous aggregate statistics and eligibility counts; it suppresses ratings when fewer than the configured number of self-declared reviewers have consented. Do **not** publish summaries of confidential holdout studies or consider aggregate counts a substitute for consent processes.

## Reviewer rubric calibration

Interpret ratings consistently: **1** = critical architectural gaps, **2** = major unresolved issues, **3** = partially supported with meaningful unknowns, **4** = generally defensible for stated scope with minor gaps, **5** = strong, specific reasoning/evidence within stated scope. Each numerical rating requires explanation. Findings must cite real requirement/component IDs when available; an unanchored semantic concern should still be described rather than invented as a fact. Reviewers should mark viability `insufficient_information` whenever the brief or quality scenarios cannot support a sound decision.

A provisional panel quorum is **at least two distinct, self-declared independent and consenting reviewer IDs per candidate**, not a verification of separate, qualified humans. Reviewer disagreement is recorded, not averaged away. Until external authentication, findings remain self-reported observations.

## Research governance and next human actions

- Recruit at least two qualified, independent practitioners per benchmark domain, preferably reviewers with distinct employers and no role in generating the candidates. A safety-critical application also requires its relevant specialist, not a generic architectural score.
- Obtain permissible de-identified real application briefs and confirm redistribution and publication rights in writing. Start with one low-risk domain, then add distributed and embedded/safety-relevant cases.
- Ask reviewers to evaluate multiple defensible architectures, not a single named “gold standard”. Record source evidence, disqualifying assumptions and plausible trade-offs.
- Independently confirm reviewer identities and conflicts; keep authentication evidence outside the repository. Set aside a genuinely undisclosed holdout, and register the rubric before revealing candidates.
- Publish an evidence-bound methods report covering disagreements, inter-reviewer reliability, false positives/negatives, unresolved failure modes and limitations, once actual independent assessments exist.

**Recruitment invitation (ready to adapt, not sent):**

> We're seeking independent, experienced software architects to review de-identified architecture alternatives for an open-source architecture-design research project. Reviews focus on requirements coverage, interfaces, data ownership, quality trade-offs and operational complexity. Participation requires a conflict-of-interest declaration and permission to use anonymized aggregate findings. This is a research review, not a product certification. See Issue #2 for scope and contribution guidelines.

## Synthetic example and current evidence status

[`examples/expert-review/ecommerce-study.json`](../examples/expert-review/ecommerce-study.json) references **two public, maintainer-curated e-commerce candidates** from Phase 6. It contains no reviewer responses. Its `development` partition is deliberate: public fixtures are not blind holdouts. No approval, verified expert claim, qualified reviewer identity, agreement measure or semantic-quality gain is reported. Progress on obtaining independent evidence remains open in Issue #2.

## Reviewer recruitment launched (2026-11-05)

The project has publicly invited [reviewer volunteers](https://github.com/MSKazemi/speccanopy/issues/3) and [permissioned benchmark case proposals](https://github.com/MSKazemi/speccanopy/issues/4). Use the [reviewer recruitment and consent workflow](reviewer-recruitment.md), [case intake guide](benchmark-case-intake.md), and issue templates for public **non-sensitive** expressions of interest only. Publication of invitations does not mean independent reviewers have been recruited, permissions obtained, or a private holdout created. Issue #2 remains open for real evidence collection.
