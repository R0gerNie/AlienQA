"""Explicit startup language wins over automatic browser detection."""
from types import SimpleNamespace

from alienqa import __main__ as cli
from alienqa.review import HumanReview, ReportBuilder, create_app
from alienqa.ui import create_ui_app
from test_ui_app import _make_app


def test_explicit_english_startup_overrides_chinese_browser(tmp_path):
    original = _make_app(tmp_path)
    app = create_ui_app(original.config['config_path'], str(tmp_path / 'settings-en.yaml'),
                        str(tmp_path / 'runs-en'), language='en')
    client = app.test_client()
    response = client.get('/', headers={'Accept-Language': 'zh-CN,zh;q=0.9'})
    assert '<html lang="en">' in response.get_data(as_text=True)
    # The user's later deliberate switch still takes priority.
    client.get('/language/zh?next=/')
    assert '<html lang="zh">' in client.get('/').get_data(as_text=True)


def test_configured_english_startup_overrides_chinese_browser(tmp_path):
    original = _make_app(tmp_path)
    from pathlib import Path
    config = Path(original.config['config_path'])
    config.write_text(config.read_text() + '\nlanguage: en\n')
    app = create_ui_app(str(config), str(tmp_path / 'settings-en.yaml'), str(tmp_path / 'runs-en'))
    assert '<html lang="en">' in app.test_client().get('/', headers={'Accept-Language': 'zh-CN'}).get_data(as_text=True)


def test_browser_detected_language_is_used_without_startup_override(tmp_path):
    app = _make_app(tmp_path)
    assert '<html lang="en">' in app.test_client().get('/', headers={'Accept-Language': 'en-US'}).get_data(as_text=True)


def test_standalone_review_respects_explicit_startup_language():
    app = create_app(HumanReview(), ReportBuilder(SimpleNamespace()), language='en')
    assert '<html lang="en">' in app.test_client().get('/', headers={'Accept-Language': 'zh-CN'}).get_data(as_text=True)


def test_cli_default_allows_browser_language_detection(monkeypatch):
    import alienqa.ui
    monkeypatch.delenv('ALIENQA_LANGUAGE', raising=False)
    selected = []
    monkeypatch.setattr(alienqa.ui, 'create_ui_app', lambda *args, **kwargs:
                        selected.append(kwargs['language']) or SimpleNamespace(run=lambda **kwargs: None))
    monkeypatch.setattr(cli, '_load_keys', lambda: None)
    assert cli.main(['--ui']) == 0
    assert selected == [None]
