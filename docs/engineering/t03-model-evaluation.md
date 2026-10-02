# T03 真实模型验收方法

状态（2026-10-02）：[首轮结果](n06-first-results.md)保留双采样 5/5 未决及单采样 1 passed/1 字段 failed；[N03 校准增量](n03-calibration-results.md)已取得新提示双采样核心配对 4/4 可用、合理校验 1/1 passed。本轮 98 次调用，旧未决未删除；新提示历史、独立人审和真实小应用仍待验，N06 开放。对应 [T03 N06](mvp-planbooks/technical/03-context-expectation-judgment.md#n06认知样例与模块关闭)。
本文件的参考解释仅在评估侧使用，不拼入被测页面、预期输入或判定提示词。

## 1. 控制样例

页面资产：[cognition-app](../../tests/fixtures/cognition-app/index.html)。每个页面包含只读字段和一个初始禁用按钮；探索不应强行点击它们。

| URL 参数 | 真实界面行为 | 人工核对重点 |
|---|---|---|
| `variant=1` | 保存按钮文字改为“已保存”，随后禁用 | 状态变化属于可见反馈；不应因没有 toast 固定判落差 |
| `variant=2` | 点击不改变界面，产生 JS exception | 技术候选与可见认知判断分开；合理反馈预期可以有落差，不从 JS 日志替代认知依据 |
| `variant=3` | 显示“请先填写邮箱，再保存设置” | 合理校验是操作结果；不能要求必定保存成功 |
| `variant=4` | 第一项保存后出现下一项，第二项也显示已保存 | 第二步可引用 ST-00001 的可见结果；不能引用未来步骤或调查解释 |

本机启动静态服务：

```bash
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory tests/fixtures
```

使用已配置模型逐项执行，替换参数、动作预算和独立结果目录；variant=4 使用两步，其余一步：

```bash
.venv/bin/python -m alienqa --config config/config.yaml \
  --url 'http://127.0.0.1:8765/cognition-app/index.html?variant=1' \
  --samples 2 --max-actions 1 --browser chromium \
  --artifacts-dir artifacts/evaluation/variant-1-run-1
```

以上是 LiteLLM 通道的执行方法；现已增加 [官方 Codex CLI 登录接口](codex-login-provider.md)与有界批量入口：

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m alienqa.evaluation \
  --config config/codex.yaml --fixtures tests/fixtures \
  --output artifacts/evaluation/new-n06-batch --max-calls 40 --repeats 1 --samples 2
```

可用 `--variants 1 2` 做明确标记的定向对照；修改 samples 的结果单列，不覆盖原配置。重复时使用新目录；先冻结模型配置、prompt_version 和 merge_version，保留每次扫描的完整产物。不能自动采信所有条目来证明模型正确。`judgment-v2` 已有 6 次真实调用；新提示核心配对 4/4 与合理校验 1/1 的结果见 [N03 校准记录](n03-calibration-results.md)，旧版本结果仍单列，不能替代当前版本验收。

## 2. 真实小应用与记录

选一款独立开发者可运行的小应用，记录应用/构建版本、URL、登录态前提、预算和已知交互样例。至少包含明确反馈、合理校验、陌生术语、未解释禁用和缺反馈的观察；不要把答案放进范围指令或 README 供预期模型读取。
观察前先写评估侧的解释与可接受等价结果，随后运行、复核模型输出；“按设计仍有认知摩擦”与“模型误读可见证据”分别标注。

每条记录保留以下信息，未知值明确写未知：

| 字段 | 来源 |
|---|---|
| 应用/构建、输入模式、URL/条件、预算、终止原因 | 被测版本与 run 元数据 |
| 实际模型/配置、prompt_version、采样次数 | manifest 与 T08 明细；Codex 为 CLI 启动计量，内部供应商请求数未直接观测 |
| run/step/action/expectation_id、输入引用、basis | `scan.json` 步骤输入与预期 |
| 前后截图、原始文字、视觉解释、judge 原文与四态 | 步骤图片、visible_result、visual_observation、judgment_outputs |
| 未决要求、生成/解析/执行失败、未覆盖内容 | expectation_generation、步骤状态与 diagnostics |
| 人工决定、备注、模型误读/可接受认知摩擦 | T06 本地审核与独立评估记录；助手复核不能冒充独立用户验收 |
| 调用数、失败/fallback、token、费用与未知原因 | T08 attempt/usage-summary；区分 CLI 启动与 provider_request，缺失费用不能填 0 |

同一控制样例重复观察，用独立 run 记录波动。先核对可用检查比例与未决原因，再讨论有用线索和误读；失败、停止或未完成扫描保留在总体样本里。不能只汇总成功 mismatch 或把 by-design 当成模型误判。

## 3. 关闭条件

N01～N05 的确定性契约回归通过，控制样例及至少一款真实小应用有可复核模型结果，误读/认知摩擦/未完成明确分类，调用成本或未知费用原因可追溯。
重点检查严格的采样分歧规则是否因同义措辞造成过多 inconclusive；若调整规则，更新 prompt/契约版本并重跑配对样例，不能删除分歧原文。
具体执行见 [N03 采样合并校准副 Planbook](mvp-planbooks/technical/03a-sampling-merge-calibration.md)：先对同一保存输出离线比较合并版本，再固定 judgment-v2 做双采样配对复跑；分别披露部分检查与完整可用判定，不能把 judge 修复效果归因于合并规则。
当前控制样例已提供真实模型材料，也暴露采样合并和 judge 输出形状的具体缺口。N03 已接入版本化有限规则、来源/完成度和部分检查展示，judge 为 judgment-v2；新真实批次与初版未决结果均见 [N03 校准记录](n03-calibration-results.md)。独立人审与真实小应用未完成时，N06/J06/V03 不标为通过。后续候选与项目内 gitignored 的接入约束见 [开源项目建议](n06-open-source-candidates.md)。
