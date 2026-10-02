# N03 采样合并校准实施与验收记录

日期：2026-10-02。对应 [N03 副 Planbook](mvp-planbooks/technical/03a-sampling-merge-calibration.md)。状态：C01～C05 工程范围已实现并回归；C06 的离线对照、真实复跑及复核材料已交付。新提示的核心配对和合理校验取得可用结果；独立人工复核、新提示的前序一致性复跑与真实应用 gate 保持开放。

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
