"""Apply the owner-delegated grouping to an intake design.json (owner pilot)."""
import json, sys
src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src))
GROUPS = {
    "grp_core": ("Core schema and export", ["speccanopy", "speccanopy.models", "speccanopy.exporters"], []),
    "grp_generation": ("Architecture generation", ["speccanopy.decomposer", "speccanopy.fixtures", "speccanopy.proposer",
                        "speccanopy.ai", "speccanopy.ai_exporters", "speccanopy.claude"], ["FR-USER-001"]),
    "grp_review": ("Review, refinement and research", ["speccanopy.review", "speccanopy.review_exporters", "speccanopy.scoring",
                    "speccanopy.benchmark", "speccanopy.refinement", "speccanopy.refinement_exporters",
                    "speccanopy.research", "speccanopy.research_exporters", "speccanopy.expert_review"], ["FR-USER-002"]),
    "grp_documentation": ("Documentation rendering and gate", ["speccanopy.documentation", "speccanopy.doc_gate"], ["FR-USER-003"]),
    "grp_source": ("Source evidence and project intake", ["speccanopy.source_evidence", "speccanopy.source_diff",
                    "speccanopy.source_impact", "speccanopy.structure_diff", "speccanopy.project_intake",
                    "speccanopy.js_intake"], ["FR-USER-004"]),
    "grp_cli": ("Command-line entry point", ["speccanopy.cli"], []),
}
TESTS = {"FR-USER-001": ("grp_generation", "tests/test_decomposer.py, tests/test_proposer.py"),
         "FR-USER-002": ("grp_review", "tests/test_review.py, tests/test_review_robustness.py"),
         "FR-USER-003": ("grp_documentation", "tests/test_documentation.py, tests/test_documentation_views.py, tests/test_doc_gate.py"),
         "FR-USER-004": ("grp_source", "tests/test_project_intake.py, tests/test_js_intake.py, tests/test_source_evidence.py")}
mods = {p["name"].removeprefix("Python module "): p for p in d["proposals_by_parent"]["system"]}
placed = [m for _, ms, _ in GROUPS.values() for m in ms]
assert sorted(placed) == sorted(mods), (set(mods) ^ set(placed))
proposals = {"system": []}
for gid, (name, members, reqs) in GROUPS.items():
    proposals["system"].append({
        "id": gid, "name": name,
        "responsibility": f"Groups {len(members)} module(s): " + ", ".join(members) + ".",
        "boundary": "Logical grouping of Python modules; not a deployment or runtime boundary.",
        "requirement_ids": reqs,
        "rationale": "Assistant-proposed from import fan-in and module names; owner delegated the grouping decision (2026-11-06), not individually confirmed.",
        "assumptions": ["Grouping is assistant-proposed and owner-delegated, not owner-confirmed."],
        "risks": [], "interfaces": [], "owned_data": [], "quality_targets": {}, "validation_evidence": [],
    })
    proposals[gid] = [mods[m] for m in members]
d["proposals_by_parent"] = proposals
d["verification_cases"] = d.get("verification_cases", []) + [{
    "id": f"VC-{rid}", "requirement_ids": [rid], "component_ids": [gid], "method": "test_plan",
    "description": f"Behaviour for {rid} is exercised by {tests}.",
    "status": "verified",
    "evidence": f"{tests} passed in GitHub Actions run 42156490953 on main 0e0cf40 (Python 3.11 and 3.13). Tests show implemented behaviour, not architecture quality.",
} for rid, (gid, tests) in TESTS.items()]
json.dump(d, open(dst, "w"), indent=2)
print("groups", len(GROUPS), "modules", len(placed))
