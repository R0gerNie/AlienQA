# T08：LLM 调用适配、失败记录与用量计量

版本：2026-10-02-tech-2。状态：K01～K05 工程实现与 K06 确定性回归已接入；K06 真实模型/真实小应用基线仍开放。见 [T08 实施记录](../../t08-implementation.md)。落实 [V02/V03](../04-validation-and-release.md)、J05 和 L02/L04；沿用 LiteLLM、本机配置和六个角色，不建设计费、账户或配额平台。
目标是知道每次实际调用做了什么、是否完成和已知花费；不靠只记录最终成功响应估计整个 run 的成本。

## 1. 实施前基线与本轮落点

| 模块 | 已有能力 | 应改进模块 |
|---|---|---|
| `llm/client.py::LLMClient.complete/complete_vision` | 主模型与 fallback 顺序调用、request_timeout、视觉编码 | 失败尝试与时间未保存；成功后仅返回 usage；缺 run/step/call 关联 |
| `llm/models.py::LLMResponse/LLMConfig/RoleConfig` | 文本、model、role、usage 与各角色配置 | usage 仅消费可 model_dump 对象，dict/缺字段等兼容需验证；无统一 attempt 状态 |
| `llm/roles.py` | gist/expectation/visual/judge/investigator/reporter 六角色调用 | 输出 text 后丢失用量上下文；采样、修复与 fallback 没有完整账目 |
| `llm/config.py`、`ui/settings.py` 与配置 YAML | 本机角色模型、温度/fallback 等 | 实际生效配置/版本摘要、能力错误、未知费用需明确 |
| pipeline/report 调用点 | 阶段错误部分可进入诊断 | 调用失败、解析失败、取消分别统计；报告调用也应归属原 run |

上表保留实施前缺口。当前已新增本地请求账目、六角色接线、解析状态、实际配置及运行/角色/模型汇总，并接通 CLI、运行详情与离线报告；停止后仍未返回的请求标为 unknown。LiteLLM/SDK 隐式重试显式关闭，由现有 fallback 循环逐次记录。
本轮通过替身与本地模拟端点验证，不发付费请求、不填实时价格。费用只接受明确的 `provider_cost={amount,currency,source:"provider_response"}` 适配字段；普通响应未提供时仍未知，不消费库内价格估算。真实供应商格式和模型结构输出/多模态能力仍由 K06 验收。

## 2. 最小调用记录契约

- 一个逻辑 `call_id` 对应角色的一次调用；每个实际模型供应商请求另记 attempt_index；采样和 JSON 修复是新的 call，并标明用途/父调用。
- 记录 run_id、可空 step_id、phase、role、实际 model、开始/结束/耗时、配置/prompt 版本与输入输出私有引用；不把 secret 或完整请求消息写进公开摘要。
- 状态区分 started/succeeded/failed/cancelled/unknown；模型 HTTP 成功但输出解析失败分别记录供应商成功和解析失败，不能重复计算供应商请求。
- 保存原始 usage 与可识别 token；费用含金额/币种/来源。缺 usage、失败被收费与中途被杀无法确认时均未知，不能填零。
- attempt 开始记录须先落盘；结束增量更新。worker 未返回时 parent 依据最后 committed 记录显示未闭合/未知，不伪造供应商取消成功。
- 接 [T04](04-runtime-pipeline-persistence.md) 的本机写入/读错误规则；汇总写 `usage-summary.json`，无新数据库或 tracing 服务。

## 3. 具体任务

### K01：在实际供应商请求边界记录所有 attempt

- 父任务 V02/J05；M1。落点 `LLMClient.complete`、`LLMResponse`、pipeline 的 client 创建与 stage 调用。
- client 接可选本地记录 sink 和 call context，旧无 sink 调用仍可运行；在每个 fallback 的 litellm.completion 前写 started，返回/抛错后写结果。
- 记录 actual model，不只记录配置主模型；错误类型/原因截断并清理凭据，不将 LLM 429/timeout 当产品技术异常。
- 调用记录写盘失败进入 storage 诊断并明确计量不完整；不能声称已掌握费用。不要为计量引入额外模型请求。
- 输入/输出：调用上下文+实际请求结果 → attempt 明细和 LLMResponse；依赖 P06，供 K02/K04/U04。
- 验收：主成功、主失败后 fallback 成功、全失败三种明细逐项准确；成功一次不能抹掉此前失败尝试。

### K02：采样、修复、视觉与输出解析接线

