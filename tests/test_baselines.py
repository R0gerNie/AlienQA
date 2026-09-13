"""基线完整性测试：验证已克隆的测试基线与 baselines.md 记录的事实一致。

这些测试不依赖 Project Loader 实现，克隆完成后即可运行。
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ROOT / "baselines"


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("name", ["cal.diy", "chatwoot"])
def test_baseline_repo_cloned(name: str):
    pkg = BASELINES / name / "package.json"
    assert pkg.exists(), f"基线 {name} 未克隆或缺少 package.json: {pkg}"


def test_cal_diy_is_nextjs():
    web_pkg = _load_json(BASELINES / "cal.diy" / "apps" / "web" / "package.json")
    scripts = web_pkg["scripts"]
    assert "next dev" in scripts["dev"]
    assert "next build" in scripts["build"]


def test_cal_diy_has_license_and_dx():
    root_pkg = _load_json(BASELINES / "cal.diy" / "package.json")
    assert "dev" in root_pkg["scripts"]
    assert "dx" in root_pkg["scripts"]
    assert (BASELINES / "cal.diy" / "LICENSE").exists()


def test_chatwoot_license_mit():
    pkg = _load_json(BASELINES / "chatwoot" / "package.json")
    assert pkg["license"] == "MIT"


def test_chatwoot_is_vue3_vite():
    pkg = _load_json(BASELINES / "chatwoot" / "package.json")
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "vue" in deps
    assert "vue-router" in deps
    assert "vite" in deps


def test_baselines_cover_two_framework_families():
    """至少覆盖 Next.js 与 Vue 两个框架家族。"""
    covered = set()

    web_pkg = _load_json(BASELINES / "cal.diy" / "apps" / "web" / "package.json")
    if "next dev" in web_pkg["scripts"].get("dev", ""):
        covered.add("nextjs")

    cw = _load_json(BASELINES / "chatwoot" / "package.json")
    deps = {**cw.get("dependencies", {}), **cw.get("devDependencies", {})}
    if "vue" in deps:
        covered.add("vue")

    assert {"nextjs", "vue"} <= covered
