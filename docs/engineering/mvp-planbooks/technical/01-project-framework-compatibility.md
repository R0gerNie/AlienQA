# 技术子计划：项目识别、框架结构与运行入口

状态：F01～F07 与 F09 的功能 MVP 已实现并进行工程验收；F08 按计划后置。更新：2026-10-02。服务独立开发者的功能 MVP，不引入岗位画像、企业部署或自动托管开发环境。
本节点落实 [L01/L02/L04](../03-local-run-and-delivery.md) 的输入、运行与回放前提，并提供 [V01/V03/V04](../04-validation-and-release.md) 的小型框架样例和支持矩阵。
原 J/R/L/V 编号不变；下列 F01～F09 是技术分解任务，不是另一套功能承诺。

## 1. 两层兼容与当前证据

**源码结构识别**回答选中了哪个应用、哪些文件/路由是它的前端表面、如何运行；**浏览器运行兼容**回答已运行 URL 的页面能否被操作、采证和回放。
框架被识别不代表其源码可由静态服务器直接运行，也不代表动态交互已经验证。URL 扫描不依赖源码框架识别成功。
首版继续 URL-first：用户已有运行页面即可扫描；源码与本机静态服务是辅助入口。显式启动命令由用户提供，不自动安装依赖或执行推断脚本。

实施代码、共享入口、版本化样例、兼容矩阵和最终验证见 [T01 实施记录](../../t01-implementation.md)。本轮真实模型调用为零；源码结构、真实框架与浏览器、安装及模型效果分别记账。

| 层次 | 当前交付 | 验证边界 |
|---|---|---|
| 应用识别与选择 | deps/devDeps 联合入口/配置；库/后端误报回归；显式 manifest；workspace 有界发现；repo root 与 app_dir 分开 | 启发式、有界扫描；未执行配置；多应用由用户明确选择 |
| 路由/入口/源码 | 所选应用的 React/Vue 字面量嵌套路由；Next 有效 root/src App/Pages、groups、动态模板及特殊目录处理 | 字面量提示不是完整 JS 路由执行；parallel/intercept 等未验证 |
| 脚本与运行 | 包管理器声明/锁文件冲突、脚本名/正文/cwd、端口提示；实际 URL 优先，显式启动使用 app_dir | 不自动 install/build；默认端口不是运行证据 |
| 产物与部署 | CLI/UI 共享入口校验；所选应用静态输出/服务型输出；显式 mount/history；回放恢复原条件 | 外部/传递资源由浏览器观测；自定义输出/SSR 变体未全面验证 |
| 机制与发布 | 核心三框架锁版本机制＋src/group/dynamic、Vite 静态入口、子路径深链独立回放；发行包与安装验收 | F08、跨平台、新依赖环境、真实应用和模型/人审 gate 继续开放 |

## 2. 最小接口增量与交接规则

以下增量已实现；旧调用、原字段顺序和历史文件保持可读，不新增运行平台。

| 增量 | 建议规则 | 消费方 |
|---|---|---|
| `ProjectLoader.load(source, app_manifest=None)` | 无选择时保留排名建议；有多个应用时展示候选并允许显式指定仓库相对 manifest；非法或非应用 manifest 明确拒绝 | CLI/UI 输入、源码调查 |
| `Project.app_dir` | 所选 manifest 的绝对父目录；无 manifest 时为 root；`root` 仍是仓库/解压根，不改变文件相对路径语义 | 显式启动 cwd、构建产物选择 |
| `Project.environment` 增量元数据 | 记录 package_manager、lockfile、所选脚本名及 cwd；保留 start/build 原始正文；存在冲突则标未知并解释 | 运行摘要、支持说明 |
| 路由提示元数据 | 保留原 `routes` 字符串兼容；模板、动态性、来源文件和 hash/history 模式另列；模板不能冒充已访问 URL | 范围定位、驱动导航、覆盖摘要 |
| 静态服务元数据 | 沿用 `artifacts.static_server={directory,port}`；增可选 `spa_fallback/base_path/entry`，旧包缺省 false、根路径服务 | 本地服务和独立回放 |

