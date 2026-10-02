# T04：运行时采证、分阶段编排与持久化

版本：2026-10-01-tech-2。状态：T04 工程范围已实现并完成本地验证；代码、产物布局与验证边界见[实施记录](../../t04-implementation.md)。
服务独立开发者的 URL QA 与一般用户认知分析，承接 MVP-02 的 R01/R02 和 MVP-03 的 L03/L04。
目标是把“浏览器发生了什么”先保存，再允许模型解释；停止、模型失败或调查失败仍能交付已采集的前缀。
复用当前 Python、SQLite、JSON、RunManager 和进程任务控制，不新增队列、工作流框架或第二套 Finding 数据库。

## 1. 实施前基线与明确缺口

下表保留拆解时的基线；当前实现状态以实施记录和下列交付表为准。

| 任务 | 当前交付 | 验证入口 |
|---|---|---|
| P01 | 结构化事件、稳定 ID、时间/上下文、窗口游标、脱敏及有界截断 | `test_runtime_records.py` |
| P02 | 入口在地图前提交；动作执行后在截图/模型前提交原始窗口与技术候选 | `test_t04_pipeline.py`、`test_t04_browser_recovery.py` |
| P03 | JS exception / HTTP 5xx 独立候选；4xx、console、失败请求仅保留原始信号 | `test_evidence_migration.py`、`test_t04_pipeline.py` |
| P04 | runtime/视觉拆分、预期失败继续技术 QA、调查失败保留前缀 | `test_t04_pipeline.py` |
| P05 | Evidence 增量字段、SQLite 迁移与 run 隔离、统一序列化 | `test_evidence_migration.py`、`test_evidence_engine.py` |
| P06 | 原子提交、权威快照、读取错误状态、停止/超时合并诊断及迟到完成保护 | `test_run_writer.py`、`test_t04_browser_recovery.py`、`test_cli_regressions.py` |
| P07 | 双来源候选共同聚类、保留所有成员、调查增量提交 | `test_t04_pipeline.py`、`test_deduplicator.py` |

T04 交付时已接入最小事前 basis 数据格式和 T07 的前缀恢复接口；随后 T03 已完成输入隔离、历史与判定绑定的工程实现，见[T03 记录](../../t03-implementation.md)。T03 真实模型验收、T05 完整回放增强、T06 analysis 与四态审核、T08 调用计量仍待推进。
因此仅关闭 T04 的采证/存储部分，不据此关闭父级 R02/L03 的完整用户交付验收。

| 当前文件 / 函数 | 已有能力 | 本计划需改进的边界 |
|---|---|---|
| `alienqa/driver/playwright_driver.py`：`_attach_listeners()`、`_on_response()`、`snapshot_runtime()` | 入口前挂载 console/pageerror/requestfailed/response；运行信号持续追加 | 信号为字符串列表，缺稳定记录 ID、时间和动作窗口；所有 HTTP ≥400 同桶 |
| `alienqa/observation/runtime_observer.py`：`observe()`、`_diff()` | 确定性采集，按列表长度求动作增量 | `{path: status}` 丢失同路径多次请求；重复窗口、截断后的游标没有约定 |
| `alienqa/observation/engine.py`：`observe()` | 合并视觉与技术观察 | 先执行视觉 LLM，随后采 runtime；视觉失败使技术观察也未返回 |
| `alienqa/pipeline.py`：`_collect_source()`、`_collect_browser()`、`_collect_live()` | 有步骤、诊断、动作预算、明确失败状态 | 源码模式先地图后启动；预期失败跳过动作；入口信号无独立证据；技术证据依赖 mismatch |
| `alienqa/pipeline.py`：`PipelineResult.save()` | 输出 scan/evidences/investigations JSON | 仅 collect 返回后保存，直接覆盖文件；模型调用中终止会丢失内存步骤 |
| `alienqa/evidence/engine.py`：`build()`、`persist()`、`_write_artifacts()` | 每条 mismatch 建证据，保存截图/技术信号/回放 | 无独立技术候选入口；缺采证来源引用，截图与证据首次持久化过晚 |
| `alienqa/evidence/models.py`、`storage.py` | `Evidence.from_dict()` 兼容缺字段；SQLite 增量添加状态字段 | 缺 finding_kind/basis/run/step 来源；默认共享 `evidence.db` 与重置 EV 编号不能保证跨 run 隔离 |
| `alienqa/ui/runs.py`：`save_results()`、`_write_json()`、`load_diagnostics()` | run 目录、原子 replace、旧记录加载 | 与 pipeline 有重复序列化；缺失诊断默认“不完整=false”，无法区分未采集与无故障 |
| `alienqa/ui/app.py`：`_scan_worker()`、`_complete_scan()` | worker 执行，parent 处理取消/超时 | 返回后才写结果；异常路径用空步骤保存诊断，会覆盖已有前缀 |

