"""alienqa.loader：项目装载器（L0 来源适配 + L1 硬排除 + L2 前端表面定位）。"""
from .entry_detector import EntryDetector, collect_entry_candidates, is_all_unit
from .loader import ProjectLoader
from .models import Budget, FrontendApp, Project, SelectionAudit, VisibleFile
from .session import capture_session
from .unit_locator import UnitLocator, UnitScope

__all__ = [
    "ProjectLoader",
    "Project",
    "FrontendApp",
    "VisibleFile",
    "Budget",
    "SelectionAudit",
    "UnitLocator",
    "UnitScope",
    "EntryDetector",
    "collect_entry_candidates",
    "is_all_unit",
    "capture_session",
]
