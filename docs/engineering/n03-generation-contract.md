# N03：外部用户预期与采样并集契约 v4

当前日期：2026-10-02。用户明确：两次采样取并集，独立人审不属于验收，误报不设控制门槛。核心价值是发现产品里那些只有内部人才觉得理所当然的地方；默认模拟懂相关行业、第一次使用本产品的外部用户。

## 当前 v4 工程契约

- `general-user-v4` 保留相关行业知识与一般交互经验，允许以 interaction_convention 提出 Enter 提交等主观要求，不再要求产品先公开承诺。不读取产品内部答案或本步执行后资料。
- `sampling-merge-v3` 将所有合法采样取并集；出现一次即可进入 judge，关系未知和互斥不排除。确定等价才去重，全部成员原文与依据保留。
- 每份响应最多 5 条，合并可达到 `5 × samples`，取消合并后 5 条阻断。单份调用/解析失败不否决有效采样，sampling.complete=false 仍明确；全部无效仍工程失败。
- `judgment-v3` 保留局部落差，同时记录 unverifiable_expectation_ids/error；缺图或未知不假装通过，也不能抹掉其它已报发现。
- 在线与离线 analysis 显示分歧备注、来源、失败/弃权及局部未知。所有用户决定都保留原发现，confirmed 仅是用户选择的采信报告。
- 发布矩阵 v2 只有工程层为 required，独立人审/试用为 optional；无误报或认知认可率门槛。未收集审阅分钟保持未知。
- 当前版本已执行三款开源应用的六次有界真实模型扫描，另开批次使用 105/200，余 95；历史 98/100 批次独立保留。结果与局限见下节及[开源应用测试](open-source-applications.md)，控制样例的 v4 复跑仍开放。

工程验收关注探索覆盖、未处理候选、证据与报告不丢失、身份/采集关联及全部调用对账。尽量减少漏报，不承诺有限预算下绝对无漏报；不建设岗位/行业画像配置器。

## v4 工程验证

本轮全量默认回归为 776 passed / 9 failed，失败均为旧策略断言：1 条仍断言 judgment-v2，8 条仍断言未知关系应阻断双方。修订这些契约断言后，相关模块与新增可选反馈用例定向 63 passed；按 classname/name 去重并采用最后结果，合计 **787 个不同用例通过，0 个未解决失败**。合并覆盖率 **88.07%**。

Chromium 定向验证包含并集进入 judge、局部落差/未知同时保留 Evidence、关系备注在线与离线可见、弃权记录及六角色计量。sdist/wheel 构建与运行/验收资产检查通过，外部目录排除；该工程阶段未做真实调用，当前未重新做干净安装或远程 CI。随后真实应用增量见下节。

已保存采样零调用离线回放：首组 v2.2 有候选 4/5 → v3 5/5；生成边界组 v2.2 2/5 → v3 4/5（剩余为空采样）。这些只证明已保存合法要求不会因关系规则被阻断，不产生新 Evidence，不代表新的真实模型效果。

本机产物均 gitignored：`artifacts/evaluation/recall-contract-v4-{junit.xml,final-junit.xml,final-coverage.json,regression-summary.json,first-samples.json,boundaries.json}`；日志 `.venv/recall-{regression,final,browser,build}.log`；发行包 `.venv/dist/recall-contract-v4/`。旧失败结果与复测单独留存，不覆盖原始 JUnit。

## v4 开源应用真实增量

2026-10-02 在固定 TodoMVC、IT-Tools 和 Memos 上各执行自主/定向四步，全部六份报告保存。97 个来源候选完整保留并合并为 81 条步骤要求；模型没有提出 mismatch，13 条要求无法判断，不能由此推导应用零落差。24 步为 15 passed、8 inconclusive、1 action_failed；均保留为有限范围的 partial。

