"""可见表面选取（L1 硬排除 + L2 表面定位）。L3 评分留待后续实现。"""
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


def _count_lines(p: Path) -> int:
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def select_visible_files(
    root: Path,
    framework: str,
    manifest_dir: Path | None,
    budget: Budget | None = None,
):
    """返回 (visible_files, selection_audit)。只选取前端用户可见表面。"""
    budget = budget or Budget()
    prefixes = [d.as_posix() for d in surface_dirs(root, framework, manifest_dir)]
    audit = SelectionAudit()
    visible: list[VisibleFile] = []

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
        visible.append(VisibleFile(path=rel, lines=_count_lines(f)))
        if budget.max_files and len(visible) >= budget.max_files:
            break

    audit.included = len(visible)
    return visible, audit
