# 技术子计划 09：样例、分层验证、兼容矩阵与发布

状态：Q01～Q03 工程实现及浏览器验收已落地；Q04 的 runner/审核与统计资产已实现，真实模型及独立人审开放；Q05 wheel/sdist 两套新依赖环境完整路径已验收；Q06/Q07 分级 CI、支持范围与实验性 gate 已落盘，远程 CI 和效果/试用门槛开放。日期：2026-10-02。记录：[T09 实施](../../t09-implementation.md)。父节点：[V01～V05](../04-validation-and-release.md)，服务独立开发者的 QA 与一般用户认知分析。
本节点消费 J/R/L 的产品契约和技术子计划产物，不另建 Evidence、Decision、SQLite 或报告接口。
Q01～Q07 是 V 的工程分解；不以大型三框架仓库、岗位画像、多人审核或 PDF 为 MVP 的进入条件。
本轮实施执行离线回归、实际浏览器、锁版本框架/外部小应用构建及新环境安装；未启动真实模型。模型调用需显式预算，独立人审不能由自动回归代填。

## 1. 当前证据与缺口

| 当前模块 / 文件 | 已有内容 | 本计划需补足 |
|---|---|---|
| `tests/fixtures/` | demo、form（含 select/required checkbox）、state、replay 页面 | 配对场景 manifest、重置配方、评估侧标注、真实小型框架运行机制 |
| `test_loader_generalization.py` | 合成 Next/Vue 嵌套结构、zip、可见文件评分 | 框架实际构建/运行、路由/异步交互的浏览器证据；结构识别不能代替运行 |
| `test_pipeline_browser_flow.py` | Chromium + 固定角色响应，验证实际动作、证据和回放链路 | 一般用户 basis、独立技术采证、取消后前缀、analysis 五态与备注的新契约 |
| `test_ui_browser_flow.py` | 真实 Flask/Chromium，worker 用 FakeJobController 替换，禁止模型调用 | 控件回归与真实 worker 执行分列；增加完整 worker→审核→离线 HTML 路径 |
| `tests/conftest.py` | `--run-baselines` 显式纳入外部 baseline/loader acceptance；默认自包含 | 可选框架 smoke 和真实模型评估分别启用，不混入无密钥默认 suite |
| `pyproject.toml/requirements-dev.lock` | Python ≥3.11，Playwright/Flask/LiteLLM；dev 固定依赖，coverage 门槛 80% | 不同安装入口的约束说明和验证证据；锁文件不是全部平台已通过的证明 |
| `MANIFEST.in` / setuptools | sdist 包含 lock/docs/tests 的 py/html；wheel 包含两套模板及 share/alienqa/config.yaml | 新框架 fixture 的 json/js/tsx/vue 等目前不会自动进 sdist；wheel 外测试资产需明确来源 |
| `.github/workflows/tests.yml` | Ubuntu Python 3.11/3.13，安装 Chromium、默认 pytest/coverage 和 build | 远程执行证据、clean wheel/sdist 安装 smoke、可选框架 job 与版本化结果 |

上表保留任务拆解时的缺口快照，不作为当前完成状态。实施前 T01 去重 694 项、覆盖率 88.30%；本轮新增 19 个成对/历史场景、真实生产管线替身和固定 TodoMVC 浏览器基线。T02/T01 的真实框架及 sdist 多类型资产已存在，Q02 直接复用，不重复建设。最终回归和安装数字见实施记录。
历史 N06/C06 已有真实控制批次；本轮真实小应用模型效果、独立人审和开发者有效性尚未验收。现有 stub 能验证输入和失败机制，不能证明模型懂一般用户，也不能证明目标应用没有问题。

## 2. 验证资产与接口边界

