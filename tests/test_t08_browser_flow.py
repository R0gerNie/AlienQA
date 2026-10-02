"""Real browser pipeline and UI accounting; supplier responses are deterministic."""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from playwright.sync_api import expect

from alienqa.llm import LLMConfig, Role, RoleConfig
from alienqa.llm.metering import load_summary, MeteringSink
from alienqa.loader import ProjectLoader
from alienqa.pipeline import AlienQAPipeline
from alienqa.review import ReportBuilder
from alienqa.run_writer import load_snapshot
from test_ui_app import _make_app
from test_ui_browser_flow import page
from test_t06_browser_flow import serve


def test_six_roles_samples_fallback_repair_and_report_accounting(http_base_url, tmp_path, monkeypatch, page):
    app = _make_app(tmp_path)
    runs = app.config['runs']
    rec = runs.create('test', mode='browser', base_url=f'{http_base_url}/cognition-app/index.html?variant=2')
    config = LLMConfig(roles={role.value: RoleConfig(model=f'test/{role.value}') for role in Role})
    config.roles['judge'].fallbacks = ['test/judge-backup']
    counts = {}
    def completion(**kwargs):
        model = kwargs['model'].split('/')[-1]
        counts[model] = counts.get(model, 0) + 1
        before = load_summary(rec.dir, rec.id)
        assert before['counts']['started'] == 1
        payload = kwargs['messages'][0]['content']
        prompt = payload[0]['text'] if isinstance(payload, list) else payload
        if model == 'gist':
            text = '{"areas":[],"relations":[]}' if '产品地图' in prompt else '保存设置页面'
        elif model == 'expectation':
            text = '{"expectations":[{"text":"保存后应反馈","expectation_basis":{"type":"visible_copy","reference":"保存"}}]}'
        elif model == 'visual':
            text = '{"changes":["no_change"],"summary":"没有变化"}'
        elif model == 'judge' and counts[model] == 1:
            raise TimeoutError('simulated provider timeout')
        elif model == 'judge-backup':
            text = 'invalid JSON'
        elif model == 'judge':
            exp = load_snapshot(rec.dir)['steps'][0]['expectations'][0]
            text = json.dumps({'status': 'mismatch', 'mismatches': [{'expectation_id': exp['id'],
                'expectation': exp['text'], 'observation': '没有反馈', 'level': 'medium', 'reasoning': '应说明操作结果'}]})
        elif model == 'investigator':
            text = '{"root_cause_hypothesis":"待核对","reproduction_steps":[],"technical_evidence":{},"affected_components":[]}'
        else:
            text = '<p>模型补充</p>'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage={'prompt_tokens': 8, 'completion_tokens': 2, 'total_tokens': 10},
            provider_cost={'amount': '0.002', 'currency': 'USD', 'source': 'provider_response'})
    monkeypatch.setattr('alienqa.llm.client._litellm', lambda: SimpleNamespace(completion=completion))
    pipeline = AlienQAPipeline(config, samples=2, max_actions=1, browser='chromium', run_dir=rec.dir,
                              run_id=rec.id, artifacts_dir=rec.dir / 'artifacts', verbose=False)
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(pipeline.collect, ProjectLoader().load_browser(rec.base_url)).result()
    assert not result.incomplete, result.diagnostics
    runs.finish(rec.id, 'done', evidence_count=len(result.evidences), issue_count=len(result.issues))
    runs.finish_usage(rec.id, 'done')
    before = runs.load_usage(rec.id)
    assert set(before['by_role']) == {'gist', 'expectation', 'visual', 'judge', 'investigator'}
    assert before['by_role']['expectation']['logical_calls'] == 2
    assert before['by_role']['judge']['logical_calls'] == 2 and before['by_role']['judge']['attempts'] == 3
    assert before['counts']['failed'] == 1 and before['parse_status']['failed'] == 1
    assert before['unknown_cost_attempts'] == 1 and before['complete']
    rows = MeteringSink(rec.dir, rec.id).read_calls()
    expectation = next(row for row in rows if row['role'] == 'expectation')
    assert expectation['step_id'] == 'ST-00001' and expectation['phase'] == 'expectation'
    assert expectation['input_ref'].endswith('/input/cognitive')
    assert expectation['prompt_version'] == 'general-user-v2'
    repair = next(row for row in rows if row['purpose'] == 'judge_repair')
    assert repair['parent_call_id'] and repair['parse_status'] == 'succeeded'
    app.config['report_builder'] = ReportBuilder(pipeline.client)
    tab, errors = page
    with serve(app) as base:
        tab.goto(base + f'/runs/{rec.id}')
        expect(tab.locator('#llm-usage')).to_contain_text('unknown_cost_attempts')
        tab.get_by_role('link', name='生成 QA 与用户认知分析', exact=True).click()
        expect(tab.locator('body')).to_contain_text('LLM 调用与用量')
        expect(tab.locator('body')).to_contain_text('provider_response')
        after = runs.load_usage(rec.id)
        assert set(after['by_role']) == {role.value for role in Role}
        assert after['attempts'] == before['attempts'] + 1
        assert after['by_role']['reporter']['attempts'] == 1
        # Viewing cached HTML consumes no additional model request.
        tab.reload()
        assert runs.load_usage(rec.id)['attempts'] == after['attempts']
    assert errors == []
    assert (rec.dir / 'usage-summary.json').is_file()
