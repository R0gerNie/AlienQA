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
