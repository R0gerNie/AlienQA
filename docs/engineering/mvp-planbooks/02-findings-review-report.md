# MVP-02：发现、开发者决定与分析报告

> 状态：T04/T03/T06 已交付本文发现到分析报告的工程闭环，并完成受控网页的真实浏览器与离线验收；真实模型效果和发行安装仍待验收。详见 [T06 实施记录](../t06-implementation.md)。目标用户是独立开发者；目标是 QA 与发现违反一般用户认知的行为，不设计岗位画像或企业协作。
> 本计划调整旧模块 12 的产品入口，复用既有 Evidence、ReviewState、报告和本地运行记录，不另建发现数据库。

## 技术实施拆解

R01/R02 的原始信号、独立技术候选、双来源 Evidence 和存储见 [T04](technical/04-runtime-pipeline-persistence.md)；认知 basis 的供应见 [T03](technical/03-context-expectation-judgment.md)。
R03～R06 的决定/备注、双模式、快照/缓存和离线 HTML 见 [T06](technical/06-review-report-artifacts.md)；回放、聚类、调查的可选增量见 [T05](technical/05-replay-dedup-investigation.md)，CLI/UI 接线见 [T07](technical/07-local-run-ui-lifecycle.md)。
模块任务与联合验收映射见[技术索引](technical/README.md)，原 R 编号及 analysis/confirmed 语义不变。

## 1. 产品结果与边界

开发者完成一次有预算的扫描后，即可看到全部认知落差、技术异常与扫描诊断，查看原始证据，记录判断并导出 HTML。
“按设计”意味着开发者接受或解释这一行为；它不删除已经发生的困惑，也不把模型预期变成产品正确答案。
报告区分浏览器记录、模型解释和开发者决定。它提供可核对的线索，不承诺证明整个产品正确或代表所有真实用户。
本阶段不做岗位画像、团队权限、Issue 合并拆分后台、工单同步、PDF、云端报告或跨用户并发审核。

## 2. 实施前基线与本轮变化

| 已核对的当前能力 | 本计划需要的变化 |
|---|---|
| Evidence 持久化截图、动作、状态、回放与技术信号；目前由模型 mismatch 驱动生成 | 补发现来源与预期依据，技术异常可独立成证据 |
| Decision 含 pending/confirmed/rejected/by-design/skipped，ReviewState 已存备注 | UI 暴露四种决定与备注，pending 保留为待审状态 |
| ReportBuilder 只收录 confirmed，其他 pending/by-design/skipped 阻止生成 | 新增 analysis 模式包含全部发现和决定；保留 confirmed 模式及旧严格 gate |
| UI 已拒绝运行中生成报告，用本地锁保护审核与报告，重审使缓存失效 | 明确终止态与数据快照，区分两类报告缓存，不让诊断缺失伪装成零问题 |
| HTML 主体确定性生成、截图内嵌，模型补充已净化 | 扩展分析内容和标签，保证复制后的 HTML 可读 |

依据：[旧模块 12](../../planbooks/12-human-review-report.md)、`alienqa/review/{models,service,report,webui}.py`、`alienqa/ui/{app,runs}.py`、`alienqa/pipeline.py`。
旧模块 12 所述“人工确认的问题才进入报告”继续适用于 confirmed 兼容入口；analysis 新入口已由 T06 实现并验证。

## 3. 最小共享契约

继续以 Evidence ID 持久化、审阅和引用；`issue_id` 只复用现有分组结果，不新增生命周期。

| 字段或对象 | 计划规则 |
|---|---|
| `finding_kind` | `technical_anomaly` 或 `cognitive_mismatch`；独立确定性技术异常使用前者，模型认知落差使用后者 |
| `expectation_basis` | 认知落差携带 `{type: visible_copy\|interaction_convention\|observed_behavior, reference: 文本}`；说明依据，不把“模型相信”当证据 |
| 旧动作、截图、前后状态、replay、技术信号 | 保留字段；模型解释与原始浏览器记录分别显示，缺项明确标未记录 |
| ReviewState | 继续 `evidence_id → decision + note`；每个发现有独立决定，默认 pending |
| 扫描诊断与范围限制 | 沿用 steps/diagnostics/stop_reason；模型/驱动故障为诊断，预算终止列范围限制，不混入产品技术异常 |

