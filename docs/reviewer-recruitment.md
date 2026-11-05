# Recruiting independent architecture reviewers

**Status (2026-11-05):** Volunteer call published in [Issue #3](https://github.com/MSKazemi/speccanopy/issues/3). The repository does **not** contain independently authenticated reviewer submissions. Recruitment is open; no reviewer identity, consent or availability is implied by publication of this document.

This document implements the human-research next step from [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2) and complements the [Phase 7 review protocol](phase7-expert-panel.md).

## Purpose and boundaries

Speccanopy is a **universal software architecture design engine**, not an application builder. The objective is to determine whether architecture proposals are defensible under stated functional, security, reliability, data, deployment-design and operational constraints. We need qualified humans to identify semantic faults that automated schema checks cannot establish.

Reviewers are not asked to endorse the engine or certify a system as production-safe. Critical disagreements, alternative valid styles and "insufficient information" responses are important outcomes.

## Two recruitment tracks

**Track A: public, nonconfidential process pilot.** Start with the published synthetic [e-commerce study](../examples/expert-review/ecommerce-study.json), which compares a modular design and a hypothetical distributed alternative. It tests instructions, submission validation, blinding labels, reviewer comprehension and aggregation. Because source designs are already public, **this is not a genuinely blind study or independent performance benchmark**.

**Track B: genuine evidence study.** After lawful case acquisition, panel screening, permissions, and a private holdout protocol, have independent reviewers evaluate permissible real application briefs and competing architecture alternatives. Keep actual identity verification, the mapping of candidates to sources and nonpublic materials in controlled, off-repository storage. Never send private case data to a model provider without separate authorization.

## Volunteer eligibility and screening

We seek reviewers who have made or reviewed consequential software architecture choices. Useful experience includes distributed/backend systems, data-intensive applications, security architecture, reliability/platform engineering, real-time/embedded systems and domain-specific quality assurance.

A coordinator should privately establish:
1. The relevant design/review experience and demonstrable public professional work or independently verifiable experience.
2. Whether the reviewer authored a candidate, has financial/employment ties to the evaluated system, or has other conflicts.
3. The ability to read the assigned case and write substantive evidence-linked findings.
4. Whether the reviewer gives **informed, specific permission** to collect a review and use de-identified aggregates; publication of verbatim findings or attribution requires separate approval.
5. An agreed private communication method and data-handling arrangement before accepting contact details or confidential artifacts.

A GitHub username, declared qualifications, source hash or self-attested independence is **not authentication**. Two GitHub usernames do not necessarily represent two independent reviewers. The coordinator must verify distinct humans and independence outside Speccanopy. Do not collect government ID scans or sensitive credentials just to screen volunteers.

## Public registration — what to share

Use the public [reviewer volunteer call](https://github.com/MSKazemi/speccanopy/issues/3), or open a new issue using the **Volunteer architecture reviewer** template.

A public response should include only: relevant technical domains; an optional high-level, non-sensitive account of experience; optional public profile/contribution link; and whether a potential candidate-authorship conflict exists.

**Never put email addresses, phone numbers, employer-internal diagrams, client case details, identification documents, private reviews or consent records in a public GitHub issue.** GitHub history and notifications may retain copies after editing or deleting a comment.

## Coordinator workflow and gates

| Gate | Coordinator action | Required record | Publishable? |
| --- | --- | --- | --- |
| 1. Interest | Note a public expression of interest | Public issue URL | Yes |
| 2. Screen | Check experience, domain and conflicts using an appropriate private method | Private screening note | No |
| 3. Consent | Explain scope, voluntary status, privacy, aggregation, withdrawal and proposed retention before sending packets | Private affirmative consent and permission scope | No |
| 4. Assign | Freeze study/rubric, generate candidate-source-blinded packets, avoid conflicts | Private assignment and packet digest | No |
| 5. Review | Receive independent, evidence-anchored ratings before showing other reviewers' results | Private validated submission | No |
| 6. Verify | Confirm independent people/qualifications and whether submission covers actual assigned candidate | Private verification record | No |
| 7. Adjudicate | Preserve disagreements and obtain domain-specialist input for safety/security-critical findings | Private adjudication log | Usually no |
| 8. Report | Aggregate only consented data, suppress identifying information, document limitations | Redacted public report, if publication authorized | Only if permitted |

**Quorum target:** at least **two verified independent reviewers per candidate**, not just two self-reported reviewer IDs. For genuine study claims, recruit across distinct organizations where possible. Do not count a contributor who authored the candidate as independent for that candidate.

**Do not claim reviewer participation is established** until a qualified person has affirmatively agreed through the coordinator's actual contact process. Do not count a completed automated example as a submitted review.

## Participant information to communicate before consent

- **Activity:** critique architecture responsibilities, interfaces, state/data ownership, failure scenarios, security, reliability and proportionality of complexity using a fixed 1–5 rubric and explanatory evidence. Reviewers may mark a candidate nonviable or insufficiently specified.
- **Participation:** voluntary, with no payment arranged for the current public volunteer call. Agree workload and scheduling individually. No need to accept a study merely because interest was expressed on GitHub.
- **Privacy:** public registration is public. Private communications and raw submissions should be handled through a mutually agreed access-controlled channel; do not commit them to GitHub. The coordinator must set and disclose an actual retention/deletion policy **before** soliciting personal data, not promise one that is not yet established.
- **Use:** permission for anonymized aggregate reporting must be explicit. Publishing attributed quotes, names, full reports or proprietary case descriptions needs separate authorization. The right to re-use application materials is independent of review consent.
- **Withdrawal:** tell participants the practical point at which withdrawal from future aggregate analysis can be honored; do not promise to remove copies from GitHub history, archived notifications or already-public downstream reports.
- **Research ethics:** this project has not claimed institutional ethics-board approval. Assess whether formal review/consent requirements apply before involving regulated, vulnerable or employee research participants.

## Pilot execution

From a trusted local checkout (not a public hosted runner):

~~~bash
python -m pip install -e '.[dev]'
speccanopy-experts prepare examples/expert-review/ecommerce-study.json --output out/expert-ecommerce
~~~

Send only the generated public packet and matching blank template to each consented reviewer. Keep the source mapping at out/expert-ecommerce/private/manifest.json private. Collect filled templates through the agreed private channel, then aggregate:

~~~bash
speccanopy-experts aggregate out/expert-ecommerce/private/manifest.json --submissions out/expert-ecommerce/submissions --output out/expert-ecommerce/report
~~~

The CLI's aggregation is **provisional**: it cannot itself establish identity or expert competence, even with two submissions. Full instructions are in [Phase 7](phase7-expert-panel.md).

## Evidence and completion criteria for Issue #2

The issue remains open until there are permissioned real-world briefs, verified independent reviewers, retained independent findings, a legitimate unseen holdout, defensible adjudication of conflicts and a published limitations report. Publishing a recruitment issue or receiving expressions of interest is **progress only**, not completion of those milestones.

For case sources and rights handling see [benchmark case intake](benchmark-case-intake.md); for potential public starting points see [public case source triage](public-case-source-triage.md).
