# N03 采样合并校准实施与验收记录

日期：2026-10-02。对应 [N03 副 Planbook](mvp-planbooks/technical/03a-sampling-merge-calibration.md)。状态：C01～C05 工程范围已实现并回归；C06 的历史离线对照、真实复跑及可选复核材料已交付。当前 v4 的三款开源应用有界真实基线已完成，控制样例的当前版本复跑仍开放；独立人审不作为验收项。

> **当前口径修订（2026-10-02）**：用户明确撤销独立人审和误报门槛，两次采样取并集，只要提出一次即保留。当前定位为懂相关行业、第一次使用产品的外部用户，揭示只有内部人才觉得理所当然之处。下文 v1/v2/v3 数据与原始运行状态是历史记录，其中人审/合理性准入要求不再是待办。当前工程契约及验证见 [N03 生成契约](n03-generation-contract.md)，任务见 [修订后的副计划](mvp-planbooks/technical/03a-sampling-merge-calibration.md)。

## 1. 工程交付

| 工程包 | 实现与证据 |
|---|---|
| C01 | `tests/fixtures/sampling-calibration/first-samples.json` 保存五对最小控制页面采样；annotation 来自助手、独立人审 pending；边界例留在测试侧 |
| C02 | `expectation/sampling.py` 对完整句子识别有限的当前点击操作反馈：可见反馈、无反馈、反馈可读性；余句、条件、数值、强制实现和对象差异不自动抹去 |
| C03 | `contracts.py` 逐条合并，保留原文代表、所有依据、成员索引、支持数和理由；`roles.py` 保存 requested/returned/validated/complete 与 call_id；`engine.py` 执行前绑定组与冻结 ID |
| C04 | Pipeline 保留局部 judgment_result；partial passed 汇总为 inconclusive，partial mismatch 保留 Evidence 且扫描不完整；RunWriter 保存完整诊断，中断的 started sample 终结为 incomplete |
| C05 | 在线详情与离线报告显示采样完成情况、覆盖、局部判定及原文/未决原因；evaluation 区分完整可用判定、局部判定和覆盖未记录的旧数据 |
| C06 | `python -m alienqa.expectation.calibration` 对相同保存采样比较 v1/v2；真实复跑由现有 evaluation 入口执行，实际结果见下节 |

初版和词形扩展批次使用 `general-user-v1`，合并分别为 `sampling-merge-v2` / `sampling-merge-v2.1`；judge 为 `judgment-v2`。新回归覆盖“可查看/未成功/形式不限”等完整反馈句型及不同动作不得继承保存结果的边界。

v2.1 的真实输出仍有未覆盖的普通改写，仅扩词形不足以稳定恢复。后续生成提示升为 **general-user-v2**：模型独立决定是否提出一般结果反馈；仅当该要求没有特定结果、对象、时限、条件或实现限制时，使用统一表述“本次操作后应有可见结果反馈”。不要求每个动作都提出它；额外限制必须保留完整原文，不能强套模板。此变化规范表达，不设置页面“正确结果”，不增加模型必填分类字段、语义裁判模型、embedding 或依赖。

普通反馈不等于保证保存成功；归并结果仍选一条原始 text/basis 交给 judge。新提示与旧提示的真实结果单列，不能把 producer 改善全部算作同一合并算法的收益。

支持次数是出现次数，不是正确率。相同 basis 不能证明相同要求，不同 basis 也不直接使相同要求失败。共同要求可在未知附加要求存在时保留，但明确冲突阻断双方，未知要求不直接作并集交给 judge。

为保持最终五条边界，归并后的候选组超过五条即显式失败，保存所有候选和 `merged_limit_exceeded`；不会通过把超额候选转为未知或截取前五条绕过上限。单份采样仍先按 N02 验证，最大五条/每条 500 字符。未知语言或未覆盖句式的语义关系可能继续未决，不能称通用语义合并已解决。

## 2. 离线对照

