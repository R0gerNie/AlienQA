# T07：本地输入、CLI/UI 与任务生命周期

版本：2026-10-02-tech-2。状态：U01～U06 功能 MVP 已接通，U07 本机真实 worker 与离线安装包完整路径已验收；新环境依赖解析、其他平台及真实应用效果仍开放。见 [T07 实施记录](../../t07-implementation.md)。落实 [L01～L05](../03-local-run-and-delivery.md)，连接采证、历史、审核和报告，不增加账号、组织、任务队列或 SaaS。
用户路径仍是 URL → 扫描 → 看证据 → 决定 → HTML。源码和启动命令放在高级输入，模型设置复用既有本机配置。

本轮状态补充：共享输入、选中目录、preflight、committed 终态、历史统计及独立 `--review-run` 已实现。安装验证使用空目录中的 wheel 与当前环境依赖，不等价于全新依赖环境；U07/T09 的平台/发布效果门槛仍分开。以下任务保留为验收契约，具体结果和限制以实施记录为准。

## 1. 当前代码与具体改进

| 模块 / 函数 | 已有能力 | 应补模块 |
|---|---|---|
| `__main__.py::main/_serve/_wait_for_app/_stop_app` | URL/source/session/start-command、预算、静态服务与进程回收 | 输入解析共用、选中 app cwd、双报告模式、增量保存；CLI 动作边界时限已说明，任意阻塞硬 deadline 未承诺 |
| `ui/app.py::_prepare_project/_scan_worker/_complete_scan` | 预处理、子进程扫描、完成回调 | 结果落盘不能只等 collect 返回；异常不可空列表覆盖前缀 |
| `ui/jobs.py::JobController.reserve/start/cancel/_monitor/_terminate` | 单任务预约、watchdog、停止/超时和进程组清理 | 与 committed prefix/终态/计量接线；未验证平台不宣称可用 |
| `ui/runs.py::RunManager` | 历史、结果、决定、scope、诊断、回放结果 | 统一读模型、缺失/损坏分类、双缓存失效和实际计数 |
| UI 模板与 settings | 输入、任务、审核和本机模型配置 | URL 主入口、四态审核、分析结果、诊断和保存反馈 |

UI 有整任务 watchdog；CLI 当前主要在动作边界检查预算。request_timeout、扫描预算、worker deadline 分别解释，不能把其中一个当任意阻塞可中断的硬超时。

## 2. 共享读写与终态

- [T04](04-runtime-pipeline-persistence.md) 的 RunWriter 是扫描前缀唯一提交入口；CLI/UI 从同一 committed 快照读取，SQLite 是证据存储，不独立决定 run 完整性。
- 保留 RunRecord 状态；附 stop_reason、步骤各阶段状态和最后提交引用。预算正常结束可以 done，认知故障/未完成标 partial；没有进入目标页面不能宣称验证完成。
- running/unknown 不生成正式 HTML。done/partial/error/timeout/cancelled 经进程停止且读取有效前缀后可生成 analysis；没有证据只有诊断也如实显示。
- parent 在 worker 退出/回收结果确认后添加终止诊断；不得空写 steps/evidences，也不得允许迟到 done 覆盖 cancelled/timeout。
- 清理失败保持资源占用并显示 cleanup_failed，避免同一浏览器/服务仍活着时开启第二次扫描；不增加分布式协调。

## 3. 具体任务

### U01：统一输入解析与 URL 主路径

- 父任务 L01/L02；M1。落点 CLI parser、UI 启动路由、`_prepare_project`、`templates/index.html`。
- 提取轻量共用输入规范：URL、可选 scope/session、正数动作/时间预算；不用创建新的配置平台或额外岗位步骤。
- 源码模式传显式 app 选择与实际 URL，消费 F01～F06；静态服务条件与 CLI/UI 选择一致。本轮 `--app`、`--unit`、`--instructions` 已实现；更完整的识别/路由增强仍依赖 T01。
- scope 原文用于定位和本地记录，不直接传预期 focus；无法确定范围明确告知，不悄悄扩大扫描。
- 验收：仅有 URL 可启动完整路径；同一无效输入 CLI/UI 给一致原因；选中子应用后 cwd、表面文件、服务目录一致。

### U02：启动检查与会话访问结果

- 父任务 L02；M1。落点配置加载、`_wait_for_app`、driver launch、UI preflight/settings。
- 本地检查模型配置、URL 格式/可达、session JSON 结构、浏览器依赖和输出可写；默认不发付费模型探测。
- 拒绝错误配置时给具体原因；供应商运行失败按 K01 记录 attempt，与产品技术异常分开。配置通过不代表远端供应商可用。
- 页面重定向至登录页时显示实际地址/范围；不从 session 文件存在推导已授权或已检查业务流程。
- start-command 保留显式授权输入、shell=False 与进程树回收；app 启动/入口超时为运行诊断，环境失败不制造产品 Bug。
- 验收：坏 session、缺模型、不可达 URL、错误启动 cwd、输出不可写分别可定位；有效 cookies/localStorage 样例进入真实受保护页面。

