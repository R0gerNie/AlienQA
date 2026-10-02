# T09：分层验收、干净安装与实验性发布

日期：2026-10-02。范围：独立开发者的本机 QA 与一般用户认知分析。先前 T01～T08 已以 `9b5a89b` 提交并推送；本记录描述随后实施的 T09。工程验收与真实模型、人审、用户有效性分别关闭。

## 实现与交接

| 任务 | 落点与结果 | 仍需外部证据 |
|---|---|---|
| Q01 | `tests/fixtures/cases/` 的 19 个版本化场景，六类正常/异常/合理例外及两步历史；受控服务、新上下文重置、私有标注隔离 | 更丰富的任务由试用反馈决定 |
| Q02 | 复用 T02/T01 精确锁版本和 24 条实际框架路径；新增固定 upstream TodoMVC React 交互与独立回放 | 复杂业务应用及其他组合 |
| Q03 | 契约、实际 Chromium、生产管线替身分层；提交身份、角色输入、attempt 对账、待审及 HTML 不混为效果证据 | 模型解释的合理性需要人审 |
| Q04 | 扩展既有 `alienqa.evaluation`，支持 manifest 子集、真实应用版本/重置、共享调用上限、真实/替身来源；生成待审模板及保留分母的统计 | 新批真实调用预算、独立人审、有效发现与阈值 |
| Q05 | 分别创建 wheel/sdist 隔离 venv、重新安装依赖、独立 Chromium 缓存、pip check、安装后完整 CLI/UI/回放/审核/离线报告 | 其他平台组合 |
| Q06 | 默认 Ubuntu 3.11/3.13 回归、干净安装 job、显式框架 job；机器摘要严格区分证据层和失败/未运行 | 默认回归与 3.11 安装远程通过；可选框架 CI 未执行 |
| Q07 | 支持范围、已知限制和实验性 release gate 已落盘；没有自动确认或自动发布 | 实际开发者试用与效果门槛 |

沿用现有 Evidence、Decision、committed checkpoint、报告和 T08 计量，没有建立第二套产品接口。评估 manifest/labels 在产品输入之外；运行器给模型使用不含异常名称的运行编号。人审模板与 checkpoint 绑定，审核不能嫁接到其他 run。

## 固定外部小应用

