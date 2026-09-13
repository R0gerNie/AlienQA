# 模块 02b：Product Mapper（浏览器黑盒产品地图）

> 是 [`02-product-mapper.md`](02-product-mapper.md) 的 **b 变体**：没有源码可读，只能"看浏览器"时建立 Product Map。
> 一句话："我不读文件，我看页面上显示出来的文字和控件。"

---

## 1. 定位

源码模式下 02 的输入是 `Project` + 可见源码 + README；黑盒模式下这些都没有。
02b 把输入替换为 **浏览器实时表面**（可见文字 + DOM 结构），但 **LLM 的概括流程完全复用**：
`summarize_gist`（粗读）→ `map_product`（细读，结构化）→ 白名单解析 `ProductMap`。

## 2. 输入

- `Project`（01b，`visible_files=[]`）
- 浏览器实时表面：`driver.visible_text()`（或 DOM 标签结构摘要）

## 3. 输出

与 02 完全相同的 `ProductMap`（areas / pages / actions / entities / roles / states / relations），
不含任何测试结论。

## 4. 关键设计

- **只换"表面来源"，不换"概括逻辑"**：
  - 源码模式：`surface_text = build_surface_text(project, root)` + `readme`
  - 黑盒模式：`surface_text = driver.visible_text()`（`readme=""`）
  - 两者都走 `LlmRoles.summarize_gist(readme, surface_text)` → `map_product(gist, surface_text)`，**roles 零改动**。
- **"用户可见"天然成立**：`visible_text()` 就是用户眼睛能看到的内容，不再需要 01 的可见性评分漏斗。
- 表面文本可能很大（如 swagger），沿用 02 的预算截断（`page_text[:4000]` 等常量）。

## 5. 接口契约

```python
class ProductMapper:
    def map(self, project: Project) -> ProductMap: ...              # 源码模式
    def map_from_browser(self, project: Project, surface_text: str) -> ProductMap: ...  # 黑盒模式
```

## 6. 关系

- 上游：`01b Project Loader (Browser)` + `04 Browser Controller`（提供 `visible_text`）。
- 下游：`03 Exploration Context`（不变）。

## 7. 实现要点

- `map_from_browser` 内部复用 `_extract(gist, surface_text)`（已存在），仅改 `gist` 与 `surface_text` 的来源。
- 建议把 `map_from_browser` 放到 `ProductMapper` 上，而不是新开类——保持单一职责与最小改动。

## 8. 验收标准

- 对静态 demo（`demo-app/index.html`）用黑盒方式（只给 `visible_text`）能产出与源码方式一致的主旨与区域。
- 对 SPA（页面渲染后）能产出非空 `ProductMap`；页面空白时返回空 `ProductMap` 且不报错。

## 9. 开放问题

- DOM 结构摘要（标签树/可交互元素清单）是否作为 `surface_text` 的补充输入——倾向只先给 `visible_text`，不足再补 DOM 结构。
