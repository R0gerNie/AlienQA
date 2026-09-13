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

## 10. 实现拆解（2026-09-13 归档）

> 决策：① 新增 `Role.REPORTER`（报告编排，config 可配模型/温度/fallbacks 走 LLM 层轮换契约）；② 前端 Flask + Jinja2（已装）；③ 保留 planbook 四态（confirmed/rejected/by-design/skipped），但 **UI 只暴露二态 switcher**（采信→confirmed / 不采信→rejected）；**报告生成前若有证据仍处于 by-design/skipped/pending，拒绝生成**。

### 子模块

```
alienqa/review/
├── models.py    # Decision(5 态含 pending) / ReviewState / Report
├── service.py   # HumanReview.inbox/decide/accepted/sorted_evidences
├── report.py    # ReportBuilder.build（gate + LLM 编排 HTML）
├── webui.py     # Flask：evidence 列表(switcher+排序) + /report
└── __init__.py
```

### 步骤

- **S0** `Role.REPORTER` + config `reporter:` 段 + `LlmRoles.compose_report`（返回 HTML 片段）。
- **S1** `Decision`（pending/confirmed/rejected/by-design/skipped）+ `ReviewState`（evidence_id→decision+note）+ `Report`。
- **S2** `HumanReview`：decide、accepted（只取 confirmed）、排序（severity / alphabetical）。
- **S3** `ReportBuilder.build`：gate（存在 by-design/skipped/pending → ValueError）→ 采信项 JSON → LLM 编排 HTML（含复现指导 + root cause）。
- **S4** Flask 前端：`/`（列表 + switcher + 排序）、`/decide`（POST 二态）、`/report`（LLM HTML）。
- **S5** 测试：状态机、排序、只含采信、gate 拦截、Flask test client。

