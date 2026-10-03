"""Locale selection stays local to each request and preserves source content."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from flask import Flask, jsonify, render_template_string

from alienqa.i18n import (get_language, install_flask_i18n, language_context,
                          normalize_language, t, translate_text)


@pytest.mark.parametrize('value, expected', [('en', 'en'), ('en-US', 'en'),
                                            ('zh-CN', 'zh'), ('ZH_tw', 'zh')])
def test_language_aliases(value, expected):
    assert normalize_language(value) == expected


def test_invalid_language_is_rejected():
    with pytest.raises(ValueError, match='Unsupported language'):
        normalize_language('fr')


def test_context_is_nested_and_thread_local():
    with language_context('en'):
        assert get_language() == 'en'
        with language_context('zh'):
            assert get_language() == 'zh'
        assert get_language() == 'en'
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(get_language).result() == 'zh'
    assert get_language() == 'zh'


def test_translation_preserves_user_values(monkeypatch):
    monkeypatch.setattr('alienqa.i18n._messages', lambda: {'无法打开 {path}': 'Cannot open {path}'})
    with language_context('en'):
        assert t('无法打开 {path}', path='用户文件.html') == 'Cannot open 用户文件.html'
        assert translate_text('无法打开 用户文件.html') == 'Cannot open 用户文件.html'
        assert translate_text('用户自己的中文描述') == '用户自己的中文描述'
    assert t('无法打开 {path}', path='用户文件.html') == '无法打开 用户文件.html'


@pytest.fixture
def app():
    app = Flask(__name__)
    install_flask_i18n(app)

    @app.get('/')
    def index():
        return render_template_string('<html lang="{{ language }}">{{ language_url("zh") }}</html>')

    @app.get('/error')
    def error():
        return jsonify(error='需要 JSON 对象', note='用户原文'), 400

    return app


def test_request_precedence_and_persistence(app):
    client = app.test_client()
    assert b'lang="zh"' in client.get('/').data
    assert b'lang="en"' in client.get('/', headers={'Accept-Language': 'en-US,en;q=0.9'}).data
    response = client.get('/?lang=en', headers={'Accept-Language': 'zh'})
    assert b'lang="en"' in response.data
    assert b'lang="en"' in client.get('/').data
    assert b'lang="zh"' in client.get('/?lang=zh').data


def test_regional_browser_preferences_respect_quality(app):
    response = app.test_client().get('/', headers={'Accept-Language': 'zh-CN, en;q=0.5'})
    assert b'lang="zh"' in response.data
    assert response.headers['Content-Language'] == 'zh'


def test_catalog_preserves_named_placeholders():
    from alienqa.i18n import _messages
    import re
    fields = re.compile(r'\{([A-Za-z_]\w*)(?:![rsa])?(?::[^{}]*)?\}')
    for source, target in _messages().items():
        assert set(fields.findall(source)) == set(fields.findall(target)), source


@pytest.mark.parametrize('destination', ['https://evil.example', '//evil.example', '/\\evil.example'])
def test_language_switch_rejects_external_redirects(app, destination):
    response = app.test_client().get('/language/en', query_string={'next': destination})
    assert response.location == '/'


def test_language_switch_preserves_local_destination(app):
    client = app.test_client()
    response = client.get('/language/en?next=/history?sort=alphabetical')
    assert response.location == '/history?sort=alphabetical'
    assert b'lang="en"' in client.get('/').data


def test_api_error_localization_preserves_payload_and_status(app):
    response = app.test_client().get('/error?lang=en')
    assert response.status_code == 400
    assert response.json == {'error': 'A JSON object is required', 'note': '用户原文'}
