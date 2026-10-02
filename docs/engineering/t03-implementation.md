# T03 实施与验证记录

日期：2026-10-01。环境：macOS、Python 3.11.14。对应计划：[T03 可见上下文、预期依据与认知判定](mvp-planbooks/technical/03-context-expectation-judgment.md)。
状态：N01～N05 的工程范围已实现，N06 的确定性样例与浏览器回归已接入；真实模型/真实小应用的效果验收尚未关闭。

2026-10-02 增量：N03 逐条采样合并、有限反馈规则、来源/完成度与部分检查展示已接通；当前规则及回归、真实复跑见 [N03 校准记录](n03-calibration-results.md)。本文下面的 basis 文本集合规则及 372 项结果保留为首次实现基线，不能代替最新合并实现或效果验收。

## 1. 交付行为

源码地图、README 摘要、自由范围指令和定位摘要用于选择扫描范围或辅助调查，不再进入预期模型。`ExplorationContext` 的兼容 brief 来自实际可见文字，源码地图的导航边不作为用户先验；预期引擎也不直接信任调用方传入的 brief。保留旧 `gist/focus` 参数形状，但预期角色不将它们拼入 prompt。

Pipeline 在预期调用前提交 `step.input.cognitive`：实际发送的可见文字、控件标签、近期可见历史、动作的可见标签、版本与身份。CSS selector、typed value、form_state、技术日志和调查解释不进入该输入。视觉模型也只接收动作的可见标签；旧 action_desc 仅作为本地显示/兼容绑定保留。URL 移除凭据与敏感参数，文本应用已有敏感赋值清理。

预期绑定 `run_id/step_id/action_id`，生成稳定的步内 ID，如 `EX-ST-00001-001`，记录 `prompt_version=general-user-v1`。判定消费原事前集合、basis、保存的前后图片/文字与明确标识为模型解释的视觉摘要。技术日志保留在技术证据侧，不发送给认知 judge。

同名动作的不同步骤不能共用预期；已冻结预期若被修改则失败。新 mismatch 必须同时引用事前 ID 和原文，集合外预期、错误 ID、重复引用会被拒绝，允许一次 JSON 修复。`failed/inconclusive` 不变成空的通过结果。

生成空数组或没有稳定有效要求时标 `inconclusive`；非法格式/伪引用标 `failed`。仍按 T04 执行动作与技术 QA，不补写事后预期。地图失败后，若已有可见输入且范围可确定，可以继续认知检查；指定范围无法定位仍明确停止，运行诊断不消失。

## 2. 依据、上限与采样

| 项目 | 实现规则 |
|---|---|
| `visible_copy` | reference 必须是冻结的当前可见文字或控件标签中的原文 |
| `interaction_convention` | 记录模型提出的明确惯例原文；类型/非空/长度验证，不把它当成业界共识已证实 |
| `observed_behavior` | `ST-00001: 可见结果原文`；必须对应本 run 最近已完成、已提交、先于当前动作的步骤，原文能在该历史快照中找到 |
| 预期与依据 | 每步最多 5 条；每条 text/reference 最多 500 字符；basis 仅有 type/reference |
| 当前输入 | 文字 4,000 字符、控件最多 40 个且每个 100 字符、URL 2,000 字符、动作标签 200 字符 |
| 可见历史 | 最近 5 个已执行且读到可见结果的步骤；每步文字 1,000 字符；原 step 引用保留，失败/未观察动作不构成历史依据 |
| 截断说明 | `input_limits` 保存文字、控件数量/长度、URL、历史数量/结果截断状态；完整图片另在证据侧 |
| 模型原文 | 预期采样与 judge 输出每次最多保存 16,000 字符，超限标 `raw_truncated`；每个采样返回即 checkpoint，失败输出仍可复核 |

固定的一般用户定义：具备通用网页经验，第一次使用目标产品，未接受本产品培训。提示词要求可观察、允许等价反馈，不固定要求 toast/弹窗，不将合理校验、禁用、只读视为缺陷，不推断未公开业务规则或后台实现。

相同预期去重；同一个 basis 的不同采样提出的要求集合不同，会留在 `expectation_generation.unresolved`，不作为必须兑现的并集交给 judge。某次没有提出该要求不等于反对，该要求仍可进入有界集合。同一文本对应不同依据、合并超限等关联不明确的情况明确失败。

