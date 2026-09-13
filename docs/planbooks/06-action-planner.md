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
    def extract_candidates(self, driver, ctx) -> list[Candidate]: ...
    def score(self, candidate: Candidate, ctx) -> float: ...
    def plan(self, ctx, candidates, graph) -> Action | None: ...
    def should_stop(self, steps: int, elapsed: float, budget) -> bool: ...


def explore(driver, tracker, planner, budget=None) -> StateTracker: ...
```

## 6. 关系

- 上游：`03 Exploration Context`、`05 State Tracker`。
- 下游：`04 Browser Controller`。

## 7. 实现要点

- 从当前页面提取可交互元素作为候选集。
- 对候选打分排序，取最高分执行；维护已探索集合避免重复。

## 8. 验收标准

1. 未点击过的高风险/边界元素，打分高于普通元素。
2. 已点击过的元素不再被选中（去重）。
3. 链接指向未探索 route 时 novelty 加分。
4. 步数/时间预算耗尽 → `explore` 停止。
5. `explore` 在 demo app 上探索到 N 个状态且不无限循环。
6. `plan` 返回可直接交给 04 的结构化 `Action`。

## 9. 开放问题

- 评分权重如何随项目类型自适应。
- 是否引入"目标导向探索"（为验证某假设而定向操作）。

## 10. 实现步骤（建议顺序）

1. **数据模型**：`Candidate`（Action + 元素元数据）、`ExploreContext`（current_route/page_text/product_brief 占位，未来由 03 接管装配）、`ExploreBudget`（max_steps/max_time）。
2. **driver 补可交互元素枚举**：`PlaywrightDriver.interactive_elements()`（button / a[href] / input / select / textarea / [role=button|link]）。
3. **候选提取**：`extract_candidates(driver, ctx)`，过滤不可见/空元素。
4. **价值评分器（纯函数）**：RISK / BOUNDARY / NAVIGATION 关键词表 + `score(candidate, ctx)`（coverage_gain + risk + boundary + novelty 加权，权重可配置）。
5. **Planner 核心**：`plan` 打分排序取最高（带 reason）；维护 `clicked` 集合 + 从 `graph()` 读 explored_routes；`should_stop()` 预算判断。
6. **探索循环（端到端）**：`explore(driver, tracker, planner, budget)`，把 04+05+06 串起来。
7. **测试/验收**：单元（scorer/预算）+ 集成（demo app 上跑 explore），对齐第 8 节 6 条验收标准。
