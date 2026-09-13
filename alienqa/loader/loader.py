"""ProjectLoader：L0 来源适配 + 编排 L1/L2/L3 的加载流程。"""
import re
from pathlib import Path

from .framework import (
    detect_framework,
    detect_frontend_apps,
    extract_commands,
    extract_env,
    extract_routes,
    rank_frontend_apps,
)
from .models import Budget, FrontendApp, Project
from .scan import load_json
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
    def load(self, source) -> Project:
        root = self._resolve(source)
        input_type = self.detect_input_type(source)
        apps = detect_frontend_apps(root)
        ranked = rank_frontend_apps(root, apps)
        framework = ranked[0][0] if ranked else "Unknown"
        manifest = ranked[0][1] if ranked else None
        start, build = extract_commands(manifest)
        environment = extract_env(manifest)
        routes = extract_routes(root, framework, manifest)
        visible_files, audit = select_visible_files(root, framework, manifest)
        return Project(
            root=str(root),
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
        raise NotImplementedError("L0 目前仅支持本地目录/zip/url 识别，docker/CI 待实现")

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
            raise FileNotFoundError(f"输入不存在: {source}")
        if p.is_dir():
            return p.resolve()
        if p.is_file() and p.suffix.lower() == ".zip":
            return self._extract_zip(p)
        raise NotImplementedError("L0 目前仅支持目录/zip 输入，docker/url/CI 待实现")

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
        for pat in (r"--port\s+(\d+)", r"-p\s+(\d+)", r"PORT[=\s]+(\d+)"):
            m = re.search(pat, script)
            if m:
                return int(m.group(1))
        return None

    def _merge_deps(self, manifest: Path | None) -> dict:
        if not manifest:
            return {}
        data = load_json(manifest) or {}
        return {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}

    def _entry_points(self, root: Path, framework: str, manifest: Path | None) -> list:
        points = set()
        base = manifest.parent if manifest else root
        if framework == "Next.js":
            for d in ("app", "pages"):
                dd = base / d
                if not dd.is_dir():
                    continue
                if d == "app":
                    for f in dd.rglob("page.*"):
                        points.add(f.relative_to(root).as_posix())
                else:
                    for f in dd.rglob("index.*"):
                        points.add(f.relative_to(root).as_posix())
        elif framework in ("Vue", "Nuxt"):
            for cand in ("app/javascript", "src"):
                dd = root / cand
                if not dd.is_dir():
                    continue
                for name in ("main.js", "main.ts", "main.jsx", "main.tsx", "entry.js", "entry.ts"):
                    if (dd / name).exists():
                        points.add(f"{cand}/{name}")
        return sorted(points)[:50]

    def _artifacts(self, framework: str) -> dict:
        if framework == "Next.js":
            return {"dist": ".next", "static": "public"}
        return {"dist": "dist", "static": "public"}
