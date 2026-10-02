# AlienQA 功能 MVP 工程 Planbook

版本：2026-10-02-mvp-15。状态：T01 F01～F07/F09 已统一应用基准、运行入口、字面量路由、静态产物/部署与本机兼容证据，F08 后置；T04、T03、T06、T08 工程范围已接通；T02 主页面交互/状态/轨迹及锁版本框架机制路径已实现，frame/shadow 只检测并说明覆盖；T05 E01～E07 的回放/分组/调查功能 MVP 已实现；T07 共享输入、终态核对、历史及本机安装包完整路径已接通；新增 Codex 登录接口与有界运行器。N03 校准 C01～C05 已实现，C06 离线对照及版本化真实复跑分别留存；T09 已实现成对样例、分层验收、独立依赖安装工具与实验性发布说明；独立人审、真实应用模型效果与发布效果 gate 仍开放。详见[T01 实施记录](../t01-implementation.md)、[T07 实施记录](../t07-implementation.md)、[T05 实施记录](../t05-implementation.md)、[T02 实施记录](../t02-implementation.md)、[T04 实施记录](../t04-implementation.md)、[T03 实施记录](../t03-implementation.md)、[T06 实施记录](../t06-implementation.md)、[T08 实施记录](../t08-implementation.md)、[N06 首轮结果](../n06-first-results.md)、[N03 校准记录](../n03-calibration-results.md)。
适用对象：独立开发者，单人本机使用。用户在本次讨论中明确：

> “先做功能层MVP”
> “一个独立开发者可以使用这个项目作为QA和分析是否违反一般用户认知”

本文、四份功能子计划及其[技术实施分解](technical/README.md)是当前阶段的执行入口，优先于旧路线图中的框架大样本、PDF、岗位画像和团队功能安排。
历史实现与验证记录见 [下一阶段总计划](../next-stage-plan.md)；原 01～13 模块仍作为代码职责索引。

## 1. 产品结果与功能边界

独立开发者给出一个可运行的网页，获得两类带证据的线索：技术异常，以及界面行为与一般用户预期的落差。
开发者能看到依据、实际观察、截图、路径和扫描限制，记录自己的决定，并保存一份完整分析报告。
“一般用户”固定为具备通用网页操作经验、第一次使用本产品、未接受本产品内部培训的人。
检查一般交互的可理解性、反馈和一致性；不承诺推导未公开的业务规则，也不声称代表所有真实用户。

| 分类 | 本次范围与理由 |
|---|---|
| 核心必需 | URL 扫描、一般用户预期、技术异常采集、证据/回放、开发者决定与完整分析 HTML；共同构成用户结果 |
| 必要支撑 | 登录态复用、动作/时间预算、停止与失败可见、用量计量、小样本验证和本地安装；限制使用与排查成本 |
| 保留现有能力 | 源码+URL、静态服务、调查假设与 confirmed 报告；不为 MVP 重建已有通道，调查失败不抹掉发现 |
| 后续阶段 | 岗位/行业画像、角色配置器、多人审核、账户/组织/权限、集中任务队列、收费、外部工单写入 |
| 迭代后再决定 | PDF、Issue 手工合并拆分、广泛框架自动启动、大型第三方仓库基准、多模型矩阵；不作为首版功能 gate |

默认输入是运行 URL；登录态和扫描单元可选。源码是辅助定位与查因输入，不是一般用户预期的正确答案。
不增加岗位选择步骤，不建设 persona 引擎，不以“零先验”表示模型没有通用知识。
已有自由文本指令在 MVP 中用于定位范围，不把内部业务答案注入预期模型，也不增加 guided 测试平台。

## 2. 最小用户路径

1. 输入 URL，必要时提供登录态，选择动作/时间预算；使用既有本机模型设置。
2. 工具在当前状态选择动作，事前形成带依据的预期，执行并保存用户可见结果和原始运行信号。
3. 展示技术候选、认知落差与扫描诊断；无发现但判定失败时明确显示检查不完整。
4. 开发者查看证据、执行回放，决定确认、拒绝、按设计保留或暂缓，并填写备注。
5. 在扫描终止后导出 analysis HTML；未审项和“按设计”仍保留其观察与状态，确认缺陷可另导出 confirmed 视图。