产物：项目内 gitignored 的 `artifacts/evaluation/n03-calibration-20261002-offline.json`。输入与首轮双采样完全相同，没有新增模型调用、Expectation ID 或 Evidence，没有改写历史 run。

| 保存步骤 | v1 | v2 | 助手校准说明 |
|---|---|---|---|
| variant=1 / ST-00001 | 未决 | 一条反馈要求 | 可见结果，不限定成功或实现形式 |
| variant=2 / ST-00001 | 未决 | 一条反馈要求 | “当前条件/状态”在明确的结果反馈句型内归并 |
| variant=3 / ST-00001 | 未决 | 未决 | 附加账户条件未被有限规则解释，不吞掉条件分支 |
| variant=4 / ST-00001 | 未决 | 一条反馈要求 | 本次保存的结果或无法完成说明 |
| variant=4 / ST-00002 | 未决 | 一条反馈要求 | 仅针对当前“保存下一项”动作，可选状态/按钮/导航反馈 |

接纳案例从 0/5 变为 4/5；这仅描述保存语料的算法变化，不是新真实扫描的可用判定比例，也不是准确率。五对标签均待独立人工复核。

v2.1 对相同首轮五对仍接纳 4/5，见 `n03-calibration-20261002-offline-v21.json`；对本轮初版定向输出接纳 3/4，见 `n03-calibration-20261002-targeted-offline-v21.json`，带“若当前账户…”条件的一对仍未知。新增四对最小语料保存在 `targeted-v2-samples.json`，标签同样待独立人工复核。两份回放均为零模型调用，不能当作真实复跑通过。

## 3. 真实模型控制样例

用户已明确选择本轮 **100 次 CLI 启动硬上限**，包含修复、失败、调查和 reporter。预算记录位于 `artifacts/evaluation/n03-calibration-20261002-budget.json`；首轮历史 40 次另计，不覆盖。

| 阶段 | 计划 | 结果目录 / 状态 |
|---|---|---|
| 初版正常/缺反馈定向对照 | variants=1/2、samples=2、repeats=2，共 4 run / 4 动作，上限 36 | `n03-calibration-20261002-targeted`，已结束：20 次调用，4/4 inconclusive |
| v2.1 全部控制样例 | variants=1～4、samples=2、repeats=2，共 8 run / 10 动作 | `n03-calibration-20261002-controls`，已结束：42 次调用，1 passed / 9 inconclusive |
| 新生成提示定向复跑 | general-user-v2、variants=1/2、samples=2、repeats=2，共 4 run / 4 动作 | `n03-calibration-20261002-prompt-v2`，30 次调用：2 passed / 2 mismatch，4/4 完整可用判定 |
| 新提示合理校验 | general-user-v2、variant=3、samples=2、repeats=1，共 1 run / 1 动作 | `n03-calibration-20261002-validation-v2`，6 次调用：1 passed，合理校验未被要求保存成功 |

初版真实输出发现“可查看的结果”“未成功”“反馈形式不限”等普通改写仍未覆盖，保留为未决；v2.1 仍遇到“能够判断”“无法进行”“不要求特定形式”等未覆盖表达及条件分支。前两批消耗 62 次，全部保留原状态；新提示两批消耗 36 次，总计 **98/100 次 CLI 启动**，剩余 2 次不足以完成另一控制 run，未继续调用。

本轮全部配置合计 **17 run / 19 个已执行动作**：4 passed、2 mismatch、13 inconclusive；完整可用判定 6/19、采样完整 19/19、未决组 26 个，均为 relation_unknown。没有生成/解析/判定故障，没有通过删除早期未决改善分母。不同 prompt/merge 配置不能混算准确率；新提示的 5/5 是本组控制样例的可用结果，不外推其它页面、语义或用户。

新提示的两次正常页面显示已保存/禁用，两次缺反馈页面保存后无结果反馈并保留独立 JS exception 技术候选，两次均形成带合法 expectation_id/text/basis 的认知 Evidence。合理校验显示“请先填写邮箱，再保存设置”，被接受为操作反馈。Codex 助手已核对保存文字、原始判断与三类截图；这不等于独立用户人工验收，review.json 决定没有自动确认。

