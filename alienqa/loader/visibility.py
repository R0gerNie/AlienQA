"""可见表面选取（L1 硬排除 + L2 表面定位 + L3 可见性评分与预算）。"""
from pathlib import Path

from .models import Budget, SelectionAudit, VisibleFile
from .scan import (
    BACKEND_EXTENSIONS,
    FRONTEND_EXTENSIONS,
    GENERATED_PATTERNS,
    TEST_PATTERNS,
    iter_repo_files,
    surface_dirs,
)


_UI_MARKERS = (
    "<button", "<input", "<form", "<select", "<textarea", "<a ",
    "onClick", "onChange", "onSubmit", "onInput",
    "@click", "v-model", "v-on:", "v-if", "v-for",
    "return (", "className", "role=", "placeholder",
)

_STYLE_EXTS = {".css", ".scss", ".less"}


def _ui_score(text: str) -> float:
    """确定性 UI 标记评分：命中标记越多，越像用户可见的界面文件。"""
    if not text:
        return 0.0
    hits = sum(1 for m in _UI_MARKERS if m in text)
    return min(hits / 8.0, 1.0)


def _classify_role(rel: str, ext: str, text: str) -> str:
    """按路径与内容判定文件角色：route / page / component / style / logic。"""
    name = Path(rel).name.lower()
    lower = rel.lower()
    if ext in _STYLE_EXTS:
        return "style"
    if name.startswith("page.") and (lower.startswith("app/") or "/app/" in lower):
        return "route"
    if (name.startswith("page.") or name.startswith("index.")) and (
        lower.startswith("pages/") or "/pages/" in lower
    ):
        return "route"
    if "route" in name or "router" in name:
        return "route"
    if ext in (".tsx", ".jsx", ".vue", ".svelte", ".html"):
        return "page" if _ui_score(text) >= 0.5 else "component"
    if ext in (".ts", ".js"):
        return "component" if _ui_score(text) >= 0.3 else "logic"
    return "unknown"


def _read_limited(path: Path, budget: Budget) -> str:
    """按单文件行数预算截断读取。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            chunks = []
            for i, line in enumerate(f):
                if budget.max_file_lines and i >= budget.max_file_lines:
                    break
                chunks.append(line)
            return "".join(chunks)
    except OSError:
        return ""


def select_visible_files(
    root: Path,
    framework: str,
    manifest_dir: Path | None,
    budget: Budget | None = None,
):
    """返回 (visible_files, selection_audit)。

    L1/L2 过滤出表面候选 → L3 可见性评分排序 → 按预算（文件数/总字符数）截断。
    """
    budget = budget or Budget()
    prefixes = [d.as_posix() for d in surface_dirs(root, framework, manifest_dir)]
    audit = SelectionAudit()
    candidates = []  # (ui_score, rel, lines, role, chars)

    for f in iter_repo_files(root):
        audit.total_files += 1
        name = f.name
        if any(p in name for p in TEST_PATTERNS):
            audit.excluded_tests += 1
            continue
        if any(p in name for p in GENERATED_PATTERNS):
            audit.excluded_generated += 1
            continue
        if Path(name).suffix.lower() in BACKEND_EXTENSIONS:
            audit.excluded_backend += 1
            continue
        if Path(name).suffix.lower() not in FRONTEND_EXTENSIONS:
            continue
        rel = f.relative_to(root).as_posix()
        if not any(rel == p or rel.startswith(p + "/") for p in prefixes):
            continue
        text = _read_limited(f, budget)
        candidates.append((
            _ui_score(text),
            rel,
            text.count("\n") + (1 if text else 0),
            _classify_role(rel, f.suffix.lower(), text),
            len(text),
        ))

    candidates.sort(key=lambda c: (-c[0], c[1]))

    visible: list[VisibleFile] = []
    total_chars = 0
    for score, rel, lines, role, chars in candidates:
        if budget.max_files and len(visible) >= budget.max_files:
            break
        total_chars += chars
        if budget.max_total_chars and total_chars > budget.max_total_chars:
            break
        visible.append(VisibleFile(path=rel, role=role, lines=lines, ui_score=round(score, 3)))

    audit.included = len(visible)
    return visible, audit
