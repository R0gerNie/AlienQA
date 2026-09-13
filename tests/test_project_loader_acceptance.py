"""Project Loader 验收测试（TDD 骨架）。

把 `docs/planbooks/01-project-loader.md` 的验收标准编码为测试。
在 `alienqa.loader` 实现之前，整个文件会被跳过（importorskip）。
实现 Loader 后，这些测试将作为验收基准自动生效。
"""
from pathlib import Path

import pytest

loader = pytest.importorskip("alienqa.loader", reason="Project Loader 尚未实现")

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ROOT / "baselines"


def test_detect_nextjs_framework():
    project = loader.ProjectLoader().load(BASELINES / "cal.diy")
    assert project.framework == "Next.js"


def test_detect_vue_framework():
    project = loader.ProjectLoader().load(BASELINES / "chatwoot")
    assert project.framework in {"Vue", "Vue.js"}


def test_extract_dev_command():
    project = loader.ProjectLoader().load(BASELINES / "chatwoot")
    assert project.start  # dev/start 命令非空


def test_extract_routes():
    project = loader.ProjectLoader().load(BASELINES / "cal.diy")
    assert isinstance(project.routes, list)
    assert "/" in project.routes


def _visible_paths(project):
    """visible_files 的仓库相对路径（统一正斜杠）。"""
    return [f.path.replace("\\", "/") for f in project.visible_files]


def test_chatwoot_visible_files_slice_backend():
    """全栈仓库切后端：只留 Vue 前端，不含 Rails 后端。"""
    project = loader.ProjectLoader().load(BASELINES / "chatwoot")
    paths = _visible_paths(project)
    assert any("app/javascript" in p for p in paths), "应包含 Vue 前端目录 app/javascript"
    assert not any(
        "app/controllers" in p or "app/models" in p for p in paths
    ), "不应包含 Rails 后端（app/controllers|models）"


def test_cal_diy_visible_files_exclude_noise():
    """visible_files 不含构建产物/测试文件/DB 目录，且覆盖 apps/web。"""
    project = loader.ProjectLoader().load(BASELINES / "cal.diy")
    paths = _visible_paths(project)
    assert any("apps/web" in p for p in paths), "应包含前端 apps/web"
    assert not any(
        p.startswith("node_modules") or ".next" in p.split("/") or "packages/prisma" in p
        for p in paths
    ), "不应包含 node_modules/.next/DB 目录"
    assert not any(
        ".test." in p or ".spec." in p or "__tests__" in p for p in paths
    ), "不应包含测试文件"


def test_twenty_primary_react_and_multi_app():
    """混合 monorepo：主应用识别为 React CRM，同时枚举出 Next.js 网站，且不把后端误判为前端。"""
    project = loader.ProjectLoader().load(BASELINES / "twenty")
    assert project.framework == "React"
    primary = project.frontend_apps[0]
    assert "twenty-front" in primary.base_dir
    assert any(a.framework == "Next.js" for a in project.frontend_apps)
    assert not any("twenty-server" in a.base_dir for a in project.frontend_apps)
