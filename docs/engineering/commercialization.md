# 付费接口预留设计（暂不设计具体付费）

> 目标：现在**不设计定价/支付/账户**，只预留"插槽"与扩展点，保证未来商业化时不需要重构核心逻辑。

---

## 1. 原则

1. **解耦**：核心测试逻辑与商业能力解耦，核心代码不 import 任何具体支付/许可实现。
2. **默认关闭**：`commercial.enabled = false`，不影响自用与开源形态。
3. **只计数不收费**：用量计量埋点只记录数据，不触发任何扣费/限制。
4. **可替换**：未来接入商业能力时只替换 `Provider` 实现，不动核心流程。

## 2. 预留的扩展点

### 2.1 `licensing/` 模块（抽象层，默认空实现）

```text
alienqa/licensing/
├── __init__.py
├── base.py          # LicenseProvider / Entitlement / FeatureGate 抽象
├── null.py          # NullLicenseProvider：永远放行（v1 默认）
└── metering.py      # 用量计量：只记录 run/step/report 计数
```

核心抽象（伪代码）：

```python
class LicenseProvider(Protocol):
    def is_licensed(self) -> bool: ...
    def get_entitlement(self) -> Entitlement: ...

@dataclass
class Entitlement:
    plan: str              # "free" | "pro" | ...
    expires_at: datetime | None
    quotas: dict[str, int]  # 并发数/项目数/报告数等
    features: set[str]      # 功能开关集合

class FeatureGate:
    def enabled(self, feature: str) -> bool: ...
```

- v1 默认注入 `NullLicenseProvider`：`is_licensed()` 恒为 `True`，`get_entitlement()` 返回无限配额。

### 2.2 入口钩子

- `main.py` 启动时调用 `check_entitlement()`：v1 为**空实现**（直接放行），未来替换为真实校验。
- 报告页脚钩子 `render_footer()`：预留水印位置（试用版 / 付费版标记），v1 输出空字符串。

### 2.3 用量计量埋点（只计数，不收费）

- `Metering.record(event, payload)` 记录：`run_started`、`step_executed`、`report_generated`。
- 写入 SQLite `metering` 表，为未来按量计费/套餐限制留数据。
- v1 不拦截任何操作，仅落库。

### 2.4 配置开关

```yaml
# config/config.yaml
commercial:
  enabled: false        # 未来打开商业化能力
  provider: null        # 未来：payment / entitlement provider 名称
  metering: true        # 是否记录用量（默认真）
```

### 2.5 数据模型预留

- `license` 表：许可证类型、到期时间、配额（v1 建表但不启用）。
- `metering` 表：事件类型、时间戳、计数（v1 即启用，仅记录）。

## 3. 明确"以后再做"清单

- 定价策略（订阅 / 买断 / 按量）。
- 支付通道（支付宝 / 微信 / Stripe 等）。
- 账户系统与许可证激活服务器。
- 许可证加密与防破解机制。
- 试用期与功能梯度（free / pro 差异）。

## 4. 边界与约束

- v1 这些接口**只留空实现/占位**，不引入任何第三方支付依赖。
- 未来接入时，只需新增 `Provider` 实现并在配置中切换，核心测试逻辑与 `docs/PLANBOOK.md` 的工作流不变。
- 商业化相关改动必须遵循 `governance.md`：单独 PR、打 `commercial` 标签、说明影响面。
