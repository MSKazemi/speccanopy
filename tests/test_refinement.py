"""Phase 5 review-driven, bounded refinement and explicit human acknowledgement."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.ai import sha256_json
from speccanopy.cli import main
from speccanopy.models import ArchitectureSpec, InterfaceContract
from speccanopy.refinement import (
    RefinementEdits, RefinementPatch, RefinementPlan, apply_refinement,
    plan_refinement, simulate_refinement,
)
from speccanopy.review import ExpectedInteraction, ReviewConfig, assess_architecture

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def fixtures():
    spec = ArchitectureSpec.model_validate_json((EXAMPLES/'generated/ecommerce/architecture.json').read_text())
    config = ReviewConfig.model_validate_json((EXAMPLES/'ecommerce.review.json').read_text())
    edits = RefinementEdits.model_validate_json((EXAMPLES/'refinement/ecommerce.edits.json').read_text())
    return spec, config, edits


def test_two_round_refinement_improves_targeted_findings_and_preserves_input():
    spec, config, edits = fixtures()
    original = spec.model_dump_json()
    plan, candidate = plan_refinement(spec, config, edits)
    assert spec.model_dump_json() == original
    assert len(plan.rounds) == 2
    assert plan.rounds[0].before_counts['interaction_contract'] == 3
    assert plan.rounds[0].after_counts['interaction_contract'] == 1
    assert plan.rounds[1].after_counts.get('interaction_contract', 0) == 0
    assert all(x.after_high_or_critical <= x.before_high_or_critical for x in plan.rounds)
    assert candidate.status == 'incomplete_requires_review'
    assert candidate.coverage_report().uncovered == spec.coverage_report().uncovered
    assert len(candidate.relationships) == len(spec.relationships)
    assert all(c.status != 'ready' for c in candidate.components if c.id in {'orders','order_lifecycle','system'})
    assert candidate.selected_style == spec.selected_style
    assert plan.status == 'pending_human_review'
    RefinementPlan.model_validate_json(plan.model_dump_json())


def test_approval_requires_explicit_acknowledgement_and_a_reviewer():
    spec, config, edits = fixtures()
    plan, preview = plan_refinement(spec, config, edits)
    with pytest.raises(ValueError, match='acknowledge-review'):
        apply_refinement(spec, config, plan, reviewer='architect', acknowledge_review=False)
    with pytest.raises(ValueError, match='reviewer identifier'):
        apply_refinement(spec, config, plan, reviewer='  ', acknowledge_review=True)
    candidate, receipt = apply_refinement(spec, config, plan, reviewer='architect', acknowledge_review=True)
    assert candidate == preview
    assert receipt.candidate_sha256 == sha256_json(candidate.model_dump(mode='json'))
    assert receipt.reviewer == 'architect'
    assert receipt.status == 'acknowledged_for_architecture_review'
    assert candidate.status != 'validated_for_scope'


def test_tampered_architecture_config_and_plan_fails_closed():
    spec, config, edits = fixtures()
    plan, _ = plan_refinement(spec, config, edits)
    changed = spec.model_copy(deep=True)
    changed.components[-1].responsibility = 'Changed since review'
    with pytest.raises(ValueError, match='Source architecture changed'):
        apply_refinement(changed, config, plan, reviewer='a', acknowledge_review=True)
    config2 = config.model_copy(deep=True)
    config2.drivers[0].importance = 1
    with pytest.raises(ValueError, match='configuration changed'):
        apply_refinement(spec, config2, plan, reviewer='a', acknowledge_review=True)
    changed_plan = plan.model_copy(deep=True)
    changed_plan.edits.patches[0].interface.name = 'unexpected'
    with pytest.raises(ValueError, match='preview no longer matches'):
        apply_refinement(spec, config, changed_plan, reviewer='a', acknowledge_review=True)
    changed_plan = plan.model_copy(deep=True)
    changed_plan.candidate_sha256 = 'not-valid'
    with pytest.raises(ValueError, match='preview no longer matches'):
        apply_refinement(spec, config, changed_plan, reviewer='a', acknowledge_review=True)


def test_wrong_finding_and_wrong_category_cannot_be_bypassed():
    spec, config, edits = fixtures()
    edits.patches[0].finding_id = 'REVIEW-999'
    with pytest.raises(ValueError, match='current, matching review finding'):
        plan_refinement(spec, config, edits)
    spec, config, edits = fixtures()
    edits.patches[0].finding_category = 'verification_pending'
    with pytest.raises(ValueError, match='current, matching review finding'):
        plan_refinement(spec, config, edits)
    spec, config, edits = fixtures()
    edits.patches[0].component_id = 'catalog'
    with pytest.raises(ValueError, match="finding's components"):
        plan_refinement(spec, config, edits)


def test_budget_and_contiguous_round_limits():
    spec, config, edits = fixtures()
    spec.brief.constraints.max_refinement_rounds = 1
    with pytest.raises(ValueError, match='max_refinement_rounds'):
        plan_refinement(spec, config, edits)
    spec, config, edits = fixtures()
    edits.patches[-1].round = 3
    edits.patches[-2].round = 3
    with pytest.raises(ValueError, match='contiguous'):
        plan_refinement(spec, config, edits)
    spec, config, edits = fixtures()
    spec.brief.constraints.max_refinement_rounds = 0
    with pytest.raises(ValueError, match='max_refinement_rounds'):
        plan_refinement(spec, config, edits)


def test_duplicate_patch_ids_and_forbidden_payloads_fail_validation():
    _, _, edits = fixtures()
    raw = edits.model_dump(mode='json')
    raw['patches'][1]['id'] = raw['patches'][0]['id']
    with pytest.raises(ValidationError, match='Patch IDs must be unique'):
        RefinementEdits.model_validate(raw)
    raw = edits.model_dump(mode='json')
    raw['patches'][0]['status'] = 'validated_for_scope'
    with pytest.raises(ValidationError):
        RefinementEdits.model_validate(raw)
    raw = edits.model_dump(mode='json')
    raw['patches'][0]['relationship'] = {'id':'EVIL','source_id':'orders','target_id':'payments','kind':'event','description':'x'}
    with pytest.raises(ValidationError, match='requires exactly'):
        RefinementEdits.model_validate(raw)
    with pytest.raises(ValidationError, match='verification must remain planned'):
        RefinementPatch.model_validate({
            'id':'P-1','round':1,'finding_id':'REVIEW-001','finding_category':'verification_pending',
            'kind':'add_verification_plan','rationale':'try',
            'verification_case':{'id':'VC-NEW','description':'x','method':'design_review',
                                 'requirement_ids':['FR-001'],'component_ids':['orders'],
                                 'status':'verified','evidence':'fabricated'},
        })


def test_existing_verified_evidence_invalidated_by_design_changes():
    spec = ArchitectureSpec.model_validate_json((EXAMPLES/'cli-utility-architecture.json').read_text())
    config = ReviewConfig.model_validate_json((EXAMPLES/'cli-utility.review.json').read_text())
    # Force a scenario design gap involving the previously verified input component.
    config.scenarios[0].expected_interactions = [
        ExpectedInteraction(source_id='input', target_id='output', kind='event')
    ]
    before = assess_architecture(spec, config)
    f = next(x for x in before.quality_review.findings if x.category == 'scenario_design')
    edits = RefinementEdits.model_validate({'author':'reviewer', 'patches':[{
        'id':'PATCH-CLI-1','round':1,'finding_id':f.id,'finding_category':f.category,
        'kind':'add_relationship','rationale':'Document the hypothetical event boundary',
        'relationship':{'id':'REL-NEW-CLI','source_id':'input','target_id':'output',
                        'kind':'event','description':'Proposed interaction for review',
                        'requirement_ids':['NFR-001']},
    }]})
    plan, candidate = plan_refinement(spec, config, edits)
    assert 'VC-001' in plan.rounds[0].invalidated_verification_cases
    case = next(c for c in candidate.verification_cases if c.id == 'VC-001')
    assert case.status == 'planned' and case.evidence is None
    assert candidate.coverage_report().verified == []
    assert candidate.status == 'incomplete_requires_review'
    assert spec.verification_cases[0].status == 'verified'


def test_add_relationship_and_refusal_of_duplicate_and_unknown_nodes():
    spec, config, _ = fixtures()
    spec.relationships = [x for x in spec.relationships if x.id != 'REL-EC-04']
    finding = next(x for x in assess_architecture(spec, config).quality_review.findings if x.category == 'scenario_design')
    edit = RefinementEdits.model_validate({'author':'human', 'patches':[{
        'id':'REL-PATCH','round':1,'finding_id':finding.id,'finding_category':'scenario_design',
        'kind':'add_relationship','rationale':'Explicit security boundary',
        'relationship':{'id':'REL-NEW','source_id':'payments','target_id':'identity',
                        'kind':'trust_boundary','description':'Authorization check', 'requirement_ids':['NFR-001']},
    }]})
    plan,candidate=plan_refinement(spec,config,edit)
    assert any(x.id=='REL-NEW' for x in candidate.relationships)
    assert not any(f.category=='scenario_design' for f in assess_architecture(candidate,config).quality_review.findings)
    spec2,config2,_=fixtures()
    with pytest.raises(ValueError,match='Equivalent typed relationship'):
        from speccanopy.refinement import _apply_patch
        _apply_patch(spec2,edit.patches[0])
    broken=edit.model_copy(deep=True)
    broken.patches[0].relationship.target_id='ghost'
    with pytest.raises(ValueError,match='unknown component'):
        plan_refinement(spec,config,broken)


def test_cli_plan_apply_and_outputs(tmp_path,capsys):
    original=EXAMPLES/'generated/ecommerce/architecture.json'
    config=EXAMPLES/'ecommerce.review.json'
    changes=EXAMPLES/'refinement/ecommerce.edits.json'
    out=tmp_path/'plan'
    assert main(['refine-plan',str(original),'--config',str(config),'--edits',str(changes),'--output',str(out)])==0
    assert (out/'candidate-preview.json').is_file()
    assert set(x.name for x in out.iterdir())=={
        'refinement-plan.json','candidate-preview.json','review-before.json','review-after.json','refinement-plan.md'
    }
    assert 'NOT approved' in (out/'refinement-plan.md').read_text()
    target=tmp_path/'approved'
    args=['refine-apply',str(original),'--config',str(config),'--plan',str(out/'refinement-plan.json'),
          '--reviewer','human-1','--output',str(target)]
    assert main(args)==1
    assert not target.exists()
    assert main(args+['--acknowledge-review'])==0
    spec=ArchitectureSpec.model_validate_json((target/'architecture.json').read_text())
    assert spec.status=='incomplete_requires_review'
    assert json.loads((target/'refinement-receipt.json').read_text())['reviewer']=='human-1'
    assert 'No changes released' in capsys.readouterr().out


def test_cli_malformed_patch_is_nonzero(tmp_path):
    architecture=EXAMPLES/'generated/ecommerce/architecture.json'
    config=EXAMPLES/'ecommerce.review.json'
    bad=tmp_path/'bad.json'; bad.write_text('{"author":"x","patches":[]}')
    assert main(['refine-plan',str(architecture),'--config',str(config), '--edits',str(bad),'--output',str(tmp_path/'out')])==1
    assert not (tmp_path/'out').exists()


def test_add_quality_target_repairs_missing_requirement():
    spec,config,_=fixtures()
    for c in spec.components:
        c.quality_targets.pop('NFR-002',None)
    review=assess_architecture(spec,config)
    finding=next(f for f in review.quality_review.findings if f.category=='quality_target' and 'NFR-002' in f.requirement_ids)
    edits=RefinementEdits.model_validate({'author':'human','patches':[{
        'id':'QUALITY-PATCH','round':1,'finding_id':finding.id,'finding_category':finding.category,
        'kind':'set_quality_target','rationale':'Add explicit idempotency design objective',
        'component_id':'payment_gateway','requirement_id':'NFR-002',
        'target_text':'Use idempotency keys for repeated payment requests'
    }]})
    _,candidate=plan_refinement(spec,config,edits)
    assert candidate.components[[c.id for c in candidate.components].index('payment_gateway')].quality_targets['NFR-002']


def test_remove_conflicting_sibling_data_owner():
    spec, config, _=fixtures()
    a=next(c for c in spec.components if c.id=='orders')
    b=next(c for c in spec.components if c.id=='inventory')
    a.owned_data.append('Reservation ledger')
    b.owned_data.append('reservation ledger')
    finding=next(f for f in assess_architecture(spec,config).quality_review.findings if f.category=='data_ownership')
    edits=RefinementEdits.model_validate({'author':'human','patches':[{
        'id':'DATA-PATCH','round':1,'finding_id':finding.id,'finding_category':finding.category,
        'kind':'remove_duplicate_data_owner','rationale':'Inventory is the canonical reservation owner',
        'component_id':'orders','data_name':'Reservation Ledger'
    }]})
    _,candidate=plan_refinement(spec,config,edits)
    assert not any(f.category=='data_ownership' for f in assess_architecture(candidate,config).quality_review.findings)
    assert not any(d.casefold()=='reservation ledger' for d in next(c for c in candidate.components if c.id=='orders').owned_data)
    assert not any(d.casefold()=='reservation ledger' for d in a.owned_data[:-1])


def test_planned_verification_cannot_claim_verified():
    spec,config,_=fixtures()
    # Remove a requirement's verification plan, but keep ownership.
    spec.verification_cases=[v for v in spec.verification_cases if 'FR-001' not in v.requirement_ids]
    finding=next(f for f in assess_architecture(spec,config).quality_review.findings if f.category=='requirement_coverage')
    edits=RefinementEdits.model_validate({'author':'human','patches':[{
        'id':'PLAN-PATCH','round':1,'finding_id':finding.id,'finding_category':finding.category,
        'kind':'add_verification_plan','rationale':'Add a review plan; no evidence claimed',
        'verification_case':{'id':'VC-PLAN-NEW','description':'Review catalog listing path',
                             'method':'design_review','requirement_ids':['FR-001'],
                             'component_ids':['catalog'],'status':'planned'}
    }]})
    _,candidate=plan_refinement(spec,config,edits)
    assert 'FR-001' in candidate.coverage_report().planned_only
    assert 'FR-001' not in candidate.coverage_report().verified


def test_malformed_reference_and_duplicate_case_rejected():
    spec,config,_=fixtures()
    spec.verification_cases=[]
    finding=next(f for f in assess_architecture(spec,config).quality_review.findings if f.category=='requirement_coverage')
    edits=RefinementEdits.model_validate({'author':'human','patches':[{
        'id':'PLAN-PATCH','round':1,'finding_id':finding.id,'finding_category':finding.category,
        'kind':'add_verification_plan','rationale':'Missing plan',
        'verification_case':{'id':'VC-PLAN-NEW','description':'Review catalog',
                             'method':'design_review','requirement_ids':['FR-001'],
                             'component_ids':['ghost'],'status':'planned'}
    }]})
    with pytest.raises(ValueError,match='unknown items'):
        plan_refinement(spec,config,edits)
