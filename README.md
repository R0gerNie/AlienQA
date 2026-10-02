# AlienQA

面向独立开发者的网页 QA 与一般用户认知分析工具。让具备通用网页使用经验、未接受本产品培训的 LLM 探索界面，比较事前预期与实际所见，保存可核对的异常线索。

当前已实现本地扫描、URL 黑盒输入、源码与运行地址结合、登录态采集、表单交互、动作级判断、证据/重放包、人工审核和独立 HTML 报告。效果仍需真实应用基准验证；模块实现和本地回归通过不等于模型判断准确率已经达标。

当前功能 MVP 计划见 [工程 Planbook 组](docs/engineering/mvp-planbooks/README.md)。T04 已实现独立技术采证、模型前保存与停止后的前缀恢复；T03 已接入可见输入隔离、可核对的预期依据、近期历史与步骤绑定。T06 已接通四种开发者决定及备注、保留所有发现的 analysis 和离线 HTML；confirmed 保持人工确认门槛。T08 已接通六角色请求账目、用量汇总和未知费用处理；真实模型效果及供应商费用格式仍待验收。T02 已补齐主页面定位、受控表单、动态控件、异步观察和尝试轨迹；锁版本 React/Vue/Next 机制路径通过工程验收，未验证区域如实保留。T05 已补齐独立目标窗口、具体技术事实再现、保守聚类及有界调查；停止/失败保留前提与步骤，回放不替代人工决定。T07 已统一 CLI/UI 输入、预算、应用选择、终态和历史计数；真实 worker 停止保留前缀，`--review-run` 可重开已保存审核，安装包在独立目录跑通本机完整路径。T01 已统一所选应用、源码路径与启动 cwd，补充 React/Vue 字面量路由、Next root/src 与动态模板、静态产物 preflight 和显式子路径/history 回放；核心框架的结构与实际机制证据分别记录，复杂变体仍列限制。岗位/行业画像和团队功能后置。

## 安装

需要 Python 3.11+。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -c requirements-dev.lock
python -m playwright install chromium
```

`requirements-dev.lock` 固定当前本地验证的开发依赖版本。Linux CI 配置了 Chromium 系统依赖、回归/覆盖率、构建和干净安装 job；本轮远程执行结果尚未取得，支持组合见 [兼容与发布状态](docs/engineering/compatibility-and-release.md)。

在环境变量中设置模型密钥，如 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`；也可在本机控制台设置页保存。六种模型角色、温度与回退配置见 [config/config.yaml](config/config.yaml)。

也可使用本机官方 Codex CLI 的既有 ChatGPT 登录：完成 `codex login` 后，运行 `python -m alienqa --config config/codex.yaml --ui`。六角色使用独立提示词和 `codex/<model>` 路由，视觉角色支持图片附件；实际消耗订阅额度，费用与供应商内部请求数未知。该通道不应用 temperature/max_tokens，实际 reasoning_effort 另存，详见 [登录接口](docs/engineering/codex-login-provider.md)。

## 使用

启动本机控制台：

```bash
python -m alienqa --ui
```

默认地址 `http://127.0.0.1:5000`。支持 URL、登录态文件、源码目录及已运行的开发服务器地址；静态 HTML / 已构建产物可由工具启动本地服务器。React/Vue/Next.js 源码应提供运行 URL，控制台不会将未经构建的源码当作静态页面运行。扫描可停止或超时回收，失败及无法判断项显示为不完整结果。

直接扫描一个 URL，保存发现后打开审核页面：

```bash
python -m alienqa --url http://localhost:3000 --artifacts-dir artifacts/my-run --review
```

结合源码与开发服务器：

```bash
python -m alienqa --project-root /path/to/frontend --url http://localhost:5173 --review
```

也可显式启动应用；命令按参数执行，不经过 shell，退出时回收启动的进程组：

```bash
python -m alienqa --project-root /path/to/frontend --url http://localhost:5173 --start-command 'npm run dev' --review
```

多个前端应用时，通过 `--app apps/web` 选择项目内应用目录；源码读取和启动命令 cwd 都使用该目录。`--unit`、`--instructions` 只用于定位范围，找不到范围会明确停止，不进入预期模型。模型配置、URL/session、浏览器与输出在本地检查；不会默认调用付费模型探测。

