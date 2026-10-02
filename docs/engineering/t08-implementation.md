# T08 实施记录：LLM 请求账目、解析结果与未知费用

日期：2026-10-02。对应 [T08 K01～K06](mvp-planbooks/technical/08-llm-execution-metering.md) 与 MVP-04 V02/V03。K01～K05 工程范围和 K06 确定性回归已完成；真实模型/真实小应用基线仍开放。

## 1. 已交付行为

`LLMClient` 支持可选 `MeteringSink`、运行上下文和局部 `call_scope`；原无 sink API 继续可用。每次逻辑调用生成 `call_id`，每个实际主模型/fallback 请求在调用供应商之前保存 started attempt。失败、耗时、实际模型和请求配置保留，不被后续成功覆盖。

LiteLLM 与供应商 SDK 的内部重试参数显式设为零，fallback 仍由客户端循环逐次执行、逐次入账。[LiteLLM 官方重试说明](https://docs.litellm.ai/docs/routing)区分 `num_retries` 与 `max_retries`；本轮还用锁定的本地 LiteLLM/SDK 连接本地模拟 HTTP 端点，验证 429 后只有一次主请求、一次 fallback 请求。此验证不声明所有供应商或代理内部请求都已可观测。

六个角色均接线：gist、expectation、visual、judge、investigator、reporter；gist 的入口识别、单元定位和地图调用以 purpose 区分。预期采样与 JSON 修复是新的逻辑调用，保存 sample_index、用途和 parent_call_id；fallback 属于原调用内的新 attempt。认知调用使用 `general-user-v1`，其他角色使用 `roles-v1`，配置与实际请求参数另行记录。

供应商返回成功与业务输出解析成功分开记录。无 choices/content 的响应仍保留供应商成功、usage 和 response_error，再按现有 fallback 策略继续；非法 JSON/字段或预期身份引用失败标记原 call 的 parse_status，修复另计。图像编码/本地文件失败标为 local_failed，不创建供应商 attempt。模型拒绝视觉输入等供应商错误保存错误类型与清理后的原因，不作为被测产品的技术异常。

## 2. 文件与计数契约

| 文件 | 内容 / 消费方式 |
|---|---|
| `llm/config.json` | run_id、版本、实际角色模型/温度/fallback/max_tokens、默认供应商与 timeout；同时标识扫描已启用计量 |
| `llm/calls/<call_id>.json` | 逻辑调用及 attempt 明细；run/step/action/phase/purpose、输入引用、时间、状态、解析结果、配置、usage、费用和错误 |
| `llm/private/<call_id>-input.json` | 凭据清理后的输入文本，每段最多 2000 字符；图像只留省略标记，不保存 base64 |
| `llm/private/<call_id>-output.json` | 凭据清理后的输出，最多 16000 字符，超限标 truncated；供本机复核 |
| `llm/metering-errors.json` | 计量保存失败诊断；另通过 pipeline 回调进入扫描诊断，不引发额外模型请求 |
| `usage-summary.json` | 派生汇总；运行详情和报告从明细重算，不把旧汇总当权威输入 |

预期输入引用指向已提交的 `scan.json#steps/<step_id>/input/cognitive`；其他调用保存对应阶段/步骤引用及裁剪后的私有输入。私有文本不是完整请求副本，仍可能包含产品信息。公开明细/汇总只保存引用、配置及必要错误/usage，不复制完整 prompt、输出、图像或登录态。密钥环境值及 authorization/cookie 等凭据字段清理，HTML 中的汇总转义显示。

汇总按 run、role 和实际 model 提供 logical_calls、attempts、调用/请求状态、parse_status、请求累计耗时、token 已知小计及缺失数量。按 model 的 logical_calls 表示触及该模型的调用，含 fallback 的同一调用可能出现在多个模型组，不能把这些逻辑调用数直接相加；attempts 可与明细逐项对照。累计耗时不是扫描墙钟时间。

`complete` 表示账目闭合且未发现存储缺口，不代表模型判断通过或费用全部已知。token 字段分别统计；缺失、非法或供应商未返回值均为未知，不推算缺少的 total_tokens。

费用只消费明确的适配字段 `provider_cost={amount,currency,source:"provider_response"}`，金额必须非负有限、币种独立汇总。已知零费用与未知费用不同；普通响应不含该字段时仍未知。不使用 LiteLLM 内部价格表估算，不假定失败调用免费，不把已知小计称为完整总价。本轮验证的是该字段契约，真实供应商格式仍须由 K06 校验。没有费用硬上限，现有动作/时间预算也不是供应商计费上限。

## 3. 停止、故障与交付

pipeline 初始化 run 账目并在阶段提交后更新上下文；UI worker 的准备调用也使用同一 run。CLI 完成/取消和 UI parent 确认 worker 结束后，将仍 started 的调用或 attempt 转为 unknown，并附本地观察到的 termination。已经保存的成功/失败结果保留；未获得响应的请求不补结束时间、usage 或零费用。本地停止不等于供应商确认取消。

计量写盘/读取故障不替换供应商返回值，不增加 fallback，也不抹掉原始证据。运行详情与报告区分 absent、available、storage_failed、corrupt；CLI 输出降级提示。旧扫描即使后来新增 reporter 调用，也明确标注扫描账目缺失，不能据此声称获得整次扫描成本。

可选 reporter 绑定原 run，报告在它返回后读取汇总；它失败时确定性正文仍可交付。账目变化失效标准 `analysis.html` / `report.html` 缓存；读取已有缓存不会再请求 reporter。运行详情、analysis/confirmed 和 CLI 均接通同一份账目，无新数据库、追踪平台或计费系统。

## 4. 验证与开放边界

全量 **453 项通过，覆盖率 87.46%**；新增计量模块覆盖率 95%。包含真实 Chromium、HTTP、worker 停止/恢复及离线报告；模型使用替身或本地模拟供应商，无付费请求。

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers COVERAGE_FILE=.venv/t08.coverage .venv/bin/pytest \
  --cov=alienqa --cov-report=term --cov-report=json:.venv/t08-coverage.json --maxfail=3
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t08
```

| 测试入口 | 验证内容 |
|---|---|
| `test_t08_metering.py` | 请求前提交、主成功/fallback/全失败、dict/model_dump/缺 usage、多币种与未知、非法响应、解析修复、缺图、脱敏、坏账目/写失败、终止保留、reporter/UI；本地 HTTP 验证真实 LiteLLM/SDK 无隐式重试 |
| `test_t08_browser_flow.py` | 真实页面扫描、六角色、两次采样、fallback、JSON 修复、步骤/事前输入归属、报告后汇总和缓存不重复调用 |
| `test_t04_browser_recovery.py` | worker 真实阻塞后停止/超时，账目 started 先保存，终止与重启后仍为 unknown，原始证据继续可读 |
| `test_cli_regressions.py` | 正常及 Ctrl+C 路径的坏账目不阻断报告/已提交前缀 |
| 既有回归 | T03 可见输入与事前身份绑定、T04 原始保存、T06 双模式/审核/离线与旧 API 继续通过 |

sdist/wheel 构建通过，已检查计量模块、运行模板和报告代码进入 wheel，T08 实施记录、计划及两份新增测试进入 sdist。此检查不代替仓库外干净安装、Windows 或远程 CI。

下一阶段联动 N06/K06/Q04：明确模型配置、真实小应用及调用预算，保存实际响应格式、失败/未知分母与独立审核结果。当前工程回归不证明真实模型发现能力、认知判断效果或供应商结算准确性；这些 gate 继续开放。
