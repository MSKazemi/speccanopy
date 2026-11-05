# Benchmark case contribution and permission intake

**Status (2026-11-05):** Public call open at [Issue #4](https://github.com/MSKazemi/speccanopy/issues/4). No real-world case has been accepted and independently validated by this intake process in the repository.

## Goal

Acquire realistic software architecture problems that can be reviewed by independent human architects and tested against multiple defensible solutions. A case does **not** require a single canonical component hierarchy. The benchmark must measure ability to identify trade-offs and risks, not agreement with one arbitrary tree.

## Public proposal: links and metadata only

Use [Issue #4](https://github.com/MSKazemi/speccanopy/issues/4) or the **Propose a benchmark case** issue template.

A suitable public proposal contains:
- A **non-sensitive** two-sentence statement of the system's purpose and domain.
- A link only when the source is already lawfully public; otherwise say "nonpublic case — permission required" without attachments.
- The origin and who controls reproduction, distribution and derivative permissions.
- Which architecture constraints matter (e.g. payments/consistency, availability, privacy, scalability, real-time deadlines), without revealing sensitive details.
- The proposed evaluation scope and whether at least two plausible architecture options can be meaningfully contrasted.

Do **not** paste customer requirements, unreleased designs, access tokens, personal data, secrets, business-sensitive performance information or private employment details into a GitHub issue.

## Private intake (only after an agreed secure channel exists)

A coordinator must separately confirm the exact permissions for:
1. **Receipt:** whether the person has authority to disclose the source brief to the coordinator.
2. **Review distribution:** whether independent external reviewers may view the sanitized case and candidate architecture packets.
3. **Storage/retention:** who stores the data, who can access it, a real deletion/retention policy, and withdrawal limits.
4. **AI processing:** separately authorize any prompts sent to a model provider; **no AI upload by default**.
5. **Publication:** whether a public derivative brief, anonymized aggregate findings, excerpts, full reports, and attributed names are individually allowed.
6. **License/source attribution:** whether the specific document is licensed for copying or just publicly readable; preserve necessary copyright and attribution notices.

A public web link **does not automatically authorize republication**. An open-source code license may not license a separate design illustration or private operational dataset. Obtain contributor approval and confirm the relevant material's terms before adding files to this repository.

## Sanitize the case

Remove or generalize organization and customer names, internal URLs, accounts, user identifiers, credentials, private topology details, exact production telemetry and vulnerability data. Preserve the architectural constraints required for meaningful review. If redaction destroys the engineering problem, restrict the case to a private approved study or reject it.

For regulated, security-critical or safety-critical systems, obtain qualified specialist input and any necessary research approvals; avoid putting sensitive failure or exploit scenarios in public artifacts.

## Acceptance rubric

| Dimension | Required evidence |
| --- | --- |
| Requirements | Functional and nonfunctional requirements with stable IDs |
| Context | Actors, external systems, major data flows, operating assumptions |
| Constraints | Team/operations, interoperability, consistency and regulatory limits where relevant |
| Alternatives | More than one plausible approach or a documented reason alternatives are constrained |
| Ground truth | Independent experts can judge a design without being forced to match one component tree |
| Rights | Written scope for circulation, use and reporting |
| Privacy | De-identification and private handling verified |
| Provenance | Original source, date/version and allowed access documented |

**Reject or defer** any case lacking rights to share it with reviewers, any incomplete privacy consent, a conflict that prevents independent assessment, or a case whose requirements are too thin for a defensible quality review.

## Holdout policy

Public synthetic examples and public-source designs are **development data, not secret holdouts**. Genuine private holdouts require authorized access, an undisclosed storage location, locked rubrics before evaluation, and restrictions on accidental disclosure to model prompts, training, issue threads or repository fixtures. A flag named "private_holdout" alone is not proof of blinding.

See [Phase 6 research methodology](phase6-architecture-research.md) and [Phase 7 expert-review packet protocol](phase7-expert-panel.md).

## Source scouting

The [public-source triage list](public-case-source-triage.md) identifies potential public reference sets. None has been imported, licensed for this specific benchmark, de-identified or expert-reviewed simply by being listed.
