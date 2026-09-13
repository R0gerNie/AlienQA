# 模块 04：Browser Controller（浏览器执行器）

> 这一层**完全不要让 LLM 直接碰浏览器**。Agent 只产出结构化 `Action`，由执行器落地。

---

## 1. 职责

- 接收结构化 `Action`，映射为浏览器操作。
- 提供截图、DOM snapshot、等待页面稳定。
- 底层 Playwright / Chromium；必要时降级 PyAutoGUI / computer-use（OS 级输入边界场景）。

## 2. 输入

```json
{ "type": "click", "target": { "text": "申请退款" } }
{ "type": "type",  "target": { "selector": "#email" }, "text": "test@example.com" }
```

## 3. 输出

- 执行结果：成功/失败 + 异常信息。
- before / after 截图、DOM snapshot、URL、耗时。
- 供 05 / 07 / 13 消费的原始数据。

## 4. 关键设计

- **Action 与执行解耦**：Agent 只描述"做什么"，执行器负责定位、等待、重试、滚动到可见。
- **定位优先级**：`text → role → selector → 坐标`（坐标是兜底）。
- **可回放性**：每次执行记录精确参数（浏览器版本、viewport、URL、cookies、action sequence），为 Replay 服务。
- **统一接口**：`PlaywrightDriver` 与 `PyAutoGuiDriver` 实现同一 `BaseDriver`，配置切换。

## 5. 接口契约

```python
class BaseDriver:
    def launch(self, project: Project) -> None: ...
    def execute(self, action: Action) -> ExecutionResult: ...
    def screenshot(self) -> bytes: ...
    def dom_snapshot(self) -> str: ...
    def collect_runtime(self) -> RuntimeSignals: ...   # console/network/exception
    def wait_for_settle(self) -> None: ...
```

## 6. 关系

- 上游：`06 Action Planner`（Action 来源）。
- 下游：`05 State Tracker`、`07 Observation Engine`、`13 Replay Engine`。

## 7. 实现要点

- 挂载 `page.on("console"/"pageerror"/"requestfailed"/"response")` 采集运行时信号。
- 点击前自动等待元素可交互；点击后等待网络/渲染稳定。
- 失败重试策略：定位失败换 selector，再失败记异常。
- 在 [`docs/engineering/baselines.md`](../engineering/baselines.md) 的可运行基线（如 cal.diy）上做端到端回归。

## 8. 验收标准

- `click/type/hover/select/goto` 五种 Action 在 Playwright 下稳定执行。
- 每次执行都能产出 before/after 截图与运行时信号，且参数可回放。

## 9. 开放问题

- 需要真实 OS 输入的边界场景清单（系统弹窗、跨应用拖拽等）。
- 多浏览器（Firefox/WebKit）支持优先级。
