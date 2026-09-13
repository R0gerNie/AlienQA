"""Product Mapper 的输入过滤与"前端表面"摘要构建。

原则：先过滤、再交给 LLM。只读用户可见的页面/路由/文案片段，不读实现细节。
"""
from pathlib import Path

from ..loader.models import Project, VisibleFile

# 表面摘要的预算（控制 LLM 成本与上下文长度）。
MAX_FILES = 50
MAX_FILE_LINES = 60
MAX_SURFACE_CHARS = 20_000
MAX_README_CHARS = 4_000

_EXCLUDE_PATH_PARTS = ("node_modules", ".next", "dist", "build", "__tests__")
_EXCLUDE_SUFFIXES = (".min.js", ".min.css", ".map")
_ROLE_PRIORITY = {"route": 0, "page": 1, "copy": 2, "component": 3, "unknown": 4}


def filter_visible_files(project: Project) -> list:
    """二次过滤 visible_files：剔除压缩/测试/构建产物，按角色优先级排序。"""
    out = []
    for f in project.visible_files:
        p = f.path.replace("\\", "/").lower()
        parts = p.split("/")
        if any(part in _EXCLUDE_PATH_PARTS for part in parts):
            continue
        if p.endswith(_EXCLUDE_SUFFIXES):
            continue
        if ".test." in p or ".spec." in p:
            continue
        out.append(f)
    out.sort(key=lambda f: _ROLE_PRIORITY.get(f.role, 4))
    return out[:MAX_FILES]


def read_readme(root) -> str:
    """读取仓库根目录的 README，截断到预算。找不到返回空串。"""
    if not root:
        return ""
    r = Path(root)
    if not r.is_dir():
        return ""
    for name in ("README.md", "readme.md", "README", "Readme.md", "README.txt"):
        p = r / name
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="replace")[:MAX_README_CHARS]
            except OSError:
                return ""
    return ""


def build_surface_text(project: Project, root) -> str:
    """拼出"前端表面"文本：路由 + 入口 + 可见文件片段。"""
    sections = []
    if project.routes:
        sections.append("路由:\n" + "\n".join(f"- {r}" for r in project.routes))
    if project.entry_points:
        sections.append("入口文件:\n" + "\n".join(f"- {e}" for e in project.entry_points))

    total = sum(len(s) for s in sections)
    file_blocks = []
    for f in filter_visible_files(project):
        content = _read_file(root, f)
        if content is None:
            continue
        snippet = "\n".join(content.splitlines()[:MAX_FILE_LINES])
        block = f"### {f.path} (role={f.role})\n{snippet}\n"
        if total + len(block) > MAX_SURFACE_CHARS:
            break
        file_blocks.append(block)
        total += len(block)

    if file_blocks:
        sections.append("可见前端文件片段:\n" + "\n".join(file_blocks))
    return "\n\n".join(sections)


def _read_file(root, f: VisibleFile) -> str | None:
    if not root or not f.path:
        return None
    p = Path(root) / f.path.replace("\\", "/")
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
