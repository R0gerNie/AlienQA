"""ContextPolicy：认知边界的可配置白名单/黑名单。"""
from dataclasses import dataclass

from .models import ALLOWED_FIELDS, FORBIDDEN_FIELDS


@dataclass
class ContextPolicy:
    """白名单/黑名单配置。未登记字段默认拒绝（default-deny）。"""

    allowed: tuple = ALLOWED_FIELDS
    forbidden: tuple = FORBIDDEN_FIELDS

    def is_allowed(self, field: str) -> bool:
        return field in self.allowed

    @classmethod
    def from_dict(cls, data: dict) -> "ContextPolicy":
        """从配置加载（如 config.yaml 的 context: 段）。"""
        d = data.get("context", data) if isinstance(data, dict) else {}
        return cls(
            allowed=tuple(d.get("allowed") or ALLOWED_FIELDS),
            forbidden=tuple(d.get("forbidden") or FORBIDDEN_FIELDS),
        )
