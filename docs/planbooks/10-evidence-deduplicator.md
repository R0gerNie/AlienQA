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

## 10. 实现拆解（2026-09-13 归档）

> 决策：① embedding **两种模式可配置**（`deterministic` 字符 2-gram + aHash / `llm` 文本 embedding + 截图仍用 aHash 预筛）；② 阈值可配置，默认文本 Jaccard `≥ 0.5`、截图 Hamming `≤ 8`（64 位）。

### 子模块

```
alienqa/dedup/
├── models.py      # Issue / Vector
├── similarity.py  # text_jaccard / ahash / hamming / cosine
├── engine.py      # Deduplicator.cluster / embed
└── __init__.py
```

### 步骤

- **S0** `Evidence.issue_id` 字段（回写关联）。
- **S1** `Issue` 模型（id/title/evidence_ids/root_cause_candidate/severity 取最高）。
- **S2** `similarity`：文本 2-gram Jaccard、截图 aHash（8×8 灰度阈值）、Hamming、LLM 向量 cosine。
- **S3** `embed()` 两种模式：deterministic（grams + aHash）/ llm（`litellm.embedding` + aHash，`embed_func` 可注入）。
- **S4** `cluster()` 两级聚类（并查集）：硬聚类 `(replay.url, 异常类型桶)` → 软聚类 `text_ok AND hash_ok`。
- **S5** Issue 生成 + 回写 `issue_id`。
- **S6** 测试：同页面同类型归并、5 条白屏跨页面归并、不同根因不合并、embed 确定性、回写、severity 取最高、LLM 模式。