源码路由只帮助发现候选入口；内部路由规则、包脚本及源码解释不进入 J01/J02 的一般用户预期提示。
动态参数由真实链接或显式提供的入口解析，不自动猜客户 ID、遍历后台资源或把 `[id]` 当浏览器地址。
同一 run 固定所选应用、实际起始 URL、服务目录和路由模式；调查、扫描和回放不能分别默认选择不同应用。

## 3. 模块级任务

### F01：应用识别与误报控制（M1）

当前状态：MVP 已实现。详见 [实施证据与限制](../../t01-implementation.md)。

- **落点**：`framework.detect_frontend_apps/_classify_package/_is_frontend_app`、`scan.find_package_jsons`；依赖 L02 输入校验。
- **改进**：结合 dependencies/devDependencies 中框架、脚本、入口/配置与 UI 文件信号；peerDependencies-only 库不因依赖名字自动变应用。保留独立 package 分类，输出识别依据。
- **兼容规则**：React/Vite、Vue/Vite、Next 先覆盖；未知框架可用 URL；坏 package.json、缺字段和非字符串 scripts 形成可解释诊断，不让整个仓库扫描崩溃。
- **已落地样例/测试**：`tests/test_t01_loader.py`：devDeps 应用、peer-only/Vite library、后端、坏 manifest 与混合仓库。
- **验收**：devDependencies-only 的前端应用可识别；组件库/后端不列为应用；坏文件不掩盖其他合法应用；识别变化不影响 URL-only 扫描。

### F02：多应用选择、扫描基准与真正 cwd（M1）

当前状态：MVP 已实现。详见 [实施证据与限制](../../t01-implementation.md)。

- **落点**：`scan.find_package_jsons/surface_dirs`、`framework.rank_frontend_apps/extract_routes`、`loader.load/_entry_points`、`models.Project`、CLI/UI 输入与 prepare。
- **改进**：支持显式 manifest 选择；在有界扫描内消费 workspace 线索，报告扫描深度/未覆盖情况；不无限递归依赖目录。
- **兼容规则**：所选应用统一决定 app_dir、表面文件、路由、启动 cwd 和产物；删除 Next 将仓库根路由混入所选应用的隐式行为；排名只是推荐。
- **已落地样例/测试**：`tests/test_t01_loader.py`、`test_cli_regressions.py`、`test_t01_integration.py`：多应用、深层 workspace、显式深路径、cwd 与调查隔离。
- **验收**：显式选择次排名应用后所有输出和启动 cwd 一致；不会扫描或服务另一应用；路径越出仓库、缺 manifest 和没有产物均明确拒绝/提示。

### F03：包管理器、脚本与实际 URL（M1）

当前状态：MVP 已实现。详见 [实施证据与限制](../../t01-implementation.md)。

- **落点**：`framework.extract_commands/extract_env`、`loader._base_url/_detect_port`、CLI `_wait_for_app` 与启动调用；UI 仅展示运行建议。
- **改进**：先读 packageManager，再核对选中应用或 workspace 根的 npm/pnpm/yarn/bun 锁文件；脚本名、正文和执行目录分开记录，锁文件冲突不默选。
- **兼容规则**：已有 `--url` 始终优先；框架默认端口只是提示。显式 start-command 必须绑定待检测 URL，不因推测 3000/5173 返回成功；处理 `--port=...` 等明确写法。
- **已落地样例/测试**：`tests/test_t01_loader.py`、`test_cli_regressions.py`：workspace 锁文件、冲突、端口、显式 URL/启动与回收。
- **验收**：启动发生在选定 app_dir；实际 URL 不可达时停止并保留启动诊断；不触发 npm install、自动 build 或任意推断命令；停止沿用既有进程组回收。

