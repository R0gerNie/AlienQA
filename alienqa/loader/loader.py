"""ProjectLoader：L0 来源适配 + 编排 L1/L2/L3 的加载流程。"""
from ..i18n import t
import re
from pathlib import Path

from .framework import (
    detect_framework,
    detect_frontend_apps,
    extract_commands,
    extract_env,
    extract_routes,
    rank_frontend_apps,
    manifest_facts, recognition,
)
from .models import Budget, FrontendApp, Project
from .scan import load_json, discover_manifests
from .routes import next_pages, route_metadata
from .visibility import select_visible_files

_BASE_URL = {
    "Next.js": "http://localhost:3000",
    "Nuxt": "http://localhost:3000",
    "Vue": "http://localhost:3000",
    "React": "http://localhost:5173",
    "Svelte": "http://localhost:5173",
    "Angular": "http://localhost:4200",
}


class ProjectLoader:
    def load(self, source, app_manifest=None) -> Project:
        root = self._resolve(source)
        input_type = self.detect_input_type(source)
        manifests, discovery = discover_manifests(root)
        diagnostics = []
        apps = detect_frontend_apps(root, manifests, diagnostics)
        ranked = rank_frontend_apps(root, apps)
        framework = ranked[0][0] if ranked else "Unknown"
        manifest = ranked[0][1] if ranked else None
        if app_manifest is not None:
            candidate = (root / str(app_manifest)).resolve()
            if not candidate.is_relative_to(root) or not candidate.is_file() or candidate.name != 'package.json':
                raise ValueError(t('应用 manifest 必须是项目内部存在的 package.json'))
            chosen = next((app for app in ranked if app[1] == candidate), None)
            if chosen is None:
                # An explicit existing file is bounded input even beyond discovery depth.
                explicit_apps = detect_frontend_apps(root, [candidate], diagnostics)
                if explicit_apps:
                    ranked = rank_frontend_apps(root, [*ranked, *explicit_apps])
                    chosen = explicit_apps[0]
            if chosen is None:
                raise ValueError(t('所选 manifest 未被识别为前端应用'))
            framework, manifest, _ = chosen
        app_dir = manifest.parent if manifest else root
        start, build = extract_commands(manifest)
        environment = extract_env(manifest, root)
        hints, route_diagnostics, mode = route_metadata(root, framework, manifest)
        routes = sorted({row["path"] for row in hints})
        environment["router_mode"] = mode
        environment["base_url_status"] = "script_hint" if self._detect_port(start) else "framework_hint"
        visible_files, audit = select_visible_files(root, framework, manifest)
        project = Project(
            root=str(root), app_dir=str(app_dir), selected_manifest=manifest.relative_to(root).as_posix() if manifest else '',
            route_hints=hints, loader_audit={'discovery': discovery, 'diagnostics': diagnostics,
                'route_diagnostics': route_diagnostics, 'selection': 'explicit' if app_manifest is not None else 'ranked_suggestion',
                'limitations': ['literal routes only; dynamic templates are not visited URLs']},
            input_type=input_type,
            framework=framework,
            start=start,
            build=build,
            base_url=self._base_url(framework, start),
            routes=routes,
            dependencies=self._merge_deps(manifest),
            environment=environment,
            entry_points=self._entry_points(root, framework, manifest),
            artifacts=self._artifacts(framework),
            frontend_apps=self._build_frontend_apps(root, ranked),
            visible_files=visible_files,
            selection_audit=audit,
        )
        from .artifacts import artifact_facts
        project.artifacts["classification"] = artifact_facts(project)
        return project

    def load_browser(self, base_url: str, routes: list[str] | None = None,
                     storage_state: str | None = None) -> Project:
        """黑盒装载（01b）：只给一个可达 URL（可选登录态文件），不扫源码。"""
        return Project(
            input_type="browser",
            framework="browser",
            base_url=base_url,
            routes=list(routes) if routes else ["/"],
            entry_points=[base_url],
            visible_files=[],
            storage_state=storage_state or "",
        )

    def _build_frontend_apps(self, root: Path, ranked) -> list:
        return [
            FrontendApp(
                framework=fw,
                name=name,
                manifest=m.relative_to(root).as_posix(),
                base_dir=m.parent.relative_to(root).as_posix(),
                recognition=recognition(m, fw),
            )
            for fw, m, name in ranked
        ]

    def detect_input_type(self, source) -> str:
        if isinstance(source, (str, Path)):
            p = Path(source)
            s = str(source)
            if p.is_dir():
                return "git_repository" if (p / ".git").exists() else "local_directory"
            if p.is_file() and p.suffix.lower() == ".zip":
                return "zip"
            if s.startswith(("http://", "https://")):
                return "url"
        raise NotImplementedError(t("L0 目前仅支持本地目录/zip/url 识别，docker/CI 待实现"))

    def detect_framework(self, project_root: Path):
        framework, _ = detect_framework(Path(project_root))
        return framework

    def extract_routes(self, project_root: Path, framework: str = None):
        root = Path(project_root)
        if framework is None:
            framework, manifest = detect_framework(root)
        else:
            _, manifest = detect_framework(root)
        return extract_routes(root, framework, manifest)

    def select_visible_files(self, project_root: Path, framework: str, budget: Budget = None):
        root = Path(project_root)
        _, manifest = detect_framework(root)
        return select_visible_files(root, framework, manifest, budget)[0]

    # ---- 内部 ----

    def _resolve(self, source) -> Path:
        p = Path(source)
        if not p.exists():
            raise FileNotFoundError(t("输入不存在: {source}", source=source))
        if p.is_dir():
            return p.resolve()
        if p.is_file() and p.suffix.lower() == ".zip":
            return self._extract_zip(p)
        raise NotImplementedError(t("L0 目前仅支持目录/zip 输入，docker/url/CI 待实现"))

    def _extract_zip(self, zip_path: Path) -> Path:
        import tempfile
        import zipfile

        target = Path(tempfile.mkdtemp(prefix="alienqa_zip_"))
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target)
        return target.resolve()

    def _base_url(self, framework: str, start_script: str) -> str:
        port = self._detect_port(start_script)
        if port:
            return f"http://localhost:{port}"
        return _BASE_URL.get(framework, "http://localhost:3000")

    @staticmethod
    def _detect_port(script: str):
        if not script:
            return None
        for pat in (r"--port(?:\s+|=)(\d+)", r"-p(?:\s+|=)(\d+)", r"PORT[=\s]+(\d+)"):
            m = re.search(pat, script)
            if m:
                port = int(m.group(1))
                return port if 0 < port < 65536 else None
        return None

    def _merge_deps(self, manifest: Path | None) -> dict:
        if not manifest:
            return {}
        data, _ = manifest_facts(manifest)
        return {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}

    def _entry_points(self, root: Path, framework: str, manifest: Path | None) -> list:
        points = set()
        base = manifest.parent if manifest else root
        if framework == 'Next.js':
            points.update(path.relative_to(root).as_posix() for _, path in next_pages(base)[0])
        else:
            for directory in ('app/javascript', 'src', '.'):
                for name in ('main.js', 'main.ts', 'main.jsx', 'main.tsx', 'entry.js', 'entry.ts', 'index.html'):
                    path = base / directory / name
                    if path.is_file():
                        points.add(path.relative_to(root).as_posix())
        return sorted(points)[:50]

    def _artifacts(self, framework: str) -> dict:
        if framework == "Next.js":
            return {"dist": ".next", "static": "public"}
        return {"dist": "dist", "static": "public"}
