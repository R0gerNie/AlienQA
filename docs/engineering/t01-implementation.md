# T01：项目识别、框架结构与运行入口实施记录

日期：2026-10-02。范围：[T01 F01～F07/F09](mvp-planbooks/technical/01-project-framework-compatibility.md) 的功能 MVP；F08 按计划后置。面向独立开发者、本机 QA 与一般用户认知分析，继续 URL-first。

源码模式现在以一个明确选中的应用为基准：识别、文件、路由、启动 cwd、静态产物、调查和回放使用同一应用。已有 URL 保持优先；扫描不会自动安装依赖、构建或执行推断脚本。源码和部署事实只用于定位、调查与记录，不进入一般用户预期提示。

## 1. 交付与接口

| 任务 | 已实现行为 | 边界 |
|---|---|---|
| F01 识别 | 按 package 合并 dependencies/devDependencies，联合入口/配置和脚本信号；peer-only 库、无前端入口的后端、显式 Vite library 不列为应用；坏 manifest/非字符串脚本给诊断；候选带实际识别依据 | 有界启发式识别，不执行配置，不宣称识别全部构建变体 |
| F02 应用基准 | `load(source, app_manifest=None)`；`root` 保持仓库根，新增 `app_dir`、`selected_manifest`；多应用 CLI/UI 必须选择。源码路径保持仓库相对，README/调查限制所选应用，启动 cwd 为 app_dir | 自动扫描深度 3、最多 4000 目录/512 manifest；npm/pnpm workspace 字面量模式最多 64 个、8 段，每模式最多 256 命中；不支持 `**`。显式存在的有效 manifest 可超出自动发现深度 |
| F03 运行事实 | 脚本名与正文分开；记录 cwd、packageManager 声明及最近一层锁文件集合，冲突时包管理器为 unknown 并诊断；支持明确的 `--port=`/`-p` 提示 | 默认端口和脚本端口均不是可达证据；显式 URL 与启动可达检查继续由 T07 执行 |
| F04 React/Vue | 有界字面量 JSX Route、App.tsx、对象数组、嵌套 children、index/pathless 和绝对子路径；记录 hash/history、模板与来源。处理 element 内 JSX 和源码注释 | 最多 128 文件、每文件 256000 字符；不执行 JS，不解析任意导入、变量、spread、生成器或完整路由 AST。表达式保持未决，不从未知父路径拼造子 URL |
| F05 Next | 根或 src 下的有效 App/Pages 目录同源枚举；路由组去除，动态/捕获模板留存；API/private/parallel/intercept 不造普通入口，API/private 等不进入前端表面 | 平行/拦截路由列未验证；动态实例来自真实链接，模板不当作已访问 URL |
| F06 产物 | 共享 `static_entry/serve_project` 供 CLI/UI；只取所选应用 dist/build/out 的 HTML；确定性默认 index 或第一个 HTML，可显式选多入口；验证直接脚本/样式资源，拒绝源码 TSX/Vue、缺资源、.next/public/服务型输出 | 目录分类先提供候选事实，选中页面才执行 preflight；外链资源和传递引用由浏览器观察。自定义输出目录、完整 SSR 构建识别未验证；SSR 可用实际 URL |
| F07 部署/回放 | 显式 `base_path` 和 `spa_fallback`；原目录、端口、页面和回退规则写入回放；hash/query 保留，目录重定向保留部署前缀；深链刷新及独立服务恢复 | 默认不启用 fallback；只对 HTML document 导航的无扩展名路径回退，缺资产/API 保持 404。实际 URL 已含部署条件，不同时接受本机静态覆盖参数 |
| F09 证据矩阵 | 结构回归、锁版本实际构建、Chromium 导航/反馈/异常回放、安装路径分列；沿用 T02/T05/T07 的机制样例 | 未将替身模型、人造故障或机制样例升级为真实模型/真实应用有效性验收 |

`Project` 新字段追加在原字段之后，保留原位置参数及 `load(source)`、字符串 `routes`。历史 `run.json` 缺字段仍可读取。`artifacts.static_server` 保留 directory/port，追加 base_path、spa_fallback、entry；旧包默认普通根路径文件服务。

`run.json.source_context` 保存所选应用、路由提示、环境、loader 审计与服务事实；控制台详情、重开审核和离线报告可以核对。静态页面选择不再让模型决定 CLI/UI 使用不同文件；范围定位仍沿用既有单元定位机制。

## 2. 使用与样例准备

```bash
# 已运行源码应用；URL 为实际地址，cwd 为所选应用目录
python -m alienqa --project-root /path/to/repository --app apps/web \
  --url http://localhost:4100 --start-command 'npm run dev'

# 静态产物；entry 相对选中的 dist/build/out，不是仓库根
python -m alienqa --project-root /path/to/repository --app apps/web \
  --entry index.html --base-path /tool/ --spa-fallback
```

控制台高级输入提供同样的应用目录、静态页面、部署路径和 history 回退；有既有 URL 时直接使用该 URL 的部署条件。多 HTML 默认规则只是可重复选择，测试另一页面需明确指定。

版本化的源文件和锁文件是项目自编 fixture，不是第三方应用副本。所有第三方依赖、源码运行副本、缓存、构建和验收数据均位于项目内且 gitignore：`examples/open-source/t02-frameworks/`、`examples/open-source/t01-frameworks/`、`artifacts/`、`.venv/`。T01 没有克隆新开源项目或下载新依赖。

```bash
# T02 已准备依赖时，省略 --install；显式准备才允许安装/构建
.venv/bin/python scripts/prepare_t02_frameworks.py --install
# T01 复用精确锁文件及项目内 T02 依赖链接，只构建自编 Next src 变体
.venv/bin/python scripts/prepare_t01_frameworks.py
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  tests/test_t01_frameworks.py --run-frameworks
```

