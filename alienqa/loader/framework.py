"""框架识别、命令/环境提取、路由提取（确定性，不用 LLM）。"""
import re
from pathlib import Path

from .scan import FRONTEND_EXTENSIONS, discover_manifests, iter_repo_files, load_json, surface_dirs
from .routes import next_pages, route_metadata

DEV_SCRIPT_PRIORITY = ("dev", "start:dev", "start", "dx", "serve")


def manifest_facts(path):
    data = load_json(path)
    problems = []
    if not isinstance(data, dict):
        return {}, ["invalid package.json object"]
    data = dict(data)
    for key in ('dependencies', 'devDependencies', 'peerDependencies', 'scripts', 'engines'):
        value = data.get(key, {})
        if not isinstance(value, dict):
            problems.append(f"{key} must be an object")
            value = {}
        invalid = any(not isinstance(v, str) for v in value.values())
        if invalid:
            problems.append(f"{key} has non-string values")
        data[key] = {k: v for k, v in value.items() if isinstance(v, str)}
    return data, problems


def recognition(manifest, framework):
    data, _ = manifest_facts(manifest)
    signals = [f"{kind}: {name}" for kind in ('dependencies', 'devDependencies')
               for name in data.get(kind, {}) if name in ('react', 'react-dom', 'vue', 'next', 'nuxt', 'svelte', '@angular/core')]
    signals.extend(f"script {key}: {value}" for key, value in data.get('scripts', {}).items()
                   if any(word in value for word in ('vite', 'next', 'nuxt', 'react-scripts', 'vue-cli', 'ng serve')))
    for path in sorted(manifest.parent.iterdir()):
        if path.name in ('index.html', 'angular.json', 'src', 'app', 'pages', 'public') or path.name.startswith(('vite.config.', 'next.config.', 'vue.config.')):
            signals.append(f"entry/config: {path.name}")
    return signals


def detect_frontend_apps(root: Path, manifests=None, diagnostics=None):
    """Package-local dependencies AND runnable entry signals; peer libraries excluded."""
    apps = []
    for path in manifests if manifests is not None else discover_manifests(root)[0]:
        data, problems = manifest_facts(path)
        if diagnostics is not None:
            diagnostics.extend({'source': path.relative_to(root).as_posix(), 'reason': reason} for reason in problems)
        deps = set(data.get('dependencies', {})) | set(data.get('devDependencies', {}))
        scripts = ' '.join(data.get('scripts', {}).values())
        framework = _classify_package(deps, scripts)
        if framework and _is_frontend_app(path.parent, framework):
            configs = list(path.parent.glob('vite.config.*'))
            library = any(re.search(r'\blib\s*:', p.read_text(encoding='utf-8', errors='replace')[:8000]) for p in configs if p.is_file())
            if library and not (path.parent / 'index.html').is_file():
                continue
            apps.append((framework, path, data.get('name') if isinstance(data.get('name'), str) else ''))
    return apps


def _classify_package(deps, script_text):
    """对单个 package.json 分类框架；不识别则返回 None。"""
    if "nuxt" in deps:
        return "Nuxt"
    if "next" in deps or "next dev" in script_text or "next build" in script_text:
        return "Next.js"
    if "vue" in deps:
        return "Vue"
    if "react" in deps and "react-dom" in deps:
        return "React"
    if "svelte" in deps:
        return "Svelte"
    if "@angular/core" in deps:
        return "Angular"
    return None


# 卫星站点的通用命名提示（用于降权，不指向任何具体项目）
_SATELLITE_HINTS = (
    "docs", "website", "blog", "marketing", "landing", "storybook", "examples", "template",
)


def _count_next_routes(base: Path) -> int:
    """统计某 Next.js 应用目录下用户可见路由文件数（app 的 page.* 与 pages 的页面文件）。"""
    return len(next_pages(base)[0])


def _surface_file_count(root: Path, framework: str, manifest: Path) -> int:
    """统计应用前端表面下的文件数量（封顶 200，避免大项目拖慢评分）。"""
    total = 0
    for d in surface_dirs(root, framework, manifest):
        dd = root / d
        if not dd.is_dir():
            continue
        for f in iter_repo_files(dd):
            if f.is_file() and f.suffix.lower() in FRONTEND_EXTENSIONS:
                total += 1
                if total >= 200:
                    return 200
    return total


