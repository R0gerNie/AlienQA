# N03 最小采样语料

`first-samples.json` 是首轮本机 `n06-codex-20261002-second` 的五个步骤、各两份采样，仅保留自建控制页面的预期和 basis 文本，不包含凭据、完整模型请求、宿主配置或第三方源码。

每条 annotation 由 Codex 助手拟定，独立人工复核为 pending。四对反馈表述暂按有限规则支持的同义关系标注；variant=3 带额外账户条件，标 relation_unknown。标签、expected_accepted 和 expected_coverage 仅供测试/离线评估，绝不拼入产品模型输入。

`targeted-v2-samples.json` 保存本轮初版 v2 真实定向复跑的四对最小采样，用于 v2.1 词形扩展回归；三个反馈改写按等价候选标注，带“若当前账户…”条件的一对仍未知。没有用校准后的代码改写 v2 批次结果。

构造边界例见 `tests/test_sampling_calibration.py`，覆盖限定增强、否定、条件、对象、缺席、冲突、独立要求、不同依据、采样故障、条数上限及顺序稳定性。

第三方开源示例统一准备到项目内 gitignored 的 `examples/open-source/`，既有 `baselines/` 同样只在项目内使用；不要放到 `/tmp`、项目兄弟目录或全局工作目录。这份脱敏控制语料属于项目自有测试资产，需要进入仓库。
