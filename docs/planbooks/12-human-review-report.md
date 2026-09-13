# 模块 12：Human Review + Report（人工审核 + 报告）

> 最后一道闸：Evidence Inbox → Issue Builder → Report。人工确认的问题才进入报告。

---

## 1. 职责

- **Evidence Inbox**：人工逐条审核 Issue（确认问题 / 误报 / 设计如此 / 跳过）。
- **Issue Builder**：把确认项组装成 Issue。
- **Report**：自动生成含证据的报告，并可导出 GitHub Issue / Jira / Linear。

## 2. 输入

- `Issue` + Investigation（10 / 11）。

## 3. 输出

```text
┌────────────────────────────────────────┐
│ EV-0231                    HIGH        │
│                                        │
│ [Before]          [After]              │
│                                        │
│ 点击「申请退款」                       │
│                                        │
│ AI：Modal 打开，但内容完全为空         │
│                                        │
│ Console: TypeError                     │
│                                        │
│ [确认问题] [误报] [设计如此] [跳过]     │
└────────────────────────────────────────┘
```

- 报告内容：标题 / 环境 / 严重程度 / 复现步骤 / 预期 / 实际 / 截图 / 录像 / Console / Network / Root Cause hypothesis。
- 导出：`GitHub Issue` / `Jira` / `Linear`。

## 4. 关键设计

- **状态机**：`pending → confirmed | rejected | by-design | skipped`（可回退）。
- **只收录 `confirmed`** 进入报告。
- 审核 UI 与报告模板分离：UI 只管状态，报告只读数据。

## 5. 接口契约

```python
class HumanReview:
    def inbox(self) -> list[Issue]: ...
    def decide(self, issue_id, decision, note) -> None: ...

class ReportBuilder:
    def build(self, confirmed: list[Issue]) -> Report: ...
    def export(self, report: Report, target: "github|jira|linear") -> None: ...
```

## 6. 关系

- 上游：`11 Investigation Agent`（及 10）。
- 下游：外部系统（GitHub / Jira / Linear）。

## 7. 实现要点

- v1 用轻量 Web UI（Streamlit / Flask + 静态页），后续可做 VS Code 面板。
- 报告用 Jinja2 → HTML → PDF（Playwright 打印）。

## 8. 验收标准

- 审核状态正确流转，报告只含 `confirmed`。
- 报告包含完整证据（截图/录像/console/network/root cause）。

## 9. 开放问题

- 导出目标的优先级（GitHub 先行）。
- 多审核人协作与权限。