- 父任务 V02/J05；M1。落点 `LlmRoles`、`ExpectationEngine`、Mapper、VisualObserver、InvestigationAgent、ReportBuilder。
- 每个 expectation sample、judge JSON repair、可选调查/报告调用均传 context；gist/reporter 无 step 仍有 run_id。
- complete_vision 复用相同计量边界；图像编码/本地文件失败单列本地诊断，未发供应商请求不能创建已计费 attempt。
- 角色输出解析状态关联原 call；无效 JSON/字段错误不伪装模型通过，输出引用保留在本机便于重查。
- 配置 fallback 不支持图像时明确能力失败；先做配置/错误与小样例回归，不添加另一套 provider SDK。
- 验收：六角色调用及修复/fallback 全有记录；缺图本地失败与供应商失败可区分；R06 的确定性报告可在 reporter 失败时交付。

### K03：配置摘要、响应兼容与敏感输入边界

- 父任务 L02/V02/V03；M1 起步，M2 验收。落点 `LLMConfig/RoleConfig/LLMResponse`、config loader、settings 与评估 manifest。
- 记录实际角色模型/温度/采样/fallback、request_timeout 和 prompt 版本；API key 只用于调用，不进入记录/HTML。
- 规范 dict/model_dump/missing usage、无 choices/content 等响应边界，保持明确失败/未知；支持范围需基于使用过的供应商响应，不猜所有格式。
- 输入引用优先指向已保存的允许快照；预期不引用源码答案，模型 payload 不复制 storage_state/完整登录凭据。
- 保存私有输出供复核和经裁剪摘要供分享，复用现有目录权限与转义；不增加完整网络抓包或敏感请求正文日志。
- 验收：脱敏配置/异常/usage 样例可分享；secret 哨兵不出现在 HTML/公开摘要；允许输入可追到相应 step。

### K04：用量与费用汇总

- 父任务 V02/V03；M1 计数，M2 基线。落点拟新增轻量 `alienqa/llm/metering.py`、RunManager/RunWriter 与运行详情。
- 汇总 run/role/model 的 logical calls、实际 attempts、成功/失败/未闭合数量、耗时、已知 token 和缺失数量。
- 费用优先保留供应商返回来源；按价格估算则记录执行时查证的价格快照、日期、币种和公式，不在计划中填当前价格。
- 已知费用与未知项目分开显示；多币种不直接相加，已知小计不能被标成完整总价。费用硬上限未实现时明确只有动作/时间/人工调用预算。
- 明细是汇总依据，重算不得丢失败/取消 run；ReportBuilder 的可选调用也入账，但不为写摘要再请求模型。
- 验收：fallback/repair 的总 attempts 与明细一致；缺 usage/未知费用不混入精确总价；同 run 报告调用可追溯且不重复累计。

### K05：停止时未闭合调用与重启读取

- 父任务 L03/L04/V02；M1。落点 sink 持久化、JobController 结束回调、RunManager.load_diagnostics 与 usage 读取。
- started 记录在实际请求前提交；终止只追加 parent 观察到的运行终止事实，未取得供应商结算/返回时仍 unknown。
- callback/异常路径不覆盖已保存成功尝试；计量加载区分旧缺文件与坏文件，坏记录明确不完整。
- 不让计量读取/汇总阻断原始证据和分析正文；在页面显示计量限制，不能宣称取消后一定不收费。
- 验收：视觉请求阻塞后 watchdog 终止，历史保留 raw 证据与 started attempt；重启显示调用未知、认知未完成，两者不变成零。

### K06：回归与真实基线消费

- 父任务 V02/V03；M2。落点 `tests/test_llm.py`、pipeline/report/job 回归及 [T09](09-fixtures-compatibility-release.md) 评估记录。
- mock 只验证请求边界、状态和账目；真实请求在显式预算下验证用量/错误格式与认知效果，模型版本和尝试集合保存。
- 不做无限 provider/模型矩阵；首轮一套配置、失败与未知均披露，再根据证据决定换模型或价格策略。
- 验收：主成功/fallback/全失败/usage 缺失/未闭合五种场景通过；首轮真实小应用能对上 run、attempt 和基线分母。

## 4. 执行顺序

K01/K03 定义明细与上下文，K02 接角色，K04 汇总，K05 与 U03 同步；K06 消费实跑。
M1 就要保存失败尝试，M2 才决定费用/效果门槛；不能等模型调优完成后再补计量。
消费端：[T03](03-context-expectation-judgment.md)、[T06](06-review-report-artifacts.md)、[T07](07-local-run-ui-lifecycle.md)、[T09](09-fixtures-compatibility-release.md)。