Enter 已生成预期，含未执行的空输入分支；Memos 无文案按钮的目标描述不足导致明确弃权，展开菜单后下一点击被弹层拦截。当前优先级转向目标身份、弹层范围、输入分支与焦点观察，不增设语义过滤。全部 105 次模型响应成功且计量对齐，金额未知；工程测试最新去重 801 项通过，完整套件覆盖率 88.10%。完整事实、账目及复测门槛见[应用记录](open-source-applications.md)。这批不能替代 v4 正常/异常/例外/两步历史控制复测。

## v3 历史范围与验证（当前要求以 v4 为准）

以下原始运行数字、版本及当时的要求保留；v3 对 Enter 常识的禁止、人审门槛及 v2.2 关系阻断已被 v4 撤销，不是当前待办。

日期：2026-10-02。范围：独立开发者功能 MVP。提示版本 `general-user-v3`；有限关系规则仍为 `sampling-merge-v2.2`，判断仍为 `judgment-v2`。本轮增强输入、表达与弃权记录，不依据事后结果生成预期。

## 从真实基线得到的改动

上一批真实结果见 [T09 记录](t09-real-baseline-results.md)。三步 TodoMVC 已经创建待办，但 blur 出现光标/样式/条件分歧，Enter 两次输出空预期。检查输入还发现 `press` 描述没有携带选定按键，模型实际不知道要按 Enter；原样保留空预期是必要的，但输入缺口需要补齐。

1. `prepare_input` 新增 `action_parameters`：仅 `press` 可携带白名单命令键，例如 Enter/Tab/Escape/方向键。普通字符、任意字符串和组合键未在白名单时为 `key=null`；type/select 值、密码、selector/scope 不进入该字段。按键是计划动作，不是关于产品行为的答案。
2. 生成提示提供按当前动作选择的可选标准表述：点击结果反馈、输入内容显示、失去输入焦点/活动光标。只有模型独立判断要求成立且完全等价时才照抄；并非每个动作必须产生预期。带样式、条件、时限、对象、否定或历史限定的要求保留完整原文与 basis，不在解析器中改写或替换。
3. Enter 不默认意味着提交、创建或保存；只有事前可见资料和已提供的历史支持具体行为时才能提出结果要求。旧 Saved 仅是前序观察，不能证明当前保存成功。
4. 空输出可携带弃权对象，明确“依据不足”或“没有可观察要求”。非空 expectations 与非空弃权对象不能共存；未知类别、空理由、额外字段或超长理由导致解析失败，保留原始输出。不会自动启动额外补写或修复调用。

```json
{
  "expectations": [],
  "abstention": {
    "code": "insufficient_visible_basis",
    "reason": "界面没有承诺 Enter 的结果"
  }
}
```

另一合法 code 是 `no_observable_expectation`。reason 限 1～500 字符。旧输出未携带弃权说明时仍接受空数组，但标记 `unrecorded`，不补造原因。非空输出原有 `text` / `expectation_basis`、条数、引用及身份约束不变。

## 持久化、审核与兼容

每份采样保留 raw/parsed 和可选 abstention；生成记录包含 `empty_samples`、`expression_templates` 和 `coverage_reason`。全部空数组记为 `no_expectations`，关系未决记为 `unresolved_relationships`；采样未完成是 `sampling_incomplete`，合并超限失败单列 `merge_failed`，避免已完成的采样被误称为未完成。空采样不增加支持数，不投反对票，不构成检查通过。原有 sampling 完整性和覆盖统计仍分开。

在线 run 页面显示每份空采样的理由；共享认知视图及复制后离线 analysis 保留相同原因。旧记录的 coverage_reason 为 `unrecorded`，不因读取而升级版本或改动开发者 Decision。

从真实基线提取的最小语料在 `tests/fixtures/sampling-calibration/generation-contract-boundaries.json`：原输入/失焦近义、失焦样式/条件、空 Enter 和历史旧 Saved 条件。语料仍注明原提示 v2、AI 校准和独立人审 pending；它是旧输出回归，不伪装成新提示的真实结果。新增 prompt 模板不会把这些保存原文自动转换为标准句。

## 验证及冻结范围

新增契约先红后绿；定向验证包括白名单按键、输入隔离、可选模板、条件保留、弃权校验、旧空输出兼容、空样本支持数，以及真实 Chromium 管线→终态快照→在线审核→下载→离线展示。完整默认回归与覆盖率另记实际结果。

