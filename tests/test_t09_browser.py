"""Paired fixtures: actual facts, fresh contexts, API exceptions and fault replay."""
from copy import deepcopy
from pathlib import Path

import pytest
from playwright.sync_api import expect

from alienqa.acceptance import load_manifest, product_input, serve_cases
from alienqa.driver import Action, PlaywrightDriver
from alienqa.evidence import EvidenceEngine
from alienqa.observation.runtime_observer import RuntimeObserver
from alienqa.replay import ReplayEngine

ROOT=Path(__file__).parent/'fixtures/cases'
CASES=load_manifest(ROOT/'manifest.json')['cases']


@pytest.fixture(scope='module')
def case_base():
    server, base=serve_cases(ROOT/'public')
    try: yield base
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_pair_facts_and_fresh_reset(case_base,case,tmp_path):
    for repeat in range(2):
        driver=PlaywrightDriver(browser='chromium')
        try:
            driver.launch(product_input(case,case_base)['url'])
            initial=driver._page.locator('#controls').inner_text()
            before=deepcopy(driver.collect_runtime())
            for index,row in enumerate(case['actions'],1):
                driver.set_runtime_context('t09',f'ST-{index}',f'A-{index}','action')
                result=driver.execute(Action.from_dict(row))
                assert result['status']=='completed',result
            for assertion in case['assertions']:
                kind,value=assertion['kind'],assertion['value']
                if kind=='text':expect(driver._page.locator(assertion['selector'])).to_have_text(value)
                if kind=='count':expect(driver._page.locator(assertion['selector'])).to_have_count(value)
                if kind=='url_contains':assert value in driver._page.url
                if kind=='page_error':assert any(value in e for e in driver.collect_runtime().page_errors)
                if kind=='http_status':assert any(e['kind']=='http_response' and e['payload']['status']==value for e in driver.collect_runtime().records)
            if repeat==0 and case['id'] in ('save-abnormal','technical-abnormal'):
                evidence=EvidenceEngine(tmp_path/'artifacts').build_technical(RuntimeObserver().observe(driver,before),
                    Action.from_dict(case['actions'][-1]),driver=driver,step_id='ST-1',action_id='A-1')[0]
            if repeat==0:first_initial=initial
            else:assert initial==first_initial
        finally:driver.close()
    if case['id'] in ('save-abnormal','technical-abnormal'):
        engine=ReplayEngine(tmp_path/'replay');engine.save(evidence)
        replay=engine.replay(evidence.id)
        assert replay.status=='reproduced',replay.note


def test_evaluator_labels_not_exposed_by_fixture_server(case_base):
    from urllib.error import HTTPError
    from urllib.request import urlopen
    with pytest.raises(HTTPError) as failure:urlopen(case_base+'/../manifest.json')
    assert failure.value.code==404