### F04：React/Vite 与 Vue 路由提示（M1 起步，M2 实跑）

当前状态：字面量结构＋核心框架机制已验证，Router 包变体未认证。详见 [实施证据与限制](../../t01-implementation.md)。

- **落点**：`framework._react_routes/_vue_routes/_iter_surface_files`、`scan.surface_dirs`、`loader._entry_points`。
- **改进**：React 增补常见 JSX Route 位于 App.tsx 及对象配置的字面量 path；Vue 保留 router 配置但组合可明确解析的父子路径。固定解析范围与不支持表达式，不宣称完整执行 JS。
- **兼容规则**：根路径、相对子路由和 pathless 布局区分；动态 `:id` 只作模板。React/Vue 的入口均以所选应用为基准，hash/history 模式显式记录。
- **已落地样例/测试**：`tests/test_t01_loader.py`：App.tsx/对象路由/嵌套 Vue/注释及表达式；既有锁版本框架及新增静态入口机制见实施记录。
- **验收**：静态路由提示正确、未解析表达式列限制；已运行 URL 上完成导航/表单/反馈/回放。识别测试与真正框架运行记录分别提交，由 V01/V03 消费。

### F05：Next 两类 Router、src 与动态路由（M1 结构，M2 实跑）

当前状态：结构及 src App/Pages 动态实例已实跑。详见 [实施证据与限制](../../t01-implementation.md)。

- **落点**：`framework._count_next_routes/_next_routes/_parts_to_route`、`scan.surface_dirs`、`loader._entry_points`。
- **改进**：统一枚举根 app/pages 与 src/app/src/pages；按目标框架版本确认有效目录规则，避免任意合并冲突布局；路由组不成为 URL，API、特殊文件和非页面目录不成为入口。
- **兼容规则**：`app/(group)/settings/page` → `/settings`；`pages/index` → `/`；`[id]`、`[...slug]`、`[[...slug]]` 保留参数性质；复杂平行/拦截路由列未覆盖，不能产生伪普通 URL。
- **已落地样例/测试**：`tests/test_t01_loader.py`、`test_t01_frameworks.py`；自编 `framework-mechanisms/next-src/`，使用 `prepare_t01_frameworks.py` 在忽略目录构建。
- **验收**：目录统计、visible_files、entry_points 与 routes 同源且不混应用；通过实际页面链接取得动态实例后可扫描/回放；SSR/hydration 样例取得实跑证据后才进入支持矩阵。

### F06：静态产物与服务型产物分类（M1）

当前状态：共享入口与实际 Vite 产物已验证。详见 [实施证据与限制](../../t01-implementation.md)。

- **落点**：`loader._artifacts`、`ui.app._static_directory/_prepare_project`、CLI 源码/serve 分支、`entry_detector.collect_entry_candidates/detect`。
- **改进**：提取一处共享入口解析规则供 CLI/UI 使用，绑定 F02 所选 app；分别表示源码、可直接服务的静态目录和需要既有运行服务的产物。
- **兼容规则**：dist/build/out 名称只是候选，要验证 HTML/资源入口；`.next`、public 和 SSR/server 输出不因目录存在成为静态应用。源码型 index 不直接运行；无 HTML 不用默认 index 制造 404。
- **已落地样例/测试**：`tests/test_t01_artifacts.py`、`test_cli_regressions.py`、`test_t01_frameworks.py`：缺资源/源码、服务输出、多 HTML、所选应用实际 Vite 构建。
- **验收**：CLI/UI 对同一输入选择一致；合法静态资源加载成功；服务型产物提示先提供运行 URL；记录实际目录/端口，回放恢复原服务，不偷偷从源码补产物。

### F07：hash/history 与部署子路径（M1 规则，M2 回放）

当前状态：子路径 hash/history 与独立回放已验证。详见 [实施证据与限制](../../t01-implementation.md)。

