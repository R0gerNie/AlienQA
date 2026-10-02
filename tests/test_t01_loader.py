"""T01 selected application, bounded recognition and structural route contracts."""
import json
from pathlib import Path

import pytest

from alienqa.loader import ProjectLoader
from alienqa.local_run import select_project


def write(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text if isinstance(text, str) else json.dumps(text))
    return p


def app(root, directory='', framework='react', dev=False):
    base = root / directory
    dependencies = {'react': '19', 'react-dom': '19'} if framework == 'react' else {framework: 'latest'}
    write(base, 'package.json', {'name': directory or 'app', 'devDependencies' if dev else 'dependencies': dependencies,
                                'scripts': {'dev': 'next dev --port=4100' if framework == 'next' else 'vite --port=4100'}})
    if framework == 'next':
        write(base, 'src/app/page.tsx', 'export default function Page(){return <button>Save</button>}')
    else:
        write(base, 'index.html', '<div id="root"></div><script type="module" src="/src/main.tsx"></script>')
        write(base, 'src/main.tsx', 'export default function App(){return <button>Save</button>}')
    return base


def test_dev_only_app_and_bad_manifests_are_isolated(tmp_path):
    app(tmp_path, 'apps/web', dev=True)
    write(tmp_path, 'broken/package.json', '{broken')
    write(tmp_path, 'bad/package.json', {'dependencies': ['react'], 'scripts': {'dev': 4}})
    write(tmp_path, 'lib/package.json', {'peerDependencies': {'react': '19'}, 'devDependencies': {'react': '19', 'react-dom': '19'}})
    write(tmp_path, 'lib/vite.config.ts', 'export default {build:{lib:{entry:"src/index.ts"}}}')
    write(tmp_path, 'backend/package.json', {'dependencies': {'react': '19', 'react-dom': '19'}, 'scripts': {'start': 'node server.js'}})
    project = ProjectLoader().load(tmp_path)
    assert [(a.framework, a.base_dir) for a in project.frontend_apps] == [('React', 'apps/web')]
    assert project.loader_audit['diagnostics']
    assert project.frontend_apps[0].recognition


def test_explicit_selection_keeps_repo_relative_files_and_excludes_other_app(tmp_path):
    app(tmp_path, 'apps/web', 'next')
    app(tmp_path, 'apps/docs', 'next')
    write(tmp_path, 'app/foreign/page.tsx', 'export default function Other(){return null}')
    write(tmp_path, 'apps/docs/src/app/(group)/help/page.tsx', 'export default function Help(){return null}')
    project = ProjectLoader().load(tmp_path, app_manifest='apps/docs/package.json')
    assert project.root == str(tmp_path)
    assert project.app_dir == str(tmp_path / 'apps/docs')
    assert project.selected_manifest == 'apps/docs/package.json'
    assert project.routes == ['/', '/help']
    assert all(f.path.startswith('apps/docs/') for f in project.visible_files)
    assert all(p.startswith('apps/docs/') for p in project.entry_points)
    selected = select_project(ProjectLoader(), str(tmp_path), 'apps/docs')
    assert selected.root == str(tmp_path) and selected.app_dir == project.app_dir


@pytest.mark.parametrize('selection', ['../package.json', 'missing/package.json', 'package.json'])
def test_invalid_or_non_application_selection_is_rejected(tmp_path, selection):
    app(tmp_path, 'web')
    write(tmp_path, 'package.json', {'private': True})
    with pytest.raises(ValueError):
        ProjectLoader().load(tmp_path, app_manifest=selection)


def test_workspace_hints_find_deeper_app_and_report_bounds(tmp_path):
    write(tmp_path, 'package.json', {'workspaces': ['products/*/clients/*']})
    app(tmp_path, 'products/one/clients/web', dev=True)
    project = ProjectLoader().load(tmp_path)
    assert project.frontend_apps[0].base_dir == 'products/one/clients/web'
    assert project.loader_audit['discovery']['bounded'] is True
    assert project.loader_audit['discovery']['workspace_patterns'] == ['products/*/clients/*']


def test_explicit_manifest_can_select_app_beyond_automatic_scan_depth(tmp_path):
    app(tmp_path, 'products/one/clients/web')
    project = ProjectLoader().load(tmp_path, app_manifest='products/one/clients/web/package.json')
    assert project.app_dir == str(tmp_path / 'products/one/clients/web')
    assert project.loader_audit['selection'] == 'explicit'


def test_selected_workspace_lock_scripts_and_port_are_metadata(tmp_path):
    write(tmp_path, 'package.json', {'workspaces': ['apps/*'], 'packageManager': 'pnpm@10.0.0'})
    write(tmp_path, 'pnpm-lock.yaml', 'lockfileVersion: 9')
    app(tmp_path, 'apps/web', 'next')
    project = ProjectLoader().load(tmp_path)
    env = project.environment
    assert env['package_manager'] == 'pnpm@10.0.0'
    assert env['lockfile'] == 'pnpm-lock.yaml'
    assert env['start_script'] == 'dev' and env['cwd'] == str(tmp_path / 'apps/web')
    assert project.start == 'next dev --port=4100' and project.base_url == 'http://localhost:4100'
    write(tmp_path, 'yarn.lock', '# conflicting lock')
    ambiguous = ProjectLoader().load(tmp_path).environment
    assert ambiguous['package_manager_status'] == 'conflict'
    assert ambiguous['diagnostics']


