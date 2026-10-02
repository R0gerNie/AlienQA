# T06 实施记录：开发者决定、双模式报告与离线 HTML

日期：2026-10-01。对应 [T06 H01～H08](mvp-planbooks/technical/06-review-report-artifacts.md) 与 [MVP-02 R03～R06](mvp-planbooks/02-findings-review-report.md)。目标仍是独立开发者的单人本机 QA 与一般用户认知分析。

## 1. 已交付行为

主控制台和 CLI 独立审核均提供“确认问题 / 不采信 / 按设计 / 暂跳过”以及备注；初始待审单独显示。按设计不删除原始认知落差。保存后刷新恢复决定与备注；网络失败、非成功状态、非法响应均保留编辑并允许重试。既有重放按钮继续可用。

`ReportBuilder.build(..., *, mode="confirmed", scan_context=None)` 支持 analysis/confirmed。旧 API 默认与无 mode 的报告 URL 保持 confirmed；CLI 新增 `--report-mode`，默认 analysis。

| 模式 | 展示内容 | 门槛 / 文件 |
|---|---|---|
| analysis | 全部发现、五态决定及备注 | 未审、按设计、跳过不阻断；`analysis.html` |
| confirmed | 开发者确认的发现 | 保留 pending/by-design/skipped gate；`report.html` |

`accepted_count` 仍只计 confirmed，`total_count` 仍计所有 Evidence；新增 `mode` 与 `displayed_count`。未记录发现不代表测试全部通过。可选 reporter 失败不影响确定性正文。

报告显示发现来源、缺项、原始动作/技术信号/可见文字/截图、事前预期与依据、模型摘要和推理、调查假设及失败状态、回放结果、开发者决定与备注。同一 Issue 的成员逐条保留；技术候选不虚构认知预期或依据；旧字段标未记录。主控制台未保存的运行预算明确显示未记录，CLI 注入其实际参数预算。

## 2. 快照与保存顺序

- `RunManager.load_report_snapshot` 在共享本地 RLock 内复核终态，一次加载 v2 `scan.json` 并复用 T04 的成员、原始引用及事前预期身份检查。报告使用该权威记录；独立汇总文件不覆盖它。
- done/partial/error/timeout/cancelled 可导出；running/unknown/cleanup_failed 拒绝，即使 HTML 缓存已存在。查看与下载使用同一入口和门槛。
- 旧目录使用明确兼容读取，不伪造 checkpoint_seq；可选文件缺失与存在但 JSON/schema 损坏分开处理。必需结果缺失且没有失败诊断时拒绝伪分析。
- Evidence/调查、决定/备注、范围、诊断、回放结果更新与报告生成共用 RunManager 锁。增量扫描数据更新同步提交到既有 scan.json；旧目录继续写兼容导出。
- 保存前先删除双缓存，保证删除失败时不推进决定；成功保存后再次失效。HTML 与 review.json 复用原子写入，失败明确返回，避免半页缓存。
- 回放 worker 只写完成结果，parent 在锁内接收并保存正式 replay_results、失效报告；不增加跨进程锁、队列、哈希或审计库。
- 独立审核由 CLI 注入已结束 collect 的 context，以局部锁保护重载磁盘 review、复制状态、保存和生成；旧嵌入 API 兼容为调用者提供的已完成证据。

## 3. 入口与离线产物

```bash
python -m alienqa --url http://localhost:3000 --artifacts-dir artifacts/my-run
python -m alienqa --url http://localhost:3000 --artifacts-dir artifacts/my-run --review
python -m alienqa --url http://localhost:3000 --artifacts-dir artifacts/demo --report-mode confirmed --auto-confirm
```

显式 `--output` 优先于所选模式的默认路径；不得与另一模式路径重合。自动采信的备注和 CLI 输出标明“未经人工审核”。审核与历史页提供独立的生成/查看/下载入口；旧 confirmed gate 提供 analysis 路径。

截图内嵌 data URI；相对 artifact 按 run 目录读取，旧绝对路径仍兼容。缺图、缺技术文件或读取失败保留局部提示。动态文字、备注、异常及 DOM 转义；模型片段复用 HTMLParser 白名单。正文及 reporter 数据不序列化 storage_state/cookies/origins；本地回放包继续保留恢复所需会话。HTML 不依赖线上资源或活动脚本。

## 4. 实际验证

全量 **431 项通过，覆盖率 87.01%**，包含真实 Chromium、HTTP 与 worker 生命周期回归。

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers COVERAGE_FILE=.venv/t06.coverage .venv/bin/pytest \
  --cov=alienqa --cov-report=term --cov-report=json:.venv/t06-coverage.json --maxfail=3
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t06
```

| 测试入口 | 验证内容 |
|---|---|
| `test_t06_reports.py` | 五态分析、计数、旧 gate、依据、凭据排除、相对文件、双 API 输入及保存失败、坏文件、终态、一次权威读取、双缓存及并发交错 |
| `test_t06_browser_flow.py` | 主 UI / 独立审核：真实扫描产生双来源与调查失败诊断；按设计备注、另一条 pending、下载、改为确认、重新下载、复制到另一目录离线打开；真实截图、依据、转义和无脚本执行 |
| `test_t06_browser_flow.py` | 两入口的网络失败、HTTP 500 和非法成功响应；编辑保留、控件恢复、重试和刷新 |
| `test_cli_regressions.py` | 默认 pending analysis、confirmed gate、自动采信标记、显式输出及参数校验；审核 context/诊断接线 |
| 既有回归 | T03 事前绑定、T04 停止后的前缀、控制台重放、旧 confirmed 报告/净化与 CLI 路径继续通过 |

sdist/wheel 构建通过，已检查审核/运行模板、T06 测试及实施记录进入对应发行包。此检查不代替仓库外干净安装验收。

本轮模型响应由替身控制；真实浏览器扫描和离线阅读证明工程交付链路，不证明真实模型判断效果。没有执行付费模型、真实小应用效果评估、Windows 或远程 CI。

H01～H08 的工程范围已完成。仓库外干净安装及发布验收仍由 Q05/U07 承接；N06 效果验收开放。建议下一步实施 T08，提供完整 attempt、实际用量与未知费用记录，支持真实模型评估。