- **落点**：本机静态服务、F04 路由提示与 `artifacts.static_server`；联动 driver 导航和 ReplayEngine URL/服务恢复。
- **改进**：hash 地址完整保留；history 深链需要服务端处理。纯静态 SPA 使用明确且有限的 HTML fallback：页面导航可回退，缺 JS/CSS/图片/API 仍真实 404。
- **兼容规则**：默认保持普通文件服务；不对所有目录全局回退。部署在 `/tool/` 的 base 路径作为实际运行条件记录，不能把资源或路由改到域名根来掩盖部署错误。
- **已落地样例/测试**：`tests/test_t01_artifacts.py`、`test_t01_browser.py`；自编 `framework-mechanisms/deployment/`，覆盖 query/hash、prefix、刷新和服务恢复。
- **验收**：同一深链可进入、刷新和独立回放；缺资源信号没有被 index.html 的 200 隐藏；不支持的部署方式给环境诊断，不误称产品页面白屏。

### F08：Nuxt/SvelteKit/Angular 与框架变体验证（后置）

- **落点**：`framework._classify_package/_is_frontend_app/extract_routes`、`scan.surface_dirs`、`loader._entry_points/_artifacts`。
- **当前边界**：已有 Nuxt/Svelte/Angular 名称分支；Nuxt 共用 Vue 文本路由、Svelte/Angular 没有路由提取，典型配置/入口与服务产物缺少完整样例；SvelteKit 不单独识别。
- **改进/依赖**：F01～F07 稳定后，按真实使用需求逐框架建立结构适配；复核锁定版本官方文档，再补框架特定配置、文件路由及构建模式。不自动克隆大型应用作为前置。
- **固定 fixture/验收**：分别拟增 `frameworks/nuxt/`、`sveltekit/`、`angular/` 最小版本化样例；每个必须同时给识别和 URL 实跑记录。未完成时继续允许 URL 模式并列未验证，不宣传全面支持。

### F09：兼容矩阵与小型集成门槛（M2）

当前状态：本机兼容矩阵已落盘，产品效果/跨平台 gate 开放。详见 [实施证据与限制](../../t01-implementation.md)。

- **落点**：`tests/test_loader_generalization.py`、`test_entry_detector.py`、`test_ui_app.py`、`test_cli_regressions.py`，新增框架 browser smoke 与文档；依赖 F01～F07。
- **改进**：矩阵分别记录识别、源码表面、启动/产物、浏览器交互、登录态、独立回放；绑定框架/Node/包管理器/浏览器版本及执行命令，不用单个 framework 名称表示全部绿色。
- **已落地样例/测试**：`test_t01_frameworks.py`＋既有 T02 的 20 条工程路径、CLI/UI/安装回归；版本和结果均见实施记录。
- **验收**：先尽早执行核心三框架小样例；结构回归可以默认运行，需构建/服务的 smoke 显式启用并保存结果；外部 baseline 保持 opt-in。首份 URL 分析无需等整个矩阵完成。
- **交接**：V01 消费确定性/浏览器回归，V03 消费一款真实小应用，V04 消费声明支持组合；不以模拟模型或已有 302 项历史回归代替新框架和真实模型验收。

## 4. 执行依赖与关闭条件

F01/F02 是源码模式的共同基准；F03/F04/F05 可在基准固定后并行；F06/F07 保证静态服务与回放一致；F09 汇总实际证据。
这些工作与 J/R 的 URL 功能闭环并行，不让源码适配阻塞一般用户预期、独立技术采证或 analysis HTML。
M1 先消除误选应用、错误 cwd、伪端口/伪静态入口；M2 尽早验证核心三框架的小型真实页面，复杂 Router 和其他框架按证据后置。
关闭必须有固定样例、接口兼容回归、真实浏览器记录及支持限制回填；仅增加识别分支或文档不能关闭运行兼容。
用户只提供 URL 时仍可完成 L→J/R 的完整路径；源码识别失败只影响辅助能力，不能被包装成产品自身技术异常。
