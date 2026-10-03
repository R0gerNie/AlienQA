# AlienQA

**帮你发现产品里那些只有内部人才觉得理所当然的地方。**

AlienQA 模拟一个懂相关行业、但第一次使用你产品的外部用户。它在浏览器中探索页面，带着事前预期执行操作，把实际所见与预期之间的落差保存成可查看、可回放的发现。

面向独立开发者，用于 QA、UX 和产品体验分析。目前是实验性的本机工具，支持扫描已运行的 Web 应用，生成可离线阅读的 HTML 报告。

## 它会帮你看什么

- 点击保存后没有反馈，用户不知道是否成功。
- 一个看起来能输入的控件，实际没有改变页面状态。
- 上一步看到的结果，和下一步呈现的信息不一致。
- 操作过程中出现 JavaScript 异常、HTTP 5xx 等技术信号。
- 功能按内部设计运行，但外部用户仍可能困惑的地方。

这些是它会尝试发现的问题类型，具体结果取决于探索路径和模型。即使团队知道某个行为“按设计如此”，这个认知落差仍值得出现在报告中。

## “俺寻思之力”是什么

外部用户会带着通用惯例和行业知识理解产品，却不知道团队的内部答案。AlienQA 先根据操作前可见的信息形成预期，再观察操作结果；产品源码和内部说明用于定位或后续调查，不提前教授给预期模型。

默认两次预期采样取并集：**只要被提出一次，就值得检查。** 重复要求保留来源后去重，分歧也保留。所有产生的发现进入分析报告，由你选择是否采信；人工审核和误报率不作为工具的验收门槛。工程优先减少漏探索、漏处理和证据丢失，有限预算下无法保证发现所有问题。

## LLM 原生使用方式

**本项目为 LLM 原生，支持 LLM-driven，全程由 LLM 部署并使用。** 欢迎各位用户把本仓库交给具备终端和浏览器操作能力的 LLM 编程助手，让它阅读文档、部署 AlienQA、配置模型通道、执行扫描并解读报告。你提供被测应用的 URL、希望探索的功能和调用预算，即可尝试这条使用路径。

可以从这样的指令开始：

> 阅读此仓库的 README，部署并运行 AlienQA。使用我提供的模型通道，测试应用 URL：……，重点探索：……，调用预算：……。完成后打开分析报告，说明发现的认知落差、探索范围和未完成的部分。

下面的快速开始同时供用户和 LLM 助手参考；需要登录模型账号或提供凭据时，由用户在本机完成。

## 快速开始

需要 Python 3.11+、可用的大模型通道，以及一个已运行的 Web 应用。在仓库目录执行以下命令（macOS / Linux）：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e . -c requirements-dev.lock
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/browsers"
python -m playwright install chromium
python -m alienqa --ui
```

打开 `http://127.0.0.1:5000`：

1. 在设置页配置文本和视觉模型。默认配置使用 DeepSeek 与通义千问，也可通过 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` 提供密钥；角色配置见 [config/config.yaml](config/config.yaml)。
2. 填入应用 URL，例如 `http://localhost:3000`。
3. 在高级输入中将浏览器选为 **Playwright Chromium**，与上面安装的浏览器一致。默认 Chrome 选项需要本机另有 Chrome。
4. 设置动作数和时间预算，开始扫描，然后查看发现和分析报告。

工具会实际填写表单、点击和提交，首次体验适合使用本地应用或可重置的测试数据。React、Vue、Next.js 等源码项目请先启动自己的开发服务器，再填入 URL；工具不会默认替你安装前端依赖。

### 使用现有 Codex 登录

也可复用本机官方 Codex CLI 已有的 ChatGPT 登录。安装 CLI 并完成 `codex login` 后，改用以下启动命令：

```bash
python -m alienqa --config config/codex.yaml --ui
```

示例配置为各模型角色提供独立提示词和图片输入。请确保配置中的模型对你的账号可用；调用消耗该账号额度，金额可能无法取得。接口和支持差异见[Codex 登录通道说明](docs/engineering/codex-login-provider.md)。

### 使用命令行

命令行请通过环境变量提供模型密钥；使用其他角色配置时加上 `--config PATH`。控制台保存的本地设置不会自动成为命令行配置。直接扫描并生成分析报告：

```bash
python -m alienqa --url http://localhost:3000 --browser chromium --max-actions 10 --artifacts-dir artifacts/my-run
```

报告保存在 `artifacts/my-run/analysis.html`。每次新扫描使用新的目录；无需先审核即可阅读报告。

需要登录的应用，可以先手动登录并保存会话，再扫描：

```bash
python -m alienqa --login https://example.com --session-out config/session.json
python -m alienqa --url https://example.com --browser chromium --storage-state config/session.json --artifacts-dir artifacts/private-run
```

已有结果可以重新打开，添加决定和备注，不重新扫描：

```bash
python -m alienqa --review-run artifacts/my-run
```

更多参数见 `python -m alienqa --help`；源码输入、启动命令和重放说明见[开发指南](docs/engineering/developer-guide.md)。

## 怎么读结果

分析报告保留技术异常、模型提出的认知落差，以及停止、失败或无法判断的说明。它也提供动作、截图和预期来源，方便你理解“这个外部用户为什么觉得不对劲”。零发现只代表这次探索没有产生发现。

你可以为每个发现记录确认、不采信、按设计或暂跳过，以及备注。**按设计的发现仍保留在分析报告中。** 如果主动选择 `confirmed` 报告，则按采信决定筛选；这不是默认交付流程。

运行目录保存原始信号、截图、模型调用账目和回放包；HTML 内嵌截图，复制后可以离线阅读。会话和回放包可能携带登录状态，应留在本机；报告仍可能包含业务内容。调用账目会区分已知用量与未知费用，动作或时间预算不是费用硬上限。

## 当前支持范围

主要面向可访问的 Web 页面和主页面 DOM 交互，支持 URL 输入、登录态、部分源码辅助与静态产物。已有 React/Vite、Vue/Vite、Next.js 的固定机制样例验证；这不代表所有框架版本或业务流程都已覆盖。

复杂 iframe、Shadow DOM、多步骤业务探索等仍有限制。当前采样并集契约已完成工程回归，并在 TodoMVC、IT-Tools、Memos 上执行了六次有界真实模型扫描，暴露了菜单交互、输入选择和观察缺口。运行方法与结果见[开源应用测试](docs/engineering/open-source-applications.md)，支持范围见[兼容和发布状态](docs/engineering/compatibility-and-release.md)。

## 文档与许可

- [开发指南](docs/engineering/developer-guide.md)：架构、测试、配置与工程文档入口。
- [当前项目分析](docs/engineering/project-status-2026-10-02.md)：已完成什么、证据边界和下一阶段重点。
- [MVP 工程计划](docs/engineering/mvp-planbooks/README.md)：功能计划与技术子计划。

本项目采用 [MIT License](LICENSE)。第三方依赖与示例项目遵循各自的许可证。
