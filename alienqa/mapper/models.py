"""Product Mapper 的数据模型：ProductMap / Area / Relation。

强结构化输出：字段受白名单约束，**没有**任何"测试结论/疑似 bug"字段。
LLM 输出里多出来的字段（如 bugs/issues/conclusion）一律丢弃。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..llm.jsonutil import loads_object


def _as_str_list(value) -> list:
    """把 LLM 可能给出的 str/list 统一成 list[str]，过滤空值。"""
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
class Area:
    """一个产品功能区域（页面 + 可做动作 + 实体 + 角色 + 状态）。"""

    name: str = ""
    pages: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    entities: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    states: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Area":
        return cls(
            name=str(d.get("name") or "").strip(),
            pages=_as_str_list(d.get("pages")),
            actions=_as_str_list(d.get("actions")),
            entities=_as_str_list(d.get("entities")),
            roles=_as_str_list(d.get("roles")),
            states=_as_str_list(d.get("states")),
        )


@dataclass
class Relation:
    """页面之间的关系（导航/嵌套等）。"""

    from_: str = ""  # "from" 是 Python 关键字，字段名用 from_
    to: str = ""
    kind: str = "navigate"

    @classmethod
    def from_dict(cls, d: dict) -> "Relation":
        return cls(
            from_=str(d.get("from") or d.get("source") or "").strip(),
            to=str(d.get("to") or d.get("target") or "").strip(),
            kind=str(d.get("kind") or "navigate").strip() or "navigate",
        )


@dataclass
class ProductMap:
    """产品地图：功能区域 + 页面关系。brief 为主旨文本（03 的 product_brief 来源）。"""

    areas: list = field(default_factory=list)      # list[Area]
    relations: list = field(default_factory=list)  # list[Relation]
    brief: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ProductMap":
        areas = [Area.from_dict(a) for a in data.get("areas", []) if isinstance(a, dict)]
        relations = [Relation.from_dict(r) for r in data.get("relations", []) if isinstance(r, dict)]
        return cls(areas=areas, relations=relations)

    @classmethod
    def from_json(cls, text: str) -> "ProductMap":
        """解析 LLM 返回的 JSON（容忍 markdown 围栏与尾随文字）。

        失败抛 ValueError，由调用方决定是否重试。
        """
        return cls.from_dict(loads_object(text))