### U03：生命周期与持久化前缀接线

- 父任务 L03/L04；M1。落点 `_scan_worker/_complete_scan`、JobController、RunManager.finish、CLI finally；依赖 P02/P06。
- worker 创建/恢复 run writer，入口与每次动作先提交 raw；parent 取消/超时只读取最后提交前缀并追加终止信息。
- 切断返回 collect 才首次 save_results 的依赖；重复结果导出必须来自同一快照，不能靠目录遍历猜最新完整版本。
- success/异常/取消回调共享终态裁决；worker 已退出且资源回收确认后才释放单任务占用，终态不能被重复 finish 改写。
- CLI 保留动作边界预算和供应商 timeout 的真实语义；若以后补硬 deadline 必须复用本机控制并验收，不是本阶段隐含承诺。
- 验收：入口 mapper、动作 visual/judge 阻塞后分别停止；重启仍有原异常与未完认知步骤。TERM 后子进程仍存活的场景不会启动下一任务。

### U04：历史读模型、诊断与计数

- 父任务 L03/L04；M1 接线，M2 异常回归。落点 RunRecord、`load_diagnostics/load_evidences/load_scope`、UI run/history。
- 统计实际尝试、执行成功、有效认知判定、两类候选、未完步骤；accepted_count 仅 confirmed，不由 Issue 数推断扫描质量。
- 区分 absent/corrupt/unsupported/available；旧缺新增字段显示未记录，新缺必需快照说明不完整，坏 JSON 不变成 []。
- 显示实际 URL/输入模式、范围、预算、stop_reason、固定一般用户/prompt 版本、最后阶段与调用摘要引用。
- 敏感 session 仅私有引用；历史摘要不输出 cookies/token，不把模型摘要标成原始事实。
- 验收：无发现正常结束、预算结束、技术降级、全部模型失败、存储故障均有不同说明；旧 run 能打开，损坏文件能定位。

### U05：UI 扫描到分析的接线

- 父任务 L01/L05/R03/R06；M1。落点 `templates/run.html/review.html`、run_detail/run_review/run_decide/run_report。
- running 显示进度/停止/已有前缀；终态展示证据、诊断、回放和主 analysis 入口，confirmed 另列明确名称。
- 消费 H01/H02 四种决定与备注；保存失败不清空用户编辑，成功才显示已保存。
- 所有新报告链接显式 `?mode=analysis` 或 confirmed；旧无 mode 路径仍 confirmed，与 H07 保持兼容。
- 验收：浏览器实际点击/填写/停止/保存/下载产生正确请求；按设计+pending 能导出 analysis，confirmed gate 说明并指向 analysis。

### U06：CLI 输出与独立审核路径

- 父任务 L01/L04/L05；M1 接线，M2 兼容验收。落点 `__main__.py::main`、`review/webui.py::create_app`，消费 H03/H07。
- 已实现 `--report-mode analysis|confirmed`，默认 analysis；旧 `ReportBuilder.build` 无 mode 默认 confirmed，两个默认属于不同层次。
- 未审扫描可写 analysis.html；confirmed 仍服从旧 gate，auto-confirm 保持显式演示选择。`--output` 优先，实际模式和路径明确打印。
- CLI 保存与 UI 相同的 run 数据/attempt 引用；启动独立审核时注入终态 scan_context，不重新收集浏览器事实。
- 中断/错误先保存已有前缀与诊断，再返回对应非成功退出结果；正常预算完成不伪装异常，报告生成失败不删除原扫描。
- 验收：默认 pending 输出分析；显式 confirmed 被 gate 拦截但 scan 可读；输出不可写、用户中断、重启审核与自定义文件名分别覆盖。

### U07：单人本机整体验收与运行说明

- 父任务 L05/V04/V05；M2/M3。落点现有 CLI/UI/browser/job 回归、README 与安装说明，消费 Q05/Q06。
- 从真实 worker+Chromium 的 URL 扫描产生两类证据，停止/恢复历史、回放、保存备注、导出和重审；替代 worker 的 UI 控件测试单独记录。
- 首批只声明实际验收的本机组合；Ubuntu CI、Windows taskkill、Firefox/WebKit 未实跑时保持未验证。
- 说明登录态保存位置、删除/保管方式、回放依赖服务/数据和预算限制；不新增企业审计、远程托管或自动工单交付。
- 验收：发行包在干净目录完成完整路径，HTML 离开 run 目录仍可读；运行器退出后已保存证据/决定不消失。

## 4. 执行顺序

U01/U02 与 J/R 并行；U03/U04 必须和 P02/P06 一起进入 M1，不能延到所有模型阶段之后。
U05/U06 接 [T06](06-review-report-artifacts.md)；U07 消费 [T05](05-replay-dedup-investigation.md)、[T08](08-llm-execution-metering.md)、[T09](09-fixtures-compatibility-release.md) 的实际产物。
完整验收分别记录执行成功、认知完成和开发者决定；“没有 confirmed”不等于“所有用户认知检查通过”。
