"""Metamorphic robustness tests for the deterministic review heuristics.

SYNTHETIC SELF-ANALYSIS. These tests transform the three shipped example
architectures in ways that should (or should not) matter and check that
``assess_architecture`` / ``evaluate_documentation_gate`` respond consistently.
They have no ground truth, measure no false-positive/false-negative rate and are
NOT independent expert evaluation. They do not advance Issue #2's human
participation requirements. See ``docs/review-robustness.md``.

Relations
  R1  consistent, bijective ID renaming changes nothing except IDs inside text
  R2  human-readable wording: observations of which heuristics read free text
  R3  list reordering changes nothing (order independence)
  R4  removing verification never reduces findings; a critical open finding never
      improves the overall status
  R5  the documentation gate obeys R1 and R3 as well

Tests marked ``xfail(strict=True)`` document a concrete observed violation of a
relation. Production code is intentionally not changed here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from speccanopy.doc_gate import evaluate_documentation_gate
from speccanopy.models import ArchitectureSpec
from speccanopy.review import ReviewConfig, assess_architecture, compare_styles

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
STEMS = ["cli-utility", "ecommerce", "file-transfer"]
CONFIG_MODES = ["with_config", "no_config"]
SEEDS = [1, 2, 3, 4, 5]

Json = dict[str, Any]


# --------------------------------------------------------------------------- loading


def load_raw(stem: str, with_config: bool) -> tuple[Json, Json | None]:
    spec = json.loads((EXAMPLES / "generated" / stem / "architecture.json").read_text())
    cfg = json.loads((EXAMPLES / f"{stem}.review.json").read_text()) if with_config else None
    return spec, cfg


def build(spec_d: Json, cfg_d: Json | None):
    """Validate transformed data through the real models, then run the review."""
    spec = ArchitectureSpec.model_validate(spec_d)
    config = ReviewConfig.model_validate(cfg_d) if cfg_d is not None else None
    return spec, config, assess_architecture(spec, config)


def run(spec_d: Json, cfg_d: Json | None):
    spec, config, review = build(spec_d, cfg_d)
    return spec, review


def gate_of(spec_d: Json, cfg_d: Json | None, *, with_review: bool = True):
    spec, _config, review = build(spec_d, cfg_d)
    return evaluate_documentation_gate(spec, review=review if with_review else None)


# --------------------------------------------------------------------------- ID renaming


def all_ids(spec_d: Json, cfg_d: Json | None) -> list[str]:
    ids: list[str] = []
    b = spec_d["brief"]
    ids += [r["id"] for r in b["functional_requirements"] + b["quality_requirements"]]
    for key in ("components", "relationships", "verification_cases", "decisions", "findings"):
        ids += [r["id"] for r in spec_d[key]]
    if cfg_d:
        ids += [s["id"] for s in cfg_d["scenarios"]]
    assert len(ids) == len(set(ids)), "fixture IDs must be globally unique for a bijective map"
    return ids


def prefix_map(ids: list[str]) -> dict[str, str]:
    """Order-preserving rename: every sort order over IDs is unchanged."""
    return {i: f"Z_{i}" for i in ids}


def scramble_map(ids: list[str]) -> dict[str, str]:
    """Order-scrambling rename to opaque tokens (changes every sort order over IDs)."""
    mapping = {i: "Q" + hashlib.sha256(i.encode()).hexdigest()[:10] for i in ids}
    assert len(set(mapping.values())) == len(mapping)
    return mapping


MAPS: dict[str, Callable[[list[str]], dict[str, str]]] = {"prefix": prefix_map, "scramble": scramble_map}


def remap_ids(spec_d: Json, cfg_d: Json | None, mapping: dict[str, str]) -> tuple[Json, Json | None]:
    """Apply ``mapping`` to every ID-bearing structured field (not to free text)."""
    m = mapping.__getitem__
    spec = copy.deepcopy(spec_d)
    b = spec["brief"]
    for r in b["functional_requirements"] + b["quality_requirements"]:
        r["id"] = m(r["id"])
    for c in spec["components"]:
        c["id"] = m(c["id"])
        if c["parent_id"] is not None:
            c["parent_id"] = m(c["parent_id"])
        c["requirement_ids"] = [m(x) for x in c["requirement_ids"]]
        c["quality_targets"] = {m(k): v for k, v in c["quality_targets"].items()}
    for r in spec["relationships"]:
        r["id"], r["source_id"], r["target_id"] = m(r["id"]), m(r["source_id"]), m(r["target_id"])
        r["requirement_ids"] = [m(x) for x in r["requirement_ids"]]
    for v in spec["verification_cases"]:
        v["id"] = m(v["id"])
        v["requirement_ids"] = [m(x) for x in v["requirement_ids"]]
        v["component_ids"] = [m(x) for x in v["component_ids"]]
    for d in spec["decisions"]:
        d["id"] = m(d["id"])
        d["requirement_ids"] = [m(x) for x in d["requirement_ids"]]
    for f in spec["findings"]:
        f["id"] = m(f["id"])
        f["requirement_ids"] = [m(x) for x in f["requirement_ids"]]
        f["component_ids"] = [m(x) for x in f["component_ids"]]
    cfg = None
    if cfg_d is not None:
        cfg = copy.deepcopy(cfg_d)
        for s in cfg["scenarios"]:
            s["id"], s["requirement_id"] = m(s["id"]), m(s["requirement_id"])
            s["component_ids"] = [m(x) for x in s["component_ids"]]
            for e in s.get("expected_interactions", []):
                e["source_id"], e["target_id"] = m(e["source_id"]), m(e["target_id"])
    return spec, cfg


def unmap_text(text: str, inverse: dict[str, str]) -> str:
    """Translate renamed IDs back to the originals inside free text."""
    if not inverse:
        return text
    alt = "|".join(re.escape(k) for k in sorted(inverse, key=len, reverse=True))
    pattern = re.compile(rf"(?<![A-Za-z0-9_.:-])({alt})(?![A-Za-z0-9_-]|[.:][A-Za-z0-9])")
    return pattern.sub(lambda mo: inverse[mo.group(1)], text)


def unmap_obj(obj: Any, inverse: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return inverse.get(obj) or unmap_text(obj, inverse)
    if isinstance(obj, list):
        return [unmap_obj(x, inverse) for x in obj]
    if isinstance(obj, dict):
        return {unmap_obj(k, inverse): unmap_obj(v, inverse) for k, v in obj.items()}
    return obj


# --------------------------------------------------------------------------- signatures

_WORDS = re.compile(r"[A-Za-z0-9_.:'-]+")


def bag(text: str) -> tuple[str, ...]:
    """Order-insensitive token bag, to compare texts that embed sorted ID lists."""
    return tuple(sorted(_WORDS.findall(text)))


def review_signature(review, inverse: dict[str, str] | None = None, *, texts: bool = True) -> Json:
    """Order-insensitive, positional-ID-insensitive summary of an ArchitectureReview.

    ``texts=False`` drops description text (used where free text was rewritten).
    """
    inv = inverse or {}
    mp = lambda xs: tuple(sorted(unmap_obj(x, inv) for x in xs))  # noqa: E731
    q = review.quality_review
    fcount = Counter(
        (f.severity, f.category, mp(f.requirement_ids), mp(f.component_ids),
         bag(unmap_text(f.description, inv)) if texts else ())
        for f in q.findings
    )
    scen = {
        unmap_obj(a.scenario_id, inv): (
            a.status, a.verification_status, unmap_obj(a.requirement_id, inv),
            tuple(sorted(bag(unmap_text(x, inv)) if texts else () for x in a.missing_design_elements)),
        )
        for a in q.scenario_assessments
    }
    sc = review.style_comparison
    return {
        "system": review.system,
        "source_status": review.source_architecture_status,
        "overall": review.overall_status,
        "quality_status": q.status,
        "findings_total": len(q.findings),
        "findings": fcount,
        "severity_counts": Counter(f.severity for f in q.findings),
        "category_counts": Counter(f.category for f in q.findings),
        "coverage": (mp(q.coverage.verified), mp(q.coverage.planned_only), mp(q.coverage.uncovered)),
        "source_findings": mp(q.source_findings),
        "scenarios": scen,
        "style_status": sc.status,
        "recommendation": sc.recommendation,
        "declared_family": sc.declared_style_family,
        "scores": {c.style: c.score for c in sc.candidates},
    }


def gate_signature(gate, inverse: dict[str, str] | None = None, *, messages: bool = True) -> Json:
    inv = inverse or {}

    def norm(s: str | None) -> str | None:
        if s is None:
            return None
        s = re.sub(r"REVIEW-\d+", "REVIEW-N", unmap_text(s, inv))  # positional IDs are not stable
        return s

    return {
        "outcome": gate.outcome,
        "counts": gate.counts,
        "blocking": gate.blocking_count,
        "attention": gate.attention_count,
        "review_supplied": gate.review_supplied,
        "items": Counter(
            (i.category, i.severity, norm(unmap_obj(i.subject_id, inv)) if i.subject_id else None,
             bag(norm(i.message) or "") if messages else ())
            for i in gate.items),
    }


def diff_keys(a: Json, b: Json) -> list[str]:
    return [k for k in a if a[k] != b[k]]


# --------------------------------------------------------------------------- reordering


def shuffle_everything(spec_d: Json, cfg_d: Json | None, seed: int) -> tuple[Json, Json | None]:
    """Reorder every list field that carries no meaning in order."""
    rnd = random.Random(seed)
    spec = copy.deepcopy(spec_d)
    cfg = copy.deepcopy(cfg_d)

    def sh(xs: list) -> None:
        rnd.shuffle(xs)

    b = spec["brief"]
    for key in ("goals", "actors", "functional_requirements", "quality_requirements"):
        sh(b[key])
    for c in spec["components"]:
        for key in ("requirement_ids", "interfaces", "owned_data", "assumptions", "risks",
                    "validation_evidence"):
            sh(c[key])
        items = list(c["quality_targets"].items())
        sh(items)
        c["quality_targets"] = dict(items)
    for key in ("components", "relationships", "verification_cases", "decisions", "findings"):
        sh(spec[key])
    for r in spec["relationships"]:
        sh(r["requirement_ids"])
    for v in spec["verification_cases"]:
        sh(v["requirement_ids"])
        sh(v["component_ids"])
    for d in spec["decisions"]:
        sh(d["requirement_ids"])
        sh(d["alternatives"])
        sh(d["tradeoffs"])
    for f in spec["findings"]:
        sh(f["requirement_ids"])
        sh(f["component_ids"])
    if cfg is not None:
        for key in ("drivers", "candidates", "scenarios"):
            if key in cfg:
                sh(cfg[key])
        for s in cfg["scenarios"]:
            sh(s["component_ids"])
            sh(s.setdefault("expected_interactions", []))
    return spec, cfg


# --------------------------------------------------------------------------- R1: ID renaming


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
@pytest.mark.parametrize("kind", ["prefix", "scramble"])
def test_r1_id_rename_preserves_review_signature(stem, mode, kind):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    mapping = MAPS[kind](all_ids(spec_d, cfg_d))
    inverse = {v: k for k, v in mapping.items()}
    new_spec, new_cfg = remap_ids(spec_d, cfg_d, mapping)

    _, base = run(spec_d, cfg_d)
    spec2, renamed = run(new_spec, new_cfg)  # also proves the transformed spec validates

    # Sanity: the transformation really renamed every ID (non-vacuous).
    assert {c.id for c in spec2.components} == {mapping[c["id"]] for c in spec_d["components"]}
    assert not ({c["id"] for c in spec_d["components"]} & {c.id for c in spec2.components})

    got = review_signature(renamed, inverse)
    want = review_signature(base)
    assert not diff_keys(want, got), diff_keys(want, got)
    assert got == want


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
def test_r1_order_preserving_rename_is_exactly_reversible(stem, mode):
    """With an order-preserving map, the full dump equals the original after mapping IDs back
    (including positional REVIEW-NNN IDs and the order of findings)."""
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    mapping = prefix_map(all_ids(spec_d, cfg_d))
    inverse = {v: k for k, v in mapping.items()}
    _, base = run(spec_d, cfg_d)
    _, renamed = run(*remap_ids(spec_d, cfg_d, mapping))
    assert unmap_obj(renamed.model_dump(mode="json"), inverse) == base.model_dump(mode="json")


# --------------------------------------------------------------------------- R2: wording


def neutralize_text(spec_d: Json, cfg_d: Json | None) -> tuple[Json, Json | None]:
    """Replace human-readable wording with neutral labels ("Component A", "Goal 1", ...).

    Deliberately leaves selected_style, owned_data and brief.system alone; those are
    probed separately because the heuristics read them.
    """
    spec = copy.deepcopy(spec_d)
    cfg = copy.deepcopy(cfg_d)
    n = iter(range(1, 100000))

    def lab(prefix: str) -> str:
        return f"{prefix} {next(n)}"

    b = spec["brief"]
    b["goals"] = [lab("Goal") for _ in b["goals"]]
    b["actors"] = [lab("Actor") for _ in b["actors"]]
    for r in b["functional_requirements"]:
        r["statement"] = lab("Functional statement")
    for r in b["quality_requirements"]:
        r["attribute"], r["statement"] = lab("Attribute"), lab("Quality statement")
    for i, c in enumerate(spec["components"]):
        c["name"] = f"Component {chr(65 + i % 26)}{i // 26 or ''}"
        c["responsibility"], c["boundary"] = lab("Responsibility"), lab("Boundary")
        c["assumptions"] = [lab("Assumption") for _ in c["assumptions"]]
        c["risks"] = [lab("Risk") for _ in c["risks"]]
        c["validation_evidence"] = [lab("Evidence") for _ in c["validation_evidence"]]
        if c["stop_reason"]:
            c["stop_reason"] = lab("Stop reason")
        for key in ("interfaces_not_applicable_reason", "data_not_applicable_reason"):
            if c[key]:
                c[key] = lab("Reason")
        c["quality_targets"] = {k: lab("Target") for k in c["quality_targets"]}
        for itf in c["interfaces"]:
            itf["name"], itf["description"] = lab("Interface"), lab("Interface description")
            if itf["failure_behavior"]:
                itf["failure_behavior"] = lab("Failure behavior")
    for r in spec["relationships"]:
        r["description"] = lab("Relationship")
    for v in spec["verification_cases"]:
        v["description"] = lab("Case")
        if v["evidence"]:
            v["evidence"] = lab("Case evidence")
    for d in spec["decisions"]:
        d["title"], d["choice"], d["rationale"] = lab("Title"), lab("Choice"), lab("Rationale")
        d["alternatives"] = [lab("Alternative") for _ in d["alternatives"]]
        d["tradeoffs"] = [lab("Tradeoff") for _ in d["tradeoffs"]]
    for f in spec["findings"]:
        f["description"] = lab("Finding")
    if cfg is not None:
        for d in cfg["drivers"]:
            d["rationale"] = lab("Driver rationale")
        for s in cfg["scenarios"]:
            s["stimulus"], s["expected_response"], s["measure"] = lab("Stimulus"), lab("Response"), lab("Measure")
    return spec, cfg


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
def test_r2_neutral_labels_do_not_change_structural_results(stem, mode):
    """No finding is added, removed or re-graded when all free-text wording is replaced by
    neutral labels. (Only descriptions that quote the old wording differ, so texts are excluded.)"""
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    _, base = run(spec_d, cfg_d)
    _, neutral = run(*neutralize_text(spec_d, cfg_d))
    assert review_signature(neutral, texts=False) == review_signature(base, texts=False)


@pytest.mark.parametrize("stem", STEMS)
def test_r2_observation_only_scenario_descriptions_quote_wording_on_shipped_examples(stem):
    """Observation: on the shipped examples the only review text that changes under neutral
    wording is the scenario assessment `description`, which quotes the scenario's response and
    measure. All finding texts are identical (the examples carry no open high/critical source
    finding whose description would be quoted)."""
    spec_d, cfg_d = load_raw(stem, True)
    neutral_spec, neutral_cfg = neutralize_text(spec_d, cfg_d)
    assert (neutral_spec, neutral_cfg) != (spec_d, cfg_d)  # non-vacuous
    _, base = run(spec_d, cfg_d)
    _, neutral = run(neutral_spec, neutral_cfg)
    assert [f.description for f in neutral.quality_review.findings] == [
        f.description for f in base.quality_review.findings]
    base_d = [a.description for a in base.quality_review.scenario_assessments]
    new_d = [a.description for a in neutral.quality_review.scenario_assessments]
    assert base_d and new_d != base_d


def test_r2_observation_open_high_source_finding_text_is_quoted_verbatim():
    """Observation: an open high source finding is re-reported with its authored description, so
    changing only the wording changes the review text but not its severity/category/links."""
    spec_d, cfg_d = load_raw("ecommerce", True)
    spec_d["findings"][0].update(severity="high", description="Wording A")
    other = copy.deepcopy(spec_d)
    other["findings"][0]["description"] = "Entirely different wording B"
    _, a = run(spec_d, cfg_d)
    _, b = run(other, cfg_d)
    assert review_signature(a, texts=False) == review_signature(b, texts=False)
    ta = next(f.description for f in a.quality_review.findings if f.category == "source_architecture_risk")
    tb = next(f.description for f in b.quality_review.findings if f.category == "source_architecture_risk")
    assert ta.endswith("Wording A") and tb.endswith("Entirely different wording B")


def _family(style: str | None) -> str | None:
    spec_d, _ = load_raw("ecommerce", False)
    spec_d["selected_style"] = style
    spec = ArchitectureSpec.model_validate(spec_d)
    return compare_styles(spec, ReviewConfig()).declared_style_family


@pytest.mark.parametrize("style,family", [
    ("modular monolith", "modular_monolith"),
    ("Modular-Monolith", "modular_monolith"),
    ("modular_monolith", "modular_monolith"),
    ("MODULAR MONOLITH (python packages)", "modular_monolith"),
    ("event-driven", "event_driven"),
    ("Event Driven architecture", "event_driven"),
    ("microservices", "microservices"),
    ("serverless functions", "serverless"),
    ("single-process", "single_process"),
])
def test_r2_style_family_tolerates_case_and_separator_variants(style, family):
    assert _family(style) == family


# Same intended meaning, different wording. Expectation = semantic equivalence.
@pytest.mark.xfail(strict=True, reason=(
    "Observed R2 keyword sensitivity (review.py:_style_family): the non-English wording "
    "'Modularer Monolith' is not recognised, so declared_style_family is None instead of "
    "modular_monolith and the style-tradeoff check is silently skipped."))
def test_r2_style_family_non_english_synonym_modular_monolith():
    assert _family("Modularer Monolith") == "modular_monolith"


@pytest.mark.xfail(strict=True, reason=(
    "Observed R2 keyword sensitivity (review.py:_style_family): 'EDA' / 'message-driven' are "
    "common synonyms of event-driven but only the literal words 'event driven' match."))
def test_r2_style_family_abbreviation_event_driven():
    assert _family("EDA (message-driven)") == "event_driven"


# Regression: `"cli" in t` was a substring test, so "client portal" was classified
# single_process (found by this suite; fixed with a whole-word match).
def test_r2_style_family_substring_cli_matches_client():
    assert _family("Layered design for the client portal") == _family("Layered design for the customer portal")


def test_r2_client_wording_no_longer_adds_a_style_tradeoff_finding_end_to_end():
    """Regression for the former 'cli'-substring false positive on the ecommerce example:
    swapping customer/client in selected_style must not change the findings."""
    spec_d, cfg_d = load_raw("ecommerce", True)
    spec_d["selected_style"] = "Layered design for the customer portal"
    _, a = run(spec_d, cfg_d)
    spec_d["selected_style"] = "Layered design for the client portal"
    _, b = run(spec_d, cfg_d)
    assert a.style_comparison.recommendation == "modular_monolith"
    assert a.style_comparison.declared_style_family is None
    assert b.style_comparison.declared_style_family is None
    cats_a = Counter(f.category for f in a.quality_review.findings)
    cats_b = Counter(f.category for f in b.quality_review.findings)
    assert cats_b == cats_a
    assert _family("Python CLI utility") == "single_process"  # whole word still matches


def _with_sibling_data(extra: str):
    """ecommerce with a second sibling (payments) claiming ``extra`` next to orders' 'Order records'."""
    spec_d, cfg_d = load_raw("ecommerce", False)
    next(c for c in spec_d["components"] if c["id"] == "payments")["owned_data"].append(extra)
    _, review = run(spec_d, cfg_d)
    return Counter(f.category for f in review.quality_review.findings)["data_ownership"]