本轮 CLI 0.159.2、路由 `codex/gpt-6.1-sol`、reasoning_effort=low，六角色同一模型独立提示，供应商内部模型构建版本未知。T08 汇总 **98 个逻辑调用 / 98 次 CLI 启动，98 个响应成功**；角色调用为 gist=34、expectation=38、visual=6、judge=6、investigator=8、reporter=6。judgment-v2 已有 6 次真实调用，未发生身份/解析失败或修复调用。

已知 prompt_tokens 小计 764956、completion_tokens 小计 19653，两项未知 attempt 为 0；total_tokens 未返回，98 个均未知，不补算。98 次金额/币种均未知，不能当作零费用或免费；内部供应商 HTTP 请求数没有直接观测。

汇总与人审材料均在项目内 gitignored 的 `artifacts/evaluation/`：

- `n03-calibration-20261002-summary.json`：四批版本、全部 run/分母和 T08 账目。
- `n03-calibration-20261002-budget.json`：用户授权、阶段关闭、实际调用数及剩余 2 次。
- `n03-calibration-20261002-review-template.json`：19 个步骤的依据、未决、判断、scan/离线分析引用；独立复核字段全部 pending，评估解释不进入模型。

独立复核需分别填写预期是否合理、合并关系是否正确、判定与可见事实是否一致、产品摩擦/合理设计/模型误读分类及备注，不以输出 passed/mismatch 直接代替人工结论。新提示尚未重跑前序一致性样例；本轮未部署真实应用，N03 效果与 N06/K06/Q04 gate 不标为关闭。

旧首轮 judge 为 roles-v1，新批次为 judgment-v2，端到端差异不能全部归因于合并规则。独立人工复核、真实小应用未完成时不关闭 N06/K06/Q04。

## 4. 回归、构建与目录约束

最终工程回归：**529 passed，行覆盖率 87.98%**。包含有限关系边界、生成模板可选/限制不改写、采样故障/截断/停止、顺序稳定性、身份绑定、真实 Chromium 的部分判定/技术证据、在线页面与复制后离线 HTML，以及既有 worker 恢复、六角色账目和旧接口回归。

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  --cov=alienqa --cov-report=term-missing
.venv/bin/python -m build --no-isolation --outdir .venv/dist/n03-calibration-final
.venv/bin/python -m alienqa.expectation.calibration \
  --corpus tests/fixtures/sampling-calibration/first-samples.json \
  --output artifacts/evaluation/new-offline-comparison.json
