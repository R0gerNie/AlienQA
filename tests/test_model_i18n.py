"""Language contracts for generated prose and conservative expectation merging."""
import json
from types import SimpleNamespace

import pytest

from alienqa.llm import LLMClient, LLMConfig, LlmRoles, RoleConfig
from alienqa.expectation.contracts import expression_templates, merge_samples
from alienqa.expectation.sampling import recognize_feedback, relation
from alienqa.evidence.severity import classify


@pytest.mark.parametrize('data,expected', [({}, 'zh'), ({'language': 'en'}, 'en'),
    ({'language': 'en-US'}, 'en'), ({'llm': {'language': 'en'}}, 'en'),
    ({'language': 'en', 'llm': {'language': 'zh'}}, 'en')])
def test_model_configuration_has_validated_language(data, expected):
    assert LLMConfig.from_dict(data).language == expected


def test_invalid_model_language_is_rejected():
    with pytest.raises(ValueError):
        LLMConfig.from_dict({'language': 'fr'})


class Capture:
    def __init__(self, language='en'):
        self.config = LLMConfig(language=language)
        self.calls = []
    def complete(self, role, messages):
        self.calls.append((role, messages))
        return SimpleNamespace(text='{"expectations":[]}', call_id='')
    def complete_vision(self, role, text, images):
        self.calls.append((role, text))
        return SimpleNamespace(text='{}', call_id='')


@pytest.mark.parametrize('invoke', [
    lambda r: r.summarize_gist('README', 'surface'),
    lambda r: r.map_product('gist', 'surface', repair=True),
    lambda r: r.locate_unit('保存', '', '', [], repair=True),
    lambda r: r.detect_entry('unit', '', ['index.html'], repair=True),
    lambda r: r.generate_expectations('', '保存', samples=1, action_desc='click 保存', with_basis=True),
    lambda r: r.judge('click 保存', 'Original expectation', b'b', b'a', repair=True),
    lambda r: r.observe_visual(b'b', b'a', 'click 保存'),
    lambda r: r.investigate('Original evidence', repair=True),
    lambda r: r.compose_report('{}'),
])
def test_every_role_requests_english_prose_without_translating_quotes(invoke):
    client = Capture()
    invoke(LlmRoles(client))
    request = client.calls[0][1]
    if isinstance(request, list):
        assert request[0]['role'] == 'system'
        request = request[0]['content']
    assert 'English' in request
    assert 'verbatim' in request


def test_report_language_is_per_call_and_does_not_mutate_config():
    client = Capture('zh')
    roles = LlmRoles(client)
    roles.compose_report('{}', language='en')
    assert client.calls[-1][1][0]['role'] == 'system'
    roles.compose_report('{}')
    assert client.calls[-1][1][0]['role'] == 'user'
    assert client.config.language == 'zh'


def test_real_vision_request_carries_system_language_instruction(monkeypatch):
    calls = []
    def completion(**kwargs):
        calls.append(kwargs)
        return {'choices': [{'message': {'content': '{}'}}]}
    monkeypatch.setattr('alienqa.llm.client._litellm', lambda: SimpleNamespace(completion=completion))
    client = LLMClient(LLMConfig(language='en', roles={'visual': RoleConfig(model='gpt-test')}))
    LlmRoles(client).observe_visual(b'b', b'a', 'click 保存')
    assert calls[0]['messages'][0]['role'] == 'system'
    assert calls[0]['messages'][1]['content'][1]['type'] == 'image_url'


@pytest.mark.parametrize('kind,rule', [('click', 'operation_feedback.visible_result'),
    ('type', 'input_value.visible_content'), ('blur', 'input_focus.blur_cursor')])
def test_english_templates_keep_same_rules_and_visible_control(kind, rule):
    template = expression_templates(f'{kind} 保存', language='en')[0]
    assert '应' not in template['text']
    if kind != 'click':
        assert '保存' in template['text']
    claim = recognize_feedback(template['text'], f'{kind} 保存')
    assert claim.rule_id == rule
    assert recognize_feedback(template['text'] + ' within 2 seconds', f'{kind} 保存') is None
    if kind != 'click':
        assert recognize_feedback(template['text'], f'{kind} Delete') is None


