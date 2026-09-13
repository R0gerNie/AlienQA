# 模块 09：Evidence Engine（证据引擎）

> 商业产品里最应该下重功夫的地方。每次 AI 认为"奇怪"，就生成一条 **Evidence**。

---

## 1. 职责

- 接收 Expectation Mismatch + Observation，沉淀为结构化 Evidence。
- 证据必须**可复现**：同步写 Replay 数据（见 13）。
- 附置信度与分类。

## 2. 输入

- `ExpectationMismatch`（08）+ `Observation`（07）+ `Action` / State（04/05）。

## 3. 输出

```json
{
  "id": "EV-00231",
  "action": { "type": "click", "target": { "text": "提交订单" } },
  "expectation": "提交完成后应该获得明确反馈",
  "observation_summary": "页面停留在原状态",
  "technical": { "network": "POST /order -> 200" },
  "classification": "ux_ambiguity",
  "confidence": 0.91,
  "timestamp": "2026-09-13T10:00:00Z",
  "artifacts": {
    "screenshots": ["before.png", "after.png"],
    "dom_snapshot": "...",
    "console": "...",
    "network": "...",
    "video": "..."
  },
  "replay": {
    "browser": "chromium 128", "viewport": "1280x800", "os": "win32",
    "url": "http://localhost:3000/orders",
    "cookies": "session:...",
    "action_sequence": []
  }
}
```

## 4. 关键设计

- **Evidence 八要素**：What happened / What was expected / Why expectation was reasonable / Screenshot / Action trace / DOM snapshot / Console / Network / Timestamp / confidence。
- **分类**：`technical_bug | ux_ambiguity | missing_feedback | misleading_copy | other`。
- **置信度**：由视觉 + 运行时信号强弱估算（如"白屏 + 500"置信度高）。
- **与 Replay 联动**：每条 Evidence 必须含 `replay` 字段，否则视为不完整证据。

## 5. 接口契约

```python
class EvidenceEngine:
    def build(self, mismatch, observation, action, state) -> Evidence: ...
    def persist(self, evidence: Evidence) -> None: ...
```

## 6. 关系

- 上游：`07 Observation Engine`、`08 Expectation Engine`。
- 下游：`10 Evidence Deduplicator`、`13 Replay Engine`。

## 7. 实现要点

- 截图/DOM/console/network/video 落盘到 `artifacts/<run>/<ev_id>/`，数据库只存路径。
- 置信度规则可先用手写阈值，后续可学习。

## 8. 验收标准

- 每条 Evidence 都包含八要素 + 完整 `replay` 字段。
- 相同现象稳定生成一致 `classification` 与合理 `confidence`。

## 9. 开放问题

- 置信度计算是否需要模型打分 + 规则融合。
- video 录制的成本与开启策略。
