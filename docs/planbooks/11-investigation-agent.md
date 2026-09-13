# 模块 11：Investigation Agent（调查员）

> 与 Explorer 必须分开。Explorer："我第一次看到这里，我觉得不对劲。" Investigator："好，我现在允许你看源码，查一下为什么。"

---

## 1. 职责

- 对每个 Issue，**允许**访问源码 / DOM / React tree / console / network / stack trace / Git diff / API。
- 生成：Root Cause Hypothesis、Reproduction Steps、Technical Evidence、Affected Components。

## 2. 输入

- `Issue`（10）+ 关联 Evidence + **专家上下文（可看源码）**。

## 3. 输出

```json
{
  "issue_id": "ISSUE-007",
  "root_cause_hypothesis": "RefundModal 在 order.refunded 状态下未渲染 children，导致空 Modal",
  "reproduction_steps": ["1. 登录 -> 订单列表", "2. 对已退款订单点击『申请退款』", "3. 观察 Modal 内容为空"],
  "technical_evidence": { "stack_trace": "...", "api": "GET /api/refund -> 200", "component": "RefundModal.tsx" },
  "affected_components": ["RefundModal", "OrderDetail"]
}
```

## 4. 关键设计

- **权限隔离**：Explorer（陌生人，禁源码）与 Investigator（专家，可看源码）是两个上下文包，互不污染。
- **工作流**：陌生人发现问题 → 专家调查问题（自然的人类 QA 流程）。
- 输出结构化，供 12 报告与人工审核。

## 5. 接口契约

```python
class InvestigationAgent:
    def investigate(self, issue: Issue, expert_ctx: InvestigatorContext) -> Investigation: ...
```

## 6. 关系

- 上游：`10 Evidence Deduplicator`。
- 下游：`12 Human Review + Report`。

## 7. 实现要点

- 从源码仓库按 affected route 检索相关文件，结合 stack trace 定位。
- 生成复现步骤时，优先引用 Evidence 的 action trace。

## 8. 验收标准

- 对注入的"空 Modal"bug，能给出指向正确组件的 Root Cause Hypothesis 与可执行复现步骤。

## 9. 开放问题

- 专家上下文的源码检索范围与成本控制。
- 是否需要多次"查证-修正"迭代。

## 10. 实现拆解（2026-09-13 归档）

> 决策：① 新增 `Role.INVESTIGATOR`（专家角色，模型/温度/fallbacks 走 LLM 层配置，可轮换）；② 源码检索按路由/组件名关键词过滤 `visible_files`（成本可控）；③ driver 加 `dom()`（`page.content()`）。React tree / git diff 本期延后。

### 子模块

```
alienqa/investigation/
├── models.py    # Investigation
├── retriever.py # 源码关键词检索
├── context.py   # build_investigator_context
├── agent.py     # InvestigationAgent.investigate
└── __init__.py
```

### 步骤

- **S0** `Role.INVESTIGATOR` + config `investigator:` 段 + `LlmRoles.investigate(expert_ctx, repair)`（结构化 JSON）。
- **S1** `Investigation` 模型 + 白名单解析。
- **S2** 扩展 `InvestigatorContext`（+console/network/api/action_trace + `to_text`）+ `retriever` + `context` 装配。
- **S3** `driver.dom()`。
- **S4** `InvestigationAgent.investigate`（repair 重试一次）。
- **S5** 测试：白名单、验收（空 Modal 指向 RefundModal + 可执行复现步骤）、源码检索、复现步骤引用 action trace、与 Explorer 隔离。

