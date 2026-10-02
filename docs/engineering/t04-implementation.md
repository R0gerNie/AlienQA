# T04 实施与验证记录

日期：2026-10-01。环境：macOS、Python 3.11.14。对应计划：[T04 运行管线与持久化](mvp-planbooks/technical/04-runtime-pipeline-persistence.md)。
状态：P01～P07 的采证、编排和持久化范围已实现；父级完整 analysis 交付仍依赖 T03/T06/T07/T08 等后续节点。

## 1. 已实现的行为

- 入口监听先于导航安装；入口原始信号和技术候选先提交，再调用产品地图。启动/导航失败也尝试保存已收到的入口信号。
- 每次动作先保存输入、稳定 action_id、独立 step_id/attempt 和事前预期；执行成功或失败均先提交运行窗口，再取执行后截图、读取可见结果或调用模型。
- runtime 与视觉分离。预期/地图失败可继续技术 QA；指定单元无法定位时明确停止，不擅自扩大范围。视觉、判定或调查失败保留此前证据。
- 未捕获 JS exception、HTTP 5xx 建立 `technical_anomaly` 候选，无需伪造认知预期；confidence 保留未知。console error、失败请求和 4xx 仅保存原始信号，不直接升级为缺陷。
- 认知 Evidence 从事前已保存且文本匹配的预期继承单个 `expectation_basis`，类型限定为 `visible_copy / interaction_convention / observed_behavior`。执行后不会补写预期。
- 技术与认知证据共用 run 内编号；聚类保留全部成员，不跨来源替换。调查按 Issue 执行，其结果增量提交。
- UI 历史读取权威快照；取消、超时和 worker 失败追加诊断并保留前缀。迟到 success 不覆盖已裁定终态。CLI Ctrl+C 保存最后提交的前缀并返回 130。

## 2. 模块与产物契约

| 模块 | 责任 |
|---|---|
| `driver/runtime.py`、`playwright_driver.py` | 事件记录、时间、稳定 ID、上下文、脱敏、游标与上限 |
| `observation/runtime_observer.py`、`engine.py` | 冻结窗口，分别提供 runtime/visual 接口，保留旧包装 |
| `pipeline.py` | 阶段状态、动作身份/重试、技术降级、增量提交与调查 |
| `evidence/models.py`、`engine.py`、`storage.py` | 双来源 Evidence、原始引用、事前 basis、完整性与 SQLite 迁移 |
| `persistence.py`、`run_writer.py` | 同目录临时写入、flush/fsync、原子 replace、快照与恢复 |
| `ui/runs.py`、`ui/app.py`、`__main__.py` | CLI/UI 统一读写与停止恢复、错误可见、历史状态 |

每个新 run 使用独立目录；pipeline 拒绝覆盖已提交的扫描。典型布局：

```text
<run>/
  scan.json                # 唯一提交权威：内嵌步骤、证据、调查、诊断及 raw_refs
  raw/<uuid>.json          # 不变的原始事件窗口
  evidence.db              # 本 run 的 SQLite，不与其他 run 共用 EV 编号空间
  evidences.json           # 导出视图
  investigations.json      # 导出视图
  diagnostics.json         # 导出视图及新格式标识
  artifacts/               # 截图、DOM、技术观察；路径可由 artifacts_dir 指定
  replay/                  # 由 EvidenceEngine 按 artifacts_dir 保存，位置依调用方配置
```

UI 将截图与 replay 放在 run 的 artifacts 目录内；CLI 指定 `--artifacts-dir` 时该目录同时作为 run 根目录。以 Evidence 中的实际路径为准。

`scan.json` 与 raw 文件采用 `schema_version=2`。快照含单调递增 `checkpoint_seq`；raw 和派生导出先写，快照最后原子提交。写入中断时以最后成功提交的快照为准，未引用文件不算已保存结果。SQLite 是 Evidence 存储，汇总 JSON 是兼容导出，均不替代快照裁决。

原始记录包含 `record_id/run_id/step_id/action_id/phase/timestamp/kind/payload`。入口的 step/action 可为空；重复请求有不同 ID。动作窗口冻结后到达的事件归后续 background 窗口，不能因模型等待扩大归因。兼容摘要保留旧字符串字段。

默认每 run 最多保留 2,000 条事件，单条文本最多 4 KiB；超限记录 dropped_count/truncated，游标继续推进，既有 ID 不复用。只采集请求/响应元数据，不读取 body、Authorization 或 Cookie；URL 移除身份、fragment 并屏蔽常见敏感查询参数。回放会话状态仍遵守既有本地凭据边界。

无版本 JSON 和旧 SQLite 可读取；新列增量迁移，不自动搬迁旧数据库或给旧证据编造 basis。新快照损坏、未知版本、引用丢失显示明确错误。新格式缺少 `scan.json` 时根据导出标识报告 absent，不退回导出文件冒充完整扫描。旧记录缺诊断文件显示未知。

原子写提供本机进程中断恢复语义；没有验证断电、网络盘或分布式多写者语义。

## 3. 验证结果

最终全量回归：**336 passed，Python 行覆盖率 86.25%**，达到项目 80% 门槛。

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/pytest \
  --cov=alienqa --cov-report=term \
  --cov-report=json:.venv/t04-coverage.json --maxfail=3
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t04
```

sdist/wheel 构建通过；检查两种包均包含 `persistence.py`、`run_writer.py`，wheel 包含 UI 模板，sdist 包含 runtime 夹具。

| 验证 | 覆盖内容 |
|---|---|
| `test_runtime_records.py` | 重复 HTTP 记录、查询脱敏、窗口、文本截断、run 上限和 ID 不复用 |
| `test_t04_pipeline.py` | 入口先提交、动作后模型前提交；map/expect/execute/visual/judge/investigate 故障；缺截图、启动失败、稳定 action 重试、SQLite 故障和双来源成员 |
| `test_evidence_migration.py` | 旧 SQLite 迁移、新字段往返、跨 run 同编号隔离、4xx/console/requestfailed 反例 |
| `test_run_writer.py` | 提交故障保留旧快照、坏文件/未知版本/引用校验、陈旧导出不覆盖权威、缺快照、取消/超时前缀 |
| `test_t04_browser_recovery.py` | 三个真实 worker + Chromium 场景：入口地图阻塞、动作后视觉阻塞、判定阻塞；停止后重启 RunManager，核对原始 JS/503、证据与终态，拒绝迟到完成 |
| 既有 CLI/UI/回放/浏览器回归 | 与旧通道兼容，包括 Ctrl+C、进程清理、页面路由和产物读取 |

模型由替身控制响应、阻塞与失败；真实的是本地浏览器、HTTP 和工作进程。没有调用付费模型，也未执行真实复杂框架 benchmark、Windows 或远程 GitHub CI。本记录不证明认知判断效果已达标。

## 4. 下一步边界

以下保留 T04 交付时的边界；随后 T03 已接入可见输入、历史与判定绑定的工程实现，当前状态见[T03 实施记录](t03-implementation.md)。

T03 继续实现一般用户输入隔离、可见历史与完整判定绑定；本次仅接入必要的事前 basis 格式，不声称已解决源码/自由指令影响预期的问题。
T06 实现 analysis、四种处理决定的 UI 和离线交付；当前报告仍沿用 confirmed gate，技术候选可在历史和审核读取，但完整 analysis 导出尚未提供。
T05/T07/T08/T09 分别继续回放增强、完整使用入口、调用计量和真实模型/发行安装验收。R02/L03 要等联合用户路径完成后关闭。