@pytest.mark.parametrize("variant", ["Order records", "order RECORDS", "  Order records  "])
def test_r2_data_ownership_conflict_detected_for_case_and_edge_whitespace(variant):
    assert _with_sibling_data(variant) == 1


@pytest.mark.parametrize("variant", ["Orders", "Order record", "Bestellungen"])
def test_r2_observation_data_ownership_misses_plural_and_synonym_wording(variant):
    """Observation (not asserted to be a bug): conflict detection is exact-text after
    strip/casefold, so a plural, singular or translated name of the same data is not a conflict."""
    assert _with_sibling_data(variant) == 0


# Regression: internal whitespace was not normalised (found by this suite; fixed).
def test_r2_data_ownership_internal_whitespace():
    assert _with_sibling_data("Order  records") == 1


def test_r2_observation_gate_depends_on_system_name_equality():
    """Observation: the gate ignores a supplied review whose `system` text differs from the spec's.
    A pure rename of brief.system in one artefact only therefore adds a blocking item."""
    spec_d, cfg_d = load_raw("ecommerce", True)
    spec, _config, review = build(spec_d, cfg_d)
    same = evaluate_documentation_gate(spec, review=review)
    spec_d2 = copy.deepcopy(spec_d)
    spec_d2["brief"]["system"] = "Neutral System"
    spec2 = ArchitectureSpec.model_validate(spec_d2)
    stale = evaluate_documentation_gate(spec2, review=review)
    assert any("different system" in i.message and i.severity == "blocking" for i in stale.items)
    assert not any("different system" in i.message for i in same.items)
    assert stale.blocking_count != same.blocking_count or stale.counts != same.counts
    _, _config2, review2 = build(spec_d2, cfg_d)
    consistent = evaluate_documentation_gate(spec2, review=review2)
    assert gate_signature(consistent, messages=False)["counts"] == gate_signature(same, messages=False)["counts"]


