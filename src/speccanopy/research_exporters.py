"""File exporters for non-certifying, provenance-aware architecture research."""

from __future__ import annotations

import json
from pathlib import Path

from .research import ResearchAssessment, SuiteAssessment


def research_markdown(result: ResearchAssessment) -> str:
    lines = ["# Architecture research evaluation", "",
             "**Curated criteria, NOT expert certification or semantic proof.**", "",
             f"Case: {result.case_id} — {result.case_title}  ",
             f"Split: {result.split}  ",
             f"Origin: {result.origin}  ",
             f"Review status: {result.review_status} (claims: {result.review_claim_count})  ",
             f"Selected style: {result.selected_style or 'unspecified'}  ",
             f"Detected family: {result.detected_style_family or 'unclassified'}  ",
             f"Common criterion coverage: {result.common_score:.2f}%  ",
             f"Overall result: **{result.result}**  ",
             f"Best diagnostic alternative: {result.best_path or 'none'}", "",
             "## Cross-cutting requirements", "",
             "| Criterion | Required | Present | Reason |", "| --- | --- | --- | --- |"]
    for c in result.common_results:
        lines.append(f"| {c.id} | {'yes' if c.required else 'no'} | {'yes' if c.present else 'no'} | {c.reason} |")
    lines.extend(["", "## Multiple acceptable alternatives", ""])
    for p in result.alternatives:
        lines.extend([f"### {p.id}: {p.name}", "",
                      f"Compatible family: {p.style_status} ({', '.join(p.permitted_styles)})  ",
                      f"Criterion coverage: {p.score:.2f}%  ",
                      f"Missing required criteria: {', '.join(p.missing_required) or 'none'}", "",
                      "| Criterion | Present | Reason |", "| --- | --- | --- |"])
        for c in p.results:
            lines.append(f"| {c.id} | {'yes' if c.present else 'no'} | {c.reason} |")
        lines.append("")
    lines.extend(["## Outstanding evidence", "",
                  f"Uncovered mandatory: {', '.join(result.uncovered_mandatory) or 'none'}  ",
                  f"Verification only planned: {', '.join(result.pending_verification) or 'none'}  ",
                  f"Open high/critical findings: {', '.join(result.open_high_or_critical_findings) or 'none'}", "",
                  "## Limits", "", result.caveat, ""])
    return "\n".join(lines)


def suite_markdown(result: SuiteAssessment) -> str:
    lines = ["# Speccanopy architecture research suite", "",
             "**Public fixtures are not an independent holdout or an expert-reviewed evaluation.**", "",
             f"Suite: {result.suite_name}  ", f"Cases evaluated: {result.total}", "",
             "| Split | Count | Criteria present, review needed | Criteria gaps | No compatible style | Mean common coverage |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for s in result.by_split:
        mean = f"{s.average_common_criterion_coverage:.2f}%" if s.average_common_criterion_coverage is not None else "n/a"
        lines.append(f"| {s.split} | {s.count} | {s.criteria_present_review_required} | {s.criteria_gaps} | {s.no_compatible_style} | {mean} |")
    lines.extend(["", "## Cases", "", "| Entry | Case | Result | Best alternative | Review status |", "| --- | --- | --- | --- | --- |"])
    for label, case in result.cases.items():
        lines.append(f"| {label} | {case.case_id} | {case.result} | {case.best_path} | {case.review_status} |")
    lines.extend(["", "## Limitations", "", result.caveat, ""])
    return "\n".join(lines)


def export_research(result: ResearchAssessment | SuiteAssessment, destination: Path) -> dict[str, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    is_suite = isinstance(result, SuiteAssessment)
    stem = "research-suite" if is_suite else "research-case"
    report_path = destination / f"{stem}.json"
    report_path.write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = destination / f"{stem}.md"
    markdown_path.write_text((suite_markdown(result) if is_suite else research_markdown(result)) + "\n", encoding="utf-8")
    return {report_path.name: report_path, markdown_path.name: markdown_path}
