"""Reference rubric measurements, not architectural correctness claims."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from speccanopy.benchmark import ReferenceRubric, compare_reference, evaluate_reference
from speccanopy.cli import main
from speccanopy.models import ArchitectureSpec
from speccanopy.refinement import RefinementEdits, plan_refinement
from speccanopy.review import ReviewConfig

EXAMPLES = Path(__file__).resolve().parents[1]/'examples'


def fixtures():
    spec = ArchitectureSpec.model_validate_json((EXAMPLES/'generated/ecommerce/architecture.json').read_text())
    config = ReviewConfig.model_validate_json((EXAMPLES/'ecommerce.review.json').read_text())
    rubric = ReferenceRubric.model_validate_json((EXAMPLES/'refinement/ecommerce.rubric.json').read_text())
    changes = RefinementEdits.model_validate_json((EXAMPLES/'refinement/ecommerce.edits.json').read_text())
    _, candidate = plan_refinement(spec,config,changes)
    return spec,config,rubric,candidate


def test_criteria_score_only_structural_presence():
    spec, config, rubric, candidate=fixtures()
    baseline=evaluate_reference(spec,config,rubric)
    after=evaluate_reference(candidate,config,rubric)
    assert baseline.rubric_status=='curated_unreviewed'
    assert after.score>baseline.score
    assert set(baseline.missing_criteria)=={'REF-EC-06','REF-EC-07','REF-EC-08','REF-EC-09','REF-EC-10'}
    assert after.missing_criteria==[]
    assert after.high_or_critical_findings==baseline.high_or_critical_findings
    assert baseline.score<100 and after.score==100
    assert 'NOT' in after.caveat or 'not' in after.caveat


def test_comparison_records_delta_and_no_new_gaps():
    spec,config,rubric,candidate=fixtures()
    result=compare_reference(spec,candidate,config,rubric)
    assert result.delta_points>0
    assert result.introduced_missing_criteria==[]
    assert result.reduced_high_or_critical==0
    assert result.before.uncovered_mandatory==result.after.uncovered_mandatory


def test_comparison_rejects_different_brief():
    spec,config,rubric,candidate=fixtures()
    candidate.brief.system='Different system'
    with pytest.raises(ValueError,match='same original system brief'):
        compare_reference(spec,candidate,config,rubric)


def test_rubric_rejects_unsubstantiated_reviewer_and_duplicate():
    _,_,rubric,_=fixtures()
    data=rubric.model_dump(mode='json'); data['status']='reviewer_attested'
    with pytest.raises(ValidationError, match='reviewer identifier'):
        ReferenceRubric.model_validate(data)
    data=rubric.model_dump(mode='json'); data['reviewer']='Anonymous'
    with pytest.raises(ValidationError,match='unreviewed'):
        ReferenceRubric.model_validate(data)
    data=rubric.model_dump(mode='json'); data['criteria'][1]['id']=data['criteria'][0]['id']
    with pytest.raises(ValidationError,match='unique'):
        ReferenceRubric.model_validate(data)


def test_rubric_rejects_invalid_criterion_payload():
    _,_,rubric,_=fixtures()
    data=rubric.model_dump(mode='json'); data['criteria'][0]['source_id']='payments'
    with pytest.raises(ValidationError,match='requires exactly'):
        ReferenceRubric.model_validate(data)
    data=rubric.model_dump(mode='json');data['criteria'][0]['kind']='guaranteed_correct'
    with pytest.raises(ValidationError):
        ReferenceRubric.model_validate(data)


def test_rubric_scenario_config_must_be_supported():
    spec,config,rubric,_=fixtures()
    config.scenarios=[]
    with pytest.raises(ValueError,match='not in review configuration'):
        evaluate_reference(spec,config,rubric)


def test_cli_evaluation_and_comparison(tmp_path):
    spec,config,rubric,candidate=fixtures()
    original=EXAMPLES/'generated/ecommerce/architecture.json'
    config_file=EXAMPLES/'ecommerce.review.json'
    rubric_file=EXAMPLES/'refinement/ecommerce.rubric.json'
    candidate_file=tmp_path/'candidate.json'; candidate_file.write_text(candidate.model_dump_json())
    out=tmp_path/'benchmark'
    args=['benchmark',str(original),'--config',str(config_file),'--rubric',str(rubric_file),'--output',str(out)]
    assert main(args)==0
    assert json.loads((out/'reference-benchmark.json').read_text())['score']<100
    assert main(args+['--candidate',str(candidate_file)])==0
    report=json.loads((out/'reference-benchmark.json').read_text())
    assert report['delta_points']>0
    assert 'not an expert architecture certificate' in (out/'reference-benchmark.md').read_text()


def test_cli_fails_for_bad_benchmark_files(tmp_path):
    original=EXAMPLES/'generated/ecommerce/architecture.json'
    config=EXAMPLES/'ecommerce.review.json'
    bad=tmp_path/'missing.json'
    assert main(['benchmark',str(original),'--config',str(config),'--rubric',str(bad),'--output',str(tmp_path/'out')])==1