def test_english_feedback_conflicts_and_constrained_claims_stay_conservative():
    positive = recognize_feedback('After this operation, visible result feedback should be provided.', 'click Save')
    negative = recognize_feedback('After this operation, feedback should not be provided.', 'click Save')
    assert relation(positive, negative) == 'conflict'
    assert recognize_feedback('After clicking Delete, the page should show a save result.', 'click Delete') is None
    assert recognize_feedback('After this operation, a green success message should appear.', 'click Save') is None
    assert recognize_feedback('After clicking Save, visible feedback should be provided.', 'click Delete') is None


@pytest.mark.parametrize('text,expected', [('misleading wording', 'misleading_copy'),
    ('The feedback is missing', 'missing_feedback'), ('No confirmation appears', 'missing_feedback'),
    ('The success message is absent', 'missing_feedback'), ('Button looks clickable', 'ux_ambiguity')])
def test_classification_supports_english_with_chinese_parity(text, expected):
    mismatch = SimpleNamespace(expectation=text, observation='', reasoning='')
    assert classify(mismatch, None, None) == expected


def test_copy_action_is_not_mistaken_for_interface_wording():
    mismatch = SimpleNamespace(expectation='Copy should copy the selected text', observation='No copied text', reasoning='')
    assert classify(mismatch, None, None) == 'ux_ambiguity'


def test_english_merge_preserves_evidence_text_and_basis():
    rows = [[{'text': 'After this operation, visible result feedback should be provided.',
              'expectation_basis': {'type': 'interaction_convention', 'reference': 'ordinary feedback'}}],
            [{'text': 'After clicking 保存, visible feedback should be provided.',
              'expectation_basis': {'type': 'visible_copy', 'reference': '保存'}}]]
    before = json.dumps(rows, ensure_ascii=False)
    diagnostic = {}
    accepted, _ = merge_samples(rows, action_desc='click 保存', diagnostics=diagnostic)
    assert len(accepted) == 1
    assert diagnostic['groups'][0]['rule_id'] == 'operation_feedback.visible_result'
    assert json.dumps(rows, ensure_ascii=False) == before


def test_standalone_english_engine_records_language_and_localizes_errors():
    from alienqa.expectation import ExpectationEngine, PageInfo
    from alienqa.context import ExplorerContext
    from alienqa.driver import Action, Target
    client = Capture('en')
    engine = ExpectationEngine(client, samples=1)
    engine.expect(ExplorerContext(visible_text='保存'), PageInfo(), Action('click', Target()))
    assert engine.last_input['language'] == 'en'
    assert engine.last_input['prompt_version'] == 'general-user-v4-en'
    assert engine.last_input['visible_text'] == '保存'
    assert engine.last_input['action'] == 'click Unlabeled control'
    assert engine.evaluate([], None).error == 'There are no verifiable expectations for this action'


def test_english_pipeline_saves_language_and_diagnostics_without_translating_page(monkeypatch, tmp_path, capsys):
    from alienqa.pipeline import AlienQAPipeline
    from alienqa.loader import Project
    from alienqa.driver.runtime import RuntimeSignals
    from alienqa.mapper import ProductMap
    class Driver:
        def __init__(self, **kwargs): pass
        def launch(self, *args, **kwargs): pass
        def close(self): pass
        def url(self): return 'http://app.test/'
        def visible_text(self): return '保存'
        def screenshot(self): return b'image'
        def collect_runtime(self): return RuntimeSignals()
        def interactive_elements(self): return []
    monkeypatch.setattr('alienqa.pipeline.PlaywrightDriver', Driver)
    monkeypatch.setattr('alienqa.pipeline.ProductMapper.map_from_browser', lambda *args: ProductMap())
    pipeline = AlienQAPipeline(LLMConfig(language='en'), run_dir=tmp_path, max_actions=1)
    result = pipeline.collect(Project(input_type='browser'))
    assert result.language == 'en'
    assert any(d['error'].startswith('No interactive actions were executed') for d in result.diagnostics)
    assert '[02b] Reading visible browser text' in capsys.readouterr().out
    saved = json.loads((tmp_path / 'scan.json').read_text())
    assert saved['language'] == 'en'
    assert all('无法' not in d['error'] for d in saved['diagnostics'])