`expectation_basis` 是每条 Expectation/Evidence 的单个对象，不聚合为依据列表。技术异常无需虚构用户预期，`expectation_basis=null`；认知落差若依据无法核对，显示“依据不足”，不在报告中补造引用。
旧 Evidence 无新字段仍可加载，显示“来源未记录”；不通过 `classification` 或严重度猜出已经验证的来源。
浏览器原始技术信号允许列出 JS exception、HTTP 5xx 等具体异常，但出现异常不自动证明用户任务失败；401 等状态可能是合理业务结果，所有候选仍待开发者判断。
同一动作同时出现技术异常和认知落差时，两条记录共享既有动作/状态/步骤引用；不因模型重复描述而重复建立同源技术记录。

## 4. 实施任务

### R01：将观察、解释和决定分开

- 落点：`evidence/models.py` 的兼容序列化、`evidence/engine.py` 构造、`review/report.py` 和审核模板。
- 接入上游认知预期的 `expectation_basis`；将既有 reasoning/调查假设明确标为模型解释。
- 截图、可见文本、DOM/运行时记录注明采集来源；`observation_summary` 若由模型总结，不标作原始事实。
- Done：一个“保存后无反馈”样例同时展示动作与截图、预期及依据、模型解释、pending 状态；旧证据仍能读取。

### R02：技术异常不依赖模型单点成功

- 落点：`pipeline.py`、`observation/engine.py` 的确定性运行时抓取、`evidence/engine.py`；复用 Driver 的运行时快照。
- 进入页面及已执行动作的原始异常独立采集；LLM 预期、视觉或判定失败不能丢掉已采集的异常。
- 页面进入后先保存原始入口信号；每次执行后立即保存步骤/runtime 与技术候选，再调用视觉/认知模型并增量更新。不等待模型返回才首次落盘，截图尚未取得时先标缺失。
- 首批独立证据限定为可明确记录的 JS exception、HTTP 5xx；普通日志、预期 HTTP 4xx 或图片空白评分不直接确认为故障。
- 技术记录保存时间、URL/请求或异常消息、动作边界及已有截图；没有截图或复现序列则标证据不完整。
- 将“预期模型超时”归入扫描诊断，而非 technical_anomaly；相关动作是否执行以步骤记录为准。
- Done：判定返回 passed 但请求 500，仍产生技术异常；视觉模型抛错时已有 JS exception 仍保留，同时报告扫描不完整。
- Done：pageerror 已落盘后视觉调用阻塞，watchdog 终止 worker；分析仍能读取该技术候选，认知判定标未完成。

### R03：开放四种决定与备注，保留困惑

- 落点：主 UI 和独立审核 UI 的模板、decide 路由、`ReviewState`/`HumanReview` 持久化。
- 显示“确认问题 / 不采信 / 按设计 / 暂跳过”，默认待审；调用既有 enum，不另定义状态含义。
- 支持保存备注，刷新后恢复；确认问题仍是开发者决定，不将其更名为模型证明。
- by-design 的备注解释设计或接受的使用成本；备注可为空，UI 提醒其解释价值，不强制填写业务知识。
- 校验 Evidence ID 和合法决定；不修改未知证据。重审允许在既有状态间调整，并使所有对应报告缓存失效。
- Done：待审→按设计并保存备注，刷新和导出后原始认知落差、决定和备注都存在；转确认后新报告反映新决定。

### R04：新增 analysis 报告，保留 confirmed 兼容入口

- 落点：`ReportBuilder.build(..., mode="confirmed")`；旧默认和严格 gate 保持兼容，新 UI 主要入口显式调用 `mode="analysis"`。
- analysis 收录全部 Evidence 与五种现有状态/备注，附扫描步骤、诊断、终止原因和证据完整性；pending 不阻止分析报告。
- 报告标题为“QA 与用户认知分析”；待审、拒绝、按设计、跳过均有明显标签，不能被呈现为已确认缺陷。
- confirmed 继续仅收录采信项，保留 pending/by-design/skipped gate；入口注明它是兼容的确认问题报告，避免误以为分析被过滤。遇到 gate 提供 analysis 入口，不要求把按设计改成不采信以便导出。
- 复用 deterministic 主体和已净化的模型补充；模型补充失败不能阻止导出记录，调查假设不能覆盖原始证据。
- `Report.accepted_count` 继续只数 confirmed，`total_count` 仍数全部；analysis 的展示数量另明确标全部发现，不改变旧字段含义。
- 缓存文件分别使用 `analysis.html` 和既有 `report.html`；非法 mode 返回明确输入错误，不能静默回到另一模式。
- Done：混合五种状态的同一批证据，analysis 全部保留并含备注；confirmed 维持原 gate 回归行为。