认知模型或调查失败不阻断已有技术证据落盘，不在执行之后补写事前预期。
回放匹配说明行为或信号是否再次出现；问题语义与业务可接受性仍由开发者解释。

## 3. 子计划与承诺覆盖

| 节点 | 工程职责 / 任务 | 提供给下游的产出 | 必要依赖 |
|---|---|---|---|
| [MVP-01](01-general-user-judgment.md) | 一般用户输入、预期依据和判定；J01～J06 | 动作绑定的预期、basis、判定和可见历史 | 本文共享契约；MVP-03 的步骤与状态 |
| [MVP-02](02-findings-review-report.md) | 独立技术证据、决定、分析报告；R01～R06 | 可审阅 Evidence、Decision/备注、analysis/confirmed HTML | 本文契约；MVP-01 的认知结果；MVP-03 的终态输入 |
| [MVP-03](03-local-run-and-delivery.md) | 单人输入、运行、停止、历史交付；L01～L05 | 输入校验、执行步骤、终止原因、完整可读产物 | 复用既有 CLI/UI/JobController；MVP-01/02 的消费接口 |
| [MVP-04](04-validation-and-release.md) | 样例、计量、真实小应用与发布；V01～V05 | 可复核基线、失败/费用记录、安装与使用证据 | J/R/L 的可运行闭环；测试样例与模型配置冻结 |

| 用户承诺 | 整体验收路径 | 覆盖状态 |
|---|---|---|
| 能做 QA | L01/L03 → R02 → R04；模拟模型失败仍保存真实 pageerror | T04 独立采证与停止恢复已验证；T06 analysis 页面及离线路径已验证 |
| 能分析一般认知落差 | J01～J05 → R01/R04；缺反馈与合理反馈分别给出可解释结果 | N03 校准工程已接入；新提示双采样核心配对 4/4 可用、合理校验 1/1 passed；旧未决保留，独立人审/历史与真实应用 gate 仍开放 |
| 能理解并决定如何处理 | R03 → R04/R05；按设计有备注且不消失，未审项明确标记 | T06 两套四种决定/备注 UI、五态 analysis 与更新导出已验证 |
| 能复现和留存 | L04/L05 + R06；前置动作回放、复制 HTML、重审更新 | T02 锁版本机制路径、T05 环境/目标窗口/异常独立回放已做工程验收；T06 双模式、截图内嵌和离线复制已验证；真实认知解释采信与真实应用仍开放 |
| 使用成本可判断 | V02/V03 + L02；失败和 fallback 计入调用记录 | T08 已持久化；Codex 六角色取得真实 CLI 启动及 token 记录，费用与内部 HTTP 数仍未知；真实应用效果基线开放 |

### 3.1 技术维度的模块实施计划

下面九份计划将 J/R/L/V 拆到代码模块、函数、接口增量、依赖、固定样例和验收；父编号不变，具体映射和批次见[技术索引](technical/README.md)。

