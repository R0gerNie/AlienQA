# T02 浏览器交互、状态与框架机制实施记录

日期：2026-10-02。对应 [T02 Planbook](mvp-planbooks/technical/02-browser-interaction-state.md)。B01～B07、B08 首版覆盖说明和 B09 最小真实框架工程路径已接通。额外 frame/shadow 全链路支持按原计划后置；真实模型效果、真实开源应用和独立人审仍分别验收。

## 1. 交付范围

| 任务 | 实现与可核对结果 |
|---|---|
| B01 稳定目标 | `Target` 增量保存 name/label/scope/viewport；枚举优先 id/testid/name，再补结构路径。selector 校验可见名称/role，失效后有限降级到唯一 label、role+name、精确文本。歧义不任取首项；坐标记录视口及布局依赖 |
| B02 受控表单 | fill/select 后重新读取 DOM 值，区分 input_rejected/input_unverified；显式 blur 候选触发真实 change/blur 语义。原生选项、必填勾选、已有值和禁用/只读规则保留。数值范围/步长、日期边界和长度有界处理；未知 pattern/矛盾约束保留未验证诊断 |
| B03 动态控件 | 枚举 combobox/listbox/option、tab、checkbox/radio/switch/menuitem；自定义选项通过 click 操作。每步重新枚举，已选选项不反复准备；可见 modal 限定候选范围，portal 关闭后恢复背景。200 项上限、消失控件及空 modal 有覆盖说明 |
| B04 有界观察 | 统一定位、动作与等待预算；最多 1500ms 观察可见文本/控件/URL，最少 600ms、连续 200ms 稳定且无可见 busy/progressbar 才标 settled。保留即时/最终文字、pending、URL、耗时和 scan 引用；不强制 networkidle，不读取框架私有 hydration 标志 |
| B05 状态收敛 | 稳定字段身份与作用域优先、index 最后降级；字段行排序后参与摘要，值不进入 State 文本快照。dialog/expanded/selected/checked/disabled/busy 等可见状态入签名，hash/query 保留。只折叠独立或明确标注的时钟，保留业务时间反馈；旧摘要单列，不证明新版已覆盖 |
| B06 尝试与回放 | 每次执行保存 locator 尝试、匹配数、动作发出状态、等待结果和 URL；成功动作与完整尝试分开，通过原 step/action ID 对齐。等待失败不重发已完成动作；调用结果不确定时不换定位策略、不在同状态自动重试，回放前置条件保持未知。回放报告原中断步骤 |
| B07 登录态边界 | cookies/localStorage 在初次扫描及独立上下文恢复；保存请求入口与实际访问 URL，过期会话重定向可核对。redirected 不直接推断已登录/认证成功。sessionStorage、IndexedDB、SSO、验证码、自动续期均未承诺 |
| B08 首版覆盖 | 检测 frame 与 open shadow 区域，报告未访问/未验证；closed shadow 不能可靠检测。单次 locator 能穿透 shadow 不推导为全链路兼容 |
| B09 联合路径 | 锁版本 React/Vite、Vue/Vite、Next App/Pages Router 实际构建、提交与客户端导航、独立回放；生产管线用模型替身验证 scan/raw/截图/Evidence/analysis 接线，并保留缺反馈对照 |

新增 `driver/browser_dom.py` 共用 DOM 元数据，不读取 store、源码或 handler 实现。模型预期继续仅消费可见输入；执行诊断与测试标签不进入事前预期。

## 2. 执行及持久化契约

`execute()` 返回增量 dict，旧消费者可忽略返回值。动作发出完成先 checkpoint，再进入独立等待；最终 execution、interaction_coverage、trajectory 同步进入 scan、运行页面和离线 analysis。`emitted=false` 表示未发出，`true` 表示调用完成，`null` 表示调用失败后无法证明是否发出。未知发出不能当作安全重试或成功前缀。

