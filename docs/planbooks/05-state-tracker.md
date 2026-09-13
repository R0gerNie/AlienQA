# 模块 05：State Tracker（状态追踪器）

> 整个系统的核心基础设施之一：负责知道"我刚才在哪里、去过哪里"，形成 **State Graph**。

---

## 1. 职责

- 维护 State 序列与 State Graph。
- 识别 `route / modal / toast` 等状态维度，判断"这是不是新状态"。
- 防重复：已探索状态不再重复点击，避免无限循环。

## 2. 输入

- 每次 Action 执行后的 `route`、DOM/可见文本、modal/toast 等 UI 状态（来自 04）。

## 3. 输出

```text
State #001  route=/orders, modal=closed
        ↓ click
State #002  route=/orders, modal=refund
        ↓ click confirm
State #003  route=/orders/123, toast=success
```

```mermaid
flowchart TD
    Login --> Dashboard --> Orders
    Orders --> OrderDetail
    OrderDetail --> Refund
    OrderDetail --> Cancel
    Orders --> Search
```

## 4. 关键设计

- **状态签名（State Signature）**：`route + 关键 UI 状态（modal 是否打开、主要文本 hash）`。
- **相似状态合并**：签名相同视为同一状态，避免重复探索。
- **持久化 State Graph**：供 Planner 查询"哪些状态已探索"。
- 记录 `parent` 与触发 `action`，保证可回溯。

## 5. 接口契约

```python
class StateTracker:
    def observe(self, route, snapshot, action=None) -> State: ...  # 新状态或合并到已有
    def is_new(self, route, snapshot) -> bool: ...
    def explored(self, state: State) -> bool: ...
    def graph(self) -> StateGraph: ...
    def sequence(self) -> list[State]: ...


def normalize(text: str) -> str: ...      # 可插拔去噪规则

def signature(route: str, text: str) -> str: ...  # 去噪后哈希
```

## 6. 关系

- 上游：`04 Browser Controller`。
- 下游：`06 Action Planner`、`03 Exploration Context`。

## 7. 实现要点

- 用 `route + modal + toast + visible_text_hash` 计算签名，哈希入集合。
- 文本 hash 需去噪（时间戳、随机 id、金额数字归一化）。

## 8. 验收标准

1. 相同 `route + 可见文本` → 相同 `signature`，`observe` 返回同一 State（去重）。
2. 时间戳/随机 ID 变化 → `signature` 不变（去噪）。
3. 可见内容变化（tab 切换 / modal 打开 / counter 自增）→ 产生新 State。
4. 重复点击同一按钮 → 节点数不增长。
5. State Graph 边正确：`parent → action → child`。
6. `graph` 可 JSON 序列化，`save/load` 往返一致。

## 9. 开放问题

- 状态签名中"文本 hash 归一化"的规则（数字/日期/随机串如何处理）。
- 深层状态（如滚动位置、分页页码）是否纳入签名。

## 10. 实现步骤（建议顺序）

1. **State 模型 + 签名**：`State` dataclass + `normalize()` / `signature()`，去噪规则可插拔。
2. **driver 补快照能力**：`PlaywrightDriver.url()`、`visible_text()`（body 可见文本）。
3. **StateTracker 核心**：`observe / is_new / explored / graph / sequence`，签名去重 + 边记录。
4. **与 driver 集成**：`tracker.capture(driver, action)`（执行后抓快照并 observe）。
5. **持久化**：`graph.to_dict()` + `save/load`（JSON）。
6. **测试/验收**：新增 `tests/fixtures/state-app/`（含 tabs/modal/counter/clock），单元 + 集成测试对齐第 8 节 6 条验收标准。