已有扫描可重开审核，保留决定和备注而不重新扫描；已有运行目录不会被下一次扫描覆盖：

```bash
python -m alienqa --review-run artifacts/my-run
```

采集并复用登录态：

```bash
python -m alienqa --login https://example.com --session-out config/session.json
python -m alienqa --url https://example.com --storage-state config/session.json --review
```

省略 `--review` 时默认生成 `analysis.html`，待审项也保留：结果包括 `scan.json`、`evidences.json`、`investigations.json`、`review.json`、截图/技术信号和 `replay/<evidence-id>.json`。默认不自动采信证据；`--auto-confirm` 是显式演示选项，备注标明未经人工审核。

```bash
python -m alienqa --url http://localhost:3000 --artifacts-dir artifacts/my-run
python -m alienqa --url http://localhost:3000 --artifacts-dir artifacts/demo --report-mode confirmed --auto-confirm
```

审核页面支持确认问题、不采信、按设计和暂跳过，以及备注；待审与已处理状态分开显示。`analysis` 展示全部五态及原始发现，按设计也保留认知落差；`confirmed` 仅展示确认项，并要求没有待审、按设计或跳过项。底层 `ReportBuilder.build` 和旧无参数报告 URL 的默认仍为 confirmed，CLI 默认为 analysis。

标准目录按模式保存 `analysis.html` / `report.html`；显式 `--output` 覆盖所选模式的路径。控制台和独立审核都提供查看、生成及下载入口。只有扫描终态可导出；重审、备注或报告消费的数据更新会失效两种文件。导出的截图内嵌于 HTML，可复制后离线阅读；缺失文件和不完整扫描如实显示，零发现不会被写成测试全部通过。

每次扫描使用新的结果目录。`scan.json` 是增量提交的权威快照，引用 `raw/` 下的原始事件；`evidence.db` 按扫描隔离。入口和动作的 JS 异常/HTTP 5xx 候选在模型解释前保存；模型失败、取消或超时保留最后提交的前缀，并标明未完成阶段。汇总 JSON 是导出视图，不能单独证明扫描完整。

LLM 明细保存在 `llm/calls/`，实际配置保存在 `llm/config.json`，汇总为 `usage-summary.json`；运行详情和 HTML 报告均显示调用、实际请求、解析状态、已知 token 与未知项。采样、JSON 修复及 fallback 分别入账，可选 reporter 归属原运行。费用仅记录明确返回的金额/币种/来源，缺失时为未知，不把失败或停止的请求当作免费，也不把多币种相加。当前没有费用硬上限；动作/时间预算不保证供应商停止计费。旧扫描缺账目与坏账目会明确显示，已有证据和分析正文仍可交付。

`llm/private/` 保存经凭据清理与裁剪的输入/输出文本，图像只保留省略标记；公开摘要和 HTML 不复制完整模型请求。私有文本仍可能包含产品信息，分享报告时只需复制 HTML。

预期只消费已保存的当前可见文字/控件与近期已完成步骤的可见结果；源码简介和范围指令用于定位，不进入认知模型。每步最多 5 条预期，引用当前文案、通用惯例或前序观察。采样按逐条要求合并：有限规则支持的操作反馈同义表达可去重，未提及不等于反对；冲突和无法解释的关系保留为未决，不以多数票决定正确答案。规则不覆盖全部自然语言。无有效预期时继续技术 QA；有效要求与未决并存时显示部分检查，局部通过不能代表完整通过。采样次数可用 `--samples` 调整，原文、依据、支持次数、合并版本与身份关联保存在步骤快照中，在线详情和离线报告可复核。

重放证据（文件名以实际生成的证据 ID 为准）：

```bash
python -m alienqa --replay artifacts/my-run/replay/EV-0001.json
```

重放恢复初始 URL、会话与成功动作历史；本地静态项目会在原端口重新启动服务。原目录必须仍可访问，原端口被占用时返回失败。回放一致性是辅助证据，疑似问题语义仍需人工确认。回放包包含本地会话状态，独立 HTML 报告不包含该凭据。

