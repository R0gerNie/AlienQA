# T03：可见上下文、预期依据与认知判定

版本：2026-10-02-tech-5。状态：N01～N05 工程实现与 N06 确定性样例已接入；首轮样例暴露的采样合并缺口已按 [N03 副计划](03a-sampling-merge-calibration.md)完成 C01～C05，新增有限反馈规则、来源/采样完成度与部分检查展示。C06 离线对照已完成，真实复跑按版本保存，详见 [N03 校准记录](../../n03-calibration-results.md)；真实应用与独立人工复核仍开放。原始 [首轮基线](../../n06-first-results.md)和[首次实施记录](../../t03-implementation.md)保留。落实 [J01～J06](../01-general-user-judgment.md)，消费 T02/T04 的事前输入和实际观察，为 T06 提供可审阅认知证据。
固定一般用户定义，沿用现有上下文、预期、判定和角色模块；不引入行业画像、岗位配置或企业规则库。

## 1. 实施前基线与缺口

下表保留计划拆解时的基线；现有接口和交付状态以实施记录为准。

| 任务 | 当前交付 / 验证 |
|---|---|
| N01 | 源码地图/范围指令/定位摘要与预期输入分离；URL/源码两条浏览器路径核对保存输入 |
| N02 | 三种依据、原文引用、5 条/500 字符上限与严格解析；无效输出不补造 basis |
| N03 | `general-user-v2` 固定定义并规范无附加限制的通用反馈表述，模型仍自主选要求；`sampling-merge-v2.1` 有限反馈关系、逐条合并/来源、采样完成度和部分检查展示；未知保留，效果见校准记录 |
| N04 | 最近 5 个已执行并提交步骤的可见结果；不传技术日志、typed value 或未来步骤 |
| N05 | run/step/action/expectation_id 绑定、原集合校验、四态、一次修复、Evidence/SQLite/历史血缘核对 |
| N06 | 首轮双采样 5/5 未决及单采样 1 passed/1 字段 failed 保留；新提示双采样配对 4/4 可用、合理校验 1/1 passed，本轮 98 次调用；独立人审、新提示历史及真实应用待验，未关闭 |

| 文件 / 函数 | 当前事实 | 应改进的模块边界 |
|---|---|---|
| `context/assembler.py::ExplorationContext.build/_brief/_history` | 白名单字段出口；brief 直接来自 Mapper；历史主要是动作描述 | 字段白名单不能消除 brief 内的内部答案；历史需包含已观察结果 |
| `mapper/filter.py`、`mapper/mapper.py` | 源码模式可读 README、源码片段，生成产品简介/地图 | 导航定位信息与一般用户可见信息分开供应；不把源码摘要直接送预期 |
| `expectation/engine.py::expect/_compose_page_text` | 执行前绑定动作；消费文字、元素及路由 | 未消费历史/截图；没有可追溯依据，scope/focus 可能提供内部答案 |
| `llm/roles.py::generate_expectations` | 多次采样后合并文本；接收 focus | 文本并集会保留矛盾或过于具体的预期；需结构化、有限输出 |
| `expectation/models.py::Expectation/parse_judgment` | 判定四态与严格 JSON 验证已存在 | 新依据需明确验证；旧文本预期与新结构并存，不能伪造补齐 |
| `expectation/engine.py::evaluate`、`llm/roles.py::judge` | 前后截图盲判；校验原预期文案和动作描述 | 应提供可见变化/反馈与依据；动作关联不能仅靠同名文案 |

以上是实施前源码事实。原始截图、DOM、技术信号、模型解释和开发者决定各保留自己的身份。

## 2. 输入输出与最小接口

