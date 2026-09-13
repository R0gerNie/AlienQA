"""模块 01 plus：入口文件智能识别——全局或按单元语义找到 HTML 入口。

规则：
- 测试单元为空或语义为「全部」→ 全局找入口（取启发式得分最高的 index.html）。
- 测试单元写了具体模块 → 先用 LLM 按语义从候选入口里挑；失败则关键词确定性兜底。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..llm import LLMClient, LlmRoles
from ..llm.jsonutil import loads_object

# 排除的噪声目录（不进候选，避免误判）
_NOISE_DIRS = {
    "node_modules", ".git", ".yarn", ".venv", "venv", "__pycache__",
    ".next", ".cache", "coverage", ".turbo", ".nx",
}

# 「全部」的语义等价表达
_ALL_TOKENS = {"", "全部", "all", "所有", "整个", "整个项目", "全局", "整体", "全部功能", "全部页面"}


def _score(rel: Path) -> int:
    parts = rel.parts
    name = parts[-1].lower()
    if name == "index.html":
        if len(parts) == 1:
            return 100  # 项目根
        if parts[-2].lower() in ("dist", "build", "public", "out"):
            return 95   # 常见构建产物目录
        return 90       # 其它 index.html（含 monorepo 子应用）
    return 60           # 其它 .html


def collect_entry_candidates(root: str | Path) -> list:
    """确定性收集所有 HTML 入口候选，按 (得分降序, 深度, 路径) 排序。"""
    root = Path(root)
    if not root.is_dir():
        return []
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _NOISE_DIRS]
        for f in filenames:
            if f.lower().endswith(".html"):
                full = Path(dirpath) / f
                rel = full.relative_to(root)
                found.append((rel.as_posix(), _score(rel)))
    found.sort(key=lambda item: (-item[1], len(Path(item[0]).parts), item[0]))
    return [p for p, _ in found]


def is_all_unit(unit: str) -> bool:
    """测试单元是否为空或语义等价于「全部」。"""
    return (unit or "").strip().lower() in _ALL_TOKENS


class EntryDetector:
    """智能识别入口：全局（无单元/全部）或单元语义（LLM + 关键词兜底）。"""

    def __init__(self, client: LLMClient | None = None):
        self.roles = LlmRoles(client) if client is not None else None

    def detect(self, root: str | Path, unit: str = "", instructions: str = "") -> str:
        candidates = collect_entry_candidates(root)
        if not candidates:
            return "index.html"  # 无候选兜底（交给浏览器 404，不中断扫描）
        if is_all_unit(unit):
            return candidates[0]
        if self.roles is not None:
            picked = self._llm_pick(unit, instructions, candidates)
            if picked:
                return picked
        return self._keyword_pick(unit, candidates) or candidates[0]

    def _llm_pick(self, unit: str, instructions: str, candidates: list) -> str | None:
        for repair in (False, True):
            raw = self.roles.detect_entry(unit, instructions, candidates, repair=repair)
            try:
                data = loads_object(raw)
                entry = str(data.get("entry") or "").strip().replace("\\", "/")
                if entry in candidates:
                    return entry
                for c in candidates:
                    if c.endswith("/" + entry) or entry.endswith(c):
                        return c
            except (ValueError, TypeError):
                continue
        return None

    def _keyword_pick(self, unit: str, candidates: list) -> str | None:
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", (unit or "").lower())
        if not tokens:
            return None
        for c in candidates:
            c_lower = c.lower()
            for t in tokens:
                if t in c_lower:
                    return c
        return None
