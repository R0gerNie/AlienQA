# 模块 03：Exploration Context（陌生人上下文 / 认知防火墙）

> 最特殊的模块之一：专门控制 **Agent 到底知道多少**。本质是一个 **Cognitive Firewall（认知防火墙）**。

---

## 1. 职责

- 定义 Explorer（陌生人）可见信息**白名单 / 黑名单**。
- 从 Product Map、State Tracker、Observation 中**只挑选允许的信息**，组装受限上下文包 `ExplorerContext`。
- 保证任何模块不得绕过本模块直接向 Explorer 塞信息。

## 2. 输入

- Product Map（02）、当前 State（05）、当前截图与可见文字（04/07）、已执行动作历史。

## 3. 输出

```json
{
  "allowed": {
    "screenshot": "current.png",
    "visible_text": "订单列表…",
    "action_history": ["click 申请退款"],
    "navigation": "可前往 /orders/:id",
    "product_brief": "这是一个电商后台，可管理订单…"
  },
  "forbidden": {
    "prd": false,
    "dev_comments": false,
    "git_history": false,
    "known_bugs": false,
    "internal_rules": false,
    "tech_details": false
  }
}
```

## 4. 关键设计

- **单一出口**：只有本模块能拼装 Explorer 上下文。
- **白名单过滤**：按字段白名单裁剪，黑名单项永不进入上下文。
- **认知边界可调**：白名单/黑名单做成配置，未来可收紧或放宽。
- **与 Investigator 隔离**：`InvestigatorContext`（11 用）允许源码 / DOM / React tree / stack trace / git diff，与 `ExplorerContext` 是两个独立上下文包。

### 允许 / 禁止对照表

| 允许 ✓ | 禁止 ✗ |
|---|---|
| 当前截图 | PRD |
| 当前页面可见文字 | 开发者评论 |
| 已执行过的动作 | Git history |
| 页面正常导航信息 | 已知 bug |
| 产品非常粗略的介绍 | 业务内部规则 |
| | 技术实现细节 |

## 5. 接口契约

```python
class ExplorationContext:
    def build(self, product_map, state, observation, history) -> ExplorerContext: ...
    def is_allowed(self, field: str) -> bool: ...
```

## 6. 关系

- 上游：`02 Product Mapper`、`05 State Tracker`、`07 Observation Engine`。
- 下游：`06 Action Planner`、`08 Expectation Engine`（二者只消费 ExplorerContext）。

## 7. 实现要点

- 用一个 `ContextPolicy` 配置描述白名单字段。
- 对截图做必要的压缩/裁剪，控制 token 成本。

## 8. 验收标准

- Explorer 上下文永远不含 PRD / 开发者评论 / git history / 已知 bug / 内部规则 / 实现细节。
- 通过单测断言：给全量信息，输出只含白名单字段。

## 9. 开放问题

- "产品非常粗略的介绍"的粒度上限如何量化。
- 是否需要按测试阶段动态放宽/收紧认知边界。