这是一条保守的分歧规则，不是语义裁判：不同措辞也可能被拦截；不同依据或同一采样内的语义矛盾不能由此保证检出。合理性、惯例是否适当和实现偏好仍需真实模型与开发者复核。上述上限是当前工程默认值，尚未通过真实模型效果校准。

## 3. 存储与兼容

| 文件 / 字段 | 责任 |
|---|---|
| `context/assembler.py`、`models.py` | 可见 brief、可见历史与限制说明；`forbidden=False` 仅表示未传入该字段，不证明语义无污染 |
| `expectation/contracts.py` | 版本、数量/长度约束、原文引用校验、采样分歧 |
| `expectation/engine.py`、`models.py`、`llm/roles.py` | 冻结输入、事前身份、原始输出、四态判定与集合校验 |
| `driver/action.py`、`observation/engine.py`、`models.py` | 模型使用可见动作标签；观察携带 run/step/action 与原始可见文字 |
| `pipeline.py` | 输入先提交、输出增量提交、历史只读此前 prefix、认知失败继续技术 QA |
| `evidence/engine.py`、`models.py`、`storage.py` | 按 ID 继承事前 basis；新增可缺省的 `expectation_id`，SQLite 增量添加 TEXT 列 |
| `run_writer.py` | 新证据的 expectation_id 必须指向同 run/step/action 已提交预期，文本/basis 一致；异常引用显示存储错误 |

复用 T04 `schema_version=2` 的兼容增量，不另建数据库。旧文本预期和无 expectation_id 的旧 Evidence 仍可读取/调用旧接口，不补造依据与身份；新 Pipeline 路径始终产生绑定 ID。SQLite、JSON、回放包和 UI 统一序列化保留新字段。

当前一般用户预期仍以文本输入为主，不读取截图进行事前生成。截图、可见结果与视觉观察用于判定；是否增加事前图像输入由实际效果验收决定。

## 4. 验证

最终全量回归：**372 passed，Python 行覆盖率 86.39%**，达到项目 80% 门槛。

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/pytest \
  --cov=alienqa --cov-report=term \
  --cov-report=json:.venv/t03-coverage.json --maxfail=3
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t03
```

sdist/wheel 构建通过；wheel 包含新增的 `expectation/contracts.py` 与现有 UI 模板，sdist 包含认知夹具、浏览器回归和本次实施/验收文档。未以此声明干净安装或跨平台验收通过。

| 资产 | 验证内容 |
|---|---|
| `tests/test_t03_cognition.py` | 源码/范围/定位信息隔离，三类引用与伪历史，限制与采样分歧，未来步骤、冻结集合、ID/原文/重复引用，技术日志隔离，视觉模型标签 |
| `tests/test_t03_browser_flow.py` | URL/源码两个 Pipeline 分支，共用真实 Chromium 页面：按钮等价反馈、缺反馈、合理校验与前序一致性；核对调用前快照、原始输出、basis 和 Evidence/SQLite 血缘 |
| `tests/test_t04_browser_recovery.py` | 扩展到预期第二次采样阻塞；真实 worker 停止、重启历史读取仍保留入口技术证据、冻结输入和第一次采样原文；其余地图/视觉/判定停止回归保持通过 |
| `tests/test_run_writer.py`、`test_evidence_migration.py` | expectation_id 往返与旧库迁移；引用缺失、文本/basis/动作身份改变明确报错 |
| 既有测试 | 旧文本接口、一次判定修复、技术失败降级、回放与 UI/CLI 通道兼容 |

浏览器、HTTP 与 worker 为真实本地执行；模型返回由替身控制。配对样例证明工程契约和实际界面机制，不证明真实模型能正确理解它们。没有执行付费模型、真实小应用效果评测、Windows 或远程 CI。

## 5. 尚待验收与下一步

[真实模型验收方法](t03-model-evaluation.md)给出控制样例、重复检查、真实小应用记录和未知费用处理。N06 效果验收保持开放，不据此关闭 J06/V03，也不将未完成 run 从效果分母删除。
下一份主实施计划为 T06：处理决定/备注、analysis/confirmed、终态快照与离线 HTML。T08 继续提供真实 attempt/用量/费用记录；原始输出记录不能替代完整调用计量。
