# 使用现有 Codex / ChatGPT 登录执行六个角色

日期：2026-10-02。接口：`alienqa/llm/codex.py`；示例配置：[config/codex.yaml](../../config/codex.yaml)。本机核对版本为 Codex CLI 0.159.2，`codex login status` 显示 ChatGPT 登录。

## 使用

先安装官方 Codex CLI 并完成 `codex login`。接口只使用 CLI 管理的既有登录，不读取、复制或导出 `auth.json`、浏览器 cookie 或访问令牌。可用模型取决于账户访问权限，成功推理才说明所选模型此次可用。[官方认证说明](https://learn.chatgpt.com/docs/auth)区分 ChatGPT 登录与 API key 登录。

```bash
codex login status
python -m alienqa --config config/codex.yaml --ui
python -m alienqa --config config/codex.yaml --url http://localhost:3000 \
  --browser chromium --artifacts-dir artifacts/my-codex-run
```

`codex/<model>` 路由选择本地 CLI，其他路由继续使用 LiteLLM。六个角色各自保留提示词和记录，可使用同一模型，也可分别填写账号可用模型；示例使用本机原配置选择的 `gpt-6.1-sol`。这项接口提供 Codex 的登录通道，其他供应商仍使用自己的授权方式。

设置页对 codex 显示登录说明，不要求或保存 API key。适配器验证 ChatGPT 登录，子进程不继承 API key，且显式限制为 ChatGPT 认证；不会因登录失败静默切换到付费 API 账户。用户显式配置的跨通道 fallback 仍可运行，并按实际通道分别入账。

## 输入与执行边界

每次调用使用新的临时工作目录、`--ephemeral`、`--ignore-user-config` 和 read-only sandbox；保留原 `CODEX_HOME` 供 CLI 使用登录，不创建新的认证目录。角色提示通过 stdin 输入；视觉消息转换为本地临时图像附件并标明顺序，目录在完成/故障后清理。外部图像 URL 不自动下载。

通过 `model_instructions_file` 替换默认编程指令，禁用 shell、浏览器、插件、hooks、memory、多 agent 与 web search；AGENTS 文档预算为零。宿主 skill 自动发现通过当前 CLI 的实验开关关闭，此支持边界随 CLI 版本复核。模型只应消费当前角色输入；返回工具 item 或额外 turn 均视为适配失败。[官方非交互说明](https://learn.chatgpt.com/docs/non-interactive-mode)支持 JSONL、临时会话与图片附件；[配置说明](https://learn.chatgpt.com/docs/config-file/config-reference)列出相关开关。

当前 CLI 不允许覆盖内置 provider ID；接口使用独立 provider 名、`requires_openai_auth=true` 和 Responses 协议，由 CLI 解析认证后的默认端点，不硬编码网页会话 API。请求/流重试配置为零，外部 fallback 仍由 AlienQA 逐次执行。超时或中断会回收整个子进程组；供应商是否完成和结算仍可能未知。

Codex CLI 不应用角色的 temperature / max_tokens；账目保留 requested 值，实际值为 null，记录实际 `reasoning_effort` 和 `alienqa-codex-v1` harness。不能用这个通道宣称完成原 DeepSeek/Qwen 温度配置的对比实验。

## 响应与计量

只接受成功终态和非空最终 agent_message。启动阶段的非阻塞诊断 item 单独保存，不能误判为模型调用工具；推理期间 error、turn.failed、非法 JSONL、工具 item、空回复和缺终态均明确失败。

CLI 返回的 input_tokens/output_tokens 对应保存到 prompt_tokens/completion_tokens，原始计数含 cached_input_tokens 另保留；未返回的总 token 不补算。启动诊断保存为 usage 中的 codex_startup_warnings，普通 JSON 解析结果仍由角色消费者单独记录。

`attempt_units.cli_invocation` 是 CLI 启动次数，不是直接观测到的供应商 HTTP 请求数；普通 LiteLLM 记录继续标为 provider_request。当前 CLI 没有可信金额/币种返回，费用始终未知。消耗现有订阅额度不等于免费，也不等于按 API token 单价结算。

## 真实样本入口

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers python -m alienqa.evaluation \
  --config config/codex.yaml --fixtures tests/fixtures \
  --output artifacts/evaluation/new-n06-run --max-calls 40 --repeats 1 --samples 2
```

运行器启动本地控制样例服务，并在所有 run 间共享调用上限。manifest 先冻结配置、提示版本、样例与评估侧参考解释；参考解释不送模型。每次请求启动前预留预算，达到上限不再发请求。失败、未决、停止和未执行样本全部保留；普通 pytest 只用替身测试这个入口，不消耗真实模型额度。

结果包括各 run 的 scan/raw/图片/调用明细/analysis，以及根目录的 manifest.json 和 evaluation.json。开发者决定保持 pending，不自动确认发现，也不自动给出准确率。控制样例、真实应用、独立人工复核是不同 gate，真实结果见 [N06 验收方法](t03-model-evaluation.md)。

本轮最终全量回归 **477 项通过，覆盖率 87.71%**，包括真实本地 Chromium/HTTP/worker，以及默认无真实模型调用的适配器、预算、启动诊断、图像、跨通道 fallback、UI 登录说明和输出形状契约测试。真实登录的 40 次调用结果单列于 [首轮结果](n06-first-results.md)，不把测试数量当作模型效果指标。

后续 [N03 校准](n03-calibration-results.md)复用了此通道：新增 98/100 次 CLI 启动，六角色响应均成功；general-user-v2 核心配对 4/4 可用、合理校验 1/1 passed，费用仍未知，独立复核和真实应用 gate 保持开放。该增量工程回归为 529 项/87.98%，原 477 项与 40 次记录保留为登录接口首轮基线。

sdist/wheel 构建与内容检查通过，计量/登录适配模块、验收运行器、UI 模板和 `codex.yaml` 示例进入 wheel；相关测试与文档进入 sdist。仓库外干净安装、Windows 与远程 CI 尚未执行。