真实验证只使用上一批尚余 24 次 CLI 启动，总授权仍是 100 次、此前已用 76 次，包含失败/调查/reporter。固定六角色模型、low、双采样、原控制样例和同一 TodoMVC commit；定向运行两步 `history-normal` 与三步 TodoMVC，其他控制不冒充已复跑。代码副本、模型配置、计划、全部输出和预算都留在 gitignored 的 `artifacts/evaluation/t09-real-20261002/`。

启动前固定门槛：按键需在动作前传入，值/定位器仍隔离；自选标准失焦约定可稳定表达，额外条件不得消失；无可靠 Enter 预期时仍 inconclusive 并记录原因；历史不得借旧反馈证明当前成功；所有计划 run、未执行、失败、未决及调用完整留存，总数不超过 100。该定向批次不单独关闭正常/异常/合理例外对照、人审或效果 gate。

## 真实定向结果

`generation-v3/` 实际执行 2 run / 5 动作，**22 次 CLI 启动**：4 passed、1 inconclusive；全部采样完成，关系未决 0，没有生成/解析/判定失败，没有额外调查或 reporter。历史两步均使用当前操作反馈要求并看到 Saved / Next item saved；第二步 basis 包含当前按钮或明确指出旧 Saved 不能证明本次成功。该结果没有改写此前 v2 保存的额外条件和未决。

TodoMVC 输入和失焦的两个采样分别自选同一标准表述，均完成盲判。Enter 的执行前快照含 `action_parameters.key=Enter`，动作后出现一条待办，但两个采样均为空并带 `insufficient_visible_basis` 理由：当前文案和历史未说明 Enter 的效果。因此没有事后补写预期，没有调用 Enter 的视觉/认知判定，没有新增 evidence，真实应用 run 仍 partial。

本轮助手核对了五步原文、依据、动作前参数、可见结果及截图；独立人工复核仍 pending。标准表述在这个小样本内减少了措辞分歧，不能据此宣称普遍准确率或完整应用验收。后续应让实际审核人判断要求是否合理，再决定是否补充用户可见的探索提示或更丰富的允许输入。

原授权新批三阶段累计 **98/100 次，剩余 2 次**；此前另一批 98 次另计。本阶段角色：gist=4、expectation=10、visual=4、judge=4。全新批总角色：gist=24、expectation=42、visual=13、judge=13、investigator=4、reporter=2，98 个响应成功；已返回 prompt_tokens=808932、completion_tokens=12131，total_tokens 与 98 次金额/币种未知，不补算，不写为零费用。没有重置或扩大调用上限。

`generation-v3-plan.json` 保存启动前门槛、父源码提交和五个源文件的冻结副本位置；实际调用时源码与副本一致。真实阶段结束后只补正了合并失败的原因标签，独立边界测试验证，没有追加模型调用。配置复用原冻结模型及样例，第三方源码、依赖、缓存、构建和所有产物均在项目内忽略目录。

`accounting-reconciliation.json` 已纳入第三阶段；`human-review-steps.json` / `human-review-README.md` 扩展为 12 run / 21 步待审，审核人和主动审阅分钟仍为空。原始阶段记录和产品 Decision 未改动。当前 v3 工程未据上一版本的远程 CI 推导已获得新版本远程验收。

## 最终工程验证

完整默认套件 **768 项通过**；合并失败原因补测 **25 项通过**（24 项重叠），去重共 **769 项**，合并行覆盖率 **88.15%**。实际 Chromium、管线持久化、在线与离线原因展示已包含在默认套件内；没有为生成提示变更重复安装第三方应用或扩大框架套件。

sdist/wheel 构建及运行模板、默认配置、验收资产检查通过，不包含第三方示例或运行产物；不据此宣称本轮做过新依赖发行安装或新版本远程 CI。完整/补充 JUnit、覆盖率、构建日志均在项目内忽略目录；真实结果与计量另存 `generation-v3/` 和根目录对账文件。
