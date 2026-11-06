"""Focused documentation views: data flow, trust boundaries, deployment, runtime.

Every view must be derived only from ArchitectureSpec fields, must say so, and
must state MISSING (not "none exist") when the schema data for it is absent.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.documentation import render_documentation
from speccanopy.models import ArchitectureSpec, InterfaceContract, Relationship
from speccanopy.source_evidence import SourceAssessment, SourceCheck

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
STEMS = ["cli-utility", "ecommerce", "file-transfer"]
DATA = "view-data-flow.md"
TRUST = "view-trust-boundaries.md"
DEPLOY = "view-deployment.md"
RUNTIME = "view-runtime.md"
VIEWS = [DATA, TRUST, DEPLOY, RUNTIME]

MISSING_TRUST = ("No trust boundaries are recorded in the architecture; "
                 "this view is MISSING, not 'none exist'.")
MISSING_DEPLOY = ("No deployment relationships are recorded in the architecture; "
                  "this view is MISSING, not 'none exist'.")


def load(stem: str) -> ArchitectureSpec:
    return ArchitectureSpec.model_validate_json(
        (EXAMPLES / "generated" / stem / "architecture.json").read_text())


def rel(spec: ArchitectureSpec, rid: str, kind: str, src: str, dst: str,
        description: str = "authored edge") -> None:
    spec.relationships.append(Relationship(
        id=rid, source_id=src, target_id=dst, kind=kind, description=description))


def with_kinds(spec: ArchitectureSpec, keep: set[str]) -> ArchitectureSpec:
    spec.relationships = [r for r in spec.relationships if r.kind in keep]
    return spec


def mermaid_blocks(text: str) -> list[str]:
    return re.findall(r"```mermaid\n(.*?)\n```", text, flags=re.S)


# ---------------------------------------------------------------- every view


@pytest.mark.parametrize("stem", STEMS)
def test_every_view_exists_states_source_and_authored_nature(stem):
    pages = render_documentation(load(stem))
    for name in VIEWS:
        text = pages[name]
        assert "## Source of this view" in text, name
        assert "authored design data" in text, name
        assert "not observed runtime behaviour" in text, name
        assert "ArchitectureSpec" in text, name
        assert "--source-evidence" in text, name  # says no source annotation was supplied
    readme = pages["README.md"]
    for name in VIEWS:
        assert f"]({name})" in readme


@pytest.mark.parametrize("stem", STEMS)
def test_cli_writes_the_view_pages_without_host_paths(stem, tmp_path):
    out = tmp_path / stem
    assert main(["document", str(EXAMPLES / "generated" / stem / "architecture.json"),
                 "--output", str(out)]) == 0
    for name in VIEWS:
        text = (out / name).read_text()
        assert str(tmp_path) not in text and "/home/" not in text


# ----------------------------------------------------------------- data flow


def test_data_flow_diagram_has_only_data_flow_and_shared_resource_edges():
    spec = load("file-transfer")
    rel(spec, "REL-SR", "shared_resource", "intake", "planner", "shared cache")
    text = render_documentation(spec)[DATA]
    (diagram,) = mermaid_blocks(text)
    edges = [ln for ln in diagram.splitlines() if "-->" in ln or "---" in ln or "-.-" in ln]
    assert len(edges) == 3  # REL-FT-01, REL-FT-04 (data_flow) and REL-SR
    assert "REL-FT-02" not in diagram and "dependency" not in diagram
    assert "event" not in diagram and "trust" not in diagram
    for rid in ("REL-FT-01", "REL-FT-04", "REL-SR"):
        assert rid in text


def test_data_flow_missing_edges_are_explicit_for_ecommerce():
    text = render_documentation(load("ecommerce"))[DATA]
    assert "No data_flow or shared_resource relationships are recorded" in text
    assert "MISSING, not 'none exist'" in text
    assert mermaid_blocks(text) == []


def test_data_owner_table_lists_owners_from_owned_data():
    spec = load("cli-utility")
    text = render_documentation(spec)[DATA]
    for comp in spec.components:
        for item in comp.owned_data:
            assert item.replace("_", "\\_") in text or item in text
            assert comp.id.replace("_", "\\_") in text or comp.id in text


def test_data_owner_table_flags_multiple_sibling_owners_and_not_recorded():
    spec = load("cli-utility")
    a, b, c, d = spec.components[:4]
    for comp in (a, b, c, d):
        comp.status = "proposed"  # only non-ready components may omit ownership
        comp.owned_data = []
        comp.data_not_applicable_reason = None
    b.parent_id = c.parent_id = a.parent_id = None
    d.parent_id = a.id
    b.owned_data = ["shared ledger"]
    c.owned_data = ["shared ledger", "mixed data"]
    d.owned_data = ["mixed data"]
    a.data_not_applicable_reason = "pure orchestration"
    text = render_documentation(spec)[DATA]
    ledger = next(ln for ln in text.splitlines() if ln.startswith("| shared ledger"))
    assert "MULTIPLE OWNERS (siblings under root)" in ledger
    mixed = next(ln for ln in text.splitlines() if ln.startswith("| mixed data"))
    assert "MULTIPLE OWNERS (different parents)" in mixed
    gaps = text.split("## Components without recorded data ownership")[1]
    assert "Not applicable: pure orchestration" in gaps
    assert "Not recorded" not in gaps
    spec.components[0].data_not_applicable_reason = None
    gaps = render_documentation(spec)[DATA].split(
        "## Components without recorded data ownership")[1]
    assert "Not recorded" in gaps and "pure orchestration" not in gaps


def test_data_flow_view_does_not_invent_payloads():
    text = render_documentation(load("cli-utility"))[DATA]
    assert "does not record which data item travels" in text


# ------------------------------------------------------------ trust boundary


def test_trust_boundary_lists_edges_and_both_sides_for_ecommerce():
    spec = load("ecommerce")
    text = render_documentation(spec)[TRUST]
    assert "REL-EC-04" in text
    assert "payments" in text and "identity" in text
    assert MISSING_TRUST not in text
    (diagram,) = mermaid_blocks(text)
    assert diagram.count("-.->") == 1


def test_trust_boundary_lists_descendants_by_parent_id_on_each_side():
    spec = load("ecommerce")
    children = {c.id for c in spec.components if c.parent_id == "payments"}
    assert children, "fixture assumption: payments has children"
    text = render_documentation(spec)[TRUST]
    row = next(ln for ln in text.splitlines()
               if ln.startswith("| REL-EC-04") and "payment\\_gateway" in ln)
    for cid in children:
        assert cid.replace("_", "\\_") in row


@pytest.mark.parametrize("stem", ["cli-utility"])
def test_trust_boundary_missing_statement(stem):
    text = render_documentation(load(stem))[TRUST]
    assert MISSING_TRUST in text
    assert mermaid_blocks(text) == []


def test_trust_boundary_reports_other_interactions_between_the_sides():
    spec = load("ecommerce")
    rel(spec, "REL-X", "synchronous_call", "payments", "identity", "token check")
    text = render_documentation(spec)[TRUST]
    assert "REL-X" in text


# ---------------------------------------------------------------- deployment


@pytest.mark.parametrize("stem", STEMS)
def test_shipped_examples_have_no_deployment_data_so_view_says_missing(stem):
    text = render_documentation(load(stem))[DEPLOY]
    assert MISSING_DEPLOY in text
    assert mermaid_blocks(text) == []


def test_deployment_view_renders_deployment_edges_only():
    spec = load("ecommerce")
    rel(spec, "REL-DEP", "deployment", "payments", "identity", "runs beside")
    text = render_documentation(spec)[DEPLOY]
    assert MISSING_DEPLOY not in text
    (diagram,) = mermaid_blocks(text)
    assert diagram.count("-->") == 1
    assert "REL-DEP" in text and "REL-EC-02" not in text
    assert "environments, hosts, regions" in text  # stated limit of the schema


# ------------------------------------------------------------------- runtime


def test_runtime_view_lists_sync_and_event_edges_with_interfaces_and_gaps():
    spec = load("ecommerce")
    text = render_documentation(spec)[RUNTIME]
    for rid in ("REL-EC-02", "REL-EC-03", "REL-EC-06"):
        assert rid in text
    assert "REL-EC-01" not in text and "REL-EC-04" not in text  # other kinds
    assert "payments\\_contract" in text  # target interface contract shown
    assert "source has no outbound non-event interface recorded" in text
    assert "target has no inbound event-kind interface recorded" in text
    assert "NO MATCHING INTERFACE" in text


def test_runtime_view_states_sequences_are_not_modelled():
    text = render_documentation(load("ecommerce"))[RUNTIME]
    assert "Sequences are not modelled" in text
    assert "no ordering" in text.lower()
    assert "sequenceDiagram" not in text


def test_runtime_view_marks_matching_when_both_ends_have_contracts():
    spec = load("ecommerce")
    orders = next(c for c in spec.components if c.id == "orders")
    orders.interfaces.append(InterfaceContract(
        name="charge_request", direction="outbound", kind="api", description="x"))
    text = render_documentation(spec)[RUNTIME]
    row = next(ln for ln in text.splitlines() if "REL-EC-02" in ln and ln.startswith("|"))
    assert "Interface contracts recorded on both ends" in row
    assert "charge\\_request" in row
    assert "NO MATCHING INTERFACE" not in row


def test_runtime_view_missing_when_no_sync_or_event_edges():
    spec = with_kinds(load("cli-utility"), {"data_flow"})
    text = render_documentation(spec)[RUNTIME]
    assert "No synchronous_call or event relationships are recorded" in text
    assert "MISSING, not 'none exist'" in text
    assert mermaid_blocks(text) == []


# ------------------------------------------------------ hostile authored text

HOSTILE = 'x"] --> Z["pwn | `tick` [a](b) #35; %% {c}\n\n# heading <b>'


def hostile_spec() -> ArchitectureSpec:
    spec = load("ecommerce")
    for rid_kind in ("data_flow", "shared_resource", "deployment"):
        rel(spec, "REL-H-" + rid_kind, rid_kind, "payments", "identity", HOSTILE)
    rel(spec, "REL-H-EVT", "event", "orders", "payments", HOSTILE)
    for comp in spec.components:
        comp.name = HOSTILE + comp.id
        comp.owned_data = [HOSTILE]
        comp.data_not_applicable_reason = None
        comp.interfaces.append(InterfaceContract(
            name=HOSTILE, direction="outbound", kind="event", description=HOSTILE))
    spec.relationships[3].description = HOSTILE
    return spec


NODE = re.compile(r'^    N\d+\["[^"\\]*"\]$')
EDGE = re.compile(r'^    N\d+ (-->|---|-\.->|-\.-)\|"[^"\\]*"\| N\d+$')


@pytest.mark.parametrize("name", VIEWS)
def test_hostile_text_cannot_break_mermaid_blocks(name):
    text = render_documentation(hostile_spec())[name]
    blocks = mermaid_blocks(text)
    for block in blocks:
        lines = block.splitlines()
        assert lines[0].startswith("flowchart ")
        for ln in lines[1:]:
            assert NODE.match(ln) or EDGE.match(ln), ln
    # the hostile payload never appears raw outside escaped form
    assert 'x"] --> Z["pwn' not in text


@pytest.mark.parametrize("name", VIEWS)
def test_hostile_text_cannot_break_markdown_tables_or_headings(name):
    text = render_documentation(hostile_spec())[name]
    assert "\n# heading" not in text and "\n## heading" not in text
    assert "<b>" not in text
    in_block = False
    tables: list[list[int]] = []
    previous_was_row = False
    for ln in text.splitlines():
        if ln.startswith("```"):
            in_block = not in_block
            previous_was_row = False
            continue
        if in_block:
            continue
        if ln.startswith("|"):
            if not previous_was_row:
                tables.append([])
            tables[-1].append(len(re.split(r"(?<!\\)\|", ln)))
            previous_was_row = True
        else:
            previous_was_row = False
    for counts in tables:
        assert len(set(counts)) == 1, counts  # no row grew or lost a cell


# --------------------------------------------------------------- determinism


@pytest.mark.parametrize("stem", STEMS)
def test_views_are_deterministic(stem):
    a = render_documentation(load(stem))
    b = render_documentation(load(stem))
    for name in VIEWS:
        assert a[name] == b[name]


def test_views_do_not_depend_on_relationship_authoring_order():
    spec = load("ecommerce")
    rel(spec, "REL-DEP", "deployment", "payments", "identity")
    base = render_documentation(spec)
    shuffled = spec.model_copy(deep=True)
    random.Random(7).shuffle(shuffled.relationships)
    again = render_documentation(shuffled)
    for name in VIEWS:
        assert base[name] == again[name]


# ------------------------------------------------------- source annotation


def check(aid: str, basis: str = "observed", status: str = "matching_snapshot",
          path: str = "src/app/mod.py") -> SourceCheck:
    return SourceCheck(
        architecture_id=aid, source_path=path, assertion="authored claim", basis=basis,
        line_start=None, line_end=None, expected_sha256="a" * 64,
        actual_sha256="a" * 64 if status == "matching_snapshot" else None, status=status)


def test_source_annotation_distinguishes_matching_other_and_none():
    spec = load("ecommerce")
    sources = SourceAssessment(
        checks=[check("payments"), check("orders", "inferred"),
                check("identity", "observed", "changed"),
                check("REL-EC-02"), check("REL-EC-04", "proposed", "missing")],
        unlinked_mandatory_requirements=[], unlinked_components=[])
    pages = render_documentation(spec, sources=sources)
    runtime, trust = pages[RUNTIME], pages[TRUST]
    row02 = next(ln for ln in runtime.splitlines() if "REL-EC-02" in ln and ln.startswith("|"))
    row03 = next(ln for ln in runtime.splitlines() if "REL-EC-03" in ln and ln.startswith("|"))
    assert "Observed source claim with matching snapshot" in row02
    assert "No source claim" in row03
    row04 = next(ln for ln in trust.splitlines() if "REL-EC-04" in ln and ln.startswith("|"))
    assert "none is a matching observed snapshot" in row04
    assert "proposed/missing" in row04
    assert "Source evidence column" in runtime
    # component-level annotation
    comp_rows = [ln for ln in trust.splitlines() if ln.startswith("| payments")
                 or ln.startswith("| orders") or ln.startswith("| identity")]
    joined = "\n".join(comp_rows)
    assert "Observed source claim with matching snapshot" in joined
    assert "inferred/matching" in joined or "observed/changed" in joined


def test_source_annotation_never_leaks_paths_and_is_absent_without_sources():
    spec = load("ecommerce")
    sources = SourceAssessment(checks=[check("payments", path="secrets/private-name.py")],
                               unlinked_mandatory_requirements=[], unlinked_components=[])
    with_src = render_documentation(spec, sources=sources)
    for name in VIEWS:
        assert "private-name" not in with_src[name]
    without = render_documentation(spec)
    for name in VIEWS:
        assert "Observed source claim" not in without[name]
        assert "Source evidence column" not in without[name]
    assert "No source evidence was supplied" in without[RUNTIME]


def test_cli_source_evidence_flag_adds_annotations(tmp_path):
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    target = project / "src" / "payments.py"
    target.write_text("PAY = 1\n", encoding="utf-8")
    import hashlib
    import json
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    evidence = tmp_path / "ev.json"
    evidence.write_text(json.dumps({"schema_version": 1, "claims": [{
        "architecture_id": "REL-EC-02", "source_path": "src/payments.py",
        "sha256": digest, "assertion": "orders calls payments", "basis": "observed"}]}),
        encoding="utf-8")
    out = tmp_path / "docs"
    assert main(["document", str(EXAMPLES / "generated/ecommerce/architecture.json"),
                 "--source-root", str(project), "--source-evidence", str(evidence),
                 "--output", str(out)]) == 0
    runtime = (out / RUNTIME).read_text()
    row = next(ln for ln in runtime.splitlines() if "REL-EC-02" in ln and ln.startswith("|"))
    assert "Observed source claim with matching snapshot" in row
    assert str(tmp_path) not in runtime
