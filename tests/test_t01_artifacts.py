"""Static artifact classification and explicitly mounted deployment behavior."""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from alienqa.loader import Project
from alienqa.local_run import static_directory


def put(directory, path, content):
    file = directory / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content)
    return file


def test_static_artifact_stays_in_selected_application(tmp_path):
    put(tmp_path, 'web/package.json', '{}')
    put(tmp_path, 'admin/dist/index.html', '<p>Other app</p>')
    project = Project(root=str(tmp_path), app_dir=str(tmp_path / 'web'))
    with pytest.raises(ValueError, match='URL'):
        static_directory(project)


@pytest.mark.parametrize('html', ['<script type="module" src="/src/main.tsx"></script>',
    '<script src="/assets/missing.js"></script>', '<link rel="stylesheet" href="/assets/missing.css">'])
def test_incomplete_or_source_artifact_is_not_served(tmp_path, html):
    put(tmp_path, 'dist/index.html', html)
    with pytest.raises(ValueError):
        static_directory(Project(root=str(tmp_path)))


def test_server_artifact_is_not_static_and_valid_export_is(tmp_path):
    put(tmp_path, '.next/server/app/index.html', '<p>Server output</p>')
    put(tmp_path, 'public/logo.txt', 'asset')
    with pytest.raises(ValueError, match='URL'):
        static_directory(Project(root=str(tmp_path), framework='Next.js'))
    put(tmp_path, 'out/index.html', '<script src="/assets/app.js"></script>')
    put(tmp_path, 'out/assets/app.js', 'console.log("compiled")')
    assert static_directory(Project(root=str(tmp_path), framework='Next.js')) == tmp_path / 'out'


def test_multiple_html_entries_are_resolved_by_shared_rule(tmp_path):
    from alienqa.loader.artifacts import static_entry
    put(tmp_path, 'dist/react.html', '<p>React</p>')
    put(tmp_path, 'dist/vue.html', '<p>Vue</p>')
    project = Project(root=str(tmp_path))
    assert static_entry(project)[1] == 'react.html'
    assert static_entry(project, 'vue.html')[1] == 'vue.html'
    with pytest.raises(ValueError):
        static_entry(project, '../package.json')


def test_mount_and_history_fallback_do_not_hide_missing_assets_or_api(tmp_path):
    from alienqa.static_server import serve
    put(tmp_path, 'index.html', '<h1>SPA</h1>')
    put(tmp_path, 'assets/app.js', 'console.log("loaded")')
    server, base = serve(tmp_path, base_path='/tool/', spa_fallback='index.html')
    try:
        for path in ('details?tab=2', 'assets/app.js'):
            with urlopen(Request(base + path, headers={'Sec-Fetch-Dest': 'document'})) as response:
                assert response.status == 200
        origin = base.removesuffix('/tool/')
        for path in (base + 'assets/missing.js', base + 'api', base + 'api/items', base + '%61pi', origin + '/details', base + 'unknown'):
            with pytest.raises(HTTPError) as error:
                with urlopen(Request(path, headers={} if path.endswith('unknown') else {'Sec-Fetch-Dest': 'document'})):
                    pass
            assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_directory_redirect_retains_mount_and_query(tmp_path):
    from alienqa.static_server import serve
    put(tmp_path, 'about/index.html', '<h1>About</h1>')
    server, base = serve(tmp_path, base_path='/tool/')
    try:
        with urlopen(base + 'about?tab=2') as response:
            assert response.geturl() == base + 'about/?tab=2'
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize('path', ['../tool/', '/tool/../', '/api?key=secret', 'https://host/tool/', '/tool%2f../'])
def test_invalid_mount_is_rejected(path):
    from alienqa.static_server import normalize_base_path
    with pytest.raises(ValueError):
        normalize_base_path(path)
