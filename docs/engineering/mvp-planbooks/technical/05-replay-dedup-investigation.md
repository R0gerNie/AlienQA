# T05：回放条件、发现聚类与按问题调查

版本：2026-10-02-tech-2。状态：E01～E07 的功能 MVP 已实现；验证与限制见 [T05 实施记录](../../t05-implementation.md)。真实模型、独立人审及真实应用 gate 仍开放。承接 [R02/R06](../02-findings-review-report.md)、[L04](../03-local-run-and-delivery.md) 与 [V01/V03](../04-validation-and-release.md)。
复用现有 ReplayEngine、Deduplicator、InvestigationAgent；调查是可选解释，不能成为获得分析报告的成功前提。

## 1. 实施前事实与改进落点（历史基线）

| 模块 | 已有能力 | 具体缺口 |
|---|---|---|
| `replay/engine.py::save/replay` | 自动回放包、起始 URL、storage_state、成功动作前缀、静态服务恢复、四态结果 | 新窗口来源/动作阶段需接线；缺图技术候选与入口异常需合法回放路径 |
| `replay/models.py::ReplayResult`、`replay/scorer.py` | 截图相似和特定信号比较；公开结果不含私有 replay 内容 | 画面再现与问题语义仍需分开说明；泛日志不能证明再现 |
| `dedup/engine.py::cluster/_hard_key/_make_issue` | 文本/截图相似与分类桶，成员 Evidence ID 保留 | 新 finding_kind 未接入；同页同类不能证明同根因；增量聚类需保留已审证据身份 |
| `investigation/context.py::build_investigator_context` | 只取对应 Issue 的保存 DOM/技术信号/动作序列 | 新 raw 引用、缺图与分阶段诊断需消费；根因仍是模型假设 |
| `investigation/retriever.py::retrieve_source` | 小规模路径/关键词检索前端文件片段 | 不是完整源码理解、source map 或组件精确追踪；需注明片段和检索限制 |
| `ui/app.py`、`ui/runs.py` | 回放任务与结果保存 | 新终态快照、双报告缓存失效和缺前提说明需统一 |

源码位置与历史测试说明现有机制；下列 E 任务是增量工程，不表示框架/语义复现已经全面验证。

## 2. 输入输出

输入是 [T04](04-runtime-pipeline-persistence.md) 已提交 Evidence、raw 引用、初始条件和成功动作前缀；不能用浏览器当前终页代替原发生现场。
输出是原 Evidence 的回放结果增量、Issue 成员关联和调查假设；不修改原始预期、basis、观察或开发者决定。
继续沿用 reproduced/not_reproduced/failed/inconclusive；failed 表示回放未完成，不能显示为没有问题。
新 run 使用 run-local 证据与回放目录；旧 ID/包格式缺字段可读，缺必要条件给出明确原因。

## 3. 具体任务

### E01：回放包与动作前提补齐

- 父任务 L04/R06；M1 接线，M2 验收。落点 `EvidenceEngine._write_artifacts/persist`、driver `replay_data`、`ReplayEngine.save/_load`。
- 保存起始 URL、实际视口/浏览器、cookies/localStorage、成功前置动作、目标动作和原 step 引用；部分执行/失败尝试单列，不冒充成功前缀。
- 初次导航的技术候选允许没有目标动作；复现入口并采集同类信号，不能人为创建一个点击来满足旧包结构。
- 新增包字段可缺省；序列化/加载与 P05 共用版本规则。原模型依据随证据保存，不在回放时补造原预期。
- 登录态只留在本机私有包；sessionStorage/IndexedDB 等未支持项按 B07 说明，不能声称所有认证都可恢复。
- 验收：跨路由前缀、入口 JS 异常、缺图技术候选均有可解释包；缺起点或坏 JSON 明确失败，不静默使用最终 URL。

### E02：静态服务与浏览器环境恢复

- 父任务 L04/V01；M2。落点 `ReplayEngine.replay/_new_driver/_ReplayHandler`，消费 F06/F07、B04/B07。
- 核对并应用保存的浏览器/视口设置；当前默认 driver 不能因包内已有 metadata 就被称为已恢复同一环境。
- 复用原静态目录/端口及拟增 spa_fallback；仅页面导航可回退，缺资源/API 不变为 HTML 200。
- 起始 URL 保留 hash、query、部署子路径；不自动更换端口、路径或依赖服务后仍宣称同条件再现。
- 端口占用、目录消失、服务不可达、浏览器缺失、认证过期各给具体阶段；finally 关闭此次创建的资源。
- 验收：关停原静态服务后恢复 history 深链；占用端口/删目录分别返回环境失败；已有外部服务不被回放任务关闭。

### E03：把再现判断与认知结论分开

- 父任务 R06/V03；M2。落点 `ReplayEngine.replay`、`image_similarity/signal_overlap`、ReplayResult 和结果展示。
- 技术候选按原 source 信号类型/路径/状态组合比较；目标窗口单独取增量，前置步骤的历史异常不冒充目标异常。
- 画面相似仅表示视觉接近；重复泛化 console 文案、共有 404、最终 URL 一样均不足以证明原问题再现。
- 保留既有可解释匹配规则，补具体的 matched_basis 和限制说明；不加必需的 LLM 二次判定，不把灰度阈值当通用语义标准。
- 认知 Evidence 使用原保存预期帮助人复核，回放状态不自动修改判定/决定；观察缺失或中途失败保留未知。
- 验收：前置动作报错而目标正常不会 falsely reproduced；视觉接近/原特定 500 再次出现分别注明匹配依据；缺图不被判 clean pass。