# --------------------------------------------------------------------------- R3: reordering


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
@pytest.mark.parametrize("seed", SEEDS)
def test_r3_reordering_lists_preserves_review_signature(stem, mode, seed):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    _, base = run(spec_d, cfg_d)
    new_spec, new_cfg = shuffle_everything(spec_d, cfg_d, seed)
    assert new_spec != spec_d  # non-vacuous: the shuffle really changed the input
    _, shuffled = run(new_spec, new_cfg)
    got, want = review_signature(shuffled), review_signature(base)
    assert not diff_keys(want, got), diff_keys(want, got)


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("seed", SEEDS)
def test_r3_reordering_preserves_exact_texts_after_sorting(stem, seed):
    """Stronger than the signature: finding texts and scenario issue texts are identical as strings
    (not just as token bags) once findings are sorted and positional REVIEW-NNN IDs ignored."""
    spec_d, cfg_d = load_raw(stem, True)
    _, base = run(spec_d, cfg_d)
    _, shuffled = run(*shuffle_everything(spec_d, cfg_d, seed))

    def exact(r):
        return sorted((f.severity, f.category, f.description, f.recommendation) for f in r.quality_review.findings)

    assert exact(shuffled) == exact(base)


def test_r3_observation_review_ids_are_positional_not_content_stable():
    """Observation: REVIEW-NNN IDs are assigned in generation order, so the id -> finding
    assignment is NOT stable under reordering even though the set of findings is. On the ecommerce
    example (three interaction_contract findings generated in component order) it differs for
    every seed; on the two smaller examples it happens to be identical."""
    spec_d, cfg_d = load_raw("ecommerce", True)
    _, base = run(spec_d, cfg_d)
    by_id = {f.id: (f.category, f.description) for f in base.quality_review.findings}
    differs = []
    for seed in SEEDS:
        _, shuffled = run(*shuffle_everything(spec_d, cfg_d, seed))
        assert sorted(by_id.values()) == sorted((f.category, f.description) for f in shuffled.quality_review.findings)
        differs.append({f.id: (f.category, f.description) for f in shuffled.quality_review.findings} != by_id)
    assert all(differs)


