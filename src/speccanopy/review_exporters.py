"""Human- and machine-readable outputs for independent architecture reviews."""

from __future__ import annotations

import json
from pathlib import Path

from .review import ArchitectureReview


def _md(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def review_markdown(report: ArchitectureReview) -> str:
    style = report.style_comparison
    quality = report.quality_review
    lines = [
        f"# Architecture review: {_md(report.system)}", "",
        f"**Source architecture status:** {_md(report.source_architecture_status)}  ",
        f"**Review status:** {_md(report.overall_status)}  ",
        "**Important:** Structural checks and heuristic style fit do not constitute architecture approval.",
        "", "## Style comparison", "",
        f"**Authored style:** {_md(style.declared_style or 'not specified')}  ",
        f"**Recommendation:** {_md(style.recommendation or 'abstain')}  ",
        f"**Result:** {_md(style.status)} — {_md(style.reason)}", "",
        "| Candidate | Score (0-10) | Trade-off |", "| --- | ---: | --- |",
    ]
    for candidate in style.candidates:
        lines.append(f"| {_md(candidate.style)} | {_md(candidate.score if candidate.score is not None else 'n/a')} | {_md(candidate.tradeoff)} |")
    lines.extend(["", "Scores use explicitly supplied drivers and heuristic profiles, **not measured benchmarks**.",
                  "", "## Quality and traceability review", "",
                  f"**Status:** {_md(quality.status)}  ",
                  f"**Mandatory requirements:** {len(quality.coverage.verified)} verified-evidence-linked, "
                  f"{len(quality.coverage.planned_only)} planned only, {len(quality.coverage.uncovered)} uncovered.", "",
                  "### Quality scenarios", ""])
    if not quality.scenario_assessments:
        lines.append("No quality scenarios were supplied. Unassessed quality requirements may still be reported as findings.")
    else:
        lines.extend(["| Scenario | Quality requirement | Assessment | Evidence |",
                      "| --- | --- | --- | --- |"])
        for scenario in quality.scenario_assessments:
            lines.append(f"| {_md(scenario.scenario_id)} | {_md(scenario.requirement_id)} | "
                         f"{_md(scenario.status)} | {_md(scenario.verification_status)} |")
    lines.extend(["", "### Findings", ""])
    if not quality.findings:
        lines.append("No deterministic rule findings; expert architecture review is still required.")
    else:
        for finding in quality.findings:
            lines.extend([f"**{_md(finding.id)} — {_md(finding.severity)} / {_md(finding.category)}**",
                          "", f"{_md(finding.description)}", "",
                          f"Action: {_md(finding.recommendation)}", ""])
    lines.extend(["", f"Source architecture open findings: {_md(', '.join(quality.source_findings) or 'none')}",
                  "", "## Provenance and limitations", "", _md(report.provenance),
                  "", _md(quality.caveat), ""])
    return "\n".join(lines)


def export_review(report: ArchitectureReview, destination: str | Path) -> dict[str, Path]:
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    content = {
        "architecture-review.json": report.model_dump(mode="json"),
        "style-comparison.json": report.style_comparison.model_dump(mode="json"),
        "quality-review.json": report.quality_review.model_dump(mode="json"),
        "architecture-review.md": review_markdown(report),
    }
    paths = {}
    for name, value in content.items():
        path = out / name
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths[name] = path
    return paths