- 输入：T04 已冻结的动作前状态、可见文字/元素、选定动作，以及先前已完成步骤的可见结果。
- 输出：事前 `Expectation`、共享 `expectation_basis={type, reference}`、四态 JudgmentResult；只把 mismatch 转为认知 Evidence。
- `visible_copy` 的 reference 指向当前可见文案/控件；`interaction_convention` 写明确惯例；`observed_behavior` 指向本 run 已保存的前序步骤和可见现象。
- basis 只有上述一个对象；不增加另一套 rationale/source 枚举。新 Evidence 逐条继承所引用预期的 basis，技术 Evidence 为 null。
- step/action 关联消费 [T04](04-runtime-pipeline-persistence.md) 的稳定 ID；预期可按该步内编号关联，旧 action_desc 继续用于显示和兼容。
- 当前新增 `Expectation.id/run_id/step_id/action_id/prompt_version`，Evidence 保存可缺省的 `expectation_id`；新判定必须同时原样引用 ID 和文本，旧文本接口保持兼容。
- 判定模型只能引用事前集合；输出无法关联、依据不合法或观察不足时 failed/inconclusive，不得补造“应该怎样”。

## 3. 具体任务

### N01：分离源码地图、范围指令与用户可见输入

- 父任务 J01/J02；M1。落点 `ExplorationContext.build`、`Mapper` 调用点、`Pipeline._collect_source/_collect_live`、`ExpectationEngine.focus`。
- 地图可以继续帮助定位范围/候选，调查可以读取源码；预期收到的 brief 只来自实际可见页面，不直接继承 README/源码导出的内部规则。
- 自由文本 scope 用于定位、筛选已有单元。不能把“保存本来没有反馈”等内部答案作为预期生成参数；原指令可作为本地扫描输入记录，不能变成用户先验。
- 截断与缺失显式记录；`ctx.forbidden=False` 只表示字段未传入，不声称已经证明语义无污染。
- 输入/输出：地图和 scope → 定位信息；动作前可见快照 → 预期输入。依赖 B01/B05、P02；供应 N02/N03。
- 验收：在不可见 README/指令加入业务答案，保持可见页面相同；确定性输入构建结果不泄露答案。没有源码时仍完整运行。

### N02：结构化预期与依据解析

- 父任务 J03/R01；M1。落点 `Expectation`、`LlmRoles.generate_expectations`、`ExpectationEngine.expect` 及 Evidence 转换。
- 新输出逐条包含 text 与 basis；验证对象、枚举、非空 reference、条数与长度。具体上限先用小样例校准，配置固定后记录版本。
- 当前/前序可见引用需能在保存输入中找到；惯例依据记录原文，允许开发者质疑，不能把模型写出依据当作已证明正确。
- 旧调用/旧记录的文本预期仍可读；缺依据标未记录。新扫描解析失败写模型诊断，不能把旧文本包装成新有效依据。
- 依赖 N01/P05，供应 N03/N05/H04；没有有效事前依据时技术 QA 按 P04 继续。
- 验收：三类 basis 往返不丢；无效枚举、伪前序引用、空 reference 和非对象逐项报错；旧记录显示缺失而非推测来源。

### N03：约束一般用户预期的合理性与可观察性

- 校准按 [N03 副 Planbook](03a-sampling-merge-calibration.md)执行：逐条关系比较、有限反馈规则、采样完成度、合并来源及部分检查展示；C01～C05 已实现，C06 效果与关闭证据见 [校准记录](../../n03-calibration-results.md)。
- 父任务 J01/J03；M1。落点角色提示词、采样合并、`ExpectationEngine.expect`。
- 固定一般用户定义与 prompt 版本；围绕当前动作生成能从页面验证的结果，允许等价反馈，不要求指定 toast、弹窗或实现细节。
- 相同预期去重；互相排斥、未公开业务规则、后台实现猜测单列为无效/未决，不把采样并集全部交给 judge 视为必须兑现。
- 当前确定性实现按要求逐条归并，有限反馈规则仅在解释整句、同一冻结动作时接纳同义关系；排版归一化不删除否定、条件、数值或对象。A 对 A+B 的共同 A 可保留，未知附加 B 留为未决；明确冲突阻断双方，不用多数票。支持范围内检查同采样冲突与跨依据同义，不声称识别所有语义矛盾或证明惯例正确。未知句式仍可能被保守拦截。
- 保留采样 requested/returned/validated/complete、组成员/支持数/规则版本和冻结 ID；partial 的局部 passed 不能使步骤完整通过，局部 mismatch 仍产生原身份的 Evidence 并显示检查不完整。
- 保留需要复核的原始模型输出引用；只做有依据的解析和筛选，不新增自动“正确答案”裁判链。
- 输入/输出：N01 输入 → 有界的 N02 事前集合或失败诊断；与 T08 合作记录实际采样调用。
- 验收：保存后按钮/状态明确变化可满足反馈预期；无反馈版本可产生落差；合理禁用/校验不固定为缺陷。无法观察的业务结果不算 passed。

