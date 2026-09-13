"""通用性测试：确认 Loader 不依赖 cal.diy/chatwoot 等具体项目，能泛化到合成结构。"""
import json
import zipfile
from pathlib import Path

from alienqa.loader import Budget, ProjectLoader


def _write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_next_monorepo_picks_main_app_not_docs(tmp_path):
    """主应用即使不叫 apps/web 也能被选中，docs 卫星站点被降权。"""
    _write_json(tmp_path / "package.json", {"name": "root", "private": True, "workspaces": ["apps/*"]})
    _write_json(
        tmp_path / "apps/main/package.json",
        {
            "name": "main",
            "dependencies": {"next": "14", "react": "18"},
            "scripts": {"dev": "next dev", "build": "next build"},
        },
    )
    (tmp_path / "apps/main/app").mkdir(parents=True)
    (tmp_path / "apps/main/app/page.tsx").write_text("export default function Page() { return null }")
    (tmp_path / "apps/main/app/login").mkdir(parents=True)
    (tmp_path / "apps/main/app/login/page.tsx").write_text("export default function Login() { return null }")

    _write_json(
        tmp_path / "apps/docs/package.json",
        {"name": "docs", "dependencies": {"next": "14"}, "scripts": {"dev": "next dev"}},
    )
    (tmp_path / "apps/docs/app/[[...mdxPath]]").mkdir(parents=True)
    (tmp_path / "apps/docs/app/[[...mdxPath]]/page.tsx").write_text("export default function Doc() { return null }")

    project = ProjectLoader().load(tmp_path)
    assert project.framework == "Next.js"
    assert "/" in project.routes
    assert "/login" in project.routes
    paths = [v.path.replace("\\", "/") for v in project.visible_files]
    assert any("apps/main" in p for p in paths)
    assert not any("apps/docs" in p for p in paths)


def test_vue_monorepo_nested_frontend(tmp_path):
    """Vue 前端嵌套在 apps/frontend（非仓库根级）也能定位到表面。"""
    _write_json(tmp_path / "package.json", {"name": "root", "private": True, "workspaces": ["apps/*"]})
    _write_json(
        tmp_path / "apps/frontend/package.json",
        {
            "name": "frontend",
            "dependencies": {"vue": "3", "vue-router": "4"},
            "devDependencies": {"vite": "6"},
            "scripts": {"dev": "vite"},
        },
    )
    (tmp_path / "apps/frontend/src").mkdir(parents=True)
    (tmp_path / "apps/frontend/index.html").write_text("<div id=\"app\"></div>")
    (tmp_path / "apps/frontend/src/main.js").write_text("import { createApp } from 'vue'")
    (tmp_path / "apps/frontend/src/App.vue").write_text("<template><button>hi</button></template>")

    project = ProjectLoader().load(tmp_path)
    assert project.framework == "Vue"
    paths = [v.path.replace("\\", "/") for v in project.visible_files]
    assert any(p.startswith("apps/frontend/src/") for p in paths)


def test_zip_input(tmp_path):
    """zip 输入能解压并识别框架与路由。"""
    proj = tmp_path / "proj"
    _write_json(
        proj / "package.json",
        {"name": "zipapp", "dependencies": {"next": "14", "react": "18", "react-dom": "18"}, "scripts": {"dev": "next dev"}},
    )
    (proj / "app").mkdir(parents=True)
    (proj / "app/page.tsx").write_text("export default function Page(){ return (<div>hi</div>) }")
    zip_path = tmp_path / "proj.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in proj.rglob("*"):
            zf.write(f, f.relative_to(tmp_path))

    project = ProjectLoader().load(zip_path)
    assert project.input_type == "zip"
    assert project.framework == "Next.js"
    assert "/" in project.routes


def test_visible_files_scored_and_ranked(tmp_path):
    """L3：可见文件带 ui_score/role，且按评分降序。"""
    _write_json(
        tmp_path / "package.json",
        {"name": "app", "dependencies": {"next": "14", "react": "18", "react-dom": "18"}, "scripts": {"dev": "next dev"}},
    )
    (tmp_path / "app").mkdir(parents=True)
    (tmp_path / "app/page.tsx").write_text(
        "export default function Page(){ return (<div><button onClick={x}>Hi</button></div>) }"
    )
    (tmp_path / "app/login").mkdir(parents=True)
    (tmp_path / "app/login/page.tsx").write_text("export default function Login(){ return (<form><input /></form>) }")

    project = ProjectLoader().load(tmp_path)
    assert project.framework == "Next.js"
    routes = [v for v in project.visible_files if v.role == "route"]
    assert len(routes) >= 2
    assert all(v.ui_score > 0 for v in routes)
    scores = [v.ui_score for v in project.visible_files]
    assert scores == sorted(scores, reverse=True)