### R05：以终止扫描的有效快照生成报告

- 落点：`ui/app.py` 报告路由、`ui/runs.py` 缓存失效、独立审核入口的本地锁与诊断输入。
- 只允许 done/partial/error/timeout/cancelled 的终止运行导出；running 和无法确认完成的 unknown 返回冲突说明。
- 在既有本地锁内一次读取 Evidence、ReviewState、调查和扫描诊断并生成/保存，审核变更按同一锁保存后失效两个缓存。
- 复用原存储写入方法与当前锁，不新增多人版本控制、哈希证明或分布式事务。
- 有效空证据可生成 analysis，正文为“未记录发现”，并保留预算、范围、步骤和不完整诊断；禁止显示“测试全部通过”。
- 终止运行若只留下失败诊断，可生成诊断分析；已声明存在的证据文件损坏不能被当作空列表，应返回读取错误及修复说明。
- Done：生成报告与重审同时到达时，保存的报告与其决定快照一致，后续重审使其失效；取消后只消费已落盘记录。

### R06：先交付可复制的本地 HTML

- 落点：报告模板、主 UI 下载入口和使用说明；HTML 不依赖开发者机器上的截图绝对路径。
- 内嵌现有截图，转义可见文本、异常和备注；原始 DOM 作为文本呈现，避免带入活动脚本。
- 缺失截图/调查/回放明确标未提供；不借模型补齐事实，也不把“不能复现”改写成“未发生”。
- 独立 HTML 不包含 storage_state/cookies 等登录凭据；本地回放包按现有方式保留，报告说明复现所需环境。
- Done：复制 HTML 到另一目录后无需运行 AlienQA 即可阅读全部记录与截图；恶意备注和模型 HTML 无法执行脚本。
- PDF 在 HTML 阅读与内容验收完成后另排，不成为本 MVP 的进入条件。

## 5. 依赖与交付顺序

共享字段以[父计划契约](README.md)为准。R01 依赖 [MVP-01](01-general-user-judgment.md) 的动作绑定预期及 basis；R02 依赖 [MVP-03](03-local-run-and-delivery.md) 的驱动原始信号与扫描步骤，允许与 R01 并行实施。
R03 复用既有状态，可与 R01/R02 并行；R04 消费 R01/R02/R03；R05 约束 R03/R04 的持久化与生成时序；R06 消费稳定的 R04/R05 输出。
本计划的整体验收必须接到 MVP-03 的一次真实扫描，并由 [MVP-04](04-validation-and-release.md) 消费验收证据；仅报告单测通过不代表独立开发者已完成 MVP 流程。

## 6. 整体回归与完成条件

| 场景 | 必须观察到的结果 |
|---|---|
| 保存按钮无反馈，开发者认为按设计 | 认知落差、依据、前后截图和说明留在 analysis；不称为确认缺陷 |
| 未审核即扫描终止 | 可以导出 analysis，全部 pending 明示；confirmed 入口仍拒绝 |
| 页面出现 500，但模型未判不符或模型失败 | 独立 technical_anomaly 和原始请求证据存在；模型失败另列诊断 |
| 零发现且预算结束或模型失败 | 预算结束注明有限扫描范围；模型失败明确检查不完整；均不生成全站“无问题”结论 |
| 五种决定与备注，含旧版 Evidence | analysis 无漏项，旧字段可读；来源未记录明确标注 |
| 报告已生成后改决定或备注 | 两种缓存失效；再次生成只消费新的有效快照 |
| 扫描运行中、unknown 或数据损坏 | 不导出伪完整报告，返回对应状态/读取原因 |
| HTML 复制、缺图、注入字符串 | 正文离线可读；缺图如实显示；脚本和危险属性不能执行 |

完成证据：以上回归通过，并用一份受控网页扫描产生“认知落差 + 技术异常 + 扫描诊断”，在 UI 审阅、改为按设计、填写备注、导出并离线打开。
该验收证明发现到报告的功能闭环；真实一般用户是否认同模型预期，仍由父计划的小规模效果验证负责，不在这里宣称已验证。

本轮整体验收已在主控制台和 CLI 独立审核执行：真实 Chromium 扫描产生两类发现和调查失败诊断，保存按设计备注、保留另一条待审、下载分析、修改决定并重新下载，复制后离线阅读截图与依据。模型输出为替身；验证结果及边界详见 T06 实施记录。