### N04：把可见使用历史真正接到预期模型

- 父任务 J04；M1 准备，M2 完成。落点 `ExplorerContext`、`_history/_compose_page_text`、步骤序列化。
- 文本历史包含原 step 引用、已完成动作、可见结果摘要/文字；只引用本次动作之前的已完成且已提交步骤，截图另留证据侧。
- 截断近期历史并说明限制；不能混入截图、技术日志、调查根因、数据库字段、隐藏值或当前动作的执行后结果。
- 文本历史先落地；预期阶段是否增加图像输入依据 V03 效果决定，不把更换视觉 API 设成 MVP 前提。
- 依赖 B06/P02，供应 observed_behavior；失败/未完成步骤标状态，不编造已经观察到的成功行为。
- 验收：先前按钮反馈可成为后续一致性依据；下一步无法引用未来 step；登录态/密码未进入历史文本或共享报告。

### N05：判定接口与 Evidence 关联

- 父任务 J05/R01；M1。落点 `evaluate/parse_judgment`、`LlmRoles.judge`、`Observation`、`EvidenceEngine.build`。
- 传入原事前预期及 basis、保存的前后截图和可见结果；技术日志单列，不让后台报错替代用户是否看见反馈的判断。
- step/action 关联不匹配直接 failed；只允许结果引用原集合，逐条可追溯；多条预期对应不同认知 Evidence 时不丢 basis。
- 保留现有四态和一次 JSON 修复；passed 需要可用观察与有效判定，截图缺失/未执行/模型失败分别标未知或故障。
- 初始禁用/只读控件只供可见上下文，不强行点击或建立静态审计新通道；动作后出现无解释禁用，仍以该实际动作的事前预期与观察为据。
- 视觉摘要与 judge 解释仍是模型输出；原始文字/图片单独保留。预期失败后的执行结果只供下步历史使用。
- 依赖 P04/P05、N02/N03/N04；供应 H03/H04 与 Q02。
- 验收：同名按钮、相同动作文案的不同步骤不能串用预期；模型返回集合外预期被拒绝；视觉失败不丢独立技术候选。

### N06：认知样例与模块关闭

- 父任务 J06/V01/V03；M2。落点 `tests/test_expectation_engine.py`、`test_pipeline_regressions.py`、`test_pipeline_browser_flow.py` 与 T09 评估资产。
- 复用 HTML 正常/异常配对和 B09 真实机制样例；预期输入污染、输出解析、历史关联先用确定性模型替身验证。
- 再用真实模型检查合理例外、等价反馈、陌生术语、未解释禁用和缺反馈；答案留在评估侧，按设计与模型误读分开标注。
- 每条结果保留预期、依据、输入引用、观察、判定、决定和费用；未完成 run 不能从效果分母删除。
- 验收：N01～N05 的契约回归通过，至少一款真实小应用有可复核结果；有用性与波动按 V03 披露，不从单测通过推导认知准确率。

## 4. 顺序与边界

N01/N02 先统一输入和字段；N03/N05 接闭环，N04 与采证并行，N06 消费实际结果。
输出消费方是 [T04](04-runtime-pipeline-persistence.md)、[T06](06-review-report-artifacts.md)、[T08](08-llm-execution-metering.md)、[T09](09-fixtures-compatibility-release.md)。
本计划分析一般认知摩擦，不承诺读懂未公开业务规则；开发者“按设计”保留的条目仍保留观察和用户预期。
