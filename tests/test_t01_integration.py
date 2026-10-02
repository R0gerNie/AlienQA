"""One selected application and one deployment contract across consumers."""
from types import SimpleNamespace

import pytest

from alienqa.loader import Project, VisibleFile
from alienqa.local_run import ScanInput
from alienqa.ui.runs import RunManager


def test_deployment_input_and_history_are_persisted(tmp_path):
    inputs = ScanInput.from_dict({'project_path': str(tmp_path), 'base_path': '/tool',
                                 'spa_fallback': True, 'static_entry': 'web.html'})
    assert inputs.base_path == '/tool/' and inputs.spa_fallback is True
    runs = RunManager(tmp_path / 'runs')
    rec = runs.create(str(tmp_path), entry=inputs.static_entry, base_path=inputs.base_path,
                      spa_fallback=inputs.spa_fallback)
    facts = {'app_dir': str(tmp_path), 'routes': ['/users/:id']}
    runs.update_target(rec.id, 'web.html', 'http://localhost/tool/web.html', source_context=facts)
    saved = runs.get(rec.id)
    assert saved.source_context == facts
    assert saved.base_path == '/tool/' and saved.spa_fallback is True


@pytest.mark.parametrize('data', [{'spa_fallback': 'true'}, {'base_path': '/a/../'},
                                 {'url': 'http://localhost', 'spa_fallback': True}])
def test_invalid_or_inapplicable_deployment_input(data, tmp_path):
    with pytest.raises(ValueError):
        ScanInput.from_dict({'project_path': str(tmp_path), **data})


def test_console_uses_deterministic_entry_and_records_deployment(tmp_path):
    from alienqa.ui.app import _prepare_project
    (tmp_path / 'web.html').write_text('<button>Save</button>')
    rec = RunManager(tmp_path / 'runs').create(str(tmp_path), entry='', base_path='/tool/', spa_fallback=True)
    detector = SimpleNamespace(detect=lambda *args: pytest.fail('entry selection must not call a model'))
    project, server = _prepare_project(rec, detector)
    try:
        assert project.base_url.endswith('/tool/web.html')
        metadata = project.artifacts['static_server']
        assert metadata['base_path'] == '/tool/' and metadata['spa_fallback'] == 'web.html'
        assert project.entry_points == ['web.html']
    finally:
        server.shutdown()
        server.server_close()


def test_investigation_and_mapping_cannot_read_another_application(tmp_path):
    from alienqa.investigation.retriever import retrieve_source
    from alienqa.mapper.filter import build_surface_text
    for name in ('web', 'admin'):
        directory = tmp_path / name
        directory.mkdir()
        (directory / 'Page.jsx').write_text(f'<button>{name} UNIQUE</button>')
    project = Project(root=str(tmp_path), app_dir=str(tmp_path / 'web'), visible_files=[
        VisibleFile('admin/Page.jsx'), VisibleFile('web/Page.jsx')])
    for text in (retrieve_source(project, None), build_surface_text(project, tmp_path)):
        assert 'web UNIQUE' in text and 'admin UNIQUE' not in text


def test_mapping_reads_selected_app_readme(tmp_path, monkeypatch):
    from alienqa.mapper.mapper import ProductMapper
    from alienqa.mapper.models import ProductMap
    from alienqa.llm import LLMClient, LLMConfig
    (tmp_path / 'web').mkdir()
    (tmp_path / 'README.md').write_text('Entire repository')
    (tmp_path / 'web/README.md').write_text('Selected product')
    mapper = ProductMapper(LLMClient(LLMConfig.from_dict({})))
    captured = []
    mapper.roles.summarize_gist = lambda readme, surface: captured.append(readme) or 'gist'
    monkeypatch.setattr(mapper, '_extract', lambda *args: ProductMap())
    mapper.map(Project(root=str(tmp_path), app_dir=str(tmp_path / 'web')))
    assert captured == ['Selected product']


def test_subpath_does_not_validate_root_relative_assets(tmp_path):
    from alienqa.loader.artifacts import static_entry
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets/app.js').write_text('compiled')
    (tmp_path / 'index.html').write_text('<script src="/assets/app.js"></script>')
    with pytest.raises(ValueError, match='前缀'):
        static_entry(Project(root=str(tmp_path)), base_path='/tool/')