CLI 退出码：`0` 采集完成，`1` 执行失败，`2` 输入错误/扫描不完整/重放未确认，`130` Ctrl+C 取消并保留已提交结果。动作数和时间可用 `--max-actions`、`--max-seconds` 限制。CLI 时间预算在动作边界检查，模型请求另有配置超时；控制台另有默认 600 秒整任务 watchdog。控制台默认保存到当前目录的 `runs/`，本地设置保存在 `config.local.yaml`。CLI 可用 `--artifacts-dir runs/my-run` 纳入同一历史。停止不保证供应商停止计费；会话和回放包应在本机保管，HTML 不包含会话凭据。删除会话文件后还需清理对应 run 的回放副本。

## 验证

```bash
python -m pytest --cov=alienqa --cov-report=term-missing
python -m build
```

默认测试使用自包含 fixture、真实本地浏览器和模拟模型响应，无需外部项目或付费模型。外部仓库基线单独运行：

```bash
python -m pytest --run-baselines -m baseline
```

该套件要求事先将对应仓库准备到 `baselines/`；准备方式见 [测试基线文档](docs/engineering/baselines.md)。
第三方开源示例只能部署在本项目内 gitignored 的 `examples/open-source/` 或既有 `baselines/`，依赖、构建和测试数据也留在对应项目目录；结果写入 gitignored 的 `artifacts/evaluation/`。

真实模型控制样例可显式运行 `python -m alienqa.evaluation --config config/codex.yaml --output artifacts/evaluation/new-run --max-calls 40`；调用上限跨样例共享，失败/未决样本保留，默认测试不会执行真实调用。[N06 首轮结果](docs/engineering/n06-first-results.md)已暴露双采样同义措辞合并与旧 judge 输出形状问题；新 judgment-v2 仅完成工程修正，真实小应用与独立人审仍待验收。

T09 新增 19 个正常/异常/合理例外与历史场景，实际浏览器回归、生产管线替身、独立审核模板和保留分母的统计；框架资产直接复用 T01/T02。使用 `--manifest tests/fixtures/cases/manifest.json --cases ...` 选择有界评估，真实小应用需明确版本和重置配方；协议替身运行须声明 `--inference-kind substitute`。这组资产和 TodoMVC 浏览器基线不代替真实模型与人审，详见 [样例说明](tests/fixtures/cases/README.md)。

发行安装验收使用 `scripts/verify_t09_distribution.py --wheel PATH --sdist PATH`：两套禁用系统依赖的独立 venv、重新安装依赖、项目内独立浏览器缓存及完整 CLI/UI/回放/审核/离线 HTML 路径。外部源码与安装产物留在项目内忽略目录，失败日志保留；复跑命令见 [T09 记录](docs/engineering/t09-implementation.md)。当前版本为实验性工具，模型效果、人审与用户试用 gate 仍开放。

## 规划与工程文档

- [下一阶段主要工程计划](docs/engineering/next-stage-plan.md)
- [功能 MVP 工程 Planbook 组](docs/engineering/mvp-planbooks/README.md)
- [模块级技术实施与框架兼容计划](docs/engineering/mvp-planbooks/technical/README.md)
- [T09 分层验收与新环境安装记录](docs/engineering/t09-implementation.md)
- [兼容证据与实验性发布状态](docs/engineering/compatibility-and-release.md)
- [T01 实施与框架/部署兼容矩阵](docs/engineering/t01-implementation.md)
- [T07 实施与本机安装包验收记录](docs/engineering/t07-implementation.md)
- [T05 实施与验证记录](docs/engineering/t05-implementation.md)
- [T02 实施与验证记录](docs/engineering/t02-implementation.md)
- [T04 实施与验证记录](docs/engineering/t04-implementation.md)
- [T03 实施与验证记录](docs/engineering/t03-implementation.md)
- [T06 实施与验证记录](docs/engineering/t06-implementation.md)
- [T08 实施与验证记录](docs/engineering/t08-implementation.md)
- [总体产品规划](docs/PLANBOOK.md)
- [13 个模块及黑盒变体索引](docs/planbooks/README.md)
- [软件工程治理](docs/engineering/governance.md)
- [商业接口预留设计](docs/engineering/commercialization.md)

下一阶段先交付独立开发者从 URL 到分析 HTML 的完整功能闭环，用定向交互样例和一款真实小应用尽早验证模型效果、审阅成本与调用费用。大型框架基准、PDF、岗位画像和团队服务按试用结果推进。
