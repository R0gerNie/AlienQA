# 模块 08：Expectation Engine（俺寻思引擎）

> 整个产品最有特色的模块。**不是** `Expected behavior = PRD`，而是：`Expected behavior = 当前这个"陌生用户"根据上下文形成的自然预期`。

> 2026-10-01 当前 MVP 使用固定一般用户，预期依据限定为可见文案、通用交互惯例和已经观察到的行为。新增 basis、发散控制、可见历史与合理例外的工程计划见 [MVP-01](../engineering/mvp-planbooks/01-general-user-judgment.md)。当前 action 绑定与四态判定已实现，新增规则尚未落地；不做岗位/行业画像。

---

## 1. 职责

- 基于受限上下文 + 当前页面，形成"自然预期"。
- 对比 Observation，产出 **Expectation Mismatch**（注意：**不是 Bug**）。

## 2. 输入

- `ExplorerContext`（03，认知防火墙过滤后的上下文）。
- `Observation`（07）。

## 3. 输出

```json
{
  "page": "/orders",
  "trigger": { "type": "click", "target": { "text": "保存" } },
  "expectations": [
    "点击后应出现保存成功提示",
    "页面状态应发生变化",
    "按钮应进入 saved 状态"
  ],
  "observation": "点击后无任何可见反馈",
  "mismatch": {
    "expectation": "用户应该能够知道保存是否成功",
    "observation": "No visible feedback",
    "level": "HIGH"
  },
  "reasoning": "保存类操作，普通用户天然预期有成功或失败提示"
}
```

## 4. 关键设计

- **先预期再执行，判定消费观察**：预期生成不读 Observation 细节，避免"顺着结果找理由"。每条预期绑定当前选定动作，不能拿整页其他动作的预期评判本次交互。
- **高温度采样取并集**：同一动作采样 2~3 次，合并预期集合，鼓励发散。
- **只产出 Mismatch，禁止定性 Bug**：Bug 的定性留给 09/11/12。
- 预期必须来自"陌生用户直觉"，不得引用 PRD/实现。

## 5. 接口契约

```python
class ExpectationEngine:
    def expect(self, ctx: ExplorerContext, page_info, action=None) -> list[Expectation]: ...
    def evaluate(self, expectations, observation) -> JudgmentResult: ...
    def judge(self, expectations, observation) -> list[ExpectationMismatch]: ...
```

2026-10-01 实现契约（C02）：`Expectation.action_desc` 记录动作绑定；`evaluate` 返回 `passed / mismatch / failed / inconclusive`。无预期、缺少观察或动作不匹配为无法判断；调用或结构解析失败明确返回失败。兼容的 `judge` 仅在判定完成时返回列表，失败/无法判断抛出 `JudgmentError`；空列表不能代表模型故障。非法输出的修复重试不会消除最终失败记录。回归见 `tests/test_expectation_engine.py`、`tests/test_pipeline_regressions.py`。

## 6. 关系

- 上游：`03 Exploration Context`、`07 Observation Engine`。
- 下游：`09 Evidence Engine`。

## 7. 实现要点

- 预期生成 prompt 强调"第一次打开产品、未经培训的普通用户直觉"。
- 判定输入只含 `action + before/after + expected + 技术信号`，不含源码。

## 8. 验收标准

- 对"保存后无反馈"场景，能产出 HIGH 级 Mismatch，且预期表述为"用户应能知道是否成功"而非 PRD 语句。
- 产出中不包含"bug"定性词。

## 9. 开放问题

- Mismatch 等级的量化阈值（HIGH/MEDIUM/LOW）。
- 多轮采样合并的去重与冲突处理。
