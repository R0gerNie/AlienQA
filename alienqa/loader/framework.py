"""框架识别、命令/环境提取、路由提取（确定性，不用 LLM）。"""
import re
from pathlib import Path

from .scan import FRONTEND_EXTENSIONS, find_package_jsons, load_json, surface_dirs

DEV_SCRIPT_PRIORITY = ("dev", "start:dev", "start", "dx", "serve")


def detect_frontend_apps(root: Path):
    """枚举仓库中所有前端应用（跨框架），返回 [(framework, manifest_path, name), ...]。

    逐个 package.json 独立分类，且只看 dependencies（排除 dev/peer 依赖），
    以便把"应用"与"组件库/工具包"区分开，兼容同一仓库混合多个框架的场景。
    """
    apps = []
    for p in find_package_jsons(root):
        data = load_json(p)
        if not data:
            continue
        name = data.get("name") or ""
        deps = set(data.get("dependencies") or {})
        scripts = data.get("scripts") or {}
        script_text = " ".join(scripts.values())
        fw = _classify_package(deps, script_text)
        if fw and _is_frontend_app(p.parent, fw):
            apps.append((fw, p, name))
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
    count = 0
    for dname in ("app", "pages"):
        dd = base / dname
        if not dd.is_dir():
            continue
        for f in dd.rglob("*"):
            if f.suffix not in (".tsx", ".jsx", ".ts", ".js"):
                continue
            if dname == "app":
                if f.name.startswith("page."):
                    count += 1
            else:
                parts = f.relative_to(dd).parts
                if parts and parts[0] == "api":
                    continue
                if any(p.startswith("_") for p in parts):
                    continue
                count += 1
    return count


def _surface_file_count(root: Path, framework: str, manifest: Path) -> int:
    """统计应用前端表面下的文件数量（封顶 200，避免大项目拖慢评分）。"""
    total = 0
    for d in surface_dirs(root, framework, manifest):
        dd = root / d
        if not dd.is_dir():
            continue
        for f in dd.rglob("*"):
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
    data = load_json(manifest_path)
    if not data:
        return "", ""
    scripts = data.get("scripts") or {}
    start = next((scripts[k] for k in DEV_SCRIPT_PRIORITY if k in scripts), "")
    build = scripts.get("build", "")
    return start, build


def extract_env(manifest_path: Path | None):
    if not manifest_path:
        return {}
    data = load_json(manifest_path) or {}
    env = {}
    engines = data.get("engines") or {}
    if engines.get("node"):
        env["node"] = engines["node"]
    if data.get("packageManager"):
        env["package_manager"] = data["packageManager"]
    return env


def extract_routes(root: Path, framework: str, manifest_path: Path | None):
    if framework == "Next.js":
        base = manifest_path.parent if manifest_path else root
        routes = _next_routes(base)
        if base != root:
            routes |= _next_routes(root)
        return sorted(routes)
    if framework in ("Vue", "Nuxt"):
        return _vue_routes(root, framework, manifest_path)
    if framework == "React":
        return _react_routes(root, framework, manifest_path)
    return []


def _iter_surface_files(root: Path, framework: str, manifest_path: Path | None):
    """只遍历该应用前端表面目录下的文件，避免全仓库扫描。"""
    for d in surface_dirs(root, framework, manifest_path):
        dd = root / d
        if not dd.is_dir():
            continue
        for f in dd.rglob("*"):
            if f.is_file():
                yield f


def _next_routes(base: Path):
    """App Router（app/）与 Pages Router（pages/）合并提取。"""
    routes = set()
    for dname in ("app", "pages"):
        dd = base / dname
        if not dd.is_dir():
            continue
        if dname == "app":
            for f in dd.rglob("page.*"):
                if f.suffix not in (".tsx", ".jsx", ".ts", ".js"):
                    continue
                route = _parts_to_route(f.relative_to(dd).parts[:-1])
                if route:
                    routes.add(route)
        else:
            for f in dd.rglob("*"):
                if f.suffix not in (".tsx", ".jsx", ".ts", ".js"):
                    continue
                parts = f.relative_to(dd).parts
                if parts and parts[0] == "api":
                    continue
                if any(p.startswith("_") for p in parts):
                    continue
                if f.stem == "index":
                    route_parts = parts[:-1]
                else:
                    route_parts = list(parts[:-1]) + [f.stem]
                route = _parts_to_route(route_parts)
                if route:
                    routes.add(route)
    return routes


def _parts_to_route(parts):
    segs = []
    for seg in parts:
        if not seg:
            continue
        if seg.startswith("(") and seg.endswith(")"):  # Next.js route group
            continue
        segs.append(seg)
    return "/" + "/".join(segs)


def _vue_routes(root: Path, framework: str, manifest_path: Path | None):
    """从 vue-router 配置中尽力提取路由（best-effort）。"""
    routes = set()
    for f in _iter_surface_files(root, framework, manifest_path):
        if f.suffix not in (".js", ".ts"):
            continue
        rel = f.relative_to(root).as_posix().lower()
        if not ("route" in f.name.lower() or "/routes/" in rel or "/router/" in rel):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "createRouter" in text or "routes" in text:
            for m in re.finditer(r"path\s*:\s*['\"]([^'\"]+)['\"]", text):
                r = m.group(1)
                if r:
                    routes.add(r if r.startswith("/") else "/" + r)
    return sorted(routes)


def _react_routes(root: Path, framework: str, manifest_path: Path | None):
    """从 React Router 配置中尽力提取路由（best-effort，按文件名过滤避免全量读文件）。"""
    routes = set()
    for f in _iter_surface_files(root, framework, manifest_path):
        if f.suffix not in (".tsx", ".jsx", ".ts", ".js"):
            continue
        if "route" not in f.name.lower() and "router" not in f.name.lower():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"path\s*=\s*['\"]([^'\"]+)['\"]", text):
            routes.add(m.group(1))
    return sorted(routes)
