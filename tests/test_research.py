"""Phase 6: provenance, alternative designs, negative controls and CLI integration."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.cli import main
from speccanopy.models import ArchitectureSpec
from speccanopy.research import (
    AcceptableAlternative, CaseProvenance, ResearchCase, ResearchCriterion,
    ResearchSuite, ReviewClaim, evaluate_case, summarize_suite,
)
from speccanopy.research_exporters import export_research, research_markdown

BASE = Path(__file__).resolve().parents[1] / 'examples'
RESEARCH = BASE / 'research'


def case(name):
    return ResearchCase.model_validate_json((RESEARCH / f'cases/{name}.json').read_text())


def spec(name):
    return ArchitectureSpec.model_validate_json((BASE / f'generated/{name}/architecture.json').read_text())


def unreviewed_distributed():
    return ArchitectureSpec.model_validate_json((RESEARCH / 'candidates/ecommerce-distributed-unreviewed.json').read_text())


def test_curated_case_is_distinct_from_expert_review():
    c = case('ecommerce')
    assert c.split == 'development'
    assert c.provenance.origin == 'synthetic_curated'
    assert c.provenance.review_claims == []
    assert len(c.alternatives) == 2
    r = evaluate_case(c, spec('ecommerce'))
    assert r.review_status == 'curated_unreviewed'
    assert r.review_claim_count == 0
    assert 'NOT' in r.caveat or 'not' in r.caveat


def test_single_process_example_matches_research_criteria_but_not_certified():
    result = evaluate_case(case('cli-utility'), spec('cli-utility'))
    assert result.result == 'criteria_present_review_required'
    assert result.best_path == 'single_process_solution'
    assert result.common_score == 100.0
    assert result.pending_verification
    assert not result.uncovered_mandatory


def test_two_different_ecommerce_styles_are_not_forced_into_one_tree():
    c = case('ecommerce')
    standard = evaluate_case(c, spec('ecommerce'))
    alternate = evaluate_case(c, unreviewed_distributed())
    assert standard.detected_style_family == 'modular_monolith'
    assert standard.best_path == 'modular_monolith_path'
    assert standard.result == 'criteria_gaps'
    assert 'EC-M-OUT' in standard.alternatives[0].missing_required
    assert alternate.detected_style_family == 'microservices'
    assert alternate.best_path == 'distributed_event_path'
    assert alternate.result == 'criteria_present_review_required'
    assert all(x.style_status == 'mismatched' or x.id == alternate.best_path for x in alternate.alternatives)
    assert all(component.id.startswith('service_') for component in unreviewed_distributed().components)
    assert alternate.pending_verification and alternate.review_status == 'curated_unreviewed'


def test_matching_different_component_ids_is_requirement_linked():
    source = spec('cli-utility').model_dump(mode='json')
    renames = {c['id']:f'renamed_{c["id"]}' for c in source['components']}
    for component in source['components']:
        component['parent_id'] = renames.get(component['parent_id'])
        component['id'] = renames[component['id']]
    for edge in source['relationships']:
        edge['source_id'] = renames[edge['source_id']]
        edge['target_id'] = renames[edge['target_id']]
    for verification in source['verification_cases']:
        verification['component_ids'] = [renames[c] for c in verification['component_ids']]
    for finding in source['findings']:
        finding['component_ids'] = [renames[c] for c in finding['component_ids']]
    candidate = ArchitectureSpec.model_validate(source)
    report = evaluate_case(case('cli-utility'), candidate)
    assert report.result == 'criteria_present_review_required'
    assert report.best_path == 'single_process_solution'
    assert report.candidate_sha256 != evaluate_case(case('cli-utility'), spec('cli-utility')).candidate_sha256


def test_wrong_brief_is_rejected():
    candidate = spec('cli-utility')
    candidate.brief.system = 'Completely different task'
    with pytest.raises(ValueError, match='same original SystemBrief'):
        evaluate_case(case('cli-utility'), candidate)


def test_unknown_architecture_style_is_not_automatically_accepted():
    candidate = spec('cli-utility')
    candidate.selected_style = 'quantum graphene cluster'
    report = evaluate_case(case('cli-utility'), candidate)
    assert report.result == 'no_compatible_style'
    assert report.alternatives[0].style_status == 'unclassified'


def test_known_but_incompatible_style_is_rejected():
    candidate = spec('cli-utility')
    candidate.selected_style = 'microservices'
    report = evaluate_case(case('cli-utility'), candidate)
    assert report.result == 'no_compatible_style'
    assert report.alternatives[0].style_status == 'mismatched'


def test_orphan_root_requirement_mapping_does_not_fool_research():
    candidate = spec('cli-utility')
    for component in candidate.components:
        if component.id != 'system':
            component.requirement_ids = [r for r in component.requirement_ids if r != 'FR-001']
    candidate = ArchitectureSpec.model_validate(candidate.model_dump(mode='json'))
    report = evaluate_case(case('cli-utility'), candidate)
    assert report.result == 'criteria_gaps'
    assert 'CLI-MAP-1' in [x.id for x in report.common_results if not x.present]


def test_edge_with_requirement_but_unrelated_endpoints_fails():
    candidate = spec('ecommerce')
    for relation in candidate.relationships:
        if relation.kind == 'event' and 'FR-005' in relation.requirement_ids:
            relation.source_id = 'catalog'
            relation.target_id = 'identity'
    result = evaluate_case(case('ecommerce'), candidate)
    matching = next(x for x in result.alternatives if x.id == 'modular_monolith_path')
    assert 'EC-M-STOCK' in matching.missing_required


def test_duplicate_data_owner_detected_without_expert_claims():
    candidate = spec('ecommerce')
    next(c for c in candidate.components if c.id == 'payments').owned_data.append('Order   records')
    result = evaluate_case(case('ecommerce'), candidate)
    assert 'EC-OWNER' in [x.id for x in result.common_results if not x.present]
    assert result.result == 'criteria_gaps'


def test_removed_quality_target_fails_common_criterion():
    candidate = spec('cli-utility')
    for c in candidate.components:
        c.quality_targets.pop('NFR-001', None)
    report = evaluate_case(case('cli-utility'), candidate)
    assert 'CLI-QUALITY' in [c.id for c in report.common_results if not c.present]
    assert report.result == 'criteria_gaps'


def test_unverified_source_risk_prevents_satisfying_status():
    candidate = spec('cli-utility')
    candidate.findings[0].severity = 'high'
    report = evaluate_case(case('cli-utility'), candidate)
    assert report.result == 'criteria_gaps'
    assert report.open_high_or_critical_findings == ['FIND-CLI-01']


def test_criterion_validation_rejects_irrelevant_fields():
    with pytest.raises(ValidationError, match='requires exactly'):
        ResearchCriterion(id='C1',kind='verification_link',description='Plan',requirement_id='FR-001',data_label='irrelevant')
    with pytest.raises(ValidationError, match='requires exactly'):
        ResearchCriterion(id='C2',kind='typed_interaction',description='Event',requirement_id='FR-001')
    with pytest.raises(ValidationError):
        ResearchCriterion(id='C3',kind='requirement_mapped',description='Map',requirement_id='FR-001',weight=0)


@pytest.mark.parametrize('mutation,expected', [
    (lambda d: d['alternatives'][1].update(id=d['alternatives'][0]['id']), 'Alternative IDs'),
    (lambda d: d['common_criteria'][1].update(id=d['common_criteria'][0]['id']), 'criterion IDs'),
    (lambda d: d['common_criteria'][0].update(requirement_id='FR-MISSING'), 'Unknown research requirement'),
    (lambda d: d['common_criteria'][0].update(kind='quality_target'), 'quality requirement'),
    (lambda d: d['alternatives'][0].update(style_families=['modular_monolith','modular_monolith']), 'must be unique'),
])
def test_case_rejects_inconsistent_reference(mutation, expected):
    data = case('ecommerce').model_dump(mode='json')
    mutation(data)
    with pytest.raises(ValidationError, match=expected):
        ResearchCase.model_validate(data)


def test_external_origin_requires_attributable_source():
    data = case('cli-utility').model_dump(mode='json')
    data['provenance']['origin'] = 'published_source'
    with pytest.raises(ValidationError, match='source_url'):
        ResearchCase.model_validate(data)
    data['provenance']['source_url'] = 'https://example.com/source'
    validated = ResearchCase.model_validate(data)
    assert str(validated.provenance.source_url).startswith('https://example.com')


def test_self_declared_claim_binds_to_subject_but_never_authenticates_expertise():
    raw = case('cli-utility').model_dump(mode='json')
    sha = case('cli-utility').subject_digest()
    raw['provenance']['review_claims'] = [dict(
        reviewer='a claimed architect', expertise='self-reported architecture experience',
        reviewed_on='2026-01-02', method='architecture_review',
        report_url='https://example.com/example-review', subject_sha256=sha,
        declares_independence=True, summary='Self-declared review with no authenticated provenance',
    )]
    with_claim = ResearchCase.model_validate(raw)
    report = evaluate_case(with_claim, spec('cli-utility'))
    assert report.review_status == 'self_declared_claims_unverified'
    assert report.review_claim_count == 1
    assert 'NOT authenticated' in report.caveat
    raw['title'] = 'Changed after claim'
    with pytest.raises(ValidationError, match='subject_sha256'):
        ResearchCase.model_validate(raw)


def test_fake_hash_and_malformed_uri_rejected():
    raw = case('cli-utility').model_dump(mode='json')
    raw['provenance']['review_claims'] = [dict(reviewer='X',expertise='X',reviewed_on='2026-01-01',
       method='architecture_review',report_url='not-a-url',subject_sha256='xyz',declares_independence=True,summary='X')]
    with pytest.raises(ValidationError):
        ResearchCase.model_validate(raw)


def test_suite_keeps_development_separate_from_public_holdout():
    suite = ResearchSuite.model_validate_json((RESEARCH/'suite.json').read_text())
    assert len(suite.entries) == 6
    cases = {}
    for entry in suite.entries:
        research = ResearchCase.model_validate_json((RESEARCH/entry.case_path).read_text())
        candidate = ArchitectureSpec.model_validate_json((RESEARCH/entry.architecture_path).read_text())
        cases[entry.id] = evaluate_case(research, candidate)
    report = summarize_suite(suite.name, cases)
    assert report.total == 6
    assert report.by_split[0].split == 'development' and report.by_split[0].count == 3
    assert report.by_split[1].split == 'public_holdout' and report.by_split[1].count == 3
    assert sum(s.criteria_present_review_required for s in report.by_split) == 4
    assert 'not an independent holdout' in report.caveat.lower()


def test_duplicate_suite_ids_rejected():
    source = json.loads((RESEARCH/'suite.json').read_text())
    source['entries'][1]['id'] = source['entries'][0]['id']
    with pytest.raises(ValidationError,match='unique'):
        ResearchSuite.model_validate(source)


def test_research_case_cli_and_strict_exit_codes(tmp_path):
    rc = RESEARCH/'cases/cli-utility.json'
    architecture = BASE/'generated/cli-utility/architecture.json'
    out = tmp_path/'case'
    assert main(['research-case',str(rc),'--architecture',str(architecture),'--output',str(out),'--strict']) == 0
    assert (out/'research-case.md').exists()
    data = json.loads((out/'research-case.json').read_text())
    assert data['result'] == 'criteria_present_review_required'
    bad = RESEARCH/'cases/ecommerce.json'
    arch = BASE/'generated/ecommerce/architecture.json'
    assert main(['research-case',str(bad),'--architecture',str(arch),'--output',str(tmp_path/'bad'),'--strict']) == 2
    assert main(['research-case',str(bad),'--architecture',str(architecture),'--output',str(tmp_path/'invalid')]) == 1


def test_suite_cli_snapshots_and_strict(tmp_path):
    destination = tmp_path/'suite'
    path = RESEARCH/'suite.json'
    assert main(['research-suite',str(path),'--output',str(destination)]) == 0
    expected = json.loads((RESEARCH/'generated/research-suite.json').read_text())
    actual = json.loads((destination/'research-suite.json').read_text())
    assert actual == expected
    assert (destination/'research-suite.md').read_text().strip() == (RESEARCH/'generated/research-suite.md').read_text().strip()
    first = (destination/'research-suite.json').read_bytes()
    assert main(['research-suite',str(path),'--output',str(destination),'--strict']) == 1
    assert (destination/'research-suite.json').read_bytes() == first
    assert main(['research-suite',str(path),'--output',str(tmp_path/'suite-strict'),'--strict']) == 2


def test_suite_ignores_external_data_and_rejects_invalid_paths(tmp_path):
    raw = json.loads((RESEARCH/'suite.json').read_text())
    raw['entries'][0]['architecture_path'] = '/does/not/exist.json'
    path = tmp_path/'suite.json'; path.write_text(json.dumps(raw))
    assert main(['research-suite',str(path),'--output',str(tmp_path/'out')]) == 1


def test_result_export_and_hashes_are_deterministic(tmp_path):
    c = case('cli-utility')
    r1 = evaluate_case(c, spec('cli-utility'))
    r2 = evaluate_case(c, spec('cli-utility'))
    assert r1.model_dump() == r2.model_dump()
    paths = export_research(r1,tmp_path)
    assert set(paths) == {'research-case.json', 'research-case.md'}
    assert len(r1.case_subject_sha256) == 64 and len(r1.candidate_sha256) == 64
    assert 'NOT expert certification' in research_markdown(r1)


def test_alternative_choice_prefers_met_requirements_before_optional_score():
    c = case('cli-utility')
    raw = c.model_dump(mode='json')
    alt = copy.deepcopy(raw['alternatives'][0])
    alt['id'] = 'competing_path'
    alt['criteria'] = [
      dict(id='ALT-REQ',kind='typed_interaction',requirement_id='FR-001',description='Require absent event',relationship_kind='event',weight=1,required=True),
      dict(id='ALT-OPT',kind='quality_target',requirement_id='NFR-001',description='Optional easy target',weight=5,required=False),
    ]
    raw['alternatives'].append(alt)
    result = evaluate_case(ResearchCase.model_validate(raw),spec('cli-utility'))
    assert result.best_path == 'single_process_solution'
    assert result.result == 'criteria_present_review_required'


@pytest.mark.parametrize('name,style,owner,data', [
    ('embedded-controller','single_process','sensor','Sensor readings'),
    ('telemetry-ingestion','event_driven','event_store','Validated events'),
])
def test_additional_domains_have_distinct_valid_draft_architectures(name, style, owner, data):
    c = case(name)
    path = RESEARCH / f'candidates/{name}.json'
    architecture = ArchitectureSpec.model_validate_json(path.read_text())
    assert c.split == 'public_holdout'  # Public and non-blind; not an independent holdout.
    assert architecture.status == 'draft'
    report = evaluate_case(c, architecture)
    assert report.detected_style_family == style
    assert report.result == 'criteria_present_review_required'
    assert owner in {c.id for c in architecture.components}
    assert sum(data in c.owned_data for c in architecture.components) == 1
    assert report.pending_verification
    assert not c.provenance.review_claims


def test_embedded_example_missing_fault_target_is_detected():
    c = case('embedded-controller')
    architecture = ArchitectureSpec.model_validate_json((RESEARCH/'candidates/embedded-controller.json').read_text())
    for node in architecture.components:
        node.quality_targets.pop('NFR-002',None)
    report = evaluate_case(c,architecture)
    assert report.result == 'criteria_gaps'
    assert 'EM-SAFETY' in [r.id for r in report.common_results if not r.present]


def test_telemetry_example_missing_tenant_boundary_is_detected():
    c = case('telemetry-ingestion')
    architecture = ArchitectureSpec.model_validate_json((RESEARCH/'candidates/telemetry-ingestion.json').read_text())
    architecture.relationships=[e for e in architecture.relationships if e.kind!='trust_boundary']
    report = evaluate_case(c,architecture)
    assert report.result == 'criteria_gaps'
    assert 'TE-AUTH' in next(a for a in report.alternatives if a.id=='async_pipeline').missing_required