def test_r3_observation_joined_issue_text_keeps_input_order():
    """Observation (cosmetic): a scenario's `missing_design_elements` and the joined text of its
    `scenario_design` finding follow the order of `expected_interactions`. The *set* of issues and
    all structured fields are order independent; only the string order differs."""
    spec_d, cfg_d = load_raw("ecommerce", True)
    extra = [
        {"source_id": "orders", "target_id": "catalog", "kind": "data_flow"},
        {"source_id": "inventory", "target_id": "orders", "kind": "event"},
    ]
    sc = copy.deepcopy(cfg_d)
    sc["scenarios"][1]["expected_interactions"] = extra
    rc = copy.deepcopy(cfg_d)
    rc["scenarios"][1]["expected_interactions"] = list(reversed(extra))
    _, a = run(spec_d, sc)
    _, b = run(spec_d, rc)
    ma = {x.scenario_id: x for x in a.quality_review.scenario_assessments}
    mb = {x.scenario_id: x for x in b.quality_review.scenario_assessments}
    sid = sc["scenarios"][1]["id"]
    assert len(ma[sid].missing_design_elements) >= 2
    assert sorted(ma[sid].missing_design_elements) == sorted(mb[sid].missing_design_elements)
    assert ma[sid].missing_design_elements != mb[sid].missing_design_elements  # order follows input
    assert review_signature(a) == review_signature(b)  # token-bag signature is unaffected


