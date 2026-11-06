"""Human-review packets, provenance and explicit approval receipts for AI drafts."""

from __future__ import annotations

import json
from pathlib import Path

from .ai import AIProposalBundle, ApprovalReceipt
from .decomposer import GenerationResult
from .exporters import check_new_output_file, export_generation
from .fixtures import FixtureDesign


def review_packet(bundle: AIProposalBundle) -> str:
    def safe(s: object) -> str:
        return str(s).replace("\n", " ").replace("|", "\\|").strip()

    lines = [
        f"# AI architecture proposal: {safe(bundle.brief.system)}", "",
        "**Status: pending human review — NOT an approved or validated architecture.**", "",
        f"Provider: {safe(bundle.provider)} / Model: {safe(bundle.model)}  ",
        f"Requests: {bundle.model_calls}  ",
        f"Draft architecture status: {bundle.generation_status}  ",
        f"Proposed components including root: {bundle.component_count}", "",
        "## Human-review checklist", "",
        "- [ ] Every mandatory requirement is addressed or explicitly recorded as missing", 
        "- [ ] Boundaries are coherent, not overlapping, and not unnecessarily complicated",
        "- [ ] Assumptions and risks are reviewed with domain expertise",
        "- [ ] Interfaces, data ownership, security, and quality targets are designed separately",
        "- [ ] Planned verification evidence is gathered before claiming a validated design", "",
        "## Proposed decomposition", "",
    ]
    for parent, proposals in bundle.fixture.proposals_by_parent.items():
        lines.extend([f"### Under {safe(parent)}", ""])
        for candidate in proposals:
            lines.extend([
                f"**{safe(candidate.id)} — {safe(candidate.name)}**", "",
                f"Responsibility: {safe(candidate.responsibility)}  ",
                f"Boundary: {safe(candidate.boundary)}  ",
                f"Requirement links: {safe(', '.join(candidate.requirement_ids) or 'none')}  ",
                f"Rationale: {safe(candidate.rationale)}", "",
            ])
            if candidate.assumptions:
                lines.append(f"Assumptions: {safe('; '.join(candidate.assumptions))}  ")
            if candidate.risks:
                lines.append(f"Risks: {safe('; '.join(candidate.risks))}  ")
            lines.append("")
    lines.extend(["## Open questions", ""])
    lines.extend(f"- {safe(q)}" for q in bundle.open_questions)
    if not bundle.open_questions:
        lines.append("No model-authored questions; this does not mean there are no uncertainties.")
    lines.extend(["", "## Budget warnings", ""])
    lines.extend(f"- {safe(w)}" for w in bundle.warnings)
    if not bundle.warnings:
        lines.append("No model-call or depth budget warnings.")
    lines.extend([
        "", "## Approval is not certification", "",
        "To release these proposals for further architecture design, use the `approve-ai` command ",
        "with an explicit reviewer identifier and `--acknowledge-review`.",
        "The resulting fixture has no verified architecture review cases or accepted design evidence.",
        "Re-run the deterministic generator and quality review after adding contracts and verification plans.", "",
    ])
    return "\n".join(lines)


def export_ai_draft(result: GenerationResult, bundle: AIProposalBundle, destination: str | Path) -> dict[str, Path]:
    paths = export_generation(
        result, destination, generator="ai-assisted-draft",
        note="Model-proposed hierarchy; untrusted proposals pending human review. Not independently validated.",
    )
    directory = Path(destination)
    documents = {
        "ai-proposals.json": json.loads(bundle.model_dump_json()),
        "ai-provenance.json": {
            "prompt_version": bundle.prompt_version,
            "provider": bundle.provider, "model": bundle.model,
            "brief_sha256": bundle.brief_sha256, "fixture_sha256": bundle.fixture_sha256,
            "model_calls": bundle.model_calls,
            "events": [e.model_dump(mode="json") for e in bundle.events],
            "warnings": bundle.warnings,
            "note": "Prompt/response hashes only; not verified architecture evidence or a credential log.",
        },
        "proposal-review.md": review_packet(bundle),
    }
    for name, obj in documents.items():
        target = directory / name
        if isinstance(obj, str):
            target.write_text(obj, encoding="utf-8")
        else:
            target.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths[name] = target
    return paths


def export_approved(fixture: FixtureDesign, receipt: ApprovalReceipt, target: str | Path) -> dict[str, Path]:
    file = check_new_output_file(target, "Approved fixture")
    approval = check_new_output_file(file.with_suffix(".approval.json"), "Approval receipt")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(fixture.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    approval.write_text(json.dumps(receipt.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"approved_fixture": file, "approval_receipt": approval}
