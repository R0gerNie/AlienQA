# 模块 10：Evidence Deduplicator（证据去重）

> 一个 Bug 点五个不同按钮都白屏，不应产生 Bug #1..#5。应该：5 条 Evidence → 同一 root cause → 1 个 Issue。

---

## 1. 职责

- 对 Evidence 做 embedding / similarity → cluster → **Potential Issue**。
- 将多条同根因证据归并为一个 Issue。

## 2. 输入

- 多条 `Evidence`（09）。

## 3. 输出

```text
EV-001  EV-017  EV-023  EV-041
                ↓
           ISSUE-007
```

```json
{
  "id": "ISSUE-007",
  "title": "退款 Modal 内容为空",
  "evidence_ids": ["EV-001", "EV-017", "EV-023", "EV-041"],
  "root_cause_candidate": "RefundModal 渲染异常",
  "severity": "high"
}
```

## 4. 关键设计

- **两级聚类**：
  1. 硬聚类：同页面 + 同异常类型（console error 类 / network fail 类）。
  2. 软聚类：文本 + 截图 embedding 相似度。
- 输出 Issue，可人工合并/拆分。
- 聚类结果回写 Evidence（`issue_id` 关联）。

## 5. 接口契约

```python
class Deduplicator:
    def cluster(self, evidences: list[Evidence]) -> list[Issue]: ...
    def embed(self, evidence: Evidence) -> Vector: ...
```

## 6. 关系

- 上游：`09 Evidence Engine`。
- 下游：`11 Investigation Agent`、`12 Human Review + Report`。

## 7. 实现要点

- embedding 可复用 LLM 接口；相似度阈值可配置。
- 截图相似度用感知哈希（pHash）做快速预筛，再上 embedding。

## 8. 验收标准

- 同一根因的 5 条白屏证据归并为 1 个 Issue。
- 不同根因的证据不会被错误合并。

## 9. 开放问题

- 聚类阈值的人工可调与自动学习。
- Issue 自动标题生成的质量。