def test_next_effective_directories_dynamic_hints_and_special_routes(tmp_path):
    base = app(tmp_path, framework='next')
    for path in ['src/app/(site)/users/[id]/page.tsx', 'src/app/files/[...slug]/page.tsx',
                 'src/app/docs/[[...slug]]/page.tsx', 'src/app/_private/page.tsx',
                 'src/app/@modal/(.)login/page.tsx', 'src/app/api/route.ts',
                 'src/pages/legacy.tsx', 'src/pages/api/secret.ts', 'src/pages/_app.tsx']:
        write(base, path, 'export default function Page(){return null}')
    project = ProjectLoader().load(tmp_path)
    assert project.routes == ['/', '/docs/[[...slug]]', '/files/[...slug]', '/legacy', '/users/[id]']
    assert len(project.entry_points) == len(project.routes)
    assert next(h for h in project.route_hints if h['path'] == '/users/[id]')['dynamic']
    assert project.loader_audit['route_diagnostics']
    assert not any('/api/' in f.path or '/_private/' in f.path or '/@modal/' in f.path for f in project.visible_files)
    write(base, 'app/root/page.tsx', 'export default function Page(){return null}')
    project = ProjectLoader().load(tmp_path)
    assert project.routes == ['/legacy', '/root']
    assert not any(f.path.startswith('src/app/') for f in project.visible_files)


@pytest.mark.parametrize('framework,source,expected,mode', [
    ('react', '''const App=()=> <BrowserRouter><Routes><Route path="/users"><Route index element={<Home/>}/><Route path=":id" element={<User/>}/></Route><Route path="/about"/></Routes></BrowserRouter>''', ['/about', '/users', '/users/:id'], 'history'),
    ('react', '''const router=createBrowserRouter([{path:'/admin',children:[{path:'settings'},{path:'/help'},{index:true}]}]);''', ['/admin', '/admin/settings', '/help'], 'history'),
    ('vue', '''const routes=[{path:'/users',children:[{path:':id'},{path:'',component:Home},{path:'/help'}]}]; const router=createRouter({history:createWebHashHistory(),routes});''', ['/help', '/users', '/users/:id'], 'hash'),
])
def test_literal_nested_routes_are_composed(tmp_path, framework, source, expected, mode):
    app(tmp_path, framework=framework)
    write(tmp_path, 'src/App.tsx' if framework == 'react' else 'src/router/index.ts', source)
    project = ProjectLoader().load(tmp_path)
    assert project.routes == expected
    assert project.environment['router_mode'] == mode
    assert all(h['source'].startswith('src/') for h in project.route_hints)


def test_route_expressions_are_unresolved_not_fabricated(tmp_path):
    app(tmp_path)
    write(tmp_path, 'src/routes.ts', "const routes=[{path: privatePath,children:[{path:'child'}]},{path:'/ok'}];")
    project = ProjectLoader().load(tmp_path)
    assert project.routes == ['/ok']
    assert project.loader_audit['route_diagnostics']


def test_root_app_routes_and_source_are_visible(tmp_path):
    app(tmp_path)
    write(tmp_path, 'App.tsx', '<BrowserRouter><Routes><Route path="/root-app" element={<button>Save</button>}/></Routes></BrowserRouter>')
    project = ProjectLoader().load(tmp_path)
    assert project.routes == ['/root-app']
    assert any(f.path == 'App.tsx' for f in project.visible_files)


def test_jsx_parent_element_does_not_end_route_tag_or_parse_comments(tmp_path):
    app(tmp_path)
    write(tmp_path, 'src/App.tsx', '''// <Route path="/comment"/>
    const App=()=> <Routes><Route path="/users" element={<Layout/>}>
    <Route path=":id" element={<User/>}/></Route></Routes>;''')
    assert ProjectLoader().load(tmp_path).routes == ['/users', '/users/:id']


def test_malformed_children_do_not_abort_other_routes(tmp_path):
    app(tmp_path)
    write(tmp_path, 'src/routes.ts', "const routes=[{path:'/ok'},{path:'/other',children:}];")
    project = ProjectLoader().load(tmp_path)
    assert '/ok' in project.routes
    assert project.loader_audit['route_diagnostics']


def test_conflicting_manager_is_unknown_not_a_run_suggestion(tmp_path):
    app(tmp_path)
    import json
    manifest = tmp_path / 'package.json'
    data = json.loads(manifest.read_text())
    write(tmp_path, 'package.json', {**data, 'packageManager': 'pnpm@10.0.0'})
    write(tmp_path, 'pnpm-lock.yaml', 'lockfileVersion: 9')
    write(tmp_path, 'yarn.lock', '# ambiguous')
    project = ProjectLoader().load(tmp_path)
    assert project.environment['package_manager'] == 'unknown'
