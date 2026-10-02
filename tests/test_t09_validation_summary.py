import json

import pytest

from scripts.summarize_t09_validation import main, test_record as record


@pytest.mark.parametrize('content,status',[
    ('<testcase name="ok"/>','passed'),
    ('<testcase name="bad"><failure/></testcase>','failed'),
    ('<testcase name="skip"><skipped/></testcase>','blocked'),
    ('','blocked'),
])
def test_junit_preserves_failed_skipped_and_empty(tmp_path,content,status):
    xml=tmp_path/'junit.xml';xml.write_text('<testsuite>'+content+'</testsuite>')
    assert record(xml,'structure')['status']==status


def test_summary_separates_levels_and_refuses_partial_installation(tmp_path):
    xml=tmp_path/'junit.xml';xml.write_text('<testsuite><testcase name="ok"/></testsuite>')
    out=tmp_path/'summary.json'
    assert main(['--structural-junit',str(xml),'--output',str(out)])==0
    saved=json.loads(out.read_text())
    assert saved['levels']['structure']=='passed'
    assert saved['levels']['browser_mechanism']=='not_run' and saved['release_ready'] is False
    install=tmp_path/'install.json';install.write_text(json.dumps({'status':'passed','environments':[{'kind':'wheel'}]}))
    with pytest.raises(ValueError):main(['--installation',str(install),'--output',str(out)])


def test_substitute_evaluation_does_not_certify_real_model(tmp_path):
    evaluation=tmp_path/'evaluation.json'
    evaluation.write_text(json.dumps({'inference_kind':'substitute','runs':[], 'summary':{'n06_closed':False}}))
    out=tmp_path/'summary.json'
    main(['--evaluation',str(evaluation),'--output',str(out)])
    assert json.loads(out.read_text())['levels']['real_model']=='not_run'


@pytest.mark.parametrize('status,level',[('completed','passed'),('partial','blocked'),('error','failed')])
def test_real_evaluation_execution_does_not_close_effect_gate(tmp_path,status,level):
    evaluation=tmp_path/'evaluation.json'
    evaluation.write_text(json.dumps({'inference_kind':'real','invocations_used':2,
        'runs':[{'id':'r','status':status}], 'summary':{'n06_closed':False}}))
    out=tmp_path/'summary.json'
    main(['--evaluation',str(evaluation),'--output',str(out)])
    saved=json.loads(out.read_text())
    assert saved['levels']['real_model']==level and saved['release_ready'] is False


def test_pending_optional_review_does_not_block_complete_engineering_summary(tmp_path):
    from alienqa.acceptance import review_template
    xml=tmp_path/'tests.xml'
    xml.write_text('<testsuite><testcase name="ok"/></testsuite>')
    installation=tmp_path/'installation.json'
    installation.write_text(json.dumps({'status':'passed','environments':[
        {'kind':kind,'system_site_packages':False,'pip_check':'passed'} for kind in ('wheel','sdist')]}))
    rows=[{'id':'run','status':'completed','steps':[]}]
    evaluation=tmp_path/'evaluation.json'
    evaluation.write_text(json.dumps({'inference_kind':'real','invocations_used':2,'runs':rows}))
    review=tmp_path/'feedback.json'
    review.write_text(json.dumps(review_template(rows, [])))
    output=tmp_path/'summary.json'
    assert main(['--junit',str(xml),'--structural-junit',str(xml),'--installation',str(installation),
                 '--evaluation',str(evaluation),'--review',str(review),'--output',str(output)])==0
    saved=json.loads(output.read_text())
    assert saved['release_ready'] and saved['levels']['independent_review']=='blocked'
    assert saved['assessment']['required_for_acceptance'] is False
