"""Versioned acceptance cases and evaluator-side adjudication contracts."""
import json
from pathlib import Path

import pytest

from alienqa import acceptance

MANIFEST = Path(__file__).parent / 'fixtures/cases/manifest.json'


def test_versioned_cases_have_pairs_reset_and_private_labels():
    manifest = acceptance.load_manifest(MANIFEST)
    cases = manifest['cases']
    assert {c['family'] for c in cases} == {'save', 'delete', 'filter', 'modal', 'navigation', 'technical', 'history'}
    for family in ('save', 'delete', 'filter', 'modal', 'navigation', 'technical'):
        assert {c['variant_kind'] for c in cases if c['family'] == family} >= {'normal', 'abnormal', 'reasonable_exception'}
    assert all(c['reset'] and c['assertions'] for c in cases)
    assert len({c['id'] for c in cases}) == len(cases)
    for case in cases:
        prepared = acceptance.product_input(case, 'http://localhost:9000')
        encoded = json.dumps(prepared)
        assert 'assertions' not in prepared and 'labels' not in prepared and 'reference' not in prepared
        assert case['labels']['sentinel'] not in encoded and 'abnormal' not in encoded


@pytest.mark.parametrize('mutation', ['duplicate', 'outside', 'absolute', 'missing_reset', 'leaked_task'])
def test_bad_manifest_is_rejected_with_context(tmp_path, mutation):
    data = json.loads(MANIFEST.read_text())
    if mutation == 'duplicate': data['cases'].append(data['cases'][0])
    if mutation == 'outside': data['cases'][0]['entry'] = '../private.json'
    if mutation == 'absolute': data['cases'][0]['entry'] = 'https://foreign.test'
    if mutation == 'missing_reset': data['cases'][0]['reset'] = ''
    if mutation == 'leaked_task': data['cases'][0]['unit'] = data['cases'][0]['labels']['sentinel']
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): acceptance.load_manifest(path)


def test_review_template_does_not_invent_independent_review():
    manifest = acceptance.load_manifest(MANIFEST)
    cases = manifest['cases'][:2]
    rows = [{'id': c['id']+'-run-1', 'case_id': c['id'], 'status': 'completed', 'steps': [], 'run_id': 'R'} for c in cases]
    review = acceptance.review_template(rows, cases)
    assert all(row['review_status'] == 'pending' and row['reviewer'] == '' and row['review_minutes'] is None for row in review['runs'])
    assert acceptance.assess(rows, cases, review)['independent_review_complete'] is False


def test_opaque_evaluation_ids_keep_human_reference_labels():
    case=acceptance.load_manifest(MANIFEST)['cases'][0]
    planned={**case,'case_id':case['id'],'id':'case-001-run-1'}
    review=acceptance.review_template([{**planned,'status':'completed'}],[planned])
    assert review['runs'][0]['reference']==case['labels']


def test_metrics_keep_unexplored_faults_and_design_exceptions():
    cases = acceptance.load_manifest(MANIFEST)['cases']
    selected = [next(c for c in cases if c['id'] == name) for name in ('save-normal','save-abnormal','technical-abnormal','save-exception')]
    rows = [{'id': c['id']+'-run-1', 'case_id': c['id'], 'status': 'not_started' if c['id']=='technical-abnormal' else 'completed', 'steps': [] if c['id']=='technical-abnormal' else [{'execution_status':'completed'}]} for c in selected]
    review = acceptance.review_template(rows, selected)
    for row in review['runs'][:2] + review['runs'][3:]:
        row.update(review_status='reviewed', reviewer='external-reviewer', independent=True, review_minutes=2,
                   expectation_reasonable=True, merge_correct=True, judgment_matches_visible=True,
                   disposition='reasonable_design' if row['case_id']=='save-exception' else 'useful_finding',
                   found_expected=row['case_id']=='save-abnormal', complaint_is_false=False, notes='Visible facts checked')
    result = acceptance.assess(rows, selected, review)
    assert result['discovery'] == {'numerator': 1, 'denominator': 2, 'unexplored': 1}
    assert result['reasonable_design_runs'] == 1 and result['false_complaints']['numerator'] == 0
    assert result['independent_review_complete'] is False and result['release_effect_gate'] is False
    assert result['review_minutes'] == 6


def test_reviews_cannot_be_attached_to_unknown_or_changed_run():
    cases = acceptance.load_manifest(MANIFEST)['cases'][:1]
    rows = [{'id': 'run', 'case_id': cases[0]['id'], 'status': 'completed', 'steps': []}]
    review = acceptance.review_template(rows, cases)
    review['runs'][0]['id'] = 'other'
    with pytest.raises(ValueError): acceptance.assess(rows, cases, review)


def test_evidence_matrix_does_not_upgrade_local_or_stub_results():
    matrix = acceptance.evidence_matrix([{'id':'core', 'level':'browser_mechanism','status':'passed',
        'platform':'macOS', 'python':'3.11', 'models':'substitute', 'result':'artifacts/example.json'}])
    assert matrix['levels']['real_model'] == 'not_run'
    assert matrix['levels']['installation'] == 'not_run'
    assert matrix['platforms'].get('Ubuntu') == 'not_run'
    assert matrix['release_ready'] is False


@pytest.mark.parametrize('duration',[float('nan'),float('inf'),-1])
def test_invalid_human_review_time_cannot_close_review(duration):
    cases=acceptance.load_manifest(MANIFEST)['cases'][:1]
    rows=[{'id':'run','case_id':cases[0]['id'],'status':'completed','steps':[]}]
    review=acceptance.review_template(rows,cases)
    review['runs'][0].update(review_status='reviewed',reviewer='human',independent=True,
        review_minutes=duration,expectation_reasonable=True,merge_correct=True,judgment_matches_visible=True,
        found_expected=False,complaint_is_false=False,disposition='reasonable_design',notes='Checked')
    with pytest.raises(ValueError):acceptance.assess(rows,cases,review)


def test_blocked_evidence_is_not_overwritten_by_another_pass():
    records=[{'id':str(i),'level':'installation','status':status,'result':'artifact.json'}
             for i,status in enumerate(('blocked','passed'))]
    assert acceptance.evidence_matrix(records)['levels']['installation']=='blocked'
