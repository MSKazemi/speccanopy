"""Checked-in Phase 5 outputs are reproducible, not fictional expert approvals."""
import json
from pathlib import Path

import pytest

from speccanopy.cli import main
from speccanopy.models import ArchitectureSpec

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples'


def test_curated_refinement_preview_matches_committed_snapshots(tmp_path):
    sample = EXAMPLES / 'refinement/generated/ecommerce'
    assert main([
        'refine-plan',str(EXAMPLES/'generated/ecommerce/architecture.json'),
        '--config',str(EXAMPLES/'ecommerce.review.json'),
        '--edits',str(EXAMPLES/'refinement/ecommerce.edits.json'),
        '--output',str(tmp_path),
    ]) == 0
    for file in sample.iterdir():
        if file.name not in {'refinement-plan.json','candidate-preview.json','review-before.json','review-after.json','refinement-plan.md'}:
            continue
        actual = (tmp_path/file.name).read_text(encoding='utf-8')
        expected = file.read_text(encoding='utf-8')
        if file.suffix == '.json':
            assert json.loads(actual) == json.loads(expected)
        else:
            assert actual.rstrip() == expected.rstrip()
    preview = ArchitectureSpec.model_validate_json((tmp_path/'candidate-preview.json').read_text())
    assert preview.status == 'incomplete_requires_review'


@pytest.mark.parametrize('name', ['cli-utility','file-transfer'])
def test_cross_domain_reference_rubric_snapshots(name,tmp_path):
    dest = tmp_path/name
    assert main(['benchmark',str(EXAMPLES/f'generated/{name}/architecture.json'),
                 '--config',str(EXAMPLES/f'{name}.review.json'),
                 '--rubric',str(EXAMPLES/f'refinement/{name}.rubric.json'),
                 '--output',str(dest)]) == 0
    expected=EXAMPLES/f'refinement/generated/{name}/reference-benchmark.json'
    assert json.loads((dest/'reference-benchmark.json').read_text()) == json.loads(expected.read_text())


def test_comparative_rubric_snapshot(tmp_path):
    sample=EXAMPLES/'refinement/generated/ecommerce'
    assert main(['benchmark',str(EXAMPLES/'generated/ecommerce/architecture.json'),
                 '--candidate',str(sample/'candidate-preview.json'),
                 '--config',str(EXAMPLES/'ecommerce.review.json'),
                 '--rubric',str(EXAMPLES/'refinement/ecommerce.rubric.json'),
                 '--output',str(tmp_path)]) == 0
    expected=sample/'reference-benchmark.json'
    assert json.loads((tmp_path/'reference-benchmark.json').read_text()) == json.loads(expected.read_text())
