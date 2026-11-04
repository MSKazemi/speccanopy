"""CLI for deterministic architecture drafts from a brief and curated proposals."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .decomposer import generate_architecture
from .exporters import export_generation
from .fixtures import FixtureDesign
from .models import SystemBrief


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="speccanopy", description="Design reviewable software architectures")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("design", help="Generate an architecture draft from a system brief and curated design fixture")
    cmd.add_argument("brief", type=Path)
    cmd.add_argument("--fixture", type=Path, help="Curated proposal fixture; default: <brief>.design.json")
    cmd.add_argument("--output", type=Path, required=True)
    cmd.add_argument("--strict", action="store_true", help="Return exit code 2 when review is required")
    args = parser.parse_args(argv)
    if args.command != "design":
        parser.error("Unknown command")
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


if __name__ == "__main__":
    raise SystemExit(main())
