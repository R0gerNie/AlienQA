# AlienQA 开发指南

最新交互修复及验证见[弹层探索、目标身份、输入分支与焦点观察](popup-exploration-fix.md)。

本文是工程入口。面向使用者的介绍见[根 README](../../README.md)，重写前的完整 README 已收至[历史归档](archive/2026-10-02-readme-before-user-guide.md)。归档中的旧合并、人审验收与发布口径不能覆盖当前契约。

## 产品与工程边界

目标用户是独立开发者。AlienQA 模拟具备通用和行业知识、首次使用产品的外部用户，优先发现内部默认假设与外部认知之间的落差。岗位配置器、团队工作流和企业级管理后置。

当前认知契约为 `general-user-v4 / sampling-merge-v3 / judgment-v3`：采样取并集，一次提出即保留；关系不明或互斥不排除候选；等价去重保留成员与来源。独立人审、误报率和接受率不作为验收或发布门槛。用户采信决定是可选的报告选择。

工程检查的是输入输出结构、记录身份、实际观测和候选传递是否完整。它不能以“团队认为合理”否决模型预期。当前完整定义见[N03 生成契约](n03-generation-contract.md)与[MVP 共享契约](mvp-planbooks/README.md)。

## 代码入口与运行顺序

| 职责 | 入口 |
|---|---|
| CLI 与本机控制台 | `alienqa/__main__.py`、`alienqa/ui/` |
| 项目输入与定位 | `alienqa/loader/`、`alienqa/mapper/`、`alienqa/context/` |
| 动作与状态 | `alienqa/driver/`、`alienqa/state/`、`alienqa/planner/` |
| 观测、认知与持久化 | `alienqa/pipeline.py`、`alienqa/observation/`、`alienqa/expectation/`、`alienqa/evidence/` |
| 分组、调查与回放 | `alienqa/dedup/`、`alienqa/investigation/`、`alienqa/replay/` |
| 决定与报告 | `alienqa/review/` |
| 模型适配、计量与验收 | `alienqa/llm/`、`alienqa/evaluation.py`、`alienqa/acceptance.py` |

入口技术信号先保存，再执行模型分析。每步先冻结事前可见输入，形成预期，执行动作并提交原始结果，再判定和增量保存认知发现。近期已完成步骤的可见结果可进入下一步历史。产品内部资料用于定位或发现后的调查，不进入预期生成。

`scan.json` 是增量提交的权威快照，引用 `raw/` 中的观测；导出 JSON 是消费视图。取消或失败保留最后提交的前缀。分组、调查和可选 reporter 失败不能抹掉原始 Evidence 或阻止基础 analysis 交付。

## 开发环境与验证

在仓库根目录使用 Python 3.11+：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -c requirements-dev.lock
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/browsers"
python -m playwright install chromium
python -m pytest --cov=alienqa --cov-report=term-missing
python -m build --outdir .venv/dist/development
```

默认测试使用自包含 fixture、本地浏览器和模型替身，不执行真实模型调用。浏览器测试需要允许本地服务监听与浏览器启动。`requirements-dev.lock` 固定已测试的依赖；SPDX 许可元数据要求构建后端 setuptools 77.0.3+。

外部仓库基线显式运行：

```bash
python -m pytest --run-baselines -m baseline
```

所有第三方开源示例只放本项目内 gitignored 的 `examples/open-source/` 或 `baselines/`，其依赖、缓存、构建和数据也留在项目内部；运行结果放 `artifacts/evaluation/`。准备方式见[外部基线](baselines.md)、[T01](t01-implementation.md)、[T02](t02-implementation.md)及[TodoMVC/T09](t09-implementation.md)。

真实模型验收必须单独确定配置、版本、重置配方和调用上限。以下仅为命令示例，不能作为重复消耗既有预算的授权：

```bash
python -m alienqa.evaluation --config config/codex.yaml --manifest tests/fixtures/cases/manifest.json --output artifacts/evaluation/new-run --max-calls 40
```

上限跨样例共享，包含失败、修复和 fallback 等调用；token、金额和供应商内部请求数缺失时保留未知，不记为零。模型替身应显式声明 `--inference-kind substitute`。见[T08](t08-implementation.md)、[样例清单](../../tests/fixtures/cases/README.md)和[登录通道](codex-login-provider.md)。

发行安装验收使用 `scripts/verify_t09_distribution.py --wheel PATH --sdist PATH`，分别创建无系统依赖的环境并测试完整安装流程。默认单元测试、构建检查、真实浏览器机制、真实模型与真实应用证据分列，历史通过不覆盖新契约。

## 高级使用与运行产物

源码辅助依然以已运行 URL 为主：

```bash
python -m alienqa --project-root /path/to/frontend --url http://localhost:5173 --browser chromium --artifacts-dir artifacts/source-run
```

可通过 `--app apps/web` 选择子应用；源码路径和启动 cwd 使用所选应用。`--start-command 'npm run dev'` 显式授权启动服务，命令按参数执行而不经过 shell，退出时回收进程组。`--unit`、`--instructions` 定位探索范围，不进入预期模型；找不到范围会明确停止。

重放使用实际证据 ID：

```bash
python -m alienqa --replay artifacts/my-run/replay/EV-0001.json
```

回放恢复初始地址、会话与成功动作历史；依赖原目录、端口和外部服务仍可用。回放结果说明特定事实是否再现，不替代用户采信决定。

| 产物 | 用途 |
|---|---|
| `scan.json`、`raw/` | 已提交步骤、阶段、覆盖限制及原始观测 |
| `evidences.json`、`evidence.db`、`replay/` | 发现、隔离存储与恢复条件 |
| `investigations.json`、`review.json` | 可选调查、用户决定与备注 |
| `analysis.html` | 全部发现及不完整状态，默认离线交付 |
| `llm/calls/`、`llm/config.json`、`usage-summary.json` | 调用 attempt、实际配置与用量账目 |

`llm/private/` 的裁剪文本仍可能包含产品信息。独立 HTML 不携带会话凭据，但可能呈现业务内容；会话文件和回放包保留在本机。每次新扫描使用新目录，已有扫描通过 `--review-run` 重开。

CLI 退出码为 `0` 采集完成、`1` 执行失败、`2` 输入错误/扫描不完整/重放未确认、`130` 取消。动作、时间和模型请求各有边界；当前没有供应商费用硬上限。默认 CLI 报告为 analysis；底层旧报告 API 的默认 confirmed 及部分旧审核措辞仍需注意，详见[现状分析](project-status-2026-10-02.md)。

## 工程文档导航

- [当前项目分析](project-status-2026-10-02.md)：工程完成度、验证边界与下一轮重点。
- [开源应用测试](open-source-applications.md)：TodoMVC、IT-Tools、Memos 的固定版本搭建、自主/定向场景与计量对账。
- [功能 MVP 计划](mvp-planbooks/README.md)和[技术计划索引](mvp-planbooks/technical/README.md)：当前范围与依赖。
- [兼容与发布状态](compatibility-and-release.md)：支持证据、安装与远程 CI 的版本边界。
- [N03 校准](n03-calibration-results.md)、[N03 当前契约](n03-generation-contract.md)、[T09 历史真实基线](t09-real-baseline-results.md)：离线与模型验证记录。
- [原模块索引](../planbooks/README.md)、[治理](governance.md)：架构背景；旧愿景不能覆盖当前 MVP 契约。
- [历史 README](archive/2026-10-02-readme-before-user-guide.md)：迁移前完整内容。

项目代码采用[MIT License](../../LICENSE)。第三方示例与依赖的许可证独立保留，不能由本项目许可覆盖。
