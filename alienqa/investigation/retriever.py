"""源码检索：按 Issue/Evidence 关键词过滤 visible_files。"""
import re
from pathlib import Path

_MAX_SOURCE_CHARS = 12_000
_MAX_FILES = 20
_ROLE_RANK = {"route": 0, "page": 1, "component": 2, "copy": 3, "unknown": 4}


def retrieve_source(project, issue, evidences=None) -> str:
    if project is None:
        return ""
    root = Path(project.root) if getattr(project, "root", "") else None
    keywords = _keywords(issue, evidences)
    selected = [f for f in (project.visible_files or []) if _matches(f.path, keywords)]
    if not selected and project.visible_files:
        # 关键词一个都没命中 → 回退到 role 优先的少量文件
        selected = sorted(project.visible_files, key=lambda f: _ROLE_RANK.get(f.role, 4))[:_MAX_FILES]
    else:
        selected = selected[:_MAX_FILES]
    blocks = []
    total = 0
    for f in selected:
        content = _read(root, f)
        if not content:
            continue
        block = f"### {f.path}\n{content[:500]}\n"
        if total + len(block) > _MAX_SOURCE_CHARS:
            break
        blocks.append(block)
        total += len(block)
    return "\n".join(blocks)


def _keywords(issue, evidences) -> set:
    kws = set()
    if issue is not None:
        kws |= _tokens(getattr(issue, "title", "") or "")
    for ev in evidences or []:
        action = getattr(ev, "action", None) or {}
        target = action.get("target") or {} if isinstance(action, dict) else {}
        for v in (target.get("text"), target.get("selector")):
            kws |= _tokens(str(v or ""))
        kws |= _tokens(getattr(ev, "expectation", "") or "")
    return {k for k in kws if len(k) >= 3}


def _tokens(text) -> set:
    return {t.lower() for t in re.split(r"[^A-Za-z0-9_./-]+", text or "") if t}


def _matches(path: str, keywords: set) -> bool:
    p = (path or "").lower()
    return any(k and k in p for k in keywords)


def _read(root, f) -> str | None:
    if root is None or not getattr(f, "path", ""):
        return None
    p = root / f.path.replace("\\", "/")
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
