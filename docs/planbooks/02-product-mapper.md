# 模块 02：Product Mapper（产品地图）

> "整个项目先读一遍"的地方。但**不是**把 5 万行代码塞进 GPT，而是建立一张 **Product Map**。

---

## 1. 职责

- 读取 `Project` + 前端**可见部分**源码与 README。
- 让 LLM 做"概括"，产出 Product Map：页面、路由、按钮、表单、实体、API、角色、状态、页面关系。
- **只回答"这大概是什么东西"，禁止产出测试结论。**

## 2. 输入

- `Project`（来自 01）+ 可见前端源码（过滤掉 minified / node_modules / dist）。

## 3. 输出

```json
{
  "areas": [
    {
      "name": "Authentication",
      "pages": ["/login", "/register"],
      "actions": ["login", "register"],
      "entities": ["User"],
      "roles": ["guest"],
      "states": []
    },
    {
      "name": "Orders",
      "pages": ["/orders", "/orders/:id"],
      "actions": ["refund", "cancel", "edit"],
      "entities": ["Order"],
      "roles": ["buyer", "admin"],
      "states": ["pending", "paid", "refunded", "cancelled"]
    }
  ],
  "relations": [
    { "from": "/orders", "to": "/orders/:id", "kind": "navigate" }
  ]
}
```

## 4. 关键设计

- **先过滤，再交给 LLM**：只读用户可见前端（组件/页面/路由/文案），不读实现细节。
- **两级粒度**：粗读（路由/页面）→ 细读（按钮/表单/实体/角色/状态）。
- **输出强结构化**：字段受 schema 约束；**无"测试结论/疑似 bug"字段**。
- 映射结果进入 `03 Exploration Context` 后，才允许被 Explorer 使用。

## 5. 接口契约

```python
class ProductMapper:
    def map(self, project: Project) -> ProductMap: ...
    def map_areas(self, project: Project) -> list[Area]: ...
```

## 6. 关系

- 上游：`01 Project Loader`。
- 下游：`03 Exploration Context`（经认知防火墙过滤后，供 06 / 08 使用）。

## 7. 实现要点

- 文件级过滤：排除 `*.min.js`、`node_modules`、构建产物、测试文件。
- 提示词约束："只概括产品是什么，不要判断它好不好、有没有 bug"。

## 8. 验收标准

- 对典型电商/后台前端，能产出包含页面、路由、按钮、实体、角色、状态的 Product Map。
- 产出中不包含任何测试结论或"疑似 bug"字段。

## 9. 开放问题

- 超大项目的映射分片与合并策略。
- 多语言/多租户前端的实体抽取规则。

### 9.1 待决项（2026-09-13 归档）

> 本期实现**未做**分片与多语言抽取，采用**预算截断兜底**：
>
> - 现状常量（`alienqa/mapper/filter.py`）：`MAX_SURFACE_CHARS=20_000`、`MAX_FILES=50`、`MAX_FILE_LINES=60`、`MAX_README_CHARS=4_000`。超出部分直接丢弃，不做分片与合并。
> - 触发条件：待 **03 Exploration Context** 接入后，用真实大 baseline（如 `baselines/twenty`、`baselines/chatwoot`）端到端跑一遍，确认 20k 字符是否足以覆盖主要路由/页面；不足则回补分片。
> - 分片方向（待定）：按 `VisibleFile.role` / 路由聚类分批调用 `map_product`，再合并 `areas`/`relations` 并去重。
> - 多语言/实体抽取方向（待定）：先统计 baseline 语言分布，再决定规则抽取或交由 LLM 抽取。