```

sdist/wheel 构建通过；wheel 包含规则、离线评估和共享诊断模块及模板；sdist 包含校准 JSON，不包含第三方示例。未据此宣称干净安装、跨平台或真实应用兼容通过。

第三方开源示例统一搭在项目内 `examples/open-source/`，既有 `baselines/` 仍只使用项目内目录，两者均 gitignored。依赖、配置、构建及持久化测试数据留在对应项目目录，结果在项目内 `artifacts/evaluation/`。本副计划的控制样例是项目自有夹具，本轮未克隆或部署候选开源应用。

## 5. T09 提交后的新批增量

以上 98 次是历史批次。随后用户另开 100 次上限，T09 的正常/异常/合理例外/两步历史与固定 TodoMVC 真实基线、同配置复测分别用了 37/39 次，共 76 次，剩余 24 次。实际输入/失焦语料促使有限整句规则升为 `sampling-merge-v2.2`，提示仍为 general-user-v2、判断仍为 judgment-v2；普通单行文本框 Enter 探索已补齐。

原保存语料的两对输入/失焦近义已离线合并；真实复测输入 passed，失焦的新样式/条件仍未决，Enter 创建待办但双采样为空，历史第二步的额外当前结果/旧 Saved 条件仍未决。未删除旧分母，没有把局部判定当作应用验收。远程默认回归和干净安装通过，独立人审、费用和效果 gate 继续开放。

全部结果、原始快照、逐步待审材料与下一轮预期生成/历史归因/调查元数据优先级见 [T09 真实基线记录](t09-real-baseline-results.md)。未来优先改进生成契约，不能无限扩展近义正则来提高 passed 数。

## 6. 预期生成契约 v3

新增可选点击/输入/失焦标准表述、动作前白名单按键参数及显式弃权理由；提示为 general-user-v3，merge v2.2 / judgment-v2 不变。样式、时限、否定和历史限制保持原文；旧空响应仍兼容并标未记录原因，空采样不补票或冒充通过。在线与离线分析保留弃权原因，合并失败与采样失败分开。

在原新批剩余 24 次上限内定向执行两步历史及三步固定 TodoMVC，实际用了 22 次：4 passed、1 inconclusive、全部采样完整、关系未决 0；输入/失焦自选标准表述，Enter 已完整传入但因事前依据不足明确弃权，动作仍创建待办。当前新批累计 **98/100 次、剩余 2 次**；旧批同为 98 次但独立记账。正常/异常/合理例外未在 v3 另行真实复跑，独立人审、未知费用和效果 gate 继续开放。

实现、冻结输入、真实结果、完整账目和限制见 [生成契约记录](n03-generation-contract.md)。不同提示的分母仍分别保留；未将历史 v2 的条件句自动转换成模板。

## 7. 定位修订后的工程接线

当前 `general-user-v4 / sampling-merge-v3 / judgment-v3`：合法采样并集交付、关系未知/互斥仅备注、合并组超过 5 条仍检查、失败采样不否决已验证采样；混合落差与未知保留全部已报告证据。用户是否采信与独立人审不影响 release_ready。
旧算法仅留在离线对照，用 v1/v2.2/current 区分结果，不改旧采样标注或历史运行。本次没有新增真实模型调用；新批仍 98/100、余 2 次。工程回归结果见生成契约的当前版本记录。

## 8. v4 三款开源应用真实基线

另开授权 200 次上限，在 TodoMVC、IT-Tools、Memos 各执行自主/定向四步，使用 **105/200 次**；与上述两个 98 次批分别记账。模型路由 `codex/gpt-6.1-sol`、low，契约 `general-user-v4 / sampling-merge-v3 / judgment-v3`。全部响应成功，角色与 attempt 对齐，105 次费用未知。

97/97 来源成员保留，81/81 合并要求进入步骤记录，六份 HTML 存在。24 步为 15 passed、8 inconclusive、1 action_failed，13 条要求无法判断，模型没有提出 mismatch/Evidence。每次扫描均因四步限额 partial；Memos 定向扫描还出现单次点击被弹层阻挡，不能描述成应用全流程通过。TodoMVC 定向初始化配方的错误已另记更正，原输入未覆盖。

实际结果、三个浏览器机制验证、801 项最新工程回归与下一轮复测门槛见[开源应用记录](open-source-applications.md)。优先增强弹层/作用域探索、无文案目标身份、语义输入及焦点观察，继续保留全部主观要求，不将人工采信或误报控制引入验收。

## 9. 弹层与观察修复后的增量

已实施[弹层、目标身份、JSON 分支与焦点观察修复](popup-exploration-fix.md)。Memos 定向八步全部执行，进入菜单并走到 Save；两条 Upload 认知落差均进入 Evidence 与报告，Save 的两条权限要求仍未知。TodoMVC 四步均完成并可判定；IT-Tools 首次因常驻 role=menu 误判而零动作，修复后合法/非法 JSON 的四步真实复测通过。原失败及分母保留。

本轮追加 76 次，原批累计 **181/200、剩余 19**；角色、原始来源、落差保存与 HTML 对账完整，金额未知。最终默认工程回归 **817 项通过、覆盖率 88.11%**，另有 24 条锁框架路径通过；发行资产核对通过。当前未取得远程 CI 状态，不以旧 CI 代替。完整源码冻结、账目、发现及限制见上述实施记录。
