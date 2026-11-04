"""CLI for deterministic architecture generation and advisory architecture review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .decomposer import generate_architecture
from .exporters import export_generation
from .fixtures import FixtureDesign
from .models import ArchitectureSpec, SystemBrief
from .review import ReviewConfig, assess_architecture
from .review_exporters import export_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="speccanopy", description="Design and review software architectures")
    sub = parser.add_subparsers(dest="command", required=True)

    design = sub.add_parser("design", help="Generate a draft from a brief and curated design fixture")
    design.add_argument("brief", type=Path)
    design.add_argument("--fixture", type=Path, help="Curated proposal fixture; default: <brief>.design.json")
    design.add_argument("--output", type=Path, required=True)
    design.add_argument("--strict", action="store_true", help="Return code 2 when review is required")

    review = sub.add_parser("review", help="Compare candidate architecture styles and review design quality")
    review.add_argument("architecture", type=Path, help="Previously generated ArchitectureSpec JSON")
    review.add_argument("--config", type=Path, help="Explicit style drivers and quality scenarios (optional)")
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--strict", action="store_true", help="Return code 2 for results requiring review")

    args = parser.parse_args(argv)
    if args.command == "design":
        fixture_path = args.fixture or args.brief.with_name(args.brief.stem + ".design.json")
        try:
            brief = SystemBrief.model_validate_json(args.brief.read_text(encoding="utf-8"))
            fixture = FixtureDesign.model_validate_json(fixture_path.read_text(encoding="utf-8"))
            result = generate_architecture(brief, fixture)
            paths = export_generation(result, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error designing architecture: {exc}", file=sys.stderr)
            return 1
        report = result.architecture.coverage_report()
        print(f"Architecture: {brief.system}")
        print(f"Status: {result.architecture.status}")
        print(f"Components: {len(result.architecture.components)}; max depth: {result.stats()['max_depth']}")
        print(f"Mandatory requirements: {len(report.verified)} verified, {len(report.planned_only)} planned, {len(report.uncovered)} uncovered")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and result.architecture.status == "incomplete_requires_review" else 0

    if args.command == "review":
        try:
            spec = ArchitectureSpec.model_validate_json(args.architecture.read_text(encoding="utf-8"))
            config = (ReviewConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
                      if args.config else ReviewConfig())
            result = assess_architecture(spec, config)
            paths = export_review(result, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error reviewing architecture: {exc}", file=sys.stderr)
            return 1
        print(f"Review: {spec.brief.system}")
        print(f"Status: {result.overall_status}")
        print(f"Advisory style: {result.style_comparison.recommendation or 'abstain'}")
        print(f"Quality findings: {len(result.quality_review.findings)}")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and result.overall_status == "requires_review" else 0
    parser.error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
