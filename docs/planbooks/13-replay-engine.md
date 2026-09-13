# 模块 13：Replay Engine（回放引擎）

> **实现优先级 P0（放得很靠前）**。一个 AI 测出来的东西，如果不能稳定复现，就很难进入开发团队的工作流。

---

## 1. 职责

- 为每条 Evidence 保存完整回放数据。
- 提供**一键重新执行**，稳定复现问题。
- 回放后对比原始证据，标记"可复现 / 不可复现"。

## 2. 输入

- `Evidence.replay` 字段（09 写入）。

## 3. 输出

```json
{
  "evidence_id": "EV-00231",
  "replay": {
    "browser": "chromium 128",
    "viewport": "1280x800",
    "os": "win32",
    "url": "http://localhost:3000/orders",
    "cookies": "session:...",
    "action_sequence": [ { "type": "click", "target": { "text": "申请退款" } } ],
    "screenshots": [], "dom_snapshots": [], "network_trace": [], "console": [], "video": ""
  },
  "result": { "reproduced": true, "match_score": 0.94 }
}
```

## 4. 关键设计

- **回放 = 重放 Action sequence + 还原会话态**（cookies/session + viewport + browser 版本）。
- 复用 `04 Browser Controller` 的确定性执行器，保证"同样的动作、同样的环境"。
- 每次回放与原始 Evidence 对比（截图/关键信号），给出 `match_score` 与 `reproduced` 判定。
- 不可复现的证据降权，提示可能是环境相关/偶发。

## 5. 接口契约

```python
class ReplayEngine:
    def save(self, evidence: Evidence) -> None: ...          # 09 调用，保存回放包
    def replay(self, evidence_id: str) -> ReplayResult: ...  # 一键回放
```

## 6. 关系

- 上游：`09 Evidence Engine`（保存回放数据）。
- 依赖：`04 Browser Controller`（执行回放）。

## 7. 实现要点

- 回放包需含：browser version、viewport、OS、URL、cookies/session state、action sequence、screenshots、DOM snapshots、network trace、console、video。
- 回放在隔离环境执行，避免残留状态影响。

## 8. 验收标准

- 对确定性 bug（如点击白屏），一键回放能稳定复现且 `reproduced=true`。
- 对偶发问题，能正确标记 `reproduced=false` 并降权。

## 9. 开放问题

- 回放环境与录制环境不完全一致时的容错策略。
- 是否需要并行回放以验证稳定性。

## 10. 实现拆解（2026-09-13 归档）

> 决策：① 会话态还原用 `launch(url, storage_state=None)`；② `match_score` 用**纯截图相似度**（信号只参与 `reproduced` 判定）；③ 回放结果存 `replay/<evidence_id>.json`。

### 子模块

```
alienqa/replay/
├── models.py   # ReplayResult（evidence_id / reproduced / match_score / note）
├── engine.py   # ReplayEngine.save(evidence) / replay(evidence_id)
├── scorer.py   # image_similarity + signal_overlap
└── __init__.py
```

### 步骤

- **S0** `Action.from_dict` / `Target.from_dict`：回放包 dict → 结构化 Action。
- **S1** `PlaywrightDriver.launch(url, storage_state=None)`：创建 context 时还原 cookies（localStorage 还原延后）。
- **S2** `ReplayResult` 模型。
- **S3** `save(evidence)`：回放包落盘 `replay/<evidence_id>.json`。
- **S4** `replay(evidence_id)`：读包 → `launch(url, storage_state)` → 逐条重放 `action_sequence` → 采 after 截图 + 运行时信号。
- **S5** `scorer`：两图缩到 64×64 灰度算平均绝对差相似度；信号重叠判定。
- **S6** `reproduced = match_score ≥ 0.7 或 信号命中`；`reproduced=false` 附降权提示（环境相关/偶发）。
- **S7** 测试：from_dict 往返、会话态还原、端到端复现、相似度、篡改包→不可复现、信号复现。

