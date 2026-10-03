"""ProductMapper：把 Project + 可见源码概括成强结构化的 ProductMap。

流程：过滤 → 读 README → 粗读(summarize_gist) → 细读(map_product) → 白名单解析。
全程只产出"产品是什么"，不产出测试结论。
"""
from alienqa.i18n import language_context, t as tr

from pathlib import Path

from ..llm import LLMClient, LlmRoles
from ..llm.jsonutil import loads_object
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
        readme = read_readme(Path(project.app_dir) if project.app_dir else root)
        gist = self.roles.summarize_gist(readme, surface_text)
        pm = self._extract(gist, surface_text)
        pm.brief = gist
        return pm

    def map_areas(self, project: Project) -> list:
        return self.map(project).areas

    def map_from_browser(self, project: Project, surface_text: str) -> ProductMap:
        """02b 黑盒：只靠浏览器可见文字建立产品地图，复用同一套概括流程。

        页面空白（无可读文字）时直接返回空 ProductMap，不打 LLM。
        """
        text = (surface_text or "").strip()
        if not text:
            return ProductMap()
        gist = self.roles.summarize_gist("", text)
        pm = self._extract(gist, text)
        pm.brief = gist
        return pm

    def _extract(self, gist: str, surface_text: str) -> ProductMap:
        with language_context(self.roles.language):
            return self._extract_localized(gist, surface_text)

    def _extract_localized(self, gist: str, surface_text: str) -> ProductMap:
        """结构化提取失败重试一次，仍失败显式报错，不能伪装成空产品地图。"""
        last_error = None
        for repair in (False, True):
            raw = self.roles.map_product(gist, surface_text, repair=repair)
            try:
                data = loads_object(raw)
                if "areas" not in data:
                    raise ValueError(tr("缺少 areas 列表；空地图需显式提供 areas: []"))
                for field in ("areas", "relations"):
                    items = data.get(field, [])
                    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                        raise ValueError(tr("{field} 必须为对象组成的列表", field=field))
                result = ProductMap.from_dict(data)
                self.roles.mark_parse("succeeded")
                return result
            except (ValueError, TypeError) as exc:
                self.roles.mark_parse("failed", exc)
                last_error = exc
        raise ValueError(tr("产品地图输出在修复后仍无效: {error}", error=last_error)) from last_error