复用 [父共享契约](../README.md#4-共享契约只做必要的增量)、[T04 原始前缀与 schema](04-runtime-pipeline-persistence.md)、[T06 决定与报告](06-review-report-artifacts.md)。
成本明细由 [T08 模型执行与计量](08-llm-execution-metering.md)提供，本节点只消费 attempt 与 run 汇总，不再实现一套计量器。

| 拟增资产 | 最小内容 / 规则 |
|---|---|
| `tests/fixtures/cases/manifest.json` | case_id、版本、正常/异常配对、入口、可达动作、初始化/重置、环境依赖、可观察断言；故障注入答案不进产品输入 |
| `tests/fixtures/framework-mechanisms/*` | 版本化最小 React/Vite、Vue/Vite、Next App/Pages；锁文件、启动 URL、构建/服务与清理配方；复用 T02/T01 的固定样例 |
| 评估侧 labels / goldens | 原始事实、可接受反馈、合理例外和标注理由；与产品 Decision 分离，关联 run/Evidence ID，不引入新产品状态 |
| 可选评估 runner | 固定 manifest、配置/prompt、重复序号、动作/时间和调用预算；明示当前是否有硬费用上限，不伪造不存在的限制 |
| 结果包 | 原始 run/checkpoint、角色输入输出引用、Evidence、回放、决定/备注、attempt 汇总、审核时长、环境/版本和限制 |
| 支持矩阵 | 识别、运行交互、回放、发行安装、真实模型效果分别记录证据级别，不由 framework 名字推断全部支持 |

公开摘要和 HTML 不含 API key、cookies/storage_state；私有会话仅保存本机引用。case_id 和答案标签只在评估侧匹配结果。
用于定位的任务描述不得携带“这里应报错”“这次默认通过”等答案；源码调查的解释不得倒灌事前预期。
发布 smoke 沿用 analysis/confirmed 双模式和五态 Decision；旧记录缺字段显示未记录，新 schema 损坏不能转换成空扫描成功。

## 3. 模块级工程任务

### Q01：配对机制样例与可重置数据（M1）

- **父任务/落点**：J05/J06、R02、L03、V01；`tests/fixtures/`、`tests/conftest.py`，新增 cases manifest 与受控小服务。
- **当前→增量**：从已有表单/状态/回放页扩展保存反馈、校验、删除/取消、空态/筛选、弹层/导航、技术故障六类配对；数量沿用父计划建议，不冒充覆盖承诺。
- **样例规则**：每类有明确异常及正常/合理例外；保存可用状态更新代替 toast；401/422 合理业务结果对照 JS exception/5xx，不能“有网络失败就有缺陷”。
- **固定资产**：manifest 描述初始可见状态、已知可达路径、重置方法、可观察事实与评估标签；服务分配可用端口，不依赖开发者真实账号或数据库。
- **依赖**：消费 T02 动作、T03 basis 和 T04 technical/raw；fixture 可先准备，断言等产品契约稳定后接入。
- **验收**：重复执行/独立回放前能恢复相同前提；正常版本仍完成相同任务；答案标签没有出现在捕获的角色请求中。

### Q02：核心框架最小运行夹具（M1 准备，M2 执行）

- **父任务/落点**：L02/L04、V01/V03；`tests/fixtures/framework-mechanisms/`、既有框架 smoke runner，复用 T02 与 [T01 F04/F05/F09](01-project-framework-compatibility.md)。
- **当前→增量**：合成 package/目录识别测试保留；复用已实现的 React/Vite、Vue/Vite、Next App/Pages 小应用与构建/运行路径，避免静态 HTML 被称为框架验证。T09 新增固定 TodoMVC 外部小应用，源码、依赖和产物仅在项目内忽略目录。
- **机制范围**：客户端路由与返回、hash/history、受控表单、异步保存、modal、hydration 后操作；Next root/src、group/dynamic 样例按 T01 限定版本，不扩成所有 Router 组合。
- **固定资产**：各 fixture 锁定版本、包管理器、构建/启动方式、实际 URL、重置及停止方式；异常和正常实现复用 Q01 语义，预期答案放评估侧。
- **依赖**：F02 选中应用/cwd、F03 URL、F06/F07 产物/深链；只在显式 smoke 中由执行者按配方安装/构建，AlienQA 正常扫描不自动 npm install。
- **验收**：真实浏览器完成既定任务并保存实际动作/截图/回放；框架构建阻塞单列环境失败，不能计模型漏报；最早一款小应用可先进入 V03，不等待三框架全部绿。

### Q03：契约、浏览器与人审 goldens 分层（M1/M2）

- **父任务/落点**：J01～J06、R01～R06、L03～L05、V01；扩展现有 expectation/context/pipeline/replay/review/UI 测试与新的受控 golden 数据。
- **层次一**：纯确定性契约用 stub 检查输入隔离、事前快照、basis schema、failed/inconclusive；供应商异常不变通过，技术候选不依赖 stub 成功。
- **层次二**：真实 Chromium + stub 检查实际表单/导航、动作窗口、checkpoint、回放、停止/超时、四种决定+pending、备注、缓存失效和 HTML 复制；UI 替代 worker 测试单独标识。
- **golden 规则**：断言稳定事实、来源关联和决定保留，不对模型自然语言或像素逐字锁定；接受多个有效反馈实现。认知 goldens 保存单人标注理由及可争议例外，不当作普遍用户真理。
- **依赖/失败样例**：消费 T04 提交点与 T06 报告接口；在入口/动作采证后阻塞模型、坏写入/旧schema/坏JSON、缺图、全部拒绝、按设计和零发现各有固定样例。
- **验收**：跨模块整条 URL→扫描→证据→回放→决定→analysis HTML 通过；取消后仍能审阅已提交技术前缀；confirmed 旧 gate 不被 analysis 改动破坏。

### Q04：真实模型基线与调用计量对账（M2）

- **父任务/落点**：J06、V02/V03；拟增显式评估 runner、结果汇总脚本与评估侧审核记录；成本直接消费 [T08](08-llm-execution-metering.md) 的 attempt 明细/汇总。
- **当前→增量**：此前只验证模型替身。基线由实际模型自行生成预期并判定，固定 Q01/Q02 manifest、一款真实小应用版本、配置/prompt、重复序号和全部启动记录。
- **计量消费**：关联 run/step/call/attempt/role，核对成功、失败、fallback、usage 缺失及停止未闭合尝试；已知费用和未知项分列，不能未知=0，不能只统计最后成功模型。
- **评估规则**：使用父 V03 的分子/分母；发现率保留未探索到的问题，对照投诉和未决分别列；by-design 可以是有效认知摩擦，不能直接计误报。
- **依赖/资产**：等 T03 输入审计、T04 checkpoint、T06 analysis 和 T08 计量可核对后执行；执行者显式启用模型并确定预算，未具备环境时继续完成离线资产。
- **验收**：保存全部原始 run/尝试、标注、审核分钟、复现和费用记录；首轮作为基线，之后冻结阈值再调优，配置变更单列；小样本与单人判断限制明示。

### Q05：clean wheel/sdist 与 CLI/UI 资产验收（M2 准备，M3）

- **父任务/落点**：L01/L05、V04；`pyproject.toml`、`MANIFEST.in`、`requirements-dev.lock`、CLI 配置定位、模板和拟增安装 smoke。
- **当前→增量**：补 sdist 的新增 fixture 资产白名单（json/js/tsx/vue/锁文件等）；保持排除 node_modules/构建缓存。wheel 包运行所需配置/模板，不要求携带全部测试仓库。
- **安装规则**：分别创建两套干净虚拟环境安装 wheel 与从 sdist 构建的 wheel，在项目内 gitignored 的独立空工作目录执行，与源码 PYTHONPATH 分离；确认导入路径为安装包，不能被源码掩盖缺资产。外部源码、依赖、缓存和结果全部留在项目内。
- **smoke 资产**：受控测试页面从版本对应测试资产/解压 sdist 提供，URL 显式输入；不依赖安装包旁边存在 tests，也不依赖开发者原 `.venv/browsers` 路径。
- **依赖/验收**：消费 Q03/T06/T07；核对 config fallback、主/独立审核模板、URL+登录态、停止、历史重启、回放、决定、离线 HTML 及 pip check；sdist 文件清单能还原默认自包含回归。
- **发布文本**：更新包 description 与 README 至“一般用户认知分析”的已定范围，写清浏览器安装与私有会话保管；不能以 build 成功代替安装后运行证据。

### Q06：兼容证据矩阵与 CI 分级（M2/M3）

- **父任务/落点**：V01/V04/V05；`.github/workflows/tests.yml`、`tests/conftest.py`、测试标记/命令、支持矩阵文档；消费 T01 F09 与 Q02/Q05。
- **分级**：分别记“仅识别回归 / 真实浏览器机制 / 发行安装 smoke / 真实模型基线”；每格关联版本、命令、结果位置和日期，未运行、失败与未覆盖分开。
- **默认 CI**：继续自包含且无密钥；Ubuntu 3.11/3.13 实际 job 通过后才说已验证，新增安装 smoke。可选框架构建 job 与真实模型评估不因本地条件缺失静默假绿。
- **环境范围**：macOS/Python 3.11/Chromium 为历史已测组合，仍需新功能验收；Windows、Firefox/WebKit、其他组合先未验证，不建全平台首版硬 gate。
- **依赖/验收**：Q03 机制与 Q05 安装证据可逐格更新；外部 `--run-baselines` 保持显式、未跑不算默认失败；框架识别通过不会把运行/回放格自动染绿。

### Q07：最小 release gate 与试用回填（M3）

- **父任务/落点**：V05；发布说明、版本/已知问题、支持矩阵与本机试用记录；依赖 Q03～Q06 的实际证据，不新建 SaaS 发布流程。
- **必须门槛**：新增契约与整条用户路径通过；安装包能从显式 URL 扫描并保存 analysis；停止/失败可读前缀、旧数据兼容、四种决定/备注和离线证据可用。
- **效果门槛**：V03 原始基线和计量可核对，有开发者认为有用的有效发现，正常/例外不普遍乱报；数值门槛在首轮后冻结，不能本轮虚构。
- **实验性边界**：模型证据不足时标实验性版本，披露未完成项；不宣称已完成父 V 关闭条件，也不将局部扫描发布为全站 QA 通过。
- **固定试用路径/验收**：独立开发者使用 URL、必要 session 和本机模型设置完成扫描→审阅→按设计备注→HTML 留存；记录失败/困惑、有效发现、主动审阅时间和全部调用成本，回填下一轮任务。
- **明确后置**：其他框架广覆盖、大型第三方应用、岗位画像、PDF、团队队列/权限和收费；新需求由试用证据决定，不能反向阻塞已有功能 MVP。

## 4. 依赖顺序与联合关闭

Q01/Q02 可先准备，Q03 随 J/R/L 落地；Q04 等真实可核对角色输入、报告和 T08 计量；Q05 安装准备与 Q04 并行。
Q06 汇总证据，Q07 决定支持声明；清单已写或 stub 已通过时保持“计划/机制验证”，不能升级成真实效果完成。
节点关闭需要固定样例 manifest、完整浏览器契约、真实模型基线/计量、发行安装路径及明确支持限制。
父 V 的最小真实应用条件保持一款；三框架小型兼容逐项推进，不以大型环境全量支持替代 MVP 有用性验证。
