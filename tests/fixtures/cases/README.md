# T09 成对验收样例

`manifest.json` 是评估侧资产，`public/` 是产品可以看到的页面。六类交互各有正常、异常、合理例外，另有一条两步历史，共 19 个场景。版本、初始状态、可达动作、断言和重置配方均在 manifest 中。

每次执行使用新浏览器上下文，从原入口重新开始；数据只在该上下文内，不需要账号、数据库或外部 API。受控服务仅实现 200/401/422/500 四种响应。例外场景包括字段校验、登录要求、取消、空结果和返回；这些结果不预设为缺陷。

`labels`、参考断言、故障名称和 scripted actions 仅供评估者使用。生产管线只收到入口 URL、无答案的范围文本和动作预算，运行 ID 使用不携带正常/异常含义的编号。服务仅开放 `public/`，不会提供 manifest；输入审计回归检查私有标注未进入角色请求。

```sh
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  tests/test_t09_acceptance.py tests/test_t09_browser.py tests/test_t09_pipeline_browser.py
```

浏览器回归执行全部场景两次，并对异常窗口执行独立回放。生产管线回归使用本项目自编的协议替身，检验提交、计量和分析报告；不证明真实模型效果。

真实模型验收需单独显式执行，下例最多启动 40 次供应商请求/CLI，包含失败、修复、fallback、调查和报告，不是费用上限：

```sh
.venv/bin/python -m alienqa.evaluation --config config/codex.yaml \
  --manifest tests/fixtures/cases/manifest.json \
  --cases save-normal save-abnormal save-exception history-normal \
  --samples 2 --repeats 1 --max-calls 40 \
  --inference-kind real --output artifacts/evaluation/t09-model-new
```

未启动、失败和未决记录保留在分母。`review-template.json` 初始全部 pending；独立人审后填写审核人、独立性、主动审阅分钟、依据/合并/判定、有效发现、无依据投诉数、分类和理由。评估分类与产品 Decision 分开：`useful_finding`、`reasonable_design`、`model_misread`、`inconclusive` 等需在理由中说明技术问题或认知摩擦。按设计不自动计为误报。不要让模型代填独立人审或根据固定答案自动确认发现。

可选真实小应用通过 `--real-app URL --app-version COMMIT --app-reset RECIPE --app-actions N` 追加到同一批共享预算；运行器记录重置配方，但不执行任意重置命令。提供者负责在运行前按配方恢复服务器数据，每次扫描只自动创建新浏览器上下文。

复用框架资产见 [framework-mechanisms](../framework-mechanisms/README.md)。外部 TodoMVC 的固定版本准备见 [T09 实施记录](../../../docs/engineering/t09-implementation.md)，克隆、依赖、缓存和产物只在项目内忽略目录。
