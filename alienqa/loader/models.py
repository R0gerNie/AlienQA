"""Project Loader 的数据模型。"""
from dataclasses import dataclass, field


@dataclass
class VisibleFile:
    """一个被判定为"前端用户可见"的文件。path 为仓库相对路径（正斜杠）。"""

    path: str
    role: str = "unknown"  # route | page | component | copy | unknown
    lines: int = 0
    ui_score: float = 0.0


@dataclass
class SelectionAudit:
    """可见表面选取的可解释审计信息。"""

    total_files: int = 0
    included: int = 0
    excluded_tests: int = 0
    excluded_backend: int = 0
    excluded_generated: int = 0


@dataclass
class Budget:
    """可见表面选取的预算约束（L3 使用）。"""

    max_files: int = 2000
    max_file_lines: int = 400
    max_total_chars: int = 200_000


@dataclass
class FrontendApp:
    """一个被识别出的前端应用（框架 + manifest）。"""

    framework: str
    name: str = ""
    manifest: str = ""   # repo 相对 posix 路径（package.json）
    base_dir: str = ""   # repo 相对 posix 路径（manifest 所在目录）


@dataclass
class Project:
    """Loader 的输出：项目事实 + 前端可见表面。"""

    root: str = ""  # 仓库根目录（绝对路径字符串），供下游按路径读文件
    input_type: str = "unknown"
    framework: str = "Unknown"
    start: str = ""
    build: str = ""
    base_url: str = "http://localhost:3000"
    storage_state: str = ""  # 黑盒模式可选：Playwright storage_state 文件路径（登录态）
    routes: list = field(default_factory=list)
    dependencies: dict = field(default_factory=dict)
    environment: dict = field(default_factory=dict)
    entry_points: list = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    frontend_apps: list = field(default_factory=list)
    visible_files: list = field(default_factory=list)
    selection_audit: SelectionAudit = field(default_factory=SelectionAudit)