上游：[TodoMVC](https://github.com/tastejs/todomvc)，commit `ff43b02e59dfa604386bb382034b2cd07c2bcd8a`，`examples/react`。通过其 package-lock 执行 `npm ci` 和 Webpack 构建，未修改第三方实现。

```sh
.venv/bin/python scripts/prepare_t09_todomvc.py --install
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  tests/test_t09_real_application.py --run-applications \
  --junitxml=artifacts/evaluation/t09-todomvc/junit.xml
```

源码、Node 依赖、缓存、构建均在忽略的 `examples/open-source/t09-todomvc/`；结果在 `artifacts/evaluation/t09-todomvc/`。新上下文/原入口恢复本样例初始数据，任务为新增→完成标记→Active 筛选，停止原服务后独立回放。该框架展示应用补充真实外部代码的机制证据，不能代表复杂业务产品，更不能代替真实模型与开发者价值验收。

## 可复跑命令

默认测试自包含，不安装 Node 或调用真实模型。框架和外部应用分别 opt-in：

```sh
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  --run-frameworks --run-applications --cov=alienqa --cov-report=term \
  --junitxml=artifacts/evaluation/t09/junit.xml
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t09
.venv/bin/python scripts/verify_t09_distribution.py \
  --wheel .venv/dist/t09/alienqa-0.1.0-py3-none-any.whl \
  --sdist .venv/dist/t09/alienqa-0.1.0.tar.gz
```

干净安装的工作目录在项目内忽略的 artifacts 中，与源码目录分离；清除源码 PYTHONPATH，两套 venv 均禁用 system-site-packages。测试资产来自版本对应 sdist；运行所需模板/配置来自 wheel。依赖缓存和浏览器不借用原 `.venv`。内部完整路径 helper 复用其调用解释器的依赖，此处调用者是新创建的隔离环境。

网络下载首轮触及 600 秒阶段超时，失败 summary 和日志保留；新增受限的 `--resume` 与可配置阶段超时，用原新环境/下载缓存恢复，不把失败历史抹掉。此处限制的是本地阶段时长，不代表模型费用上限。

结果摘要使用 `scripts/summarize_t09_validation.py`，接受结构 JUnit、浏览器 JUnit、安装 summary 与评估/人审文件；不由总测试数量、框架名称或替身推导真实效果。公开 CI 上传回归和安装摘要/日志，不上传私有会话和模型输入。

## 本轮证据

- 成对场景浏览器：20 项通过，19 个场景各执行两次；私有 manifest HTTP 404。
- 固定 TodoMVC：添加、完成、筛选与独立回放通过；模型调用 0。
- 生产管线替身：三类场景的终态提交、analysis、私有输入隔离、调用上限与 attempt 对账通过。
- 完整套件 745 项通过、覆盖率 88.20%，含 24 条锁版本框架路径及 1 条外部小应用路径；最终关联/矩阵修正的 25 项定向补充通过，其中 21 项重复，去重共 749 项；合并覆盖率仍为 88.20%。两套新依赖环境的 pip check 和安装后完整路径均通过；原始记录保存在项目内忽略目录。
- 本轮未启动真实模型。上一批 100 次上限已使用 98 次；新批预算仍需单独确定。独立人工审核尚未完成。

支持声明与 release gate 见 [兼容与发布状态](compatibility-and-release.md)。下一步回到 N06/C06/K06/V03：冻结本轮任务与模型配置，执行有预算的真实控制/例外/历史/小应用批次，独立审核并记录有效发现、未决、审阅分钟和未知费用，然后冻结下一轮阈值。

### 安装实测记录

`artifacts/evaluation/t09-installation/2bede4f4f2b54198bab350ce8849c2b6/summary.json`：wheel/sdist 两套隔离 Python 3.11 环境均 passed；pip check、CLI、真实 worker UI、独立回放、重开审核、离线 HTML 全部通过。Playwright 1.63.0、LiteLLM 1.103.2，独立项目内 Chromium 缓存。首次网络超时保留在 prior_attempts，恢复后成功。真实模型调用 0。

### 最终回归与证据汇总

完整套件 `artifacts/evaluation/t09/junit.xml`（745 项）与最终定向 `artifacts/evaluation/t09-final/junit.xml`（25 项，21 项重复）去重共 749 项，无失败/跳过；合并覆盖率 88.20%，明细 `.venv/t09-coverage-final.json`。定向补充核对不携带答案的运行 ID 仍能在人审侧找到参考标注、真实/替身来源分列、失败/未决的矩阵状态及请求计量对账。

最终发行代码另外在上述新依赖环境中从最终 wheel 和最终 sdist 构建的 wheel 各跑一次完整路径，均通过，证据为 `artifacts/evaluation/t09-installation/2bede4f4f2b54198bab350ce8849c2b6/final-validation/summary.json`。此复验复用刚独立安装的依赖/浏览器，不伪称第三、第四套新环境。

机器摘要 `artifacts/evaluation/t09/validation-summary.json`：structure/browser_mechanism/installation = passed，real_model/user_trial = not_run，independent_review = blocked，release_ready = false。默认与可选框架 CI 的语法/分级核对通过；本机 gh 未登录，未取得远程结果，不能写为 Ubuntu 已验收。

## 提交后的远程与真实基线增量

T09 已以 `f8928fe` 提交推送。首个远程 CI 暴露浏览器缓存目录与图片测试遍历顺序问题，修复 `52281e0` 后，[CI 37002558875](https://github.com/R0gerNie/AlienQA/actions/runs/37002558875) 的 Ubuntu Python 3.11/3.13 默认回归、Python 3.11 wheel/sdist 两套干净安装路径均成功。可选框架 job 未运行。

用户另授权 100 次 CLI 启动；真实控制、例外、历史和固定 TodoMVC 首轮用了 37 次，暴露输入/失焦合并及 Enter 探索缺口。后续修复、同配置复测、全部账目和人审状态见 [真实基线记录](t09-real-baseline-results.md)。上面的 0 次调用、远程未知及机器摘要是提交前工程阶段的历史记录，不能覆盖后续实际结果；人审、费用未知和试用 gate 继续开放。