| 技术维度 | 应改进的模块 / 任务 |
|---|---|
| [T01 项目与框架兼容](technical/01-project-framework-compatibility.md) | loader：应用识别/选择、workspace/cwd、包管理器/URL、React/Vue/Next 路由、静态/SSR 产物、深链；F01～F09 |
| [T02 浏览器交互与状态](technical/02-browser-interaction-state.md) | driver/state/planner：稳定定位、受控表单、自定义控件、portal、SPA/hydration、异步窗口、尝试轨迹/登录态；B01～B09 |
| [T03 上下文与认知判定](technical/03-context-expectation-judgment.md) | context/mapper/expectation：输入隔离、依据解析、有限预期、可见历史、判定绑定；N01～N06 |
| [T04 管线与持久化](technical/04-runtime-pipeline-persistence.md) | runtime/observation/pipeline/evidence/storage：模型前保存、独立技术候选、增量证据、旧数据兼容和异常恢复；P01～P07 |
| [T05 回放、聚类与调查](technical/05-replay-dedup-investigation.md) | replay/dedup/investigation：初始条件、环境恢复、再现依据、双来源聚类、按 Issue 调查；E01～E07 |
| [T06 审核与报告产物](technical/06-review-report-artifacts.md) | review/模板/路由：四种决定及备注、双模式、终态快照、双缓存、离线 HTML；H01～H08 |
| [T07 本地运行与生命周期](technical/07-local-run-ui-lifecycle.md) | CLI/ui/jobs/runs：URL 入口、preflight、停止回收、历史计数、报告接线；U01～U07 |
| [T08 LLM 执行与计量](technical/08-llm-execution-metering.md) | client/models/config/roles：所有 attempt、输出解析、fallback、未知用量与费用；K01～K06 |
| [T09 样例、兼容与发布](technical/09-fixtures-compatibility-release.md) | fixtures/测试/包/CI：正常异常配对、真实框架机制、真实模型基线、发行安装与支持证据；Q01～Q07 |

框架识别、已运行 URL 的交互、源码启动/构建产物、独立回放分别验收；识别分支存在不代表整套框架兼容。
当前 T03 专项增量见 [N03 采样合并校准副 Planbook](technical/03a-sampling-merge-calibration.md)：同义与分歧边界、来源记录、部分检查展示已接通；真实模型小样本与待复核项见 [校准记录](../n03-calibration-results.md)，不由工程完成推导效果 gate 已关闭。
React/Vite、Vue/Vite、Next App/Pages 优先用小型真实样例验证；Nuxt/SvelteKit/Angular 和复杂组件库按需求后置，未知框架仍可通过 URL 输入。
技术任务属于同一功能 MVP：先打通原始采证、认知依据、analysis 和终态，再扩兼容面；不把九份计划全部完成设为首份分析的前置。

## 4. 共享契约：只做必要的增量

以下为共享契约：T02 已支持目标语义、执行/观察结果和原步骤轨迹；T04 已支持 Evidence 来源/basis、原始记录和提交快照，T03 已接入可见输入、引用校验与身份绑定；T06 已接入报告模式与审核入口，T08 已接入请求账目及其消费；T05 已接入独立回放窗口、具体来源匹配、组织分组与有界调查增量。沿用 Evidence、ReviewState、RunRecord、PipelineResult 和现有 JSON/SQLite。
不新增一套 Finding 数据库，不重写 13 模块，不以引入工作流框架作为任务前提。