# --------------------------------------------------------------------------- R4: monotonicity

_OVERALL_RANK = {"candidate_for_human_review": 0, "requires_review": 1}
_SCENARIO_RANK = {"evidence_documented": 0, "verification_pending": 1, "design_gap": 2}


def remove_case(spec_d: Json, index: int) -> Json:
    out = copy.deepcopy(spec_d)
    del out["verification_cases"][index]
    return out


def case_indexes(stem: str) -> list[int]:
    return list(range(len(load_raw(stem, False)[0]["verification_cases"])))


CASE_PARAMS = [(s, i) for s in STEMS for i in case_indexes(s)]


@pytest.mark.parametrize("stem,index", CASE_PARAMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
def test_r4_removing_a_verification_case_never_improves_the_review(stem, index, mode):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    _, base = run(spec_d, cfg_d)
    _, less = run(remove_case(spec_d, index), cfg_d)

    bq, lq = base.quality_review, less.quality_review
    # coverage can only get worse
    assert set(lq.coverage.verified) <= set(bq.coverage.verified)
    assert set(lq.coverage.uncovered) >= set(bq.coverage.uncovered)
    # every requirement flagged as lacking verification before is still flagged
    def flagged(q):
        return {r for f in q.findings
                if f.category in {"requirement_coverage", "verification_pending", "scenario_evidence"}
                for r in f.requirement_ids}
    assert flagged(lq) >= flagged(bq)
    # no scenario assessment gets better
    for a in lq.scenario_assessments:
        b = next(x for x in bq.scenario_assessments if x.scenario_id == a.scenario_id)
        assert _SCENARIO_RANK[a.status] >= _SCENARIO_RANK[b.status]
    # overall status does not improve
    assert _OVERALL_RANK[less.overall_status] >= _OVERALL_RANK[base.overall_status]
    # high-or-worse findings do not decrease
    sev = lambda q: sum(f.severity in {"critical", "high"} for f in q.findings)  # noqa: E731
    assert sev(lq) >= sev(bq)


@pytest.mark.parametrize("stem,index", CASE_PARAMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
def test_r4_removing_a_verification_case_does_not_reduce_total_finding_count(stem, index, mode):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    _, base = run(spec_d, cfg_d)
    _, less = run(remove_case(spec_d, index), cfg_d)
    assert len(less.quality_review.findings) >= len(base.quality_review.findings)


def _aggregation_probe() -> tuple[Json, Json]:
    """ecommerce reduced to ONE planned-only requirement (FR-001) and several uncovered ones;
    the second spec drops FR-001's only (planned) case."""
    spec_d, _ = load_raw("ecommerce", False)
    keep = [c for c in spec_d["verification_cases"] if c["requirement_ids"] == ["FR-001"]]
    assert keep, "fixture assumption: a case dedicated to FR-001 exists"
    keep[0]["status"], keep[0]["evidence"] = "planned", None
    spec_d["verification_cases"] = keep
    less_d = copy.deepcopy(spec_d)
    less_d["verification_cases"] = []
    return spec_d, less_d


@pytest.mark.xfail(strict=True, reason=(
    "Observed violation of count-monotonicity (review.py review_quality, aggregated findings): on "
    "ecommerce reduced to one planned-only requirement (FR-001) plus uncovered ones, removing the "
    "planned FR-001 case DROPS the findings from 7 to 6: the aggregated medium `verification_pending` "
    "finding disappears while the existing high `requirement_coverage` finding merely absorbs FR-001 "
    "into its list. The situation is worse, the raw finding count is lower."))
def test_r4_count_monotonic_on_aggregation_probe():
    base_d, less_d = _aggregation_probe()
    _, base = run(base_d, None)
    _, less = run(less_d, None)
    assert len(less.quality_review.findings) >= len(base.quality_review.findings)


def test_r4_aggregation_probe_is_still_monotonic_per_requirement_and_severity():
    """The count form above fails, but the information-bearing forms hold on the same input:
    FR-001 stays flagged, now under a higher severity, and the high-or-worse count does not fall."""
    base_d, less_d = _aggregation_probe()
    _, base = run(base_d, None)
    _, less = run(less_d, None)
    bq, lq = base.quality_review, less.quality_review
    assert bq.coverage.planned_only == ["FR-001"] and bq.coverage.uncovered
    assert "FR-001" in lq.coverage.uncovered
    cats = lambda q: Counter(f.category for f in q.findings)  # noqa: E731
    assert cats(bq)["verification_pending"] == 1 and cats(lq)["verification_pending"] == 0
    assert any("FR-001" in f.requirement_ids and f.severity == "high"
               for f in lq.findings if f.category == "requirement_coverage")
    assert sum(f.severity in {"critical", "high"} for f in lq.findings) >= sum(
        f.severity in {"critical", "high"} for f in bq.findings)
    assert (len(bq.findings), len(lq.findings)) == (7, 6)


CRITICAL = {
    "id": "ZZ-CRIT-1", "severity": "critical", "description": "Synthetic critical open finding",
    "requirement_ids": [], "component_ids": [], "status": "open",
}


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
def test_r4_adding_a_critical_open_finding_never_improves_the_review(stem, mode):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    worse_d = copy.deepcopy(spec_d)
    root = next(c["id"] for c in worse_d["components"] if c["parent_id"] is None)
    worse_d["findings"].append({**CRITICAL, "component_ids": [root]})
    _, base = run(spec_d, cfg_d)
    _, worse = run(worse_d, cfg_d)

    assert _OVERALL_RANK[worse.overall_status] >= _OVERALL_RANK[base.overall_status]
    assert len(worse.quality_review.findings) == len(base.quality_review.findings) + 1
    old = Counter((f.severity, f.category, f.description) for f in base.quality_review.findings)
    new = Counter((f.severity, f.category, f.description) for f in worse.quality_review.findings)
    assert not (old - new), "every earlier finding is still present"
    added = new - old
    assert list(added) == [("critical", "source_architecture_risk",
                            "Unresolved source finding ZZ-CRIT-1: Synthetic critical open finding")]
    assert "ZZ-CRIT-1" in worse.quality_review.source_findings


def _tiny_validated() -> Json:
    return {
        "brief": {
            "system": "Tiny", "goals": ["Be tiny"],
            "functional_requirements": [{"id": "FR-1", "statement": "Do it"}],
            "quality_requirements": [{"id": "QR-1", "attribute": "latency", "statement": "Fast"}],
        },
        "selected_style": "modular monolith",
        "components": [{
            "id": "root", "name": "Root", "responsibility": "Everything", "boundary": "Whole app",
            "requirement_ids": ["FR-1", "QR-1"], "interfaces_not_applicable_reason": "single unit",
            "data_not_applicable_reason": "stateless", "validation_evidence": ["walkthrough"],
            "stop_reason": "atomic", "quality_targets": {"QR-1": "p95 < 1s"}, "status": "ready",
        }],
        "verification_cases": [{
            "id": "VC-1", "description": "Review", "method": "design_review",
            "requirement_ids": ["FR-1", "QR-1"], "component_ids": ["root"],
            "status": "verified", "evidence": "authored walkthrough notes",
        }],
        "status": "validated_for_scope",
    }


TINY_CONFIG: Json = {
    "drivers": [{"key": "modular_boundaries", "importance": 5, "desired": 5, "rationale": "Clear modules"},
                {"key": "independent_deployment", "importance": 3, "desired": 1, "rationale": "One unit"}],
    "scenarios": [{"id": "SC-1", "requirement_id": "QR-1", "stimulus": "Load", "expected_response": "Fast",
                   "measure": "p95", "component_ids": ["root"]}],
}


def test_r4_tiny_fixture_reaches_candidate_for_human_review_so_the_monotonic_tests_are_not_vacuous():
    _, review = run(_tiny_validated(), TINY_CONFIG)
    assert review.quality_review.findings == []
    assert review.style_comparison.status == "recommendation"
    assert review.overall_status == "candidate_for_human_review"


def test_r4_critical_open_finding_cannot_coexist_with_validated_scope():
    bad = _tiny_validated()
    bad["findings"] = [{**CRITICAL, "component_ids": ["root"]}]
    with pytest.raises(ValidationError, match="Open high/critical findings"):
        ArchitectureSpec.model_validate(bad)
    # Dropping the authored status instead makes the review strictly worse, never better.
    bad["status"] = "draft"
    _, worse = run(bad, TINY_CONFIG)
    assert worse.overall_status == "requires_review"
    assert [f.category for f in worse.quality_review.findings] == ["source_architecture_risk"]


def test_r4_removing_the_only_verification_case_cannot_keep_validated_scope():
    bad = _tiny_validated()
    bad["verification_cases"] = []
    with pytest.raises(ValidationError, match="verified coverage"):
        ArchitectureSpec.model_validate(bad)
    bad["status"] = "draft"
    _, worse = run(bad, TINY_CONFIG)
    assert worse.overall_status == "requires_review"
    assert len(worse.quality_review.findings) > 0


# --------------------------------------------------------------------------- R5: doc_gate


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
@pytest.mark.parametrize("with_review", [True, False], ids=["review", "no_review"])
@pytest.mark.parametrize("kind", ["prefix", "scramble"])
def test_r5_gate_is_invariant_under_id_renaming(stem, mode, with_review, kind):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    mapping = MAPS[kind](all_ids(spec_d, cfg_d))
    inverse = {v: k for k, v in mapping.items()}
    base = gate_of(spec_d, cfg_d, with_review=with_review)
    renamed = gate_of(*remap_ids(spec_d, cfg_d, mapping), with_review=with_review)
    got, want = gate_signature(renamed, inverse), gate_signature(base)
    assert not diff_keys(want, got), diff_keys(want, got)


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
@pytest.mark.parametrize("with_review", [True, False], ids=["review", "no_review"])
@pytest.mark.parametrize("seed", SEEDS)
def test_r5_gate_is_invariant_under_reordering(stem, mode, with_review, seed):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    base = gate_of(spec_d, cfg_d, with_review=with_review)
    shuffled = gate_of(*shuffle_everything(spec_d, cfg_d, seed), with_review=with_review)
    got, want = gate_signature(shuffled), gate_signature(base)
    assert not diff_keys(want, got), diff_keys(want, got)


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("seed", SEEDS)
def test_r5_gate_without_review_is_exactly_order_independent(stem, seed):
    """Without a review (no positional IDs involved) the whole gate dump is byte-identical."""
    spec_d, cfg_d = load_raw(stem, False)
    base = gate_of(spec_d, cfg_d, with_review=False)
    shuffled = gate_of(*shuffle_everything(spec_d, cfg_d, seed), with_review=False)
    assert shuffled.model_dump(mode="json") == base.model_dump(mode="json")


@pytest.mark.parametrize("stem,index", CASE_PARAMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
def test_r5_removing_a_verification_case_never_improves_the_gate(stem, index, mode):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    base = gate_of(spec_d, cfg_d)
    less = gate_of(remove_case(spec_d, index), cfg_d)
    assert less.blocking_count >= base.blocking_count
    assert less.outcome == "requires_review" or base.outcome == "ready_for_human_signoff"
    # Observation: the *attention* count may legitimately drop, because removing a `verified`
    # case removes its "authored evidence is not independently checked" attention item.
    assert less.counts["uncovered_requirement"] + less.counts["planned_only_requirement"] >= (
        base.counts["uncovered_requirement"] + base.counts["planned_only_requirement"])


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("mode", CONFIG_MODES)
def test_r5_adding_a_critical_open_finding_never_improves_the_gate(stem, mode):
    spec_d, cfg_d = load_raw(stem, mode == "with_config")
    worse_d = copy.deepcopy(spec_d)
    worse_d["findings"].append(dict(CRITICAL))
    base = gate_of(spec_d, cfg_d)
    worse = gate_of(worse_d, cfg_d)
    assert worse.blocking_count > base.blocking_count
    assert worse.outcome == "requires_review"