Next 副本在 `examples/open-source/t01-frameworks/apps/web`，将已有自编 app/pages 移至 src，增加 `(site)/settings`、`users/[id]` 与 Pages `records/[id]`。Turbopack root 固定为项目目录，以同时包含应用和复用依赖链接。普通 pytest 不收集需准备依赖的框架套件，普通扫描不执行准备脚本。

## 3. 本机兼容矩阵

验证组合：macOS 26.4 ARM64、Python 3.11.14、Node 25.1.0、npm 11.6.2、Playwright 1.63.0、Chromium 153.0.8010.12。精确包锁为 React 19.3.0、Vue 3.5.43、Vite 8.3.2、Next 16.3.8。

| 组合 | 结构/产物 | 真实浏览器/回放 | 单列限制 |
|---|---|---|---|
| React/Vite | React 的 devDeps、库误报、JSX/对象路由有结构回归；真实 react.html 构建资源通过共享 preflight | T02/T05 机制路径＋T01 静态服务入口的输入、提交、导航、故障与停止原服务后独立回放 | T02 Vite fixture 同时含 React/Vue，manifest 识别为 Vue；显式 HTML 分别验证两个 renderer，不是两个独立项目；React Router 包运行未单独认证 |
| Vue/Vite | 嵌套相对/绝对路径和 hash 模式有结构回归；真实 vue.html 多入口构建通过 preflight | 同上，真实 Vue DOM/状态及静态产物独立回放 | Vue Router 配置为字面量结构回归；不宣称所有 router 插件/生成路由已实跑 |
| Next 根 App/Pages | 原 T02 固定布局及锁文件 | 原 T02/T05 的 SSR/hydration、受控表单、导航、异常和独立回放 | 登录态机制见 T07，未逐框架验收真实 SSO |
| Next src App/Pages | 所选 apps/web 的路由/入口/表面同基准；路由组与参数模板正确 | 实际构建；HTTP SSR 文本；hydration 表单反馈；真实链接进入 User 7/Record 7；刷新保留 query/hash，目标故障独立回放 | parallel/intercept/catch-all 仅结构限制/模板，未逐类实际运行 |
| 静态 `/tool/` SPA | 直接脚本/样式完整性与前缀检查；资源/API 404、目录重定向 | hash/history 深链进入与刷新、表单反馈、原服务停止后的前缀恢复和具体异常再现 | 由项目自编部署 HTML 验证；不自动修改用户源码 base 或推断服务端 rewrite |
| Nuxt/SvelteKit/Angular | 现有名字分支不升级成完整支持声明 | 可用已有 URL 主路径；框架专项未验收 | F08 后置 |

已有 20 条 T02/T05/T07 框架工程路径继续纳入显式套件；T01 增加 4 条锁版本框架路径（Next src App/Pages 两条、实际 Vite 静态入口两条）和 2 条默认自包含部署浏览器路径。实际框架日志与再现结果位于 `artifacts/evaluation/t01-frameworks/`。

采用的官方规则依据：[Next src](https://nextjs.org/docs/app/api-reference/file-conventions/src-folder)、[Next 目录约定](https://nextjs.org/docs/app/getting-started/project-structure)、[Turbopack root](https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopack)、[React Router nested/index/pathless](https://reactrouter.com/start/data/routing)、[Vue 嵌套路由](https://router.vuejs.org/guide/essentials/nested-routes)、[Vue history](https://router.vuejs.org/guide/essentials/history-mode.html)。文档核对与本机所锁版本实跑证据分别列示。

## 4. 工程验证与开放 gate

真实模型/API/正式 Codex CLI 调用 **0 次**。管线测试和安装路径使用已有自编离线协议替身；框架/浏览器机制测试直接验证 DOM 与采证回放。最终完整套件 **693 项通过**；显式深路径选择增量随后完成 **23 项定向回归**（其中 22 项与全量重复，去重共 **694 项**）。合并覆盖率 **88.30%**。包含 24 条锁版本框架工程路径，另有自包含部署浏览器路径。完整及补充 JUnit 位于 `artifacts/evaluation/t01/junit.xml`、`artifacts/evaluation/t01-selection/junit.xml`；汇总为 `artifacts/evaluation/t01/summary.json`，日志和覆盖率为 `.venv/t01-tests.log`、`.venv/t01-selection.log`、`.venv/t01-coverage.json`。

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  --run-frameworks --cov=alienqa --cov-report=term \
  --cov-report=json:.venv/t01-coverage.json \
  --junitxml=artifacts/evaluation/t01/junit.xml
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t01
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python scripts/verify_t07_installation.py \
  --wheel .venv/dist/t01/alienqa-0.1.0-py3-none-any.whl
```

最终 sdist/wheel 构建与样例资产/外部目录排除检查通过。安装脚本复用 T07 配方，在项目内忽略的空目录离线安装最终 wheel，实际 CLI/UI worker、回放、保存决定、双模式报告、独立审核重开和离线图像均通过。最终安装结果为 `artifacts/evaluation/t07-installation/1ae7ee661df84a13839862f42b094575/summary.json`，日志为 `.venv/t01-installation.log`。依赖复用调用环境，不证明全新依赖环境可安装。

开放项：F08、复杂/生成 Router、任意自定义构建目录/SSR 变体、跨平台/跨浏览器、新环境依赖解析；真实小应用、人审与模型效果/计量验收继续属于 N06/K06/T09。下一工程主节点为 T09，优先 Q01/Q02/Q03 的验收资产整理及 Q05 的新环境安装，再推进 Q04 的独立复核和真实小应用；不因完成 T01 而关闭产品效果或发布 gate。
