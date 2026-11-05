# Candidate public sources for architecture research cases

**Scouting status (2026-11-05): candidate discovery only.** These are external reference collections, not acquired or validated benchmark cases. No source has been copied or claimed to be a genuinely blind evaluation set.

| Candidate collection | What it could provide | Verification still needed |
| --- | --- | --- |
| [arc42 architecture examples](https://github.com/arc42/examples.arc42.org-site) and [arc42 example site](https://examples.arc42.org/) | Real-system architecture documentation across domains, with goals, constraints, building blocks, runtime views and decisions | Each case's underlying author, license, republication rights, completeness and suitability for an independent comparison. An example described as real is not automatically permissioned. |
| [Kubernetes Enhancement Proposals](https://www.kubernetes.dev/resources/keps/) and the [kubernetes/enhancements repo](https://github.com/kubernetes/enhancements) | Publicly documented feature requirements, motivation, design options, API/deployment impacts and trade-offs for a large distributed system | Which specific KEP provides a sufficiently self-contained review brief; copyright and license for the exact materials; independence of reviewers with respect to KEP authors; whether a model may already have encountered the public proposal. |

## Why these are leads, not verified cases

A real project's published design may be a useful source of requirements and real trade-offs, but an existing documented architecture may leak a "reference answer" to reviewers and AI models. This undermines blind evaluation unless a separate, lawful and truly undisclosed holdout is created.

Architectural documentation is also not equivalent to independently verified evidence of correctness or engineering outcomes. Reviewers must assess requirements, risks and alternatives rather than trusting the source's claimed success.

## Acquisition checklist

1. Select one **specific** document or version and inspect its license/re-use terms and authorship; preserve attribution.
2. Verify rights to extract or paraphrase its requirements for a new evaluation corpus. If permissions are uncertain, **link only** and do not copy source content.
3. Determine whether enough context exists for an independent expert to judge several viable alternatives.
4. Extract an implementation-neutral brief with stable requirement IDs; remove solution-specific clues where possible without changing its engineering meaning.
5. Mark public cases as **development/public evidence**, never secret holdouts. Secure separately permissioned real-world cases for true blind tests.
6. Register baseline rubric, domain assumptions and candidate provenance before review. Track disagreements and negative outcomes.

## Next human decision

A study coordinator should select **one specific source** for legal/technical triage, contact the rights holder if necessary and seek qualified reviewers who had no role in producing the source. Until that happens, both collections remain leads only.

For safe submission details see [benchmark case intake](benchmark-case-intake.md).
