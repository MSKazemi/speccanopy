"""CLI for deterministic architecture generation and advisory architecture review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .ai import (
    AIProposalBundle, ApprovalReceipt, OpenAIResponsesClient, ScriptedProposalClient,
    approve_proposal_bundle, brief_digest, draft_architecture, fixture_digest,
)
from .ai_exporters import export_ai_draft, export_approved
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

    propose_ai = sub.add_parser("propose-ai", help="Draft a component hierarchy using structured AI model proposals")
    propose_ai.add_argument("brief", type=Path)
    propose_ai.add_argument("--output", type=Path, required=True)
    propose_ai.add_argument("--backend", choices=["openai", "scripted"], default="openai")
    propose_ai.add_argument("--model", help="Explicit model ID for live Responses API")
    propose_ai.add_argument("--responses", type=Path, help="Scripted offline responses (not AI inference)")
    propose_ai.add_argument("--max-model-calls", type=int, default=40)

    approve_ai = sub.add_parser("approve-ai", help="Record explicit human review and release proposed hierarchy as a fixture")
    approve_ai.add_argument("bundle", type=Path, help="ai-proposals.json produced by propose-ai")
    approve_ai.add_argument("--reviewer", required=True, help="Identifier of human reviewing proposals")
    approve_ai.add_argument("--acknowledge-review", action="store_true", help="Confirm the human reviewed candidate components")
    approve_ai.add_argument("--output", type=Path, required=True, help="Output *.design.json fixture path")

    args = parser.parse_args(argv)
    if args.command == "propose-ai":
        try:
            brief = SystemBrief.model_validate_json(args.brief.read_text(encoding="utf-8"))
            if args.backend == "scripted":
                if not args.responses:
                    raise ValueError("--backend scripted requires --responses")
                responses = json.loads(args.responses.read_text(encoding="utf-8"))
                if not isinstance(responses, dict):
                    raise ValueError("Scripted responses must be a JSON object keyed by parent ID")
                client = ScriptedProposalClient(responses, model=args.model or "scripted-v1")
            else:
                if args.responses:
                    raise ValueError("--responses is only valid with --backend scripted")
                if not args.model:
                    raise ValueError("--model is required for live Responses API proposals")
                client = OpenAIResponsesClient(args.model)
            result, bundle = draft_architecture(brief, client, max_model_calls=args.max_model_calls)
            paths = export_ai_draft(result, bundle, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error drafting AI architecture: {exc}", file=sys.stderr)
            return 1
        print(f"Proposal for {brief.system}: {bundle.component_count} components, "
              f"{bundle.model_calls} model requests, {bundle.generation_status}")
        print("Human review required before using these proposals as an approved fixture")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 0

    if args.command == "approve-ai":
        try:
            bundle = AIProposalBundle.model_validate_json(args.bundle.read_text(encoding="utf-8"))
            fixture, receipt = approve_proposal_bundle(
                bundle, reviewer=args.reviewer, acknowledge_review=args.acknowledge_review,
            )
            paths = export_approved(fixture, receipt, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error approving AI proposals: {exc}", file=sys.stderr)
            return 1
        print("Proposal hierarchy acknowledged for further architecture review; not validated")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 0

    if args.command == "design":
        fixture_path = args.fixture or args.brief.with_name(args.brief.stem + ".design.json")
        try:
            brief = SystemBrief.model_validate_json(args.brief.read_text(encoding="utf-8"))
            fixture = FixtureDesign.model_validate_json(fixture_path.read_text(encoding="utf-8"))
            approval_path = fixture_path.with_suffix(".approval.json")
            if approval_path.exists():
                receipt = ApprovalReceipt.model_validate_json(approval_path.read_text(encoding="utf-8"))
                if brief_digest(brief) != receipt.brief_sha256:
                    raise ValueError("Approved AI fixture does not match this application brief")
                if fixture_digest(fixture) != receipt.fixture_sha256:
                    raise ValueError("Approved AI fixture changed after approval")
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