动作发出成功而等待 timeout/failed，执行仍为 completed，planner 不重复执行，认知检查保持 inconclusive，原技术信号照常先保存。受控值拒绝/无法读取则保留失败输入尝试，不把后续保存未发生当作产品无反馈。运行在模型返回后再次检查截止时间，不在预算耗尽后发起动作。

`action_sequence` 继续读取旧 Action 字段，新增原 step/action ID 和实际 locator；`attempts` 保存全部尝试。新回放优先使用记录的定位策略，恢复保存的浏览器类型/视口；观察未稳定返回 inconclusive，中途失败返回 failed 并指出原步骤。视觉相似仍只用于再现依据，不改变认知结论或人工决定。

## 3. 验证与复跑

真实机制版本：React/React DOM **19.3.0**、Vue **3.5.43**、Vite **8.3.2**、Next **16.3.8**；本机 Node **25.1.0**、npm **11.6.2**、Python **3.11.14**、Playwright **1.63.0**。精确依赖锁与 [样例 manifest](../../tests/fixtures/framework-mechanisms/manifest.json) 已版本化；Playwright 下限提升到 1.51 以消费 visible locator filter。

```sh
.venv/bin/python scripts/prepare_t02_frameworks.py --install
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  --run-frameworks --cov=alienqa --cov-report=term \
  --cov-report=json:.venv/t02-coverage.json \
  --junitxml=artifacts/evaluation/t02-frameworks/junit.xml
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t02
```

最终全量（含显式框架套件）**574 项通过，覆盖率 87.43%**，其中真实框架套件 **16 项**。sdist/wheel 构建通过；核对新 DOM 模块、运行模板、源码样例与锁文件入包，第三方副本、node_modules 和运行目录未入包。`git diff --check` 与文档本地链接核对通过。本轮未执行独立干净安装、Windows 或远程 CI 发布验收。框架套件包括顺序交互、独立回放、有限探索和生产管线模型替身；输出保存于项目内忽略的 `artifacts/evaluation/t02-frameworks/`，失败调试输出保留，不能混为真实模型准确率。

准备脚本仅在显式 `--install` 时装依赖；默认 pytest 不收集框架外部依赖套件。所有依赖、npm 缓存、构建、服务日志和框架运行数据均在项目内忽略目录；发布包不包含这些第三方副本。

## 4. 支持范围与开放项

- 样例通过证明上述版本的特定路径；不代表所有 React/Vue/Next 应用、组件库、虚拟列表、业务数据、SSR/hydration 时序都兼容。
- 可见稳定不是未来不会再变化的证明；无 busy 标记且晚于窗口的反馈、未标明就绪的迟绑定处理器仍可能超出观察范围。长期 loading、轮询、枚举截断和未访问区域保留未知/限制。
- Next 主页面路径可完成，但其额外 shadow 区域仍产生覆盖诊断；路径 passed 不覆盖整次扫描的 incomplete 标记。
- 名称提取覆盖本次使用的标签及常见 ARIA 来源，不是完整可访问性审计；无稳定属性的同名作用域、复杂画布/拖拽、frame/shadow 全链路仍受限。
- F07 的 SPA 深链静态 fallback、T05 的回放环境/语义匹配与聚类调查全项不在本轮自动关闭。
- 本轮真实模型与 Codex CLI 调用 **0 次**；没有使用 N03 已结束批次的剩余额度。N03 独立复核/新提示历史复跑，以及 N06/K06/Q04 真实小应用 gate 继续开放。

API 行为依据 [Playwright 定位](https://playwright.dev/python/docs/locators)及[动作就绪检查](https://playwright.dev/python/docs/actionability)；框架样例参考 [React createRoot](https://react.dev/reference/react-dom/client/createRoot)、[Vue 表单绑定](https://vuejs.org/guide/essentials/forms.html)、[Next 服务端/客户端组件](https://nextjs.org/docs/app/getting-started/server-and-client-components)，支持声明以本地实际验收为准。
