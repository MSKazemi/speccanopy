# Architecture contract and validation semantics (Phase 1)

**Status:** Executable foundation, not architecture generation.

This contract implements the first slice of the [execution roadmap](execution-roadmap.md) and follows the [confirmed vision](vision-and-goal.md). Speccanopy **designs architectures**; it does not build or deploy target software.

## Input

`SystemBrief`: a system name, nonempty goals, actors, functional requirements, quality requirements, and design constraints. Requirements have stable IDs and a mandatory flag. IDs must be unique across functional/quality requirements. Unknown fields are rejected.

See [`examples/cli-utility.json`](../examples/cli-utility.json).

## Output

`ArchitectureSpec` contains:
- The input `brief` and selected architecture style (if decided).
- `components[]`: a normalized, singly rooted containment hierarchy; every child references `parent_id`, and no duplicated nested copy is stored.
- `relationships[]`: typed graph edges between existing components. Containment cycles are forbidden; inter-component dependency cycles may be documented.
- `verification_cases[]`: architecture-level verification plans or reviewed evidence, linked to explicit requirements *and* responsible components.
- `decisions[]`: candidate/accepted architectural decisions, alternatives and trade-offs.
- `findings[]`: review issues, risks and their resolution status.
- An overall document `status`: `draft`, `incomplete_requires_review`, or `validated_for_scope`.

See [`examples/cli-utility-architecture.json`](../examples/cli-utility-architecture.json). It is deliberately `draft`: a validated JSON document is **not necessarily** a fully reviewed design.

## Structural validation rules

1. Validate with Pydantic v2; refuse unknown fields and invalid IDs.
2. Require one root component. No duplicate element IDs, dangling parents, or containment cycles.
3. Enforce document budgets `max_depth` and `max_nodes`.
4. All edges, verification cases, findings and referenced requirement IDs must point to existing elements.
5. For a component to have status `ready`, it must state its interface or why none applies, data ownership or why none applies, review evidence, and an explicit stop reason.
6. A verification case with status `verified` must include evidence. A case cannot verify a requirement if none of its referenced components owns that requirement.
7. `validated_for_scope` requires an explicit style, all components `ready`, every mandatory requirement supported by linked verified architecture evidence, and no open high/critical findings.

These are **necessary structural and process gates, not sufficient proof of real-world design correctness**. Evidence is currently a human-authored text field; independent expert review and stronger quality checks are future milestones.

## Coverage semantics

`ArchitectureSpec.coverage_report()` evaluates **mandatory** requirements:
- `verified`: linked to a responsible component and a `verified` architecture verification case with evidence.
- `planned_only`: linked to a responsible component and a `planned` verification case, but none verified.
- `uncovered`: neither of the above. A component ID alone does not mean the requirement was actually verified.

Do not confuse architectural verification cases with application-code tests. Speccanopy does not execute the target application.

## Deterministic proposer

`ComponentProposer` is a Python protocol; `FixtureComponentProposer` takes predefined candidate child components and returns them without side effects. It rejects duplicate IDs, self-children and unknown requirement IDs. The future recursive engine will consume this protocol, score/validate candidates and manage the priority queue and termination.

No LLM integration or adaptive decomposition engine has been implemented in Phase 1.

## Local checks

After installing with `python -m pip install -e '.[dev]'`, run:

```bash
pytest -q
python -c "from speccanopy.models import SystemBrief; print(SystemBrief.model_validate_json(open('examples/cli-utility.json').read()).system)"
python -c "from speccanopy.models import ArchitectureSpec; s=ArchitectureSpec.model_validate_json(open('examples/cli-utility-architecture.json').read()); print(s.coverage_report().model_dump())"
```

## Next development slice

Implement a bounded recursive decomposer that takes `SystemBrief` and `ComponentProposer`, produces `ArchitectureSpec`, and proves varying child counts, early stopping, and explicit incomplete statuses against three contrasting fixtures. Only then add an AI-backed proposer and independent architecture quality review.
