"""ProductMapper：把 Project + 可见源码概括成强结构化的 ProductMap。

流程：过滤 → 读 README → 粗读(summarize_gist) → 细读(map_product) → 白名单解析。
全程只产出"产品是什么"，不产出测试结论。
"""
from pathlib import Path

from ..llm import LLMClient, LlmRoles
from ..loader.models import Project
from .filter import build_surface_text, read_readme
from .models import ProductMap


class ProductMapper:
    def __init__(self, client: LLMClient, root=None):
        self.client = client
        self.roles = LlmRoles(client)
        self._root = Path(root) if root else None

    def map(self, project: Project) -> ProductMap:
        root = self._root or (Path(project.root) if project.root else None)
        surface_text = build_surface_text(project, root)
        readme = read_readme(root)
        gist = self.roles.summarize_gist(readme, surface_text)
        pm = self._extract(gist, surface_text)
        pm.brief = gist
        return pm

    def map_areas(self, project: Project) -> list:
        return self.map(project).areas

    def _extract(self, gist: str, surface_text: str) -> ProductMap:
        """结构化提取 + JSON 解析，失败重试一次，仍失败返回空 ProductMap。"""
        raw = self.roles.map_product(gist, surface_text)
        try:
            return ProductMap.from_json(raw)
        except (ValueError, TypeError):
            raw2 = self.roles.map_product(gist, surface_text, repair=True)
            try:
                return ProductMap.from_json(raw2)
            except (ValueError, TypeError):
                return ProductMap()