def _is_frontend_app(base: Path, framework: str) -> bool:
    """是否有前端应用入口/构建信号（区分应用与后端/库）。

    NestJS 等后端虽可能依赖 react，但不会有 index.html/vite.config 等前端入口，
    因此据此排除，避免把后端/库误判为前端应用。
    """
    if framework == "Next.js":
        if _count_next_routes(base) > 0:
            return True
        return any((base / f"next.config.{e}").exists() for e in ("ts", "js", "mjs", "cjs"))
    if (base / "index.html").exists() or (base / "public" / "index.html").exists():
        return True
    if any((base / f"vite.config.{e}").exists() for e in ("ts", "js", "mts", "mjs")):
        return True
    if (base / "vue.config.js").exists() or (base / "angular.json").exists():
        return True
    return False


def _app_score(root: Path, app) -> int:
    fw, manifest, name = app
    base = manifest.parent
    n = (name or "").lower()
    last = base.name.lower()
    s = 0
    if _is_frontend_app(base, fw):
        s += 60
    s += min(_surface_file_count(root, fw, manifest), 60)
    if any(k in n or k == last for k in _SATELLITE_HINTS):
        s -= 100
    return s


def rank_frontend_apps(root: Path, apps):
    """按"更像主应用"程度排序，primary 排第一。"""
    scored = sorted(((a, _app_score(root, a)) for a in apps), key=lambda x: x[1], reverse=True)
    return [a for a, _ in scored]


def detect_framework(root: Path):
    """返回主前端应用的 (framework, manifest)。多应用时按 rank_frontend_apps 取第一。"""
    apps = detect_frontend_apps(root)
    if not apps:
        return "Unknown", None
    primary = rank_frontend_apps(root, apps)[0]
    return primary[0], primary[1]


def extract_commands(manifest_path: Path | None):
    """从 manifest 提取 dev/start 与 build 命令。"""
    if not manifest_path:
        return "", ""
    data, _ = manifest_facts(manifest_path)
    if not data:
        return "", ""
    scripts = data.get("scripts") or {}
    start = next((scripts[k] for k in DEV_SCRIPT_PRIORITY if k in scripts), "")
    build = scripts.get("build", "")
    return start, build


def extract_env(manifest_path: Path | None, root=None):
    if not manifest_path:
        return {}
    root = Path(root or manifest_path.parent).resolve()
    data, _ = manifest_facts(manifest_path)
    parents = [manifest_path.parent]
    while parents[-1] != root and parents[-1].is_relative_to(root):
        parents.append(parents[-1].parent)
    declarations = [manifest_facts(p / 'package.json')[0].get('packageManager') for p in parents]
    declared = next((value for value in declarations if isinstance(value, str) and value), '')
    locks = []
    for parent in parents:
        local = [(manager, parent / name) for manager, name in [('npm', 'package-lock.json'), ('npm', 'npm-shrinkwrap.json'),
            ('pnpm', 'pnpm-lock.yaml'), ('yarn', 'yarn.lock'), ('bun', 'bun.lock'), ('bun', 'bun.lockb')] if (parent / name).is_file()]
        if local:
            locks = local
            break
    managers = {manager for manager, _ in locks}
    explicit = declared.split('@')[0] if declared else ''
    conflict = len(managers) > 1 or bool(explicit and managers and explicit not in managers)
    scripts = data.get('scripts', {})
    start_name = next((name for name in DEV_SCRIPT_PRIORITY if scripts.get(name)), '')
    env = {'cwd': str(manifest_path.parent), 'start_script': start_name, 'build_script': 'build' if scripts.get('build') else '',
           'package_manager': 'unknown' if conflict else declared or (next(iter(managers)) if len(managers) == 1 else 'unknown'),
           'package_manager_declared': declared,
           'package_manager_status': 'conflict' if conflict else 'declared' if declared else 'lockfile' if locks else 'unknown',
           'lockfile': locks[0][1].relative_to(root).as_posix() if len(locks) == 1 else '',
           'lockfiles': [path.relative_to(root).as_posix() for _, path in locks],
           'diagnostics': ['packageManager/lockfiles conflict; no executable suggestion selected'] if conflict else []}
    if data.get('engines', {}).get('node'):
        env['node'] = data['engines']['node']
    return env


def extract_routes(root: Path, framework: str, manifest_path: Path | None):
    return sorted({row['path'] for row in route_metadata(root, framework, manifest_path)[0]})


def _next_routes(base: Path):
    return {route for route, path in next_pages(base)[0]}


def _parts_to_route(parts):
    return '/' + '/'.join(p for p in parts if p and not (p.startswith('(') and p.endswith(')')))