| 对象 / 字段 | 规则 |
|---|---|
| 一般用户定义 | 固定文本与 prompt 版本；无岗位/行业配置；内部元数据可记录该固定定义的版本 |
| `Target` 增量 | name/label/scope/viewport 可缺省；旧 selector/text/role/坐标仍读取。名称/作用域用于定位，不能成为产品内部答案 |
| 执行与观察 | execution 分开保存定位、emitted、动作与 wait 状态；false/true/null 分别为未发出/调用完成/发出未知。等待未稳定不自动重发动作，也不显示认知通过 |
| 尝试与回放身份 | trajectory、全部 attempts 与成功 action_sequence 共享原 step/action ID；旧记录可缺 ID，未知前置条件不伪装成完整成功前缀 |
| 回放包 v2 | `package_version=2`；`action_sequence` 是成功前置序列，`target_action/target_window/source_signals/observation_window` 单列目标及来源。driver 的成功历史仍不变；旧包最后动作语义保留并说明限制 |
| 回放结果增量 | `phase/preconditions/target_window/executed_steps/matched_basis/limits`；停止/超时是 inconclusive + termination；不修改原 Evidence/决定或扫描完整性 |
| 调查增量 | `evidence_ids/input_status/status/error`；根因/位置只是 hypothesis，结果与报告缓存共用本地锁；来源缺失不以当前页面补齐 |
| `Expectation.expectation_basis` | 每条预期的单个 `{type, reference}` 对象；`type` 为 `visible_copy / interaction_convention / observed_behavior` |
| 预期身份 | T03 新增 `Expectation.id/run_id/step_id/action_id/prompt_version`；Evidence 的 `expectation_id` 引用该步已提交预期，旧记录可缺省 |
| `Evidence.finding_kind` | `technical_anomaly / cognitive_mismatch`；前者是原始运行异常候选，后者是事前预期与实际的落差 |
| `Evidence.expectation_basis` | 认知证据继承所引用预期的 basis；技术证据为 null，不编造用户预期 |
| 原始字段 | 保留 expectation、observation_summary、reasoning、action、状态 ID、artifacts、replay 和 classification |
| 技术运行引用 | run/step/action、原始记录引用、schema 与 committed checkpoint 的最小交接由 [T04 §2](technical/04-runtime-pipeline-persistence.md#2-共享输入输出与提交点)统一定义，CLI/UI/报告复用，不各定权威 |
| 运行诊断 | 定位/执行/模型/解析/环境故障另列 diagnostics，不能把运行器失败作为产品技术缺陷 |
| 判定结果 | 沿用 passed / mismatch / failed / inconclusive；模型判定与动作执行事实分别可核对 |
| 开发者决定 | 沿用 pending / confirmed / rejected / by-design / skipped 与 note；按设计表示接受设计，保留原始落差 |
| 报告入口 | 拟增 `ReportBuilder.build(..., mode="confirmed")`；旧默认兼容。新 CLI/UI 分析入口显式选择 `mode="analysis"` |
| analysis 模式 | 展示所有已保存证据、全部决定与备注、扫描范围和诊断；未审项标为待审，不能算已确认缺陷 |
| confirmed 模式 | 保留现有严格终稿 gate 及 confirmed-only 行为；被 gate 拦截时指向 analysis，不要求把 by-design 改为 rejected |

旧文件可缺少新增字段：显示“旧记录未提供依据/类型”，不编造出处，不自动按新规则重新确认。
新认知记录必须具有对应事前预期与 basis；依据表述本身仍可被开发者拒绝，不能等同于合理性已证明。
网络 4xx/5xx、JS 异常是观察信号；单个信号不自动证明产品有 Bug，合理登录/校验异常作为反例保留。
classification 与 finding_kind 分别表示现有表象分类与证据来源，不从分类名推导“已确认”。

数据时序：输入快照 → 事前预期（可能失败）→ 执行 → 立即保存原始步骤/runtime 与技术候选 → 保存可获得的截图/可见结果 → 视觉/认知判定 → 增量保存认知结果。
进入页面的技术信号也先保存，再进入产品地图等模型阶段；不等待任何模型成功才首次保存已有异常。
任务在视觉/判定调用中被停止时，保留已保存原始前缀和技术候选，该步认知检查标为未完成。
认知预期失败时可继续技术 QA，但该动作的认知检查保持未完成；本次结果只能成为下一步的可见历史。
报告消费同一 run 的终态扫描数据与一次有效审核快照；重审后既有报告失效，回放不覆盖原始证据。
复用现有本机锁与任务占用，不引入团队审核冲突裁决、分布式版本服务或新消息队列。

## 5. 调整后的执行顺序

| 阶段 | 必做结果 | 可并行准备 | 进入下一阶段的条件 |
|---|---|---|---|
| M0：定位与契约 | 本文，J/R/L/V 交接规则 | 定向样例设计 | 当前用户/范围已按本次要求固定；新字段和报告语义一致 |
| M1：功能核心 | J01～J03/J05，R01～R04，L01～L03；技术与认知候选到 analysis 页面 | V01 样例、V02 计量；J04 历史，R05/R06 和 L04/L05 | 一次 URL 扫描能看两类证据、诊断与决定，模型失败不使 QA 证据消失 |
| M2：可用验证 | 完成 J/R/L；V01/V02/V03，保存小应用真实模型记录与基线 | V04 安装 smoke；交互说明迭代 | 控制样例和例外可区分，真实小应用有可核对结果，失败与费用有记录 |
| M3：单人发布 | V04/V05；本地安装、报告复制、旧产物兼容、支持范围说明 | 下一轮发现率/审阅成本改进 | 独立开发者完成输入、扫描、复核、决定、HTML 留存的完整路径 |

真实模型检查在 M1 可运行后尽早开始，随 M2 迭代；不等大型 React/Vue/Next.js 候选环境全部准备完。
源码调查已有实现可继续使用，不是分析报告生成的必需成功条件。PDF 和复杂 Issue 管理不阻塞 HTML 闭环。
开发可以并行；运行时的预期、证据、审核、报告依赖不能颠倒。
本计划不承诺人员、人日、发布日期或未经测量的模型效果数字。

## 6. MVP 完成定义与当前状态

- 一次有前置动作的本地 URL 扫描，能形成可回溯的认知线索与独立技术候选。
- 清楚反馈、合理校验/禁用等正常反例不会被固定当作认知缺陷；未知和模型故障显示不完整。
- 开发者可记录四种处理决定和备注；analysis 完整保留“按设计”和未审项，confirmed 兼容原有语义。
- HTML 换目录后仍能读取截图与证据；本机回放恢复已记录前置条件，凭据不进入独立报告。
- 有定向浏览器回归、至少一款真实小应用的模型记录、调用/失败计量及干净安装材料。

截至上一轮：302 项默认测试通过、Python 覆盖率 85.88%、sdist/wheel/pip check 通过。
这些证据包含真实浏览器和模拟模型，证明既有确定性链路；不证明本文新增任务已完成或真实模型效果达标。
上述 302 项为计划落盘前的历史基线。随后已实现 T04、T03、T06、T08 与登录适配/验收运行器；当时 477 项通过、覆盖率 87.71%，sdist/wheel 构建通过。随后 N03 工程校准为 529 项/87.98%；随后 T02 全量（含显式框架套件）574 项通过、覆盖率 87.43%，sdist/wheel 及样例资产核对通过。T05 全量 620 项通过、覆盖率 87.59%，包含 20 项真实框架工程路径（4 项新增异常回放），sdist/wheel 构建与产物核对通过。本轮 T07 全量 649 项通过、覆盖率 87.82%，最终 wheel 在项目内独立空目录完成 CLI/UI 真实 worker、回放、重审和离线 HTML 路径；依赖复用当前环境，新依赖环境仍待 T09。T01 完整套件 693 项通过，新增显式深路径定向回归后去重共 694 项，合并覆盖率 88.30%；包含 24 条锁版本框架工程路径，最终 sdist/wheel 及独立目录安装通过，细节见 [T01 记录](../t01-implementation.md)。另有 40 次真实 Codex CLI 启动的控制样例及排障记录，未知费用如实保留；真实应用与独立人审未完成。新增验证与剩余边界见各实施记录及 [N06 首轮结果](../n06-first-results.md)。

T09 的样例、评估/人工审核资产、分级 CI、干净安装和支持范围已实施，固定 TodoMVC 的机制与独立回放已验收；最终证据及限制见 [T09 记录](../t09-implementation.md)与[兼容/发布状态](../compatibility-and-release.md)。下一阶段优先 N06/C06/K06/V03 的有预算真实复跑与独立人审，不自动追加框架广覆盖或企业功能。

T09 提交前工程证据：完整回归 745 项与最终定向补充 25 项去重共 749 项，合并覆盖率 88.20%；24 条固定框架路径、固定 TodoMVC 独立回放及 wheel/sdist 两套新依赖完整路径通过。当时模型调用 0，机器 release_ready=false。

提交后已完成远程默认回归/干净安装及新批真实基线，输入/失焦合并与 Enter 探索按实际缺口修复；同配置复测、计量对账及预先冻结的门槛见 [T09 真实基线记录](../t09-real-baseline-results.md)。独立人审与有效性 gate 仍需真实参与者提供结论和审阅分钟。
