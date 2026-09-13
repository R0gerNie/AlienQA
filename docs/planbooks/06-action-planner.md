# 模块 06：Action Planner（探索策略）

> 这才是真正的 Agent。面对"当前状态 + 当前页面 + 已经探索过什么"，回答：**下一步干什么最有价值**。不是"把所有按钮点一遍"。

---

## 1. 职责

- 主动探索（active exploration）：基于价值评分选下一步。
- 发现并优先调查**状态边界**（如"订单状态=已退款"时，优先调查"再次退款"）。

## 2. 输入

- `ExplorerContext`（03 过滤后的受限上下文）。
- `StateGraph` 与已探索覆盖（05）。

## 3. 输出

- 单个结构化 `Action`（交给 04）。

```json
{ "type": "click", "target": { "text": "再次退款" }, "reason": "state_boundary" }
```

## 4. 关键设计

- **价值评分（粗粒度）**：

```text
score = w1 * novelty        # 新状态/新页面
      + w2 * boundary       # 状态边界（非法/少见状态下的操作）
      + w3 * risk           # 高风险操作（删除/支付/退款）
      + w4 * coverage_gain  # 覆盖尚未探索的交互
```

- **预算控制**：步数/时间上限，耗尽即停。
- **可插拔策略**：随机 / 贪心（纯评分）/ LLM 规划（结合上下文）。

## 5. 接口契约

```python
class ActionPlanner:
    def plan(self, ctx: ExplorerContext, graph: StateGraph) -> Action: ...
    def score(self, candidate: Action, ctx) -> float: ...
```

## 6. 关系

- 上游：`03 Exploration Context`、`05 State Tracker`。
- 下游：`04 Browser Controller`。

## 7. 实现要点

- 从当前页面提取可交互元素作为候选集。
- 对候选打分排序，取最高分执行；维护已探索集合避免重复。

## 8. 验收标准

- 面对"已退款订单"场景，优先产出"再次退款"而非无关按钮。
- 步数预算耗尽时自动停止。

## 9. 开放问题

- 评分权重如何随项目类型自适应。
- 是否引入"目标导向探索"（为验证某假设而定向操作）。
