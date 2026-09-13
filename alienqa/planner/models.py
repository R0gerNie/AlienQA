"""Action Planner 数据模型。"""
from dataclasses import dataclass

from alienqa.driver import Action


@dataclass
class Candidate:
    """一个可执行动作候选：结构化 Action + 元素元数据。"""

    action: Action
    selector: str = ""
    text: str = ""
    tag: str = ""
    href: str = ""
    role: str = ""


@dataclass
class ExploreBudget:
    max_steps: int = 50
    max_time_seconds: float = 300.0
