"""Actual bounded evaluator + production pipeline; protocol substitute only."""
import json
from pathlib import Path
import sys
import uuid

from alienqa.evaluation import main
from alienqa.run_writer import load_snapshot

ROOT=Path(__file__).resolve().parents[1]


def test_real_pipeline_evaluator_preserves_private_labels_pending_review_and_commits():
    directory=ROOT/'artifacts/evaluation/t09-offline'/uuid.uuid4().hex
    directory.mkdir(parents=True)
    executable=directory/'offline-model'
    executable.write_text(f'#!{sys.executable}\n'+(ROOT/'tests/fixtures/t07-model-provider.py').read_text())
    executable.chmod(0o700)
    config=directory/'config.json'
    config.write_text(json.dumps({'llm':{'codex':{'executable':str(executable)},'roles':{
        role:{'model':f'codex/{role}'} for role in ('gist','expectation','visual','judge','investigator','reporter')}}}))
    output=directory/'runs'
    result=main(['--config',str(config),'--manifest',str(ROOT/'tests/fixtures/cases/manifest.json'),
                 '--cases','save-normal','save-abnormal','history-normal','--max-calls','100','--inference-kind','substitute',
                 '--samples','1','--output',str(output)])
    assert result in (0,2)
    saved=json.loads((output/'evaluation.json').read_text())
    assert len(saved['runs'])==3 and saved['invocations_used']>0
    assert all(row['status'] in ('completed','partial') for row in saved['runs'])
    for row in saved['runs']:
        committed=load_snapshot(output/row['id'])
        assert committed['phase']=='terminal' and committed['checkpoint_seq']==row['checkpoint_seq']
        assert (output/row['id']/'analysis.html').is_file()
    calls=[json.loads(line) for line in executable.with_suffix('.calls.jsonl').read_text().splitlines()]
    assert len(calls)==saved['invocations_used']
    assert sum(row['usage']['attempts'] for row in saved['runs'])==saved['invocations_used']
    for call in calls:
        assert 'EVALUATOR_ONLY_' not in call['prompt'] and 'known_problem' not in call['prompt']
        if call['model'] in ('expectation','judge'):
            assert 'save-abnormal' not in call['prompt'] and 'variant_kind' not in call['prompt']
    review=json.loads((output/'review-template.json').read_text())
    assert all(row['reference'].get('sentinel','').startswith('EVALUATOR_ONLY_') for row in review['runs'])
    assert all(row['review_status']=='pending' and not row['independent'] for row in review['runs'])
    assert saved['summary']['n06_closed'] is False