## 2. 共享输入、输出与提交点

输入来自 [T02 浏览器交互](02-browser-interaction-state.md)的动作执行窗口和监听，以及 [T03 一般用户认知](03-context-expectation-judgment.md)的事前预期或明确失败结果。
输出给 [T05 回放与调查](05-replay-dedup-investigation.md)、[T06 分析报告](06-review-report-artifacts.md)、[T07 本地运行](07-local-run-ui-lifecycle.md)、[T08 模型执行与计量](08-llm-execution-metering.md)；产品字段以[父契约](../README.md#4-共享契约只做必要的增量)为准。

| 对象 / 最小增量 | 契约 |
|---|---|
| run / step / action | `run_id` 是本次扫描身份；`step_id` 在 run 内稳定；`action_id` 绑定同一选定动作，重试另记 attempt，不靠文案关联 |
| phase | `entry / expectation / action / raw_capture / visual / judgment / investigation`；事实、模型状态分别记录，不能一个 passed 覆盖整步 |
| raw record | `record_id, run_id, step_id, action_id, phase, timestamp, kind, payload`；入口的 step/action 可为空，并标 `phase=entry` |
| runtime window | 返回游标范围、记录 ID 列表、截断标记；入口与动作窗口不重叠，同条记录被多个视图引用仍保持原 ID |
| Evidence | 增 `finding_kind, expectation_basis, run_id, step_id, action_id, source_record_ids`；技术 basis 为 null，认知 basis 引用事前已保存的预期 |
| schema | 新 run 扫描与原始记录采用 `schema_version=2`；Evidence 序列化携带版本。无版本按旧格式读取，未知新版本明确“不支持” |
| checkpoint | 原始文件与证据先完整写入，run 快照最后提交；只有最后成功提交的快照算已保存前缀，未引用临时文件不算扫描成功 |

已新增轻量 `alienqa/run_writer.py::RunWriter`，统一 CLI/UI 的 checkpoint 入口。
构造函数绑定目录与 run_id；`checkpoint(*, phase, steps, evidences, diagnostics, raw_refs, ...)` 返回已提交快照，失败抛出 `StorageError`。
run 快照携带单调 `checkpoint_seq`、已提交步骤/证据 ID 与对应引用；外部汇总 JSON 由该快照导出，不允许各调用方自行决定完整性。
当前以 `scan.json` 内嵌数据及 raw 引用作为唯一提交权威；汇总 JSON 与 SQLite 不是冲突裁决来源，布局见实施记录。
`durable` 在本机指临时文件写完、flush/fsync 后原子 replace，随后提交引用；不承诺未验证的断电或网络盘恢复语义。

## 3. 具体模块任务

### P01：把原始运行信号变成可引用的记录

- 改 `driver/runtime.py` 的 RuntimeSignals 和 driver 监听回调；保留原字符串派生视图给旧消费者。
- 为监听事件分配 run 内递增 record_id 和采集时间，保存 JS exception、console error、失败请求、HTTP response 元数据。
- HTTP 保留 method、清理后的 URL、status、resource_type；同路径多次请求均可追溯，`http_status` 仅是兼容摘要。
- 默认不读取 request/response body、Authorization、Cookie；URL 敏感参数屏蔽，保留路径、状态和来源关联即可支持首版诊断。
- 原始记录设置单次 run 数量和单条文本上限；建议初始值 2,000 条 / 4 KiB，作为配置建议值，经 T09 压测再固定。
- 超限保留此前引用，追加 dropped_count/truncated 元信息；不静默清空，不让列表长度游标在截断后错配窗口。
- 输入/输出：浏览器事件 → 原始记录 + 窗口游标。依赖 T02 监听安装和动作边界，供应 P02/P03。
- Done：相同错误在两次动作中出现有两个记录 ID；旧窗口重读不产生新 ID；大量轮询触顶仍能解释截断。

### P02：入口和动作窗口先提交，再调用模型

- 改 `_collect_source()`/`_collect_browser()`：获得入口并 launch 后，立即读取并提交入口 runtime；地图调用在此提交之后。
- 改 `_collect_live()`：选择动作后保存输入快照及事前预期状态；执行无论成功/失败都在 finally 采集本窗口 runtime。
- 执行后先提交 action 事实、runtime 和可建立的技术 Evidence，再获取截图/可见文本/状态；这些成功后另提交增量。
- 截图失败先写 `artifact_missing` 与诊断，已有 JS exception/5xx 候选可缺图存在；不为等截图或模型推迟首次保存。
- 原始证据携带初始 URL、已成功动作前缀和来源窗口；入口异常没有虚构触发动作，动作失败保留 attempted 与 completed 的区别。
- 输入/输出：P01 窗口、执行结果 → committed raw prefix + 技术候选，供应视觉/认知及 T07 终止读取。
- Done：入口有 pageerror，Mapper 阻塞后取消；重启查看仍有入口技术候选。动作后 pageerror 同理不依赖视觉返回。

### P03：建立无需 LLM 的技术候选入口

- 在 `EvidenceEngine` 增 `build_technical(runtime_window, action, states, driver)`，不伪造 Mismatch 或自然用户预期。
- 首版稳定规则：未捕获 JS exception、HTTP 5xx 建 `technical_anomaly` 候选；classification 可沿用 technical_bug，但不代表已确认。
- console error、requestfailed 和 HTTP 4xx 保留原始信号；有明确事实组合时再产生可解释候选，不把单个日志自动提升为缺陷。
- 401/403 登录态失效、422 合理校验、主动取消请求作为反例；模型供应商报错、driver 超时、解析失败只进运行 diagnostics。
- severity 按客观影响说明而非仅状态码判“崩溃”；confidence 不复用认知合理性分数，缺依据时保留未知。
- 输入/输出：P01/P02 committed window → 稳定 source 引用的技术 Evidence；技术异常最多每类事实一条候选，可引用多个记录。
- Done：视觉/预期模型均抛错仍保存 JS/5xx；正常 401 校验不被标已确认产品缺陷；LLM 429 不进入产品候选。

### P04：拆开视觉、runtime、认知与调查阶段

- 改 `ObservationEngine.observe()`，公开 `observe_runtime()` 与 `observe_visual()`；保留旧 observe 包装用于兼容，但 pipeline 调用新阶段接口。
- runtime 读取完成后立即停止该窗口，视觉耗时期间的新事件归后续窗口或 background 记录，不能因等待模型扩大动作归因。
- 预期或 Mapper 失败时记录 `cognitive_status=failed/inconclusive`；使用已有确定性动作候选继续技术 QA，不能补写事后预期。
- Mapper 失败后的降级范围仍遵守所选单元：无法确定范围则明确 scope 未完成，不擅自扩大扫描；可用 DOM 候选只在已有范围内执行。
- 视觉失败仍保留 raw 与 technical；认知判定只消费事前有效 basis、可用观察，失败不能输出 clean pass。
- InvestigationAgent 按 issue 消费对应证据；调查为可选增量，失败不得撤销 scan、覆盖 evidence 或阻塞 analysis 导出。
- 输入/输出：committed prefix + T03 预期 → phase 状态与认知增量；调用/失败记录由 T08 计量节点接收。
- Done：分别在 map/expect/visual/judge/investigate 注入失败，每次读取前缀完整，并能说明哪些动作仅做技术 QA。

### P05：Evidence、SQLite 与 JSON 的最小兼容迁移

- 改 `Evidence.to_dict()/from_dict()`，统一 UI `_evidence_to_dict/_evidence_from_dict` 委托它，防止新字段被历史页面丢弃。
- finding_kind/basis 与 run/step/action/source 字段增量添加；旧记录显示类型/依据缺失，不能推断为新认知证据或编造来源。
- `EvidenceStore._init_schema()` 为缺列做迁移，basis/source_record_ids 用 JSON TEXT；insert/update 明确写新列，事务失败不能先返回成功。
- 新扫描显式使用当前 run 目录的 SQLite 路径，避免不同 run 的 EV-00001 互相替换；旧全局数据库保持可读，不自动批量搬迁。
- 新 Evidence ID 在该 run 中跨技术/认知路径共用生成器；关联始终使用 `(run_id, evidence_id)`，保持旧 EV 文案可读。
- artifacts 缺失、回放条件缺失作为完整性状态保留；`is_complete()` 的“有 replay 即完整”不能代表全部采证成功。
- 输入/输出：P03 技术 / T03 认知 → 可持久化双来源 Evidence，供 T05/T06。
- Done：旧 JSON/旧 SQLite 读取无异常；新字段读写不丢；两个 run 同编号独立；同一动作两种 Evidence 均可列出。

### P06：统一原子写、失败诊断与重启恢复

- 将 `RunManager._write_json()` 原子 replace 提取复用，覆盖 PipelineResult.save、raw records、证据/回放 JSON 与阶段快照。
- 写文件失败保留上次已提交版本，终态明确 storage_failed；不吞异常，不把空列表作为“保存完成”的替代物。
- CLI/UI 历史读取区分 absent / corrupt / unsupported / available；新 run 缺必需快照即检查不完整，旧 run 缺新增文件则标旧记录未知。
- parent 只能在 worker 已退出或清理失败状态确认后追加终止诊断；读取 committed checkpoint，不能以 `[]` 覆盖已存在步骤。
- `_scan_worker()` 异常、`_complete_scan()` 取消/timeout 合并诊断并保留前缀；迟到的 worker success 不能覆盖已生效 cancelled/timeout。
- T07 负责任务锁与终态裁决，本计划提供 checkpoint_seq、最后 phase、前缀计数和 `append_terminal_diagnostic()` 接口。
- 输入/输出：P02/P05 checkpoint → 可恢复 run 读模型；保留当前本机单写者，不引入分布式协调。
- Done：临时写故障、坏 JSON、取消视觉调用、worker 异常退出各有明确历史状态；最后有效证据仍可进入 analysis。

### P07：汇总与调查消费已提交证据

- `_collect_live()` 将 P05 已提交的技术与认知 Evidence 交给 `Deduplicator.cluster()`；同动作的技术/认知证据不得互相替换。
- 消费 T05 的 Issue 输出，验证 `Issue.evidence_ids` 保留全部成员；详细硬/软聚类、稳定分组与调查实现归 T05。
- Issue 回写只更新关联，不改 raw、basis、观察或开发者决定；阶段重算使用稳定 Evidence ID，不让编号变化影响审核。
- 再次扫描是新 run，回放是验证增量，不能以它们的结果覆盖本次证据；T05 定义再现结果契约。
- 输入/输出：P05 双来源 Evidence → Issue 关联 + 原证据，供应调查和 T06 分组报告。
- Done：点击触发 500 且界面无反馈，分析保留技术候选与认知落差；两个不同动作相同 console 文案不会失去路径。

## 4. 依赖顺序与联合验收

P01/P05 可先并行；P02 消费 P01/P05，P03 与 P04 随后接入；P06 与 T07 共同完成终态，P07 与 T06 共同验证双来源展示。
T02 提供执行成功、部分执行、settle 超时等动作事实；T03 提供事前预期及 basis，失败不能反向阻断 P02/P03。
T05 消费已保存原始前缀和稳定引用，不要求截图全部存在；T06 消费终态快照和诊断，不等待调查成功。
[T09 验证与发布](09-fixtures-compatibility-release.md)以真实浏览器夹具验证确定性采证，以模型替身控制阻塞/报错时点；真实模型效果单独验收。

1. 含入口 JS exception 的 URL：地图模型阻塞后停止，历史显示 cancelled、认知未完成、原始异常可审阅。
2. 动作触发 500 且无反馈：视觉调用中停止，技术候选已保存；正常完成后可新增认知证据，二者来源均能核对。
3. 登录失效/422 校验/模型 429：产品信号与运行故障分别显示，不捏造技术缺陷或“未发现问题”的结论。
4. 末次 checkpoint 写失败、旧文件缺字段、新文件损坏：保存前缀和缺失说明，重启后不显示空扫描成功。
5. 调查失败、报告导出或回放失败：原 scan/Evidence 保留，analysis 仍明确列出已有证据与失败阶段。

以上联合场景通过才关闭 R02/L03；不能以 runtime、EvidenceStore、JobController 的独立单测通过代替这条用户路径。
本计划不涉及行业/岗位画像、企业审计、网络响应正文分析或多用户数据库；框架差异由 T01/T02 的支持矩阵决定。
