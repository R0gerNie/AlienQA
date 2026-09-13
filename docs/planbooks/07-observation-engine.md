# 模块 07：Observation Engine（观察器）

> 至少拆成两个：**Visual Observer（视觉观察）** 与 **Runtime Observer（运行时观察）**。两者合并，证据质量远高于单纯截图。

---

## 1. 职责

- **7.1 Visual Observer**：只关心"人眼看到什么"。
- **7.2 Runtime Observer**：DOM / Console / Network / HTTP status / JS exception / resource failure / URL / storage。

## 2. 输入

- `before screenshot`、`after screenshot`、`action`（04 提供）。

## 3. 输出

```json
{
  "visual": {
    "changes": ["modal_opened", "page_body_disappeared", "loading_persisted", "button_state_changed", "text_changed"],
    "blank_screen_score": 0.02
  },
  "runtime": {
    "console_errors": ["Uncaught TypeError: ..."],
    "network_failures": ["GET /api/refund -> 500"],
    "http_status": { "/api/refund": 500 },
    "js_exceptions": ["TypeError at RefundModal.tsx:12"],
    "resource_failures": [],
    "url": "/orders/123",
    "storage": { "localStorage": {}, "sessionStorage": {} }
  }
}
```

## 4. 关键设计

- **并行采集**：视觉由视觉 LLM 完成；运行时由确定性 hook 完成，互不阻塞。
- **合并为单一 Observation**：视觉"白屏" + 运行时"Uncaught TypeError + /api/refund 500" = 高质量证据。
- 白屏分（blank_screen_score）用像素方差等确定性手段计算，作为视觉 LLM 的客观旁证。

## 5. 接口契约

```python
class VisualObserver:
    def observe(self, before, after, action) -> VisualObservation: ...

class RuntimeObserver:
    def observe(self, page) -> RuntimeObservation: ...

class ObservationEngine:
    def observe(self, before, after, action, page) -> Observation: ...
```

## 6. 关系

- 上游：`04 Browser Controller`。
- 下游：`08 Expectation Engine`、`09 Evidence Engine`。

## 7. 实现要点

- Runtime 用 `page.on("console"/"pageerror"/"requestfailed"/"response")` 采集，确定性。
- Visual 用视觉 LLM 输出结构化变化列表，并附白屏分。

## 8. 验收标准

- 对"点击后白屏"场景，能同时产出视觉"主体消失"与运行时"JS 异常/接口错误"。
- 白屏分对纯白页面接近 1，对正常页面接近 0。

## 9. 开放问题

- 视觉变化分类（modal/loading/text 等）的粒度与稳定输出格式。
- storage 变化是否纳入观察（成本 vs 收益）。