### E04：按来源改进聚类，保留每条证据

- 父任务 R02/R04；M1。落点 `Deduplicator.embed/cluster/_hard_key/_make_issue`、`dedup/models.py`，消费 P05/P07。
- hard key 纳入 finding_kind 和可核对的技术事实特征；认知分组保留原预期/依据差异，不凭 classification 推断同根因。
- 同动作技术异常与认知落差不互相替换；可关联一个 Issue，但成员全保留，报告仍按 Evidence 显示来源与决定。
- 相似度仅做组织候选；不同动作同文案、相似页面不同落差使用反例测试。跨来源软聚类保守处理，避免截图相似自动合并解释。
- 增量回写只更新 Issue 关联；Evidence ID 与 raw/basis 不改变，审核仍绑定原 Evidence。
- 验收：保存 500 与无反馈同时可审；重复同一信号可合组而路径不丢；不同功能按钮的相同错误不会合成无法追溯的一条。

### E05：增量汇总与失败隔离

- 父任务 L03/L04/R05；M1。落点 pipeline 聚类/调查调度、Issue 序列化、RunWriter/RunManager。
- 聚类从 committed Evidence 读取，结果作为可选增量保存；汇总出错仍能按原 Evidence 查看和导出 analysis。
- 未审记录不因重复计算更换 ID；Issue 编号可为当前视图，但不作为决定的独立权威。首版不新增手工合并/拆分工作流。
- 回放保存新增结果，调查保存假设；两者都不能把原扫描从 partial 改为 done 或删除其诊断。
- 依赖 P06/U03，消费端 H05/H06；终态下的调查/回放等增量写入和双缓存失效与报告生成共用同一本地锁，不只锁决定操作。
- 验收：聚类/调查中抛错仍保留技术与认知证据；重启看到最后有效增量；已有决定不因重新分组丢失。

### E06：按 Issue 的调查输入与源码限制

- 父任务 R06/L04；M2。落点 `build_investigator_context`、`retrieve_source`、`InvestigationAgent.investigate_issue`、`parse_investigation`。
- 继续只引用 Issue 成员对应 raw/DOM/截图/动作；补 finding_kind、basis、来源步骤和完整性，未知/未执行不得写成已发生。
- 源码基准使用 F02 所选应用；片段携带路径与截断说明，依证据相关关键词有界检索。找不到片段就说明未知，不制造组件或代码位置。
- URL-only 仍可提供技术解释，但没有源码时不声称源码根因。框架识别只作调查元数据，源码不回流到 N01 预期。
- 调查 status 与 error 独立保存；模型输出是根因假设。source map/组件树/服务端链路追踪依据后续需求再决定。
- 验收：两个 Issue 不串用信号与动作；源码不可读或 investigator 失败仍导出原证据；根因和猜测位置明确标为假设。

### E07：回放入口与新上下文整体验收

- 父任务 L04/L05/R06/V01；M2。落点 UI 回放路由、JobController、RunManager.save_replay_result 与现有 replay/UI 测试。
- 终止后的 run 才使用稳定快照发起回放；复用单任务占用，停止/超时也记录中断步骤和环境故障。
- 页面显示前提、实际执行前缀、目标阶段、匹配依据和限制；回放失败可继续审阅，不要求先“复现成功”才作决定。worker 回传结果，由 parent 在 H06 共享锁内保存并失效报告，避免绕过终态更新保护。
- 在独立浏览器上下文验证前置表单→客户端导航→触发异常；应用数据由固定 fixture 重置，不自动重置未知用户系统。
- 验收：React/Vue/Next 最小机制样例分别取得适用的独立回放记录；损坏包、会话过期、目标失败与未支持作用域不共同显示“未复现”。

## 4. 关闭顺序

E01/E04/E05 与采证闭环同步；E02/E03/E06/E07 在 M2 完成，消费 [T01](01-project-framework-compatibility.md)、[T02](02-browser-interaction-state.md)、[T07](07-local-run-ui-lifecycle.md) 和 [T09](09-fixtures-compatibility-release.md)。
发布说明分别给出“可回放”“观察再次出现”“认知解释经人采信”；不能用其中一种证据替代另外两种结论。

## 5. 本轮关闭说明

E01/E03：包 v2 的前缀与目标窗口分开，技术按具体来源事实比较，画面接近不替代技术再现；旧包保留可读性与窗口未知说明。E02：回放消费者支持导航限定 SPA 回退及实际浏览器/视口核对；F07 配置生产者仍属于 T01。E04/E05：保守组织分组、committed 副本计算、共享锁增量与报告缓存；E06：Issue 成员事实、可见文字快照标识、源码/输入截断和独立调查失败状态；E07：终态入口、进度保留与四条锁版本框架异常独立回放。完整工程验收数字、命令和剩余范围见 [实施记录](../../t05-implementation.md)，不据此声明真实用户认知或根因准确率。
