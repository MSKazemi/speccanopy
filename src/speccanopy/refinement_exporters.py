"""Machine-readable and human-readable outputs for bounded refinement."""

from __future__ import annotations

import json
from pathlib import Path

from .benchmark import BenchmarkAssessment, BenchmarkComparison
from .exporters import prepare_new_output_dir
from .models import ArchitectureSpec
from .refinement import RefinementPlan, RefinementReceipt
from .review import ArchitectureReview


def _write_json(out: Path, name: str, value: object) -> Path:
    path = out / name
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def plan_markdown(plan: RefinementPlan) -> str:
    lines = [
        "# Architecture refinement proposal", "",
        "**Pending human review — NOT approved architecture.**", "",
        f"Author (self-declared): {plan.edits.author}  ",
        f"Proposed rounds: {len(plan.rounds)}  ",
        f"Actions: {len(plan.edits.patches)}", "",
        "## Change log and review effects", "",
    ]
    for step in plan.rounds:
        lines.extend([
            f"### Round {step.round}", "",
            f"Patches: {', '.join(step.patch_ids)}  ",
            f"High/critical findings: {step.before_high_or_critical} → {step.after_high_or_critical}  ",
            f"Rule categories before: {step.before_counts}  ",
            f"Rule categories after: {step.after_counts}  ",
            f"Invalidated prior verification evidence: {', '.join(step.invalidated_verification_cases) or 'none'}  ",
            f"Remaining gaps: {', '.join(step.unresolved_categories) or 'none'}", "",
        ])
    lines.extend(["## Human review checklist", "",
                  "- [ ] Check patch rationale against requirements and domain constraints",
                  "- [ ] Inspect interfaces, ownership, and failure paths for contradictions",
                  "- [ ] Review evidence invalidation and remaining quality findings",
                  "- [ ] Inspect the preview against the original architecture",
                  "- [ ] Record explicit acknowledgement before releasing a revised draft", "",
                  plan.caveat, ""])
    return "\n".join(lines)


def export_refinement_plan(plan: RefinementPlan, candidate: ArchitectureSpec,
                           before: ArchitectureReview, after: ArchitectureReview,
                           destination: str | Path) -> dict[str, Path]:
    out = prepare_new_output_dir(destination, "Refinement plan")
    paths = {
        "refinement-plan.json": _write_json(out, "refinement-plan.json", plan),
        "candidate-preview.json": _write_json(out, "candidate-preview.json", candidate),
        "review-before.json": _write_json(out, "review-before.json", before),
        "review-after.json": _write_json(out, "review-after.json", after),
    }
    target = out / "refinement-plan.md"
    target.write_text(plan_markdown(plan), encoding="utf-8")
    paths[target.name] = target
    return paths


def export_refinement_approved(candidate: ArchitectureSpec, receipt: RefinementReceipt,
                               after: ArchitectureReview, destination: str | Path) -> dict[str, Path]:
    out = prepare_new_output_dir(destination, "Refined architecture")
    return {
        "architecture.json": _write_json(out, "architecture.json", candidate),
        "refinement-receipt.json": _write_json(out, "refinement-receipt.json", receipt),
        "review-after.json": _write_json(out, "review-after.json", after),
    }


def benchmark_markdown(result: BenchmarkAssessment | BenchmarkComparison) -> str:
    comparison = isinstance(result, BenchmarkComparison)
    assessment = result.after if comparison else result
    lines = ["# Architecture reference rubric evaluation", "",
             "**Structural rubric checks only; not an expert architecture certificate.**", "",
             f"System: {assessment.system}  ",
             f"Rubric: {assessment.rubric_name} ({assessment.rubric_status})  ",
             f"Criterion coverage: {assessment.score:.2f}% ({assessment.satisfied}/{assessment.total})", ""]
    if comparison:
        lines.extend([f"Before: {result.before.score:.2f}%  ",
                      f"After: {result.after.score:.2f}%  ",
                      f"Change: {result.delta_points:+.2f} percentage points  ",
                      f"High/critical finding reduction: {result.reduced_high_or_critical}  ",
                      f"Newly missing criteria: {', '.join(result.introduced_missing_criteria) or 'none'}", ""])
    lines.extend(["| Criterion | Met | Weight | Reason |", "| --- | --- | ---: | --- |"])
    for item in assessment.results:
        text = item.reason.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item.id} | {'yes' if item.present else 'no'} | {item.weight} | {text} |")
    lines.extend(["", "## Limitations", "", result.caveat, ""])
    return "\n".join(lines)


def export_benchmark(result: BenchmarkAssessment | BenchmarkComparison,
                     destination: str | Path) -> dict[str, Path]:
    out = prepare_new_output_dir(destination, "Benchmark")
    report = _write_json(out, "reference-benchmark.json", result)
    md = out / "reference-benchmark.md"
    md.write_text(benchmark_markdown(result), encoding="utf-8")
    return {report.name: report, md.name: md}
