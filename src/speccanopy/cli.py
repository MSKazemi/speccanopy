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
from .claude import ClaudeMessagesClient
from .decomposer import generate_architecture
from .doc_gate import evaluate_documentation_gate, export_documentation_gate
from .documentation import export_documentation
from .exporters import check_new_output_dir, export_generation
from .fixtures import FixtureDesign
from .models import ArchitectureSpec, SystemBrief
from .review import ArchitectureReview, ReviewConfig, assess_architecture
from .review_exporters import export_review
from .benchmark import ReferenceRubric, evaluate_reference, compare_reference
from .refinement import RefinementEdits, RefinementPlan, plan_refinement, apply_refinement
from .refinement_exporters import (
    export_refinement_plan, export_refinement_approved, export_benchmark,
)
from .research import ResearchCase, ResearchSuite, evaluate_case, summarize_suite
from .research_exporters import export_research
from .source_diff import compare_inventories, export_inventory_diff
from .structure_diff import (
    compare_module_observations, export_structure_diff, load_module_observations,
)
from .source_impact import assess_claim_impact, export_claim_impact
from .source_evidence import (
    SourceEvidence, SourceInventory, assess_sources, scan_sources, save_inventory,
)
from .project_intake import prepare_project_intake, export_project_intake


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

    document = sub.add_parser("document", help="Render a reviewable Markdown architecture documentation pack")
    document.add_argument("architecture", type=Path, help="Existing ArchitectureSpec JSON")
    document.add_argument("--review", type=Path, help="Optional matching architecture-review.json")
    document.add_argument("--output", type=Path, required=True, help="New or empty docs directory")
    document.add_argument("--strict", action="store_true", help="Exit 2 when architecture or review remains unvalidated")
    document.add_argument("--source-root", type=Path, help="Authorized local application root for snapshot verification")
    document.add_argument("--source-evidence", type=Path, help="JSON mapping of authored architecture claims to source hashes")
    document.add_argument("--max-source-bytes", type=int, default=1000000)

    intake = sub.add_parser(
        "project-intake",
        help="Draft module architecture inputs from bounded offline static analysis "
             "(Python AST, or JavaScript/TypeScript lexical scan)",
    )
    intake.add_argument("project", type=Path, help="Authorized local application root")
    intake.add_argument(
        "--language", choices=("python", "javascript"), default="python",
        help="Source language to analyze: python (.py, AST; default) or javascript "
             "(.js .jsx .mjs .cjs .ts .tsx, lexical scan; nothing is executed)",
    )
    intake.add_argument("--system", required=True, help="Human-supplied system name")
    intake.add_argument("--goal", required=True, help="Human-supplied project goal")
    intake.add_argument(
        "--requirement", required=True, action="append",
        help="Human-supplied functional requirement; repeat as needed",
    )
    intake.add_argument("--output", type=Path, required=True, help="New or empty output directory")
    intake.add_argument(
        "--exclude", action="append", default=None, metavar="PATH",
        help="Project-relative directory or file to leave out (e.g. test fixtures); repeatable",
    )
    intake.add_argument("--max-modules", type=int, default=30)
    intake.add_argument("--max-files", type=int, default=2000)
    intake.add_argument("--max-file-bytes", type=int, default=1000000)

    sources = sub.add_parser("source-inventory", help="Inventory allowlisted local files without exporting contents")
    sources.add_argument("project", type=Path, help="Authorized application directory")
    sources.add_argument("--output", type=Path, required=True, help="New JSON metadata file")
    sources.add_argument("--max-files", type=int, default=2000)
    sources.add_argument("--max-file-bytes", type=int, default=1000000)
    sources.add_argument(
        "--record-git-revision", action="store_true",
        help="Also record the commit/branch read from <project>/.git files (no git is run; "
             "working-tree cleanliness is not recorded)",
    )

    source_diff = sub.add_parser(
        "source-diff", help="Compare two source inventories: added, removed, changed, unchanged files"
    )
    source_diff.add_argument("before", type=Path, help="Earlier source-inventory.json")
    source_diff.add_argument("after", type=Path, help="Later source-inventory.json")
    source_diff.add_argument("--output", type=Path, required=True, help="New or empty output directory")
    source_diff.add_argument(
        "--strict", action="store_true",
        help="Exit 2 when files differ, coverage is not comparable or oversized files were skipped",
    )

    structure_diff = sub.add_parser(
        "structure-diff",
        help="Compare two project-intake outputs by static module/import structure (not bytes)",
    )
    structure_diff.add_argument("before", type=Path,
                                help="Earlier project-intake directory or module-observations.json")
    structure_diff.add_argument("after", type=Path,
                                help="Later project-intake directory or module-observations.json")
    structure_diff.add_argument("--output", type=Path, required=True, help="New or empty output directory")
    structure_diff.add_argument(
        "--strict", action="store_true",
        help="Exit 2 when the static module/import structure changed",
    )

    source_impact = sub.add_parser(
        "source-impact", help="Map source inventory changes onto authored source-evidence claims"
    )
    source_impact.add_argument("before", type=Path, help="Earlier source-inventory.json")
    source_impact.add_argument("after", type=Path, help="Later source-inventory.json")
    source_impact.add_argument("--evidence", type=Path, required=True,
                               help="Authored source-evidence.json claims to check")
    source_impact.add_argument("--architecture", type=Path,
                               help="Optional ArchitectureSpec JSON: check IDs and mandatory requirements")
    source_impact.add_argument("--output", type=Path, required=True, help="New or empty output directory")
    source_impact.add_argument("--strict", action="store_true",
                               help="Exit 2 when any claim or file change requires review")

    doc_gate = sub.add_parser(
        "doc-gate", help="Check a documentation pack's inputs for gaps that need human decisions"
    )
    doc_gate.add_argument("architecture", type=Path, help="Existing ArchitectureSpec JSON")
    doc_gate.add_argument("--review", type=Path, help="Optional matching architecture-review.json")
    doc_gate.add_argument("--source-root", type=Path, help="Authorized local application root")
    doc_gate.add_argument("--source-evidence", type=Path, help="Authored source-evidence.json claims")
    doc_gate.add_argument("--max-source-bytes", type=int, default=1000000)
    doc_gate.add_argument("--output", type=Path, required=True, help="New or empty output directory")
    doc_gate.add_argument("--strict", action="store_true",
                          help="Exit 2 when the gate outcome is requires_review")

    propose_ai = sub.add_parser("propose-ai", help="Draft a component hierarchy using structured AI model proposals")
    propose_ai.add_argument("brief", type=Path)
    propose_ai.add_argument("--output", type=Path, required=True)
    propose_ai.add_argument("--backend", choices=["openai", "claude", "scripted"], default="openai")
    propose_ai.add_argument("--model", help="Explicit model ID for live OpenAI Responses or Claude Messages API")
    propose_ai.add_argument("--responses", type=Path, help="Scripted offline responses (not AI inference)")
    propose_ai.add_argument("--max-model-calls", type=int, default=40)

    approve_ai = sub.add_parser("approve-ai", help="Record explicit human review and release proposed hierarchy as a fixture")
    approve_ai.add_argument("bundle", type=Path, help="ai-proposals.json produced by propose-ai")
    approve_ai.add_argument("--reviewer", required=True, help="Identifier of human reviewing proposals")
    approve_ai.add_argument("--acknowledge-review", action="store_true", help="Confirm the human reviewed candidate components")
    approve_ai.add_argument("--output", type=Path, required=True, help="Output *.design.json fixture path")

    refinement_plan = sub.add_parser("refine-plan", help="Preview bounded, finding-specific human-authored changes")
    refinement_plan.add_argument("architecture", type=Path)
    refinement_plan.add_argument("--config", type=Path, required=True)
    refinement_plan.add_argument("--edits", type=Path, required=True)
    refinement_plan.add_argument("--output", type=Path, required=True)

    refinement_apply = sub.add_parser("refine-apply", help="Release a reviewed revision (never certify architecture)")
    refinement_apply.add_argument("architecture", type=Path)
    refinement_apply.add_argument("--config", type=Path, required=True)
    refinement_apply.add_argument("--plan", type=Path, required=True)
    refinement_apply.add_argument("--reviewer", required=True)
    refinement_apply.add_argument("--acknowledge-review", action="store_true")
    refinement_apply.add_argument("--output", type=Path, required=True)

    benchmark = sub.add_parser("benchmark", help="Evaluate a draft against a curated, explicit reference rubric")
    benchmark.add_argument("architecture", type=Path)
    benchmark.add_argument("--config", type=Path, required=True)
    benchmark.add_argument("--rubric", type=Path, required=True)
    benchmark.add_argument("--candidate", type=Path, help="Compare a refined candidate against the source draft")
    benchmark.add_argument("--output", type=Path, required=True)

    research_case = sub.add_parser("research-case", help="Score a draft against multiple documented architecture alternatives (not expert certification)")
    research_case.add_argument("case", type=Path, help="ResearchCase JSON with provenance and acceptable alternatives")
    research_case.add_argument("--architecture", type=Path, required=True)
    research_case.add_argument("--output", type=Path, required=True)
    research_case.add_argument("--strict", action="store_true", help="Exit 2 unless all required case criteria match")

    research_suite = sub.add_parser("research-suite", help="Run a public provenance-aware architecture research fixture suite")
    research_suite.add_argument("suite", type=Path)
    research_suite.add_argument("--output", type=Path, required=True)
    research_suite.add_argument("--strict", action="store_true", help="Exit 2 if any case has structural rubric gaps")

    args = parser.parse_args(argv)
    if args.command == "research-case":
        try:
            case = ResearchCase.model_validate_json(args.case.read_text(encoding="utf-8"))
            spec = ArchitectureSpec.model_validate_json(args.architecture.read_text(encoding="utf-8"))
            result = evaluate_case(case, spec)
            paths = export_research(result, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error evaluating research case: {exc}", file=sys.stderr)
            return 1
        print(f"Research {result.case_id}: {result.result}, best alternative={result.best_path}")
        print("Signals only; NOT independent expert certification or implementation readiness")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and result.result != "criteria_present_review_required" else 0

    if args.command == "research-suite":
        try:
            suite = ResearchSuite.model_validate_json(args.suite.read_text(encoding="utf-8"))
            reports = {}
            for item in suite.entries:
                # Paths are relative to the user-selected suite file, not external network data.
                case_path = args.suite.parent / item.case_path
                architecture_path = args.suite.parent / item.architecture_path
                case = ResearchCase.model_validate_json(case_path.read_text(encoding="utf-8"))
                spec = ArchitectureSpec.model_validate_json(architecture_path.read_text(encoding="utf-8"))
                reports[item.id] = evaluate_case(case, spec)
            result = summarize_suite(suite.name, reports)
            paths = export_research(result, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error evaluating research suite: {exc}", file=sys.stderr)
            return 1
        print(f"Research suite {result.suite_name}: evaluated {result.total} curated candidate entries")
        print("Public fixtures are NOT independent holdout data or authenticated expert review")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and any(
            r.result != "criteria_present_review_required" for r in result.cases.values()
        ) else 0

    if args.command == "refine-plan":
        try:
            spec = ArchitectureSpec.model_validate_json(args.architecture.read_text(encoding="utf-8"))
            config = ReviewConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
            edits = RefinementEdits.model_validate_json(args.edits.read_text(encoding="utf-8"))
            plan, candidate = plan_refinement(spec, config, edits)
            paths = export_refinement_plan(
                plan, candidate, assess_architecture(spec, config),
                assess_architecture(candidate, config), args.output,
            )
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error preparing refinement plan: {exc}", file=sys.stderr)
            return 1
        print(f"Refinement preview: {len(plan.rounds)} rounds, {len(plan.edits.patches)} actions")
        print("No changes released. Inspect preview and acknowledge the plan separately.")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 0

    if args.command == "refine-apply":
        try:
            spec = ArchitectureSpec.model_validate_json(args.architecture.read_text(encoding="utf-8"))
            config = ReviewConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
            plan = RefinementPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
            candidate, receipt = apply_refinement(
                spec, config, plan, reviewer=args.reviewer,
                acknowledge_review=args.acknowledge_review,
            )
            paths = export_refinement_approved(
                candidate, receipt, assess_architecture(candidate, config), args.output,
            )
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error applying architecture refinement: {exc}", file=sys.stderr)
            return 1
        print("Refined architecture released for FURTHER architecture review; status remains incomplete")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 0

    if args.command == "benchmark":
        try:
            spec = ArchitectureSpec.model_validate_json(args.architecture.read_text(encoding="utf-8"))
            config = ReviewConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
            rubric = ReferenceRubric.model_validate_json(args.rubric.read_text(encoding="utf-8"))
            if args.candidate:
                candidate = ArchitectureSpec.model_validate_json(args.candidate.read_text(encoding="utf-8"))
                result = compare_reference(spec, candidate, config, rubric)
            else:
                result = evaluate_reference(spec, config, rubric)
            paths = export_benchmark(result, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error evaluating architecture reference rubric: {exc}", file=sys.stderr)
            return 1
        report = result.after if args.candidate else result
        print(f"Reference criterion coverage: {report.score:.2f}% ({report.satisfied}/{report.total})")
        print("This measures authored structural checks only, not correctness or expert signoff.")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 0

    if args.command == "propose-ai":
        try:
            # Refuse an unusable output folder BEFORE any (possibly billed) model call.
            check_new_output_dir(args.output, "Architecture")
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
                    raise ValueError("--model is required for live model proposals")
                client = ClaudeMessagesClient(args.model) if args.backend == "claude" else OpenAIResponsesClient(args.model)
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

    if args.command == "project-intake":
        try:
            prepared = prepare_project_intake(
                args.project, system=args.system, goal=args.goal,
                requirements=args.requirement, max_modules=args.max_modules,
                max_files=args.max_files, max_file_bytes=args.max_file_bytes,
                language=args.language, exclude=args.exclude,
            )
            paths = export_project_intake(prepared, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error preparing project intake: {exc}", file=sys.stderr)
            return 1
        label = "JavaScript/TypeScript" if args.language == "javascript" else "Python"
        kind = "lexical" if args.language == "javascript" else "static"
        print(
            f"{label} source intake: {len(prepared.observations.modules)} modules, "
            f"{len(prepared.observations.dependencies)} {kind} import edges"
        )
        print("PROVISIONAL: owner must check module boundaries and map requirements; no code executed")
        print(f"Artifacts: {', '.join(str(path) for path in paths.values())}")
        return 0

    if args.command == "source-inventory":
        try:
            inventory = scan_sources(args.project, max_files=args.max_files,
                                     max_bytes=args.max_file_bytes,
                                     record_revision=args.record_git_revision)
            path = save_inventory(inventory, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error inventorying sources: {exc}", file=sys.stderr)
            return 1
        print(f"Source inventory: {len(inventory.files)} metadata-only file records; "
              f"{inventory.skipped_oversized} oversized excluded")
        if inventory.revision is not None:
            rev = inventory.revision
            if rev.status == "recorded":
                where = rev.ref or "detached HEAD"
                print(f"Git revision: {rev.commit[:12]} ({where}); working-tree state is not recorded")
            else:
                print(f"Git revision: unknown ({rev.reason}); working-tree state is not recorded")
        print(f"Artifact: {path}")
        print("Hashes are not semantic architecture verification; keep paths private if sensitive")
        return 0

    if args.command == "source-diff":
        try:
            before = SourceInventory.model_validate_json(args.before.read_text(encoding="utf-8"))
            after = SourceInventory.model_validate_json(args.after.read_text(encoding="utf-8"))
            diff = compare_inventories(before, after)
            paths = export_inventory_diff(diff, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error comparing source inventories: {exc}", file=sys.stderr)
            return 1
        print(f"Source diff: {len(diff.added)} added, {len(diff.removed)} removed, "
              f"{len(diff.changed)} changed, {len(diff.unchanged)} unchanged")
        print(f"Coverage: {diff.coverage}; requires review: {'yes' if diff.requires_review else 'no'}")
        print("Byte-level metadata comparison only; not semantic or architectural verification")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and diff.requires_review else 0

    if args.command == "structure-diff":
        try:
            before = load_module_observations(args.before)
            after = load_module_observations(args.after)
            check_new_output_dir(args.output, "Structure diff")
            sdiff = compare_module_observations(before, after)
            paths = export_structure_diff(sdiff, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error comparing project structure: {exc}", file=sys.stderr)
            return 1
        print(f"Structure diff: modules {len(sdiff.added_modules)} added, "
              f"{len(sdiff.removed_modules)} removed, {len(sdiff.kept_modules)} kept; "
              f"import edges {len(sdiff.edges_added)} added, {len(sdiff.edges_removed)} removed, "
              f"{len(sdiff.edges_kept)} kept")
        print(f"Structure changed: {'yes' if sdiff.structure_changed else 'no'}")
        print("Static syntax only; renames not inferred; not behavioural or architectural verification")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and sdiff.structure_changed else 0

    if args.command == "source-impact":
        try:
            before = SourceInventory.model_validate_json(args.before.read_text(encoding="utf-8"))
            after = SourceInventory.model_validate_json(args.after.read_text(encoding="utf-8"))
            claims = SourceEvidence.model_validate_json(args.evidence.read_text(encoding="utf-8"))
            spec = (ArchitectureSpec.model_validate_json(args.architecture.read_text(encoding="utf-8"))
                    if args.architecture else None)
            check_new_output_dir(args.output, "Claim impact")
            impact = assess_claim_impact(compare_inventories(before, after), claims, spec)
            paths = export_claim_impact(impact, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error assessing source claim impact: {exc}", file=sys.stderr)
            return 1
        counts = ", ".join(f"{n} {status}" for status, n in impact.status_counts.items() if n)
        print(f"Claim impact: {len(impact.entries)} claims ({counts or 'none'})")
        print(f"Possibly affected architecture IDs: {len(impact.affected_architecture_ids)}; "
              f"uncited added files: {len(impact.uncited_added_paths)}")
        print(f"Requires review: {'yes' if impact.requires_review else 'no'}")
        print("Byte digests only; no claim verified and no documentation edited")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and impact.requires_review else 0

    if args.command == "doc-gate":
        try:
            spec = ArchitectureSpec.model_validate_json(args.architecture.read_text(encoding="utf-8"))
            review = (ArchitectureReview.model_validate_json(args.review.read_text(encoding="utf-8"))
                      if args.review else None)
            if (args.source_root is None) != (args.source_evidence is None):
                raise ValueError("--source-root and --source-evidence must be provided together")
            check_new_output_dir(args.output, "Documentation gate")
            sources_report = None
            if args.source_evidence is not None:
                claims = SourceEvidence.model_validate_json(
                    args.source_evidence.read_text(encoding="utf-8")
                )
                sources_report = assess_sources(
                    spec, claims, args.source_root, max_bytes=args.max_source_bytes
                )
            gate = evaluate_documentation_gate(spec, review=review, sources=sources_report)
            paths = export_documentation_gate(gate, args.output)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error evaluating documentation gate: {exc}", file=sys.stderr)
            return 1
        print(f"Documentation gate: {spec.brief.system}")
        print(f"Outcome: {gate.outcome} ({gate.blocking_count} blocking, "
              f"{gate.attention_count} attention)")
        print("Deterministic completeness check of authored data; not expert review or "
              "certification. A human must sign off.")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and gate.outcome == "requires_review" else 0

    if args.command == "document":
        try:
            spec = ArchitectureSpec.model_validate_json(args.architecture.read_text(encoding="utf-8"))
            review = (ArchitectureReview.model_validate_json(args.review.read_text(encoding="utf-8"))
                      if args.review else None)
            if (args.source_root is None) != (args.source_evidence is None):
                raise ValueError("--source-root and --source-evidence must be provided together")
            sources_report = None
            if args.source_evidence is not None:
                claims = SourceEvidence.model_validate_json(
                    args.source_evidence.read_text(encoding="utf-8")
                )
                sources_report = assess_sources(
                    spec, claims, args.source_root, max_bytes=args.max_source_bytes
                )
            paths = export_documentation(spec, args.output, review=review,
                                         sources=sources_report)
        except (OSError, ValidationError, ValueError) as exc:
            print(f"Error documenting architecture: {exc}", file=sys.stderr)
            return 1
        print(f"Documentation: {spec.brief.system}")
        print(f"Source architecture status: {spec.status} — no independent approval inferred")
        if sources_report is not None:
            matched = sum(x.status == "matching_snapshot" for x in sources_report.checks)
            print(f"Source citations: {matched}/{len(sources_report.checks)} byte snapshots match; "
                  "not proof of architectural correctness")
        print(f"Artifacts: {', '.join(str(p) for p in paths.values())}")
        return 2 if args.strict and (
            spec.status != "validated_for_scope" or
            (review is not None and review.overall_status == "requires_review") or
            (sources_report is not None and sources_report.requires_review)
        ) else 0

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
