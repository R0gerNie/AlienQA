"""模块 01 plus：单元定位器——把自然语言的单元描述映射到具体元素范围。

流程：Project Loader 装载之后、探索之前，若人类交代了「本次测哪个单元」，
用 LLM 在页面真实元素清单里圈定该单元（selectors + 文本关键词），
后续 Action Planner 只在圈定的范围内探索，其余元素一律不点。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..llm import LLMClient, LlmRoles
from ..llm.jsonutil import loads_object


def _as_str_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    out = []
    for it in items:
        if isinstance(it, (str, int, float)) and str(it).strip():
            out.append(str(it).strip())
    return out


@dataclass
class UnitScope:
    """一个单元的可执行范围：命中 selectors 或文本关键词的元素属于该单元。"""

    unit: str = ""
    instructions: str = ""
    selectors: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    summary: str = ""

    def is_empty(self) -> bool:
        return not self.selectors and not self.keywords

    def matches(self, candidate) -> bool:
        """判断一个候选元素是否落在本单元内；空范围=不限（全量探索）。"""
        if self.is_empty():
            return True
        selector = (getattr(candidate, "selector", "") or "").strip()
        text = (getattr(candidate, "text", "") or "").strip()
        href = (getattr(candidate, "href", "") or "").strip()
        if selector and selector in self.selectors:
            return True
        haystack = f"{text} {href}".lower()
        for kw in self.keywords:
            if kw and kw.lower() in haystack:
                return True
        return False


class UnitLocator:
    """调用 LLM 定位单元；解析失败返回空范围（退化为全量探索）。"""

    def __init__(self, client: LLMClient):
        self.roles = LlmRoles(client)

    def locate(self, unit: str, instructions: str, product_brief: str,
               elements: list) -> UnitScope:
        scope = UnitScope(unit=unit, instructions=instructions)
        if not unit and not instructions:
            return scope
        for repair in (False, True):
            raw = self.roles.locate_unit(unit, instructions, product_brief, elements, repair=repair)
            try:
                data = loads_object(raw)
                scope.selectors = _as_str_list(data.get("selectors"))
                scope.keywords = _as_str_list(data.get("keywords"))
                scope.summary = str(data.get("summary") or "").strip()
                return scope
            except (ValueError, TypeError):
                continue
        return scope
