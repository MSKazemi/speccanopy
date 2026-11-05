# Contributing to Speccanopy

Thanks for considering a contribution. Speccanopy is an open-source **software architecture design engine**, not a system that automatically implements, builds or deploys the applications it designs.

There are three distinct ways to help: **review proposed architectures**, **suggest permissioned reference cases**, and **improve the Speccanopy code or documentation**. Please keep those activities separate: a passing test or self-reported reviewer name is never a professional architecture certification.

## 1. Volunteer to review architectures

Start with [the reviewer invitation, Issue #3](https://github.com/MSKazemi/speccanopy/issues/3), or use the *Volunteer architecture reviewer* GitHub issue template. The initial study compares two already-public synthetic e-commerce designs; it is a **process pilot, not a genuine blinded expert benchmark**.

In the public issue, share only your relevant architecture domain, a non-sensitive description of your professional experience and any potential conflict with the evaluated candidates. An expression of interest is **not research consent, verified expertise or a completed review**.

The study coordinator must privately verify reviewer identity and independence, describe the scope and data-handling terms, obtain informed consent and provide the review packet. Read the [recruitment guide](docs/reviewer-recruitment.md) and [review protocol](docs/phase7-expert-panel.md). Do not send completed review submissions in a public issue or pull request.

## 2. Suggest a benchmark application

Use [the benchmark case invitation, Issue #4](https://github.com/MSKazemi/speccanopy/issues/4), or the *Propose an architecture benchmark case* issue template. Public suggestions should contain only links to already-public sources, non-sensitive context, and a description of who controls publication rights.

**A public GitHub document is not automatically licensed for redistribution.** Do not upload customer materials, proprietary system diagrams, internal endpoints, credentials, personal data or private performance figures. Review or evaluation of any nonpublic case requires explicit permission, privacy safeguards and a secure intake arrangement **before** sharing details.

See the [case intake and permission guide](docs/benchmark-case-intake.md). Real-world case acceptance and genuine unseen holdouts remain outstanding research work, tracked by [Issue #2](https://github.com/MSKazemi/speccanopy/issues/2).

## 3. Contribute code, tests or documentation

Speccanopy targets Python 3.11+ and uses Pydantic v2 and pytest. In a local checkout:

```bash
python -m pip install -e '.[dev]'
pytest -q
```

Create a focused pull request describing:
- The architectural-design problem being addressed, or the affected documentation.
- Changes to input/output schemas, traceability, design statuses, evidence handling or backwards compatibility.
- Tests or reproducible fixtures for new code.
- Limitations and any open quality/security risks.

Retain the confirmed product boundary: **architecture specifications, not autonomous implementation of the target applications**. Preserve mandatory requirement IDs and explicit incomplete/requires-review statuses. Never mark a draft architecture validated merely because it is structurally consistent or a heuristic reviewer favors it.

Prefer small, reviewable patches. The continuous integration workflow tests Python 3.11 and 3.13. Before making a breaking schema change, explain its migration implications in the pull request.

## Privacy, security and research integrity

- **Do not put secrets or private information** in GitHub issues, pull requests, example briefs, test snapshots, logs or commit history. Deleting a post may not remove it from notifications, caches or git history.
- Do not create fictional expert ratings, fabricated qualifications, inferred consent or artificial holdout secrecy. Label all synthetic, mock and scripted examples clearly.
- AI-generated architecture proposals must retain provenance and the human approval boundary; a model's own claim of completeness is not sufficient evidence.
- For permissioned or sensitive research, use an **approved private process** arranged by the coordinator; public GitHub is not the collection point.
- Raise potentially sensitive security flaws using an appropriate private reporting path agreed with the project maintainer; **do not** disclose exploit details in public issues by default.

## Useful reading

- [Project vision and scope](docs/vision-and-goal.md)
- [Adaptive Recursive Architecture Design](docs/adaptive-recursive-architecture-design.md)
- [Current independent review status](docs/outreach-distribution.md)
- [Reviewers and consent](docs/reviewer-recruitment.md)
- [Case rights and intake](docs/benchmark-case-intake.md)
- [Independent research evidence tracker, Issue #2](https://github.com/MSKazemi/speccanopy/issues/2)

**Evidence status:** The software coordination and deterministic evaluation tools exist, but authenticated independent reviewers and permissioned real-world benchmarks are still needed.
